"""Binary sensors: the heater, the filter cycles running, the circulation pump."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from pybalboa.enums import HeatState

from . import SpaConfigEntry
from .entity import SpaEntity
from .hub import SpaHub
from .model import OFF


@dataclass(frozen=True, kw_only=True)
class SpaBinaryDescription(BinarySensorEntityDescription):
    is_on: Callable[[SpaHub], bool]


DESCRIPTIONS = (
    SpaBinaryDescription(
        key="heater",
        translation_key="heater",
        device_class=BinarySensorDeviceClass.HEAT,
        is_on=lambda hub: hub.client.heat_state == HeatState.HEATING,
    ),
    SpaBinaryDescription(
        key="filter_cycle_1",
        translation_key="filter_cycle_1",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:sync",
        is_on=lambda hub: hub.client.filter_cycle_1_running,
    ),
    SpaBinaryDescription(
        key="filter_cycle_2",
        translation_key="filter_cycle_2",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:sync",
        is_on=lambda hub: hub.client.filter_cycle_2_running,
    ),
)

CIRCULATION = SpaBinaryDescription(
    key="circulation_pump",
    translation_key="circulation_pump",
    device_class=BinarySensorDeviceClass.RUNNING,
    icon="mdi:pump",
    is_on=lambda hub: hub.levels.get("circulation_pump", OFF) != OFF,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: SpaConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    hub = entry.runtime_data
    descriptions = list(DESCRIPTIONS)
    if hub.component("circulation_pump") is not None:
        descriptions.append(CIRCULATION)
    async_add_entities(SpaBinarySensor(hub, d) for d in descriptions)


class SpaBinarySensor(SpaEntity, BinarySensorEntity):
    entity_description: SpaBinaryDescription

    def __init__(self, hub: SpaHub, description: SpaBinaryDescription) -> None:
        super().__init__(hub, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        return self.entity_description.is_on(self.hub)
