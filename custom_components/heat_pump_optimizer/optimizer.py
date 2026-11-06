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
    duration_hours: float
    heat_demand_kwh: float
    outdoor_c: float
    buy_price: float
    sell_price: float
    pv_kwh: float = 0.0

def _q(value: float, step: float) -> int:
    return int(round(value / step))

def running_cost(
    electrical_kwh: float,
    pv_kwh: float,
    buy_price: float,
    sell_price: float,
) -> float:
    pv_used_kwh = min(electrical_kwh, max(pv_kwh, 0.0))
    grid_kwh = max(electrical_kwh - pv_used_kwh, 0.0)
    return pv_used_kwh * sell_price + grid_kwh * buy_price

def optimize(points: list[ForecastPoint], cop: COPModel, *, power_levels_w: list[int], slab_min_kwh: float, slab_max_kwh: float, initial_slab_kwh: float, terminal_reserve_kwh: float, state_step_kwh: float, startup_cost_eur: float, initially_on: bool = False, max_heat_kw: float = 0.0) -> list[dict]:
    if not points:
        return []
    # The observed initial state may lie outside the slab limits. Such a state
    # may only move back towards the allowed range, never further away from it.
    states = {(_q(initial_slab_kwh, state_step_kwh), initially_on): (0.0, initial_slab_kwh)}
    # Per interval: state key -> (previous state key, power_w, next_soc).
    # The winning path is reconstructed afterwards instead of copying it per state.
    back_pointers = []
    for point in points:
        # COP, heat and cost only depend on the interval and power level.
        options = []
        for power_w in power_levels_w:
            elec_kwh = power_w / 1000.0 * point.duration_hours
            heat_kwh = elec_kwh * cop.predict(point.outdoor_c, power_w)
            if max_heat_kw > 0 and heat_kwh > max_heat_kw * point.duration_hours + 1e-09:
                # Beyond the heat pump's capacity: it could not draw this power here.
                continue
            interval_cost = running_cost(elec_kwh, point.pv_kwh, point.buy_price, point.sell_price)
            options.append((power_w, power_w > 0, heat_kwh, interval_cost))
        nxt = {}
        back = {}
        for key, (cost, soc) in states.items():
            was_on = key[1]
            for power_w, on, heat_kwh, interval_cost in options:
                next_soc = soc + heat_kwh - point.heat_demand_kwh
                if (next_soc < slab_min_kwh - 1e-09 and next_soc < soc) or (next_soc > slab_max_kwh + 1e-09 and next_soc > soc):
                    continue
                start = on and (not was_on)
                total = cost + interval_cost + (startup_cost_eur if start else 0.0)
                new_key = (_q(next_soc, state_step_kwh), on)
                old = nxt.get(new_key)
                if old is None or total < old[0]:
                    nxt[new_key] = (total, next_soc)
                    back[new_key] = (key, power_w, next_soc)
        if not nxt:
            raise ValueError('No feasible schedule. Increase slab range/power levels or check heat demand units.')
        back_pointers.append(back)
        states = nxt
    feasible = {key: value for key, value in states.items() if value[1] >= terminal_reserve_kwh}
    if not feasible:
        feasible = states
    key = min(feasible, key=lambda k: feasible[k][0])
    path = []
    for point, back in zip(reversed(points), reversed(back_pointers)):
        prev_key, power_w, next_soc = back[key]
        on = power_w > 0
        start = on and (not prev_key[1])
        elec_kwh = power_w / 1000.0 * point.duration_hours
        cop_v = cop.predict(point.outdoor_c, power_w)
        heat_kwh = elec_kwh * cop_v
        interval_cost = running_cost(elec_kwh, point.pv_kwh, point.buy_price, point.sell_price)
        path.append({'timestamp': point.timestamp, 'duration_hours': round(point.duration_hours, 6), 'target_electrical_power_w': power_w, 'predicted_cop': round(cop_v, 3) if on else None, 'predicted_heat_kwh': round(heat_kwh, 3), 'heat_demand_kwh': round(point.heat_demand_kwh, 3), 'slab_energy_kwh': round(next_soc, 3), 'buy_price_eur_kwh': point.buy_price, 'sell_price_eur_kwh': point.sell_price, 'pv_kwh': point.pv_kwh, 'interval_cost_eur': round(interval_cost + (startup_cost_eur if start else 0), 4)})
        key = prev_key
    path.reverse()
    return path
