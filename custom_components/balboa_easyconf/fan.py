"""The pumps and blowers, as fans with a speed per level.

A one-speed pump is on or off. A two-speed pump has low (50 %) and high
(100 %); turning it on without a speed runs it at high, as the jets button on
the spa's panel ends up doing.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util.percentage import ordered_list_item_to_percentage, percentage_to_ordered_list_item
from pybalboa import SpaControl

from . import SpaConfigEntry
from .entity import SpaEntity
from .model import OFF, Component, controls_by_id


async def async_setup_entry(
    hass: HomeAssistant, entry: SpaConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    hub = entry.runtime_data
    controls = controls_by_id(hub.client)
    async_add_entities(
        SpaFan(hub, component, controls[component.id])
        for component in hub.components
        if component.kind in ("pump", "blower") and component.id in controls
    )


class SpaFan(SpaEntity, FanEntity):
    _attr_supported_features = FanEntityFeature.SET_SPEED | FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF

    def __init__(self, hub, component: Component, control: SpaControl) -> None:
        super().__init__(hub, component.id)
        self.component = component
        self.control = control
        self._attr_translation_key = component.kind
        self._attr_translation_placeholders = self.number_placeholder(component)
        self._attr_icon = "mdi:pump" if component.kind == "pump" else "mdi:chart-bubble"

    @property
    def speed_count(self) -> int:
        return len(self.component.levels)

    @property
    def _level(self) -> str:
        return self.hub.levels.get(self.component.id, OFF)

    @property
    def is_on(self) -> bool:
        return self._level != OFF

    @property
    def percentage(self) -> int:
        level = self._level
        if level == OFF:
            return 0
        return ordered_list_item_to_percentage(list(self.component.levels), level)

    async def _set_level(self, level: str) -> None:
        await self.hub.async_set_level(self.component, level)

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage <= 0:
            await self._set_level(OFF)
        else:
            await self._set_level(percentage_to_ordered_list_item(list(self.component.levels), percentage))

    async def async_turn_on(self, percentage: int | None = None, preset_mode: str | None = None, **kwargs: Any) -> None:
        if percentage is None:
            await self._set_level(self.component.levels[-1])
        else:
            await self.async_set_percentage(percentage)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set_level(OFF)
