"""The spa's thermostat: water temperature, set temperature, ready or rest.

Ready keeps the water at the set temperature. Rest heats only during the
filter cycles, which is as close to off as a Balboa spa goes; as in Home
Assistant's own Balboa integration, the thermostat's "off" is rest.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pybalboa.enums import HeatMode, HeatState, TemperatureUnit

from . import SpaConfigEntry
from .entity import SpaEntity

PRESETS = {HeatMode.READY: "ready", HeatMode.REST: "rest", HeatMode.READY_IN_REST: "rest"}
ACTIONS = {
    HeatState.OFF: HVACAction.IDLE,
    HeatState.HEATING: HVACAction.HEATING,
    HeatState.HEAT_WAITING: HVACAction.IDLE,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: SpaConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([SpaThermostat(entry.runtime_data)])


def _unit(client) -> str:
    if client.temperature_unit == TemperatureUnit.CELSIUS:
        return UnitOfTemperature.CELSIUS
    return UnitOfTemperature.FAHRENHEIT


# Home Assistant 2026.11 renamed the thermostat's unit and temperatures to
# native_*, and reports the old names (gone in 2027.11); 2026.9 has only the
# old ones. Give the release that runs this the names it reads.
if hasattr(ClimateEntity, "native_temperature_unit"):

    class _Temperatures:
        @property
        def native_temperature_unit(self) -> str:
            return _unit(self.hub.client)

        @property
        def native_current_temperature(self) -> float | None:
            return self.hub.client.temperature

        @property
        def native_target_temperature(self) -> float | None:
            return self.hub.client.target_temperature

else:

    class _Temperatures:  # type: ignore[no-redef]
        @property
        def temperature_unit(self) -> str:
            return _unit(self.hub.client)

        @property
        def current_temperature(self) -> float | None:
            return self.hub.client.temperature

        @property
        def target_temperature(self) -> float | None:
            return self.hub.client.target_temperature


class SpaThermostat(SpaEntity, _Temperatures, ClimateEntity):
    _attr_name = None
    _attr_translation_key = "spa"
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_preset_modes = ["ready", "rest"]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, hub) -> None:
        super().__init__(hub, "climate")

    @property
    def target_temperature_step(self) -> float:
        return 0.5 if self.hub.client.temperature_unit == TemperatureUnit.CELSIUS else 1.0

    @property
    def precision(self) -> float:
        return self.target_temperature_step

    @property
    def min_temp(self) -> float:
        return self.hub.client.temperature_minimum

    @property
    def max_temp(self) -> float:
        return self.hub.client.temperature_maximum

    @property
    def preset_mode(self) -> str | None:
        return PRESETS.get(self.hub.client.heat_mode.state)

    @property
    def hvac_mode(self) -> HVACMode:
        return HVACMode.HEAT if self.hub.client.heat_mode.state == HeatMode.READY else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        return ACTIONS.get(self.hub.client.heat_state, HVACAction.IDLE)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self.hub.client.set_temperature(float(temperature))

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        await self.hub.client.heat_mode.set_state(HeatMode.READY if preset_mode == "ready" else HeatMode.REST)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self.async_set_preset_mode("ready" if hvac_mode == HVACMode.HEAT else "rest")

    async def async_turn_on(self) -> None:
        await self.async_set_preset_mode("ready")

    async def async_turn_off(self) -> None:
        await self.async_set_preset_mode("rest")
