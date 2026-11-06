"""COP lookup table over outdoor temperature and electrical power, without pickle/joblib."""
from __future__ import annotations
from bisect import bisect_right
MAX_COP = 8.0

def _bracket(x, xs):
    """Lower index and fraction of x between xs[i] and xs[i + 1], clamped to the ends."""
    if x <= xs[0]:
        return 0, 0.0
    if x >= xs[-1]:
        return len(xs) - 2, 1.0
    i = bisect_right(xs, x) - 1
    return i, (x - xs[i]) / (xs[i + 1] - xs[i])

def _numbers(line):
    return line.replace(',', ' ').replace(';', ' ').replace(':', ' ').split()

def _is_number(token):
    try:
        float(token)
    except ValueError:
        return False
    return True

def parse_cop_table(text):
    """Parse a table whose first row lists electrical powers (W) and whose other rows
    each start with an outdoor temperature (°C) followed by the COP at each power.
    A non-numeric first cell in the header (e.g. "W") is ignored."""
    rows = [tokens for tokens in (_numbers(line) for line in str(text).splitlines()) if tokens]
    if len(rows) < 3:
        raise ValueError('COP table needs a power header row and at least two temperature rows')
    header = rows[0][1:] if not _is_number(rows[0][0]) else rows[0]
    powers = [float(p) for p in header]
    if len(powers) < 2 or any(p <= 0 for p in powers) or any(b <= a for a, b in zip(powers, powers[1:])):
        raise ValueError('COP table header needs at least two positive, increasing powers')
    table = {}
    for tokens in rows[1:]:
        if len(tokens) != len(powers) + 1:
            raise ValueError(f'COP table row {" ".join(tokens)!r} needs a temperature and {len(powers)} COP values')
        temperature, *cops = (float(v) for v in tokens)
        if temperature in table:
            raise ValueError(f'COP table lists {temperature:g} °C twice')
        if any(c <= 0 for c in cops):
            raise ValueError('COP table values must be positive')
        table[temperature] = cops
    temperatures = sorted(table)
    return temperatures, powers, [table[t] for t in temperatures]

def format_cop_table(temperatures, powers, cops, decimals=2):
    width = decimals + 3
    lines = ['W  ' + ' '.join(f'{p:>{width}g}' for p in powers)]
    lines += [f'{t:>3g} ' + ' '.join(f'{c:{width}.{decimals}f}' for c in row) for t, row in zip(temperatures, cops)]
    return '\n'.join(lines)

class COPModel:

    def __init__(self, table_text):
        self.temperatures, self.powers, self.cops = parse_cop_table(table_text)

    def predict(self, outdoor_c, electrical_power_w):
        """Bilinear interpolation in the table; inputs outside it use the nearest edge."""
        if electrical_power_w <= 0:
            return 0.0
        i, ft = _bracket(float(outdoor_c), self.temperatures)
        j, fp = _bracket(float(electrical_power_w), self.powers)
        c = self.cops
        cop = (1 - ft) * ((1 - fp) * c[i][j] + fp * c[i][j + 1]) + ft * ((1 - fp) * c[i + 1][j] + fp * c[i + 1][j + 1])
        return max(1.0, min(MAX_COP, cop))
