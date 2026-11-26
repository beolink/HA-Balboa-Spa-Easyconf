"""The base of every entity: one spa's device, updated when the hub says so."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.entity import Entity

from .model import Component
from .words import component_words

if TYPE_CHECKING:
    from .hub import SpaHub


class SpaEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hub: SpaHub, key: str) -> None:
        self.hub = hub
        self._attr_unique_id = f"{hub.mac}_{key}"
        self._attr_device_info = hub.device_info

    @property
    def available(self) -> bool:
        return self.hub.available

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.hub.async_add_listener(self.async_write_ha_state))

    def part_name(self, component: Component) -> str:
        """The part's words for this house's language: "pump 1", "blåsare"."""
        return component_words(component, self.hub.lang, numbered=component.kind in self.hub.numbered)

    def number_placeholder(self, component: Component) -> dict[str, str]:
        numbered = component.kind in self.hub.numbered and component.number is not None
        return {"number": f" {component.number}" if numbered else ""}
