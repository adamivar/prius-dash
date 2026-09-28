"""Decode a full sensor test log (from tools/full_sensor_test.ps1) with every formula in the ZVW30 PID spreadsheet.

Run:  python tools/analyze_test.py path/to/prius_fulltest_YYYYMMDD_HHMMSS.txt [path/to/spreadsheet.xlsx]
The spreadsheet ("ZVW30 Custom PIDs for Torque (Android App)", from the PriusChat GenIII custom PIDs thread) is not
included in this repo; by default it's looked for in your Downloads folder.
Writes a report next to the log: <log name>_report.txt
"""
import math
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import OrderedDict, defaultdict
from pathlib import Path

SHEET = Path.home() / "Downloads" / "ZVW30 Custom PIDs for Torque (Android App) 12Nov12.xlsx"
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

# standard OBD readings added on top of the spreadsheet: (header, pid, name, equation, unit)
STANDARD = [
    ("7E0", "0105", "Coolant temp (standard OBD)", "A - 40", "C"),
    ("7E0", "010B", "Manifold pressure (standard OBD)", "A", "kPa"),
    ("7E0", "010C", "Engine RPM (standard OBD)", "(A * 256 + B) / 4", "rpm"),
    ("7E0", "0133", "Barometric pressure (standard OBD)", "A", "kPa"),
    ("7E0", "013C", "Catalyst temp B1S1 (standard OBD)", "(A * 256 + B) / 10 - 40", "C"),
    ("7E0", "0132", "Fuel tank vapour pressure (standard OBD)", "(A * 256 + B) / 4", "Pa"),
    ("7E0", "0104", "Engine load (standard OBD)", "A * 100 / 255", "%"),
    ("7E0", "0106", "Short-term fuel trim (standard OBD)", "A * 100 / 128 - 100", "%"),
    ("7E0", "0107", "Long-term fuel trim (standard OBD)", "A * 100 / 128 - 100", "%"),
    ("7E0", "010D", "Vehicle speed (standard OBD)", "A", "km/h"),
    ("7E0", "010E", "Ignition timing (standard OBD)", "A / 2 - 64", "deg"),
    ("7E0", "010F", "Intake air temp (standard OBD)", "A - 40", "C"),
    ("7E0", "0110", "Air flow (standard OBD)", "(A * 256 + B) / 100", "g/s"),
    ("7E0", "0111", "Throttle position (standard OBD)", "A * 100 / 255", "%"),
    ("7E0", "0115", "Rear oxygen sensor B1S2 voltage (standard OBD)", "A / 200", "V"),
    ("7E0", "011F", "Run time since start (standard OBD)", "A * 256 + B", "s"),
    ("7E0", "0121", "Distance with check-engine light on (standard OBD)", "A * 256 + B", "km"),
    ("7E0", "012C", "Commanded EGR (standard OBD)", "A * 100 / 255", "%"),
    ("7E0", "012E", "Commanded evap purge (standard OBD)", "A * 100 / 255", "%"),
    ("7E0", "0130", "Warm-ups since codes cleared (standard OBD)", "A", ""),
    ("7E0", "0131", "Distance since codes cleared (standard OBD)", "A * 256 + B", "km"),
    ("7E0", "0134", "Front air-fuel sensor lambda B1S1 (standard OBD)", "(A * 256 + B) * 2 / 65536", ""),
    ("7E0", "013E", "Catalyst temp B1S2 (standard OBD)", "(A * 256 + B) / 10 - 40", "C"),
    ("7E0", "0142", "Engine computer supply voltage (standard OBD)", "(A * 256 + B) / 1000", "V"),
    ("7E0", "0143", "Absolute engine load (standard OBD)", "(A * 256 + B) * 100 / 255", "%"),
    ("7E0", "0144", "Commanded air-fuel ratio lambda (standard OBD)", "(A * 256 + B) * 2 / 65536", ""),
    ("7E0", "0145", "Relative throttle position (standard OBD)", "A * 100 / 255", "%"),
    ("7E0", "0147", "Throttle position B (standard OBD)", "A * 100 / 255", "%"),
    ("7E0", "014C", "Commanded throttle actuator (standard OBD)", "A * 100 / 255", "%"),
    ("7E0", "014D", "Minutes with check-engine light on (standard OBD)", "A * 256 + B", "min"),
    ("7E0", "014E", "Minutes since codes cleared (standard OBD)", "A * 256 + B", "min"),
]


