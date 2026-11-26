"""The spa's power, from which parts run and how much each draws.

Every level of every part has a power in watts: the one set in the options,
or the one learned from a meter (learn.py) when that is turned on and has
enough measurements. The spa's power is the sum over its parts at the level
each is at; off draws nothing, the controller (``standby``) always draws its
figure while the spa answers.

The defaults are typical figures for a Balboa spa on 230 V. The heater's 3 kW
and a two-speed pump's 400 W on low are close to what was measured on a
BP2100G1 (2.95 kW, 435 W); a pump's high speed, a blower, a light and the
controller vary more between spas, so set or learn them.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .const import POWER_PREFIX
from .model import OFF, Component, power_key

#: Watts per kind and level.
DEFAULTS: dict[str, dict[str, float]] = {
    "heater": {"on": 3000.0},
    "pump": {"on": 1500.0, "low": 400.0, "medium": 900.0, "high": 1500.0},
    "blower": {"on": 700.0, "low": 350.0, "medium": 500.0, "high": 700.0},
    "circulation_pump": {"on": 100.0},
    "light": {"on": 10.0},
    "aux": {"on": 0.0},
    "mister": {"on": 50.0},
    "standby": {"on": 10.0},
}

#: The most a field accepts, in watts.
MAX_POWER = 12000.0


def default_power(component: Component, level: str) -> float:
    by_level = DEFAULTS.get(component.kind, {})
    if level in by_level:
        return by_level[level]
    return max(by_level.values(), default=0.0)


def configured_powers(components: list[Component], options: Mapping[str, Any]) -> dict[str, float]:
    """Each power key's watts as set in the options, else the default."""
    out: dict[str, float] = {}
    for component in components:
        for level in component.levels:
            key = power_key(component, level)
            value = options.get(POWER_PREFIX + key)
            out[key] = float(value) if value is not None else default_power(component, level)
    return out


def component_powers(
    components: list[Component], levels: Mapping[str, str], powers: Mapping[str, float]
) -> dict[str, float]:
    """Watts per component at the levels given."""
    out: dict[str, float] = {}
    for component in components:
        level = levels.get(component.id, OFF)
        if level == OFF or level not in component.levels:
            out[component.id] = 0.0
        else:
            out[component.id] = float(powers.get(power_key(component, level), 0.0))
    return out
