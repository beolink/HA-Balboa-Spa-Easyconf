"""Buttons: set the spa's clock now, and forget the learned powers."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SpaConfigEntry
from .entity import SpaEntity
from .hub import SpaHub


async def async_setup_entry(
    hass: HomeAssistant, entry: SpaConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    hub = entry.runtime_data
    entities: list[ButtonEntity] = [SyncClockButton(hub)]
    if hub.reference_entity is not None:
        entities.append(ForgetLearnedButton(hub))
    async_add_entities(entities)


class SyncClockButton(SpaEntity, ButtonEntity):
    _attr_translation_key = "sync_clock"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:clock-check-outline"

    def __init__(self, hub: SpaHub) -> None:
        super().__init__(hub, "sync_clock")

    async def async_press(self) -> None:
        await self.hub.async_sync_clock()


class ForgetLearnedButton(SpaEntity, ButtonEntity):
    _attr_translation_key = "forget_learned"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:eraser"

    def __init__(self, hub: SpaHub) -> None:
        super().__init__(hub, "forget_learned")

    @property
    def available(self) -> bool:
        return True

    async def async_press(self) -> None:
        self.hub.async_reset_learned()
