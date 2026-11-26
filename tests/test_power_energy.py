"""The power model and the energy meter."""

from __future__ import annotations

import pytest

from custom_components.balboa_easyconf.energy import EnergyMeter
from custom_components.balboa_easyconf.model import OFF, Component
from custom_components.balboa_easyconf.power import component_powers, configured_powers, default_power

HEATER = Component("heater", "heater", None, ("on",))
PUMP1 = Component("pump_1", "pump", 1, ("low", "high"))
PUMP2 = Component("pump_2", "pump", 2, ("on",))
STANDBY = Component("standby", "standby", None, ("on",))
PARTS = [HEATER, PUMP1, PUMP2, STANDBY]


def test_defaults_and_options():
    assert default_power(HEATER, "on") == 3000
    assert default_power(PUMP1, "low") == 400
    assert default_power(PUMP2, "on") == 1500
    powers = configured_powers(PARTS, {"power_heater": 2950, "power_pump_1_low": "435"})
    assert powers == {"heater": 2950.0, "pump_1_low": 435.0, "pump_1_high": 1500.0, "pump_2": 1500.0, "standby": 10.0}


def test_power_per_part():
    powers = configured_powers(PARTS, {"power_heater": 2950, "power_pump_1_low": 435, "power_pump_2": 2000})
    idle = {"heater": OFF, "pump_1": OFF, "pump_2": OFF, "standby": "on"}
    assert component_powers(PARTS, idle, powers) == {"heater": 0, "pump_1": 0, "pump_2": 0, "standby": 10}
    heating = {**idle, "heater": "on", "pump_1": "low"}
    assert sum(component_powers(PARTS, heating, powers).values()) == pytest.approx(2950 + 435 + 10)
    jets = {**idle, "pump_1": "high", "pump_2": "on"}
    assert component_powers(PARTS, jets, powers)["pump_2"] == 2000


def test_energy_holds_each_power_until_the_next_update():
    meter = EnergyMeter()
    meter.update(0, {"heater": 3000, "pump_1": 400})
    meter.update(1800, {"heater": 0, "pump_1": 400})  # half an hour of both
    meter.update(3600, {"heater": 0, "pump_1": 0})  # half an hour of the pump
    assert meter.totals_wh == pytest.approx({"heater": 1500, "pump_1": 400})
    assert meter.kwh() == pytest.approx(1.9)
    assert meter.kwh("heater") == pytest.approx(1.5)


def test_energy_counts_nothing_while_the_spa_is_away():
    meter = EnergyMeter({"heater": 1000})
    meter.update(0, {"heater": 3000})
    meter.update(600, None)  # 10 min counted, then gone
    meter.update(4000, {"heater": 3000})  # back: the gap is not counted
    meter.update(4600, {"heater": 0})
    assert meter.totals_wh["heater"] == pytest.approx(1000 + 500 + 500)


def test_energy_ignores_a_stalled_clock():
    meter = EnergyMeter()
    meter.update(0, {"heater": 3000})
    meter.update(10_000, {"heater": 3000})
    assert meter.kwh() == 0
