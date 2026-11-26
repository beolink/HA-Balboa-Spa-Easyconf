"""The filter cycles' start and end times."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SpaConfigEntry
from .entity import SpaEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: SpaConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    hub = entry.runtime_data
    async_add_entities(FilterCycleTime(hub, cycle, end) for cycle in (1, 2) for end in ("start", "end"))


class FilterCycleTime(SpaEntity, TimeEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:clock-outline"

    def __init__(self, hub, cycle: int, end: str) -> None:
        super().__init__(hub, f"filter_cycle_{cycle}_{end}")
        self.cycle = cycle
        self.end = end
        self._attr_translation_key = f"filter_cycle_{cycle}_{end}"

    @property
    def native_value(self) -> time | None:
        return getattr(self.hub.client, f"filter_cycle_{self.cycle}_{self.end}")

    async def async_set_value(self, value: time) -> None:
        await self.hub.async_set_filter_cycle(self.cycle, **{self.end: value})
