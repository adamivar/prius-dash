"""ELM327 driver for the Prius (tuned with the speed test of 2026-09-26).

Speed tricks, all measured in the car:
- "expect N replies": adding the number of reply frames to a question (e.g. 218A1) stops the adapter waiting
  for more replies. Single-frame questions went from 64-174 ms to 36-44 ms. The count is learned from the first
  full reply; if a reply ever comes back incomplete, the trick is switched off for that question.
- switching computers with ATSH only (auto receive, ATAR) instead of ATSH + ATCRA saves one command per switch.
  If a computer doesn't answer that way, the reply filter (ATCRA) is added back for that computer only.
- replies are read as soon as the '>' prompt arrives (no fixed read timeout per question).
"""
import time

import config as cfg


class ElmError(Exception):
    pass


class Elm327:
    def __init__(self, port=cfg.PORT, baud=cfg.BAUD, header="7E2", link=None):
        """port = COM port; or pass link = a function that opens and returns a serial-like connection
        (read / write / in_waiting / reset_input_buffer / close / is_open), e.g. Android Bluetooth."""
        self.port = port
        self.link = link
        self.baud = baud
        self.header = header
        self.reply_header = self._reply(header)
        self.ser = None
        self.frames = {}          # (header, pid) -> reply frame count to announce, 0 = don't announce
        self.need_filter = set()  # computers that only answer with the ATCRA reply filter
        self.filter_on = False
        self.retried = set()

    @staticmethod
    def _reply(header):
        return f"{int(header, 16) + 8:X}"   # Toyota replies come from request header + 8 (7E2 -> 7EA)

    def open(self):
        if self.link:
            self.ser = self.link()
        else:
            import serial  # pip install pyserial
            self.ser = serial.Serial(self.port, self.baud, timeout=cfg.SERIAL_READ_TIMEOUT_S)
        self.send("ATZ", timeout=cfg.ELM_RESET_TIMEOUT_S)
        time.sleep(cfg.ELM_RESET_WAIT_S)
        for cmd in ("ATE0", "ATL0", "ATS1", "ATH1", "ATSP6", "ATAR", f"ATSH{self.header}"):
            self.send(cmd)

    def set_header(self, header):
        """Talk to a different computer."""
        if header == self.header:
            return
        self.send(f"ATSH{header}")
        if header in self.need_filter:
            self.send(f"ATCRA{self._reply(header)}")
            self.filter_on = True
        elif self.filter_on:
            self.send("ATAR")
            self.filter_on = False
        self.header, self.reply_header = header, self._reply(header)

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()

    def send(self, cmd, timeout=cfg.ELM_TIMEOUT_S):
        """Send one command, return the reply text (without the '>' prompt) as soon as the prompt arrives."""
        self.ser.reset_input_buffer()
        self.ser.write((cmd + "\r").encode("ascii"))
        buf = bytearray()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            chunk = self.ser.read(self.ser.in_waiting or 1)   # waits for at most one byte, then takes what's there
            if chunk:
                buf += chunk
                if b">" in chunk:
                    break
        else:
            raise ElmError(f"timeout waiting for reply to {cmd}")
        return buf.decode("ascii", errors="replace").replace(">", "").strip()

    def query(self, pid):
        """Send a mode/PID like '2161'. Return the data bytes (A, B, C...) or None."""
        key = (self.header, pid)
        count = self.frames.get(key, 0)
        text = self.send(pid + (f"{count:X}" if 0 < count <= cfg.MAX_FRAMES_HINT else ""))
        msg, length, nframes = self._join_isotp(text)
        complete = length is not None and len(msg) >= length
        if count and not complete:            # the shortcut cut the reply short: stop using it for this question
            self.frames[key] = 0
            text = self.send(pid)
            msg, length, nframes = self._join_isotp(text)
            complete = length is not None and len(msg) >= length
        elif key not in self.frames and complete:
            self.frames[key] = nframes         # learn how many frames this question's reply has
        if not complete and "NO DATA" in text and self.header not in self.need_filter and key not in self.retried:
            # maybe this computer needs the reply filter - try once with it
            self.retried.add(key)
            self.need_filter.add(self.header)
            header, self.header = self.header, None
            self.set_header(header)
            result = self.query(pid)
            if result is None:                 # the filter didn't help either: go back to auto receive
                self.need_filter.discard(header)
                self.header = None
                self.set_header(header)
            return result
        mode, pid_byte = int(pid[:2], 16), int(pid[2:4], 16)
        if len(msg) < 2 or msg[0] != mode + 0x40 or msg[1] != pid_byte:
            return None  # NO DATA, negative response (7F ...) or garbage
        return msg[2:]

    def _join_isotp(self, text):
        """Rebuild one ISO-TP message from lines like '7EA 10 23 61 81 ...'. Returns (bytes, length, frames)."""
        out, length, frames = [], None, 0
        for line in text.splitlines():
            tok = line.split()
            if len(tok) < 2 or tok[0] != self.reply_header:
                continue
            try:
                b = [int(t, 16) for t in tok[1:]]
            except ValueError:
                continue
            frames += 1
            frame_type = b[0] >> 4
            if frame_type == 0:  # single frame
                length = b[0] & 0x0F
                out += b[1:]
            elif frame_type == 1:  # first frame of a multi-frame reply
                length = ((b[0] & 0x0F) << 8) + b[1]
                out += b[2:]
            elif frame_type == 2:  # consecutive frame
                out += b[1:]
        return (out[:length] if length is not None else out), length, frames
