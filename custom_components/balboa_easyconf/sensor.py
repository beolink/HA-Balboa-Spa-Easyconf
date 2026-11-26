"""Sensors: water temperature, heat state, last fault, and the spa's power and energy.

Power and energy come from the parts that run (hub.py, power.py, energy.py):
one pair for the whole spa and one per part. With a meter set in the options
there is also one learned power per level of each part, as a diagnostic.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfPower, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util
from pybalboa.control import FaultLog
from pybalboa.enums import HeatState, TemperatureUnit

from . import SpaConfigEntry
from .entity import SpaEntity
from .hub import SpaHub
from .model import OFF, Component, power_key
from .words import capitalized, level_words

HEAT_STATES = {HeatState.OFF: "off", HeatState.HEATING: "heating", HeatState.HEAT_WAITING: "heat_waiting"}

#: The fault log's message codes (pybalboa's FAULT_LOG_ERROR_CODES) as states.
FAULTS = {
    15: "sensors_out_of_sync",
    16: "low_flow",
    17: "flow_failed",
    18: "settings_reset",
    19: "priming_mode",
    20: "clock_failed",
    21: "settings_reset",
    22: "memory_failure",
    26: "service_sensor_sync",
    27: "heater_dry",
    28: "heater_may_be_dry",
    29: "water_too_hot",
    30: "heater_too_hot",
    31: "sensor_a_fault",
    32: "sensor_b_fault",
    34: "pump_stuck",
    35: "hot_fault",
    36: "gfci_test_failed",
    37: "standby_mode",
}
FAULT_OPTIONS = sorted({*FAULTS.values(), "unknown"})

#: Parts whose own power and energy start disabled: small or rarely there.
QUIET_KINDS = frozenset({"standby", "light", "aux", "mister"})


async def async_setup_entry(
    hass: HomeAssistant, entry: SpaConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    hub = entry.runtime_data
    entities: list[SensorEntity] = [
        WaterTemperatureSensor(hub),
        HeatStateSensor(hub),
        FaultSensor(hub),
        TotalPowerSensor(hub),
        TotalEnergySensor(hub),
    ]
    for component in hub.components:
        entities.append(ComponentPowerSensor(hub, component))
        entities.append(ComponentEnergySensor(hub, component))
    if hub.reference_entity is not None:
        for component in hub.components:
            if component.kind == "standby":
                continue
            entities.extend(LearnedPowerSensor(hub, component, level) for level in component.levels)
    async_add_entities(entities)


class WaterTemperatureSensor(SpaEntity, SensorEntity):
    _attr_translation_key = "water_temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, hub: SpaHub) -> None:
        super().__init__(hub, "water_temperature")

    @property
    def native_unit_of_measurement(self) -> str:
        if self.hub.client.temperature_unit == TemperatureUnit.CELSIUS:
            return UnitOfTemperature.CELSIUS
        return UnitOfTemperature.FAHRENHEIT

    @property
    def native_value(self) -> float | None:
        return self.hub.client.temperature


class HeatStateSensor(SpaEntity, SensorEntity):
    _attr_translation_key = "heat_state"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(HEAT_STATES.values())

    def __init__(self, hub: SpaHub) -> None:
        super().__init__(hub, "heat_state")

    @property
    def native_value(self) -> str | None:
        return HEAT_STATES.get(self.hub.client.heat_state)


class FaultSensor(SpaEntity, SensorEntity):
    """The newest entry of the spa's fault log, asked for every ten minutes."""

    _attr_translation_key = "last_fault"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = FAULT_OPTIONS
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hub: SpaHub) -> None:
        super().__init__(hub, "last_fault")

    @property
    def _fault(self) -> FaultLog | None:
        fault = self.hub.client.fault
        return fault if fault is not None and fault.count > 0 else None

    @property
    def native_value(self) -> str | None:
        if (fault := self._fault) is None:
            return None
        return FAULTS.get(fault.message_code, "unknown")

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if (fault := self._fault) is None:
            return None
        occurred = fault.fault_datetime.replace(tzinfo=dt_util.get_default_time_zone())
        return {
            "occurred": occurred.isoformat(),
            "code": fault.message_code,
            "message": fault.message,
            "faults_logged": fault.count,
        }


class TotalPowerSensor(SpaEntity, SensorEntity):
    _attr_translation_key = "power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_suggested_display_precision = 0

    def __init__(self, hub: SpaHub) -> None:
        super().__init__(hub, "power")

    @property
    def native_value(self) -> float | None:
        return self.hub.total_power

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.hub.powers is None:
            return None
        return {"parts": {cid: round(watts) for cid, watts in self.hub.powers.items() if watts}}


class _PartSensor(SpaEntity, SensorEntity):
    def __init__(self, hub: SpaHub, component: Component, key: str) -> None:
        super().__init__(hub, key)
        self.component = component
        part = self.part_name(component)
        self._attr_translation_placeholders = {"part": capitalized(part) if hub.lang == "en" else part}
        self._attr_entity_registry_enabled_default = component.kind not in QUIET_KINDS


class ComponentPowerSensor(_PartSensor):
    _attr_translation_key = "part_power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_suggested_display_precision = 0

    def __init__(self, hub: SpaHub, component: Component) -> None:
        super().__init__(hub, component, f"{component.id}_power")

    @property
    def native_value(self) -> float | None:
        if self.hub.powers is None:
            return None
        return self.hub.powers.get(self.component.id)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        configured = self.hub.configured_powers()
        levels: dict[str, Any] = {}
        for level in self.component.levels:
            key = power_key(self.component, level)
            entry: dict[str, Any] = {"configured_w": configured.get(key), "used": self.hub.power_source(key)}
            if self.hub.reference_entity is not None:
                entry["learned_w"] = self.hub.learner.estimate(key)
                entry["measurements"] = self.hub.learner.count(key)
            levels[level] = entry
        return {"level": self.hub.levels.get(self.component.id, OFF), "levels": levels}


class TotalEnergySensor(SpaEntity, SensorEntity):
    _attr_translation_key = "energy"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2

    def __init__(self, hub: SpaHub) -> None:
        super().__init__(hub, "energy")

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> float:
        return round(self.hub.meter.kwh(), 4)


class ComponentEnergySensor(_PartSensor):
    _attr_translation_key = "part_energy"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2

    def __init__(self, hub: SpaHub, component: Component) -> None:
        super().__init__(hub, component, f"{component.id}_energy")

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> float:
        return round(self.hub.meter.kwh(self.component.id), 4)


class LearnedPowerSensor(SpaEntity, SensorEntity):
    """What one level of one part draws, as measured on the meter so far."""

    _attr_translation_key = "learned_power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_suggested_display_precision = 0
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hub: SpaHub, component: Component, level: str) -> None:
        self.key = power_key(component, level)
        super().__init__(hub, f"{self.key}_learned_power")
        numbered = component.kind in hub.numbered
        self._attr_translation_placeholders = {"part": level_words(component, level, hub.lang, numbered=numbered)}

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> float | None:
        return self.hub.learner.estimate(self.key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "measurements": self.hub.learner.count(self.key),
            "values_w": list(self.hub.learner.samples.get(self.key, [])),
            "meter": self.hub.reference_entity,
        }
