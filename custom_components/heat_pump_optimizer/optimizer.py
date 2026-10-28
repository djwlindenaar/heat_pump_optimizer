"""Discrete dynamic-programming optimizer for slab thermal storage."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from .cop_model import COPModel
INTERVAL_MINUTES = 15
INTERVAL_HOURS = INTERVAL_MINUTES / 60.0

@dataclass(frozen=True)
class ForecastPoint:
    timestamp: datetime
    heat_demand_kwh: float
    outdoor_c: float
    buy_price: float
    sell_price: float
    pv_kwh: float = 0.0

def _q(value: float, step: float) -> int:
    return int(round(value / step))

def optimize(points: list[ForecastPoint], cop: COPModel, *, power_levels_w: list[int], slab_min_kwh: float, slab_max_kwh: float, initial_slab_kwh: float, terminal_reserve_kwh: float, state_step_kwh: float, startup_cost_eur: float) -> list[dict]:
    if not points:
        return []
    lo, hi = (_q(slab_min_kwh, state_step_kwh), _q(slab_max_kwh, state_step_kwh))
    initial = max(lo, min(hi, _q(initial_slab_kwh, state_step_kwh)))
    states = {(initial, False): (0.0, [])}
    for point in points:
        nxt = {}
        for (soc_q, was_on), (cost, path) in states.items():
            soc = soc_q * state_step_kwh
            for power_w in power_levels_w:
                on = power_w > 0
                elec_kwh = power_w / 1000.0 * INTERVAL_HOURS
                cop_v = cop.predict(point.outdoor_c, power_w)
                heat_kwh = elec_kwh * cop_v
                next_soc = soc + heat_kwh - point.heat_demand_kwh
                if next_soc < slab_min_kwh - 1e-09 or next_soc > slab_max_kwh + 1e-09:
                    continue
                new_q = max(lo, min(hi, _q(next_soc, state_step_kwh)))
                grid = elec_kwh - point.pv_kwh
                interval_cost = max(grid, 0) * point.buy_price + min(grid, 0) * point.sell_price
                start = on and (not was_on)
                total = cost + interval_cost + (startup_cost_eur if start else 0.0)
                key = (new_q, on)
                old = nxt.get(key)
                row = {'timestamp': point.timestamp, 'target_electrical_power_w': power_w, 'predicted_cop': round(cop_v, 3) if on else None, 'predicted_heat_kwh': round(heat_kwh, 3), 'heat_demand_kwh': round(point.heat_demand_kwh, 3), 'slab_energy_kwh': round(new_q * state_step_kwh, 3), 'buy_price_eur_kwh': point.buy_price, 'sell_price_eur_kwh': point.sell_price, 'pv_kwh': point.pv_kwh, 'interval_cost_eur': round(interval_cost + (startup_cost_eur if start else 0), 4)}
                if old is None or total < old[0]:
                    nxt[key] = (total, path + [row])
        if not nxt:
            raise ValueError('No feasible schedule. Increase slab range/power levels or check heat demand units.')
        states = nxt
    feasible = [v for (soc, _), v in states.items() if soc * state_step_kwh >= terminal_reserve_kwh]
    if not feasible:
        feasible = list(states.values())
    return min(feasible, key=lambda x: x[0])[1]