def load_sheet(path):
    """Rows of the Metric tab: (header, pid, name, equation, min, max, unit). Read requests only."""
    z = zipfile.ZipFile(path)
    shared = [''.join(t.text or '' for t in si.iter('{%s}t' % NS['m']))
              for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si', NS)]
    rows = []
    for row in ET.fromstring(z.read('xl/worksheets/sheet3.xml')).iter('{%s}row' % NS['m']):
        cells = {}
        for c in row.findall('m:c', NS):
            v = c.find('m:v', NS)
            if v is not None:
                cells[re.sub(r'\d', '', c.get('r'))] = shared[int(v.text)] if c.get('t') == 's' else v.text
        name, pid, header = cells.get('A'), (cells.get('C') or '').strip(), cells.get('H')
        if not name or name == 'Name' or not header or pid[:2] not in ('21', '01'):
            continue
        rows.append((header.strip(), pid, name.strip(), cells.get('D', ''), cells.get('E'), cells.get('F'),
                     cells.get('G') or ''))
    return rows


def letter_index(tok):
    return ord(tok) - 65 if len(tok) == 1 else 26 + ord(tok[1]) - 65


def compile_eq(eq):
    """Torque-style equation -> python function of the data bytes, or ('ascii', letters)."""
    eq = eq.strip()
    if re.fullmatch(r'[A-Z]{3,}', eq):                     # e.g. ABCDEFG = text characters
        return lambda d: ''.join(chr(d[letter_index(ch)]) for ch in eq)
    py = re.sub(r'\{([A-Z]{1,2}):(\d)\}', r'((\1 >> \2) & 1)', eq)
    py = re.sub(r'\b([A-Z]{1,2})\b', lambda m: f'd[{letter_index(m.group(1))}]', py)
    code = compile(py, eq, 'eval')
    return lambda d: eval(code, {'math': math}, {'d': d})


def parse_log(path):
    """{step: {(header, pid): [list of data byte lists]}} and {(header, pid): status}."""
    data = defaultdict(lambda: defaultdict(list))
    status = {}
    for line in open(path, encoding='utf-8-sig', errors='replace'):
        parts = line.rstrip('\n').split('|')
        if len(parts) < 6 or parts[0] in ('HEADER', 'INIT'):
            continue
        step, _, h, pid, st, hexdata = parts[:6]
        if step == 'BASELINE':
            status[(h, pid)] = st
        if st == 'OK' and hexdata:
            data[step][(h, pid)].append([int(x, 16) for x in hexdata.split()])
    return data, status


def fmt(v):
    if isinstance(v, str):
        return repr(v)
    if abs(v) >= 100 or float(v).is_integer():
        return f'{v:.0f}'
    return f'{v:.2f}'


def supported_pids(header, bitmap_pid, d):
    base = int(bitmap_pid[2:], 16)
    bits = int(''.join(f'{b:08b}' for b in d[:4]), 2)
    return [f'01{base + i + 1:02X}' for i in range(32) if bits & (1 << (31 - i))]


def main(log_path, sheet=SHEET):
    rows = load_sheet(sheet) + [(h, p, n, e, None, None, u) for h, p, n, e, u in STANDARD]
    data, status = parse_log(log_path)
    steps = [s for s in data if s != 'BASELINE']
    out = []
    counts = defaultdict(int)
    by_request = OrderedDict()
    for r in rows:
        by_request.setdefault((r[0], r[1]), []).append(r)

    out.append('SUPPORTED STANDARD OBD READINGS (from the 0100/0120/0140 lists)')
    for (h, pid), samples in data['BASELINE'].items():
        if pid in ('0100', '0120', '0140', '0160'):
            out.append(f'  {h} {pid}: {", ".join(supported_pids(h, pid, samples[0]))}')
    out.append('')

    for (h, pid), items in by_request.items():
        st = status.get((h, pid), 'not in log')
        out.append(f'=== {h} {pid}  [{st}]')
        for h_, p_, name, eq, lo, hi, unit in items:
            try:
                fn = compile_eq(eq)
            except Exception as e:
                out.append(f'  ?? {name}: cannot read formula {eq!r} ({e})')
                counts['formula problem'] += 1
                continue
            base = data['BASELINE'].get((h, pid), [])
            try:
                bval = fn(base[0]) if base else None
            except IndexError:
                out.append(f'  -- {name}: reply too short for formula {eq}')
                counts['reply too short'] += 1
                continue
            if bval is None:
                out.append(f'  -- {name}: no data')
                counts['no data'] += 1
                continue
            counts['decoded'] += 1
            flag = ''
            try:
                if lo is not None and hi is not None and not isinstance(bval, str) and not (
                        float(lo) - 1e-6 <= bval <= float(hi) + 1e-6):
                    flag = f'  (outside sheet range {float(lo):g}..{float(hi):g})'
                    counts['outside expected range'] += 1
            except ValueError:
                pass
            changes = []
            for step in steps:
                vals = []
                for d in data[step].get((h, pid), []):
                    try:
                        vals.append(fn(d))
                    except IndexError:
                        pass
                if not vals:
                    continue
                if isinstance(bval, str):
                    if any(v != bval for v in vals):
                        changes.append(f'{step}: {vals[-1]!r}')
                    continue
                vmin, vmax = min(vals), max(vals)
                if abs(vmin - bval) > 1e-9 or abs(vmax - bval) > 1e-9:
                    rng = fmt(vmin) if abs(vmax - vmin) < 1e-9 else f'{fmt(vmin)}..{fmt(vmax)}'
                    changes.append(f'{step}: {rng}')
            if changes:
                counts['reacted in a step'] += 1
            out.append(f'  OK {name} = {fmt(bval)} {unit}{flag}')
            for c in changes:
                out.append(f'       changed -> {c}')
        out.append('')

    head = ['SUMMARY'] + [f'  {k}: {v}' for k, v in counts.items()] + ['']
    report = Path(log_path).with_name(Path(log_path).stem + '_report.txt')
    report.write_text('\n'.join(head + out), encoding='utf-8')
    print('\n'.join(head))
    print(f'Full report: {report}')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], Path(sys.argv[2]) if len(sys.argv) > 2 else SHEET)
