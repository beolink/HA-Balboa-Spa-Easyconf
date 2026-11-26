"""Switches: filter cycle 2 on or off, and the aux outputs and misters."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pybalboa import SpaControl

from . import SpaConfigEntry
from .entity import SpaEntity
from .model import OFF, Component, controls_by_id


async def async_setup_entry(
    hass: HomeAssistant, entry: SpaConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    hub = entry.runtime_data
    controls = controls_by_id(hub.client)
    entities: list[SwitchEntity] = [FilterCycle2Switch(hub)]
    entities.extend(
        ControlSwitch(hub, component, controls[component.id])
        for component in hub.components
        if component.kind in ("aux", "mister") and component.id in controls
    )
    async_add_entities(entities)


class FilterCycle2Switch(SpaEntity, SwitchEntity):
    _attr_translation_key = "filter_cycle_2_enabled"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:sync"

    def __init__(self, hub) -> None:
        super().__init__(hub, "filter_cycle_2_enabled")

    @property
    def is_on(self) -> bool:
        return self.hub.client.filter_cycle_2_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.hub.async_set_filter_cycle(2, enabled=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.hub.async_set_filter_cycle(2, enabled=False)


class ControlSwitch(SpaEntity, SwitchEntity):
    def __init__(self, hub, component: Component, control: SpaControl) -> None:
        super().__init__(hub, component.id)
        self.component = component
        self.control = control
        self._attr_translation_key = component.kind
        self._attr_translation_placeholders = self.number_placeholder(component)

    @property
    def is_on(self) -> bool:
        return self.hub.levels.get(self.component.id, OFF) != OFF

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.hub.async_set_level(self.component, "on")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.hub.async_set_level(self.component, OFF)
