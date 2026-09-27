"""Android Classic Bluetooth (serial port profile) link to the ELM327, shaped like a pyserial port so elm.py can
use it unchanged. Pair the adapter in Android's Bluetooth settings first (PIN usually 1234 or 0000).

Uses pyjnius to call Android's Bluetooth classes. Cheap ELM327 clones often refuse the normal secure connection,
so it falls back to an insecure one, then to channel 1 directly.
"""
import time

import config as cfg

SPP_UUID = "00001101-0000-1000-8000-00805F9B34FB"   # the standard serial port profile


def available():
    try:
        from jnius import autoclass  # noqa: F401
        return True
    except ImportError:
        return False


def _adapter():
    from jnius import autoclass
    adapter = autoclass("android.bluetooth.BluetoothAdapter").getDefaultAdapter()
    if adapter is None:
        raise OSError("this phone has no Bluetooth")
    if not adapter.isEnabled():
        raise OSError("Bluetooth is off - turn it on and try again")
    return adapter


def paired_devices():
    """[(name, address)] of the phone's paired Bluetooth devices."""
    out = []
    for d in _adapter().getBondedDevices().toArray():
        out.append((d.getName() or d.getAddress(), d.getAddress()))
    return sorted(out, key=lambda nd: (not any(w in nd[0].upper() for w in ("OBD", "ELM", "VEEPEAK", "VLINK")), nd[0]))


def request_permissions(callback=None):
    """Android 12+ asks the user for 'Nearby devices' permission before any Bluetooth call."""
    try:
        from android.permissions import Permission, request_permissions as ask
    except ImportError:
        if callback:
            callback()
        return
    perms = [getattr(Permission, p) for p in ("BLUETOOTH_CONNECT",) if hasattr(Permission, p)]
    ask(perms, (lambda *_: callback()) if callback else None)


class BtSerial:
    def __init__(self, address):
        from jnius import autoclass
        adapter = _adapter()
        uuid = autoclass("java.util.UUID").fromString(SPP_UUID)
        device = adapter.getRemoteDevice(address)
        try:
            adapter.cancelDiscovery()   # a running scan slows connecting; needs a scan permission on Android 12+
        except Exception:
            pass
        errors = []
        self.sock = None
        attempts = (lambda: device.createRfcommSocketToServiceRecord(uuid),
                    lambda: device.createInsecureRfcommSocketToServiceRecord(uuid),
                    lambda: device.getClass().getMethod("createRfcommSocket", autoclass("java.lang.Integer").TYPE)
                    .invoke(device, 1))
        for make in attempts:
            try:
                sock = make()
                sock.connect()
                self.sock = sock
                break
            except Exception as e:  # jnius JavaException etc.
                errors.append(str(e))
        if self.sock is None:
            raise OSError("could not connect to the adapter: " + " / ".join(errors[-1:]))
        self.inp, self.out = self.sock.getInputStream(), self.sock.getOutputStream()
        self.timeout = cfg.SERIAL_READ_TIMEOUT_S

    @property
    def is_open(self):
        return self.sock is not None

    @property
    def in_waiting(self):
        return self.inp.available()

    def reset_input_buffer(self):
        n = self.inp.available()
        while n > 0:
            self.inp.skip(n)
            n = self.inp.available()

    def write(self, data):
        self.out.write(bytes(data))
        self.out.flush()

    def read(self, n=1):
        """Up to n bytes: whatever has arrived, waiting at most the read timeout for the first one."""
        deadline = time.monotonic() + self.timeout
        while self.inp.available() == 0:
            if time.monotonic() >= deadline:
                return b""
            time.sleep(0.002)
        k = min(n, self.inp.available())
        return bytes(self.inp.read() & 0xFF for _ in range(k))

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            finally:
                self.sock = None
