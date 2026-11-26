"""Selects: the heat mode (ready or rest) and the temperature range (low or high)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pybalboa.enums import HeatMode, LowHighRange

from . import SpaConfigEntry
from .entity import SpaEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: SpaConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    hub = entry.runtime_data
    async_add_entities([HeatModeSelect(hub), TemperatureRangeSelect(hub)])


class HeatModeSelect(SpaEntity, SelectEntity):
    _attr_translation_key = "heat_mode"
    _attr_options = ["ready", "rest"]
    _attr_icon = "mdi:thermometer-auto"

    def __init__(self, hub) -> None:
        super().__init__(hub, "heat_mode")

    @property
    def current_option(self) -> str | None:
        return "ready" if self.hub.client.heat_mode.state == HeatMode.READY else "rest"

    async def async_select_option(self, option: str) -> None:
        await self.hub.client.heat_mode.set_state(HeatMode.READY if option == "ready" else HeatMode.REST)


class TemperatureRangeSelect(SpaEntity, SelectEntity):
    _attr_translation_key = "temperature_range"
    _attr_options = ["low", "high"]
    _attr_icon = "mdi:thermometer-lines"

    def __init__(self, hub) -> None:
        super().__init__(hub, "temperature_range")

    @property
    def current_option(self) -> str | None:
        return "high" if self.hub.client.temperature_range.state == LowHighRange.HIGH else "low"

    async def async_select_option(self, option: str) -> None:
        await self.hub.client.set_temperature_range(LowHighRange.HIGH if option == "high" else LowHighRange.LOW)
