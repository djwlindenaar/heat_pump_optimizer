"""Discrete dynamic-programming optimizer for slab thermal storage."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from .cop_model import COPModel
INTERVAL_MINUTES = 15
INTERVAL_HOURS = INTERVAL_MINUTES / 60.0
# Resolution of the delivered power in the DP state key.
POWER_STATE_STEP_W = 250.0

@dataclass(frozen=True)
class ForecastPoint:
    timestamp: datetime
    duration_hours: float
    heat_demand_kwh: float
    outdoor_c: float
    buy_price: float
    sell_price: float
    pv_kwh: float = 0.0

@dataclass(frozen=True)
class PlantModel:
    """How the power the heat pump delivers follows the target power.

    After a start the heat pump runs its own start-up: in the n-th quarter of the
    run it draws start_profile_w[n] on average, whatever the target. After that
    the mean power moves towards the target by at most ramp_up_w / ramp_down_w per
    quarter (0 = no limit). A target of 0 stops it within the interval.
    """
    start_profile_w: tuple[float, ...] = ()
    ramp_up_w: float = 0.0
    ramp_down_w: float = 0.0

    @property
    def start_quarters(self) -> int:
        return len(self.start_profile_w)

    def step(self, was_on: bool, delivered_w: float | None, run_quarters: int, target_w: float, duration_hours: float) -> tuple[float, int]:
        """Mean delivered power in the interval and the run age after it.

        delivered_w is the mean power of the previous interval; None means unknown,
        in which case the target is assumed to be reached.
        """
        if target_w <= 0:
            return 0.0, 0
        if not was_on:
            delivered_w, run_quarters = 0.0, 0
        if run_quarters < self.start_quarters:
            return float(self.start_profile_w[run_quarters]), run_quarters + 1
        if delivered_w is None:
            return float(target_w), run_quarters
        scale = duration_hours / INTERVAL_HOURS
        power = float(target_w)
        if self.ramp_up_w > 0:
            power = min(power, delivered_w + self.ramp_up_w * scale)
        if self.ramp_down_w > 0:
            power = max(power, delivered_w - self.ramp_down_w * scale)
        return power, run_quarters

def parse_start_profile(text: str) -> tuple[float, ...]:
    """Comma-separated mean powers (W) per quarter after a start; empty for none."""
    values = tuple(float(item) for item in str(text).replace(';', ',').split(',') if item.strip())
    if any(value <= 0 for value in values):
        raise ValueError('Start profile powers must be positive')
    return values

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

def optimize(points: list[ForecastPoint], cop: COPModel, *, power_levels_w: list[int], slab_min_kwh: float, slab_max_kwh: float, initial_slab_kwh: float, terminal_reserve_kwh: float, state_step_kwh: float, startup_cost_eur: float, initially_on: bool = False, max_heat_kw: float = 0.0, plant: PlantModel = PlantModel(), initial_delivered_w: float | None = None, initial_run_quarters: int | None = None, power_change_cost_eur_per_kw: float = 0.0, previous_targets_w: list[int | None] | None = None, plan_change_cost_eur_per_kw: float = 0.0) -> list[dict]:
    """Choose a target power per interval at minimum cost.

    The target is what the heat pump is asked for; heat, cost and slab energy
    follow from the power the plant model says it delivers. Among targets that
    lead to the same delivered power, the one closest to it is chosen.
    power_change_cost_eur_per_kw penalises changes of the delivered power while
    running. previous_targets_w (aligned with points, None where absent) with
    plan_change_cost_eur_per_kw penalises deviating from the previous plan.
    """
    if not points:
        return []
    if initial_run_quarters is None:
        initial_run_quarters = plant.start_quarters if initially_on else 0
    initial_delivered = (initial_delivered_w if initially_on else 0.0)
    # The delivered power only needs to be part of the state when the next
    # interval depends on it.
    dynamic_power = plant.ramp_up_w > 0 or plant.ramp_down_w > 0 or power_change_cost_eur_per_kw > 0
    # States are grouped by plant state (on, delivered power key, run age); within
    # a group they are keyed by quantized slab energy. Transitions only depend on
    # the plant state, so they are worked out once per group.
    # The observed initial state may lie outside the slab limits. Such a state
    # may only move back towards the allowed range, never further away from it.
    plant0 = (initially_on, None if initial_delivered is None or not dynamic_power else _q(initial_delivered, POWER_STATE_STEP_W), min(initial_run_quarters, plant.start_quarters))
    states = {plant0: {_q(initial_slab_kwh, state_step_kwh): (0.0, initial_slab_kwh, initial_delivered)}}
    inv_step = 1.0 / state_step_kwh
    low = slab_min_kwh - 1e-09
    high = slab_max_kwh + 1e-09
    # Per interval: plant state -> slab key -> (cost, soc, delivered, previous plant state, previous slab key, target_w).
    # The winning path is reconstructed afterwards instead of copying it per state.
    history = []
    for index, point in enumerate(points):
        previous_target = previous_targets_w[index] if previous_targets_w and index < len(previous_targets_w) else None
        # COP, heat and cost only depend on the interval and the delivered power.
        outcomes: dict[float, tuple[float, float] | None] = {}

        def outcome(delivered_w: float):
            cached = outcomes.get(delivered_w, False)
            if cached is not False:
                return cached
            result = None
            elec_kwh = delivered_w / 1000.0 * point.duration_hours
            heat_kwh = elec_kwh * cop.predict(point.outdoor_c, delivered_w)
            # Beyond the heat pump's capacity: it could not draw this power here.
            if not (max_heat_kw > 0 and heat_kwh > max_heat_kw * point.duration_hours + 1e-09):
                result = (heat_kwh, running_cost(elec_kwh, point.pv_kwh, point.buy_price, point.sell_price))
            outcomes[delivered_w] = result
            return result
        nxt: dict[tuple, dict[int, tuple]] = {}
        for plant_state, group in states.items():
            was_on, power_key, age = plant_state
            # Plant states in one key bucket share their transitions.
            delivered = power_key * POWER_STATE_STEP_W if power_key is not None else next(iter(group.values()))[2]
            # (on, delivered, age) -> the cheapest target leading to it
            by_outcome = {}
            for target_w in power_levels_w:
                on = target_w > 0
                new_delivered, new_age = plant.step(was_on, delivered, age, target_w, point.duration_hours)
                result = outcome(new_delivered)
                if result is None:
                    continue
                heat_kwh, extra = result
                if on and not was_on:
                    extra += startup_cost_eur
                elif on and delivered is not None:
                    extra += power_change_cost_eur_per_kw * abs(new_delivered - delivered) / 1000.0
                if previous_target is not None:
                    extra += plan_change_cost_eur_per_kw * abs(target_w - previous_target) / 1000.0
                # Tie-break only: prefer the target closest to what is delivered.
                extra += 1e-09 * abs(target_w - new_delivered)
                option_key = (on, new_delivered, new_age)
                old = by_outcome.get(option_key)
                if old is None or extra < old[0]:
                    by_outcome[option_key] = (extra, target_w, heat_kwh - point.heat_demand_kwh, new_delivered, (on, _q(new_delivered, POWER_STATE_STEP_W) if dynamic_power else None, new_age))
            for extra, target_w, delta, new_delivered, new_plant in by_outcome.values():
                target_group = nxt.get(new_plant)
                if target_group is None:
                    target_group = nxt[new_plant] = {}
                for soc_key, value in group.items():
                    cost, soc = value[0], value[1]
                    next_soc = soc + delta
                    if (next_soc < low and next_soc < soc) or (next_soc > high and next_soc > soc):
                        continue
                    total = cost + extra
                    new_key = int(round(next_soc * inv_step))
                    old = target_group.get(new_key)
                    if old is None or total < old[0]:
                        target_group[new_key] = (total, next_soc, new_delivered, plant_state, soc_key, target_w)
        nxt = {plant_state: group for plant_state, group in nxt.items() if group}
        if not nxt:
            raise ValueError('No feasible schedule. Increase slab range/power levels or check heat demand units.')
        history.append(nxt)
        states = nxt
    final = [(value[0], plant_state, soc_key) for plant_state, group in states.items() for soc_key, value in group.items() if value[1] >= terminal_reserve_kwh]
    if not final:
        final = [(value[0], plant_state, soc_key) for plant_state, group in states.items() for soc_key, value in group.items()]
    _, plant_state, soc_key = min(final, key=lambda item: item[0])
    path = []
    for point, layer in zip(reversed(points), reversed(history)):
        _, next_soc, delivered_w, prev_plant, prev_soc_key, power_w = layer[plant_state][soc_key]
        on = power_w > 0
        start = on and (not prev_plant[0])
        elec_kwh = delivered_w / 1000.0 * point.duration_hours
        cop_v = cop.predict(point.outdoor_c, delivered_w)
        heat_kwh = elec_kwh * cop_v
        interval_cost = running_cost(elec_kwh, point.pv_kwh, point.buy_price, point.sell_price)
        path.append({'timestamp': point.timestamp, 'duration_hours': round(point.duration_hours, 6), 'target_electrical_power_w': power_w, 'expected_electrical_power_w': round(delivered_w), 'predicted_cop': round(cop_v, 3) if on else None, 'predicted_heat_kwh': round(heat_kwh, 3), 'heat_demand_kwh': round(point.heat_demand_kwh, 3), 'slab_energy_kwh': round(next_soc, 3), 'buy_price_eur_kwh': point.buy_price, 'sell_price_eur_kwh': point.sell_price, 'pv_kwh': point.pv_kwh, 'interval_cost_eur': round(interval_cost + (startup_cost_eur if start else 0), 4), '_in_start': on and (start or prev_plant[2] < plant.start_quarters)})
        plant_state, soc_key = prev_plant, prev_soc_key
    path.reverse()
    # During the start-up the target does not change what is delivered. Ask for
    # the power the run continues at, so the controller already heads there.
    follow = None
    for row in reversed(path):
        if row.pop('_in_start'):
            if follow:
                row['target_electrical_power_w'] = follow
        else:
            follow = row['target_electrical_power_w']
    return path
