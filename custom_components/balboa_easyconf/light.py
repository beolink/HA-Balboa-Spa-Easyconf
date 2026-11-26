"""The spa's lights, on or off."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ColorMode, LightEntity
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
    async_add_entities(
        SpaLight(hub, component, controls[component.id])
        for component in hub.components
        if component.kind == "light" and component.id in controls
    )


class SpaLight(SpaEntity, LightEntity):
    _attr_translation_key = "light"
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, hub, component: Component, control: SpaControl) -> None:
        super().__init__(hub, component.id)
        self.component = component
        self.control = control
        self._attr_translation_placeholders = self.number_placeholder(component)

    @property
    def is_on(self) -> bool:
        return self.hub.levels.get(self.component.id, OFF) != OFF

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.hub.async_set_level(self.component, "on")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.hub.async_set_level(self.component, OFF)
