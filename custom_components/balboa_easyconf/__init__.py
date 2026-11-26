"""Balboa Spa Easyconf: a Balboa spa on its BWA Wi-Fi module, with its power and energy.

Control and status come over the module's local TCP port (4257) through
pybalboa, the library Home Assistant's own Balboa integration uses. The module
takes one client at a time, so this and the built-in Balboa integration
cannot both be connected to the same spa.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.storage import Store
from pybalboa import SpaClient

from .const import CONF_COMPONENTS, DEFAULT_PORT, DOMAIN, STORE_VERSION
from .hub import SpaHub
from .model import components_to_data

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.FAN,
    Platform.LIGHT,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
]

type SpaConfigEntry = ConfigEntry[SpaHub]


async def async_setup_entry(hass: HomeAssistant, entry: SpaConfigEntry) -> bool:
    host = entry.data[CONF_HOST]
    client = SpaClient(host, entry.data.get(CONF_PORT, DEFAULT_PORT))
    if not await client.connect():
        await client.disconnect()
        raise ConfigEntryNotReady(
            f"No answer from the spa at {host}. Its Wi-Fi module takes one connection at a time: "
            "is another integration or app connected to it?"
        )
    if not await client.async_configuration_loaded():
        await client.disconnect()
        raise ConfigEntryNotReady(f"The spa at {host} answered but did not send its configuration")

    # From here on the module's only connection is ours: give it back on any failure.
    hub: SpaHub | None = None
    try:
        store: Store = Store(hass, STORE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        hub = SpaHub(hass, entry, client, store, await store.async_load())
        components = components_to_data(hub.components)
        if entry.data.get(CONF_COMPONENTS) != components:
            hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_COMPONENTS: components})
        entry.runtime_data = hub
        await hub.async_start()
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        if hub is not None:
            await hub.async_stop()
        else:
            await client.disconnect()
        raise

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SpaConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_stop()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: SpaConfigEntry) -> None:
    await Store(hass, STORE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()


async def _async_options_updated(hass: HomeAssistant, entry: SpaConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
