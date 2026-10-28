"""Transparent datasheet-informed COP model, without pickle/joblib."""
from __future__ import annotations
from bisect import bisect_right
DATASHEET_T = [-7.0, -4.0, -2.0, 2.0, 7.0, 10.0, 15.0, 20.0]
DATASHEET_COP = [3.61, 3.9, 4.09, 4.73, 5.24, 5.83, 6.37, 6.91]

def _interp(x, xs, ys):
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    i = bisect_right(xs, x) - 1
    f = (x - xs[i]) / (xs[i + 1] - xs[i])
    return ys[i] + f * (ys[i + 1] - ys[i])

def parse_correction_curve(text):
    points = []
    for item in text.split(','):
        p, c = item.strip().split(':')
        points.append((float(p), float(c)))
    points.sort()
    if len(points) < 2:
        raise ValueError('COP correction curve needs at least two power:factor points')
    return ([p for p, _ in points], [c for _, c in points])

class COPModel:

    def __init__(self, correction_curve):
        self.power, self.correction = parse_correction_curve(correction_curve)

    def nominal(self, outdoor_c):
        return _interp(float(outdoor_c), DATASHEET_T, DATASHEET_COP)

    def predict(self, outdoor_c, electrical_power_w):
        if electrical_power_w <= 0:
            return 0.0
        correction = _interp(float(electrical_power_w), self.power, self.correction)
        return max(1.0, min(8.0, self.nominal(outdoor_c) * correction))
