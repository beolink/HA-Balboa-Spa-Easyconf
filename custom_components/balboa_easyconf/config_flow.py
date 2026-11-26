"""Set-up: find the spa, read what it has, ask what each part draws.

The user step searches the network the way Balboa's app does (a UDP
"Discovery" broadcast on port 30303, answered by the BWA module) and offers
the first spa found; any address can be typed. DHCP discovery (Balboa's MAC
prefix 00:15:27) leads to the same place. Before an entry is made the spa is
connected to once, for its MAC address, model and parts; the powers step then
lists a field per level of every part.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from pybalboa import SpaClient
from pybalboa.discovery import DiscoveredSpa, async_discover
import voluptuous as vol

from .const import (
    CONF_COMPONENTS,
    CONF_MAC,
    CONF_MODEL,
    CONF_REFERENCE,
    CONF_SYNC_TIME,
    CONF_USE_LEARNED,
    DEFAULT_PORT,
    DOMAIN,
    POWER_PREFIX,
)
from .model import Component, components_from_client, components_from_data, components_to_data, power_key
from .power import MAX_POWER, default_power

_LOGGER = logging.getLogger(__name__)

DISCOVERY_SECONDS = 4


class CannotConnect(Exception):
    """The module did not take the connection."""


class NoConfiguration(Exception):
    """The spa answered but did not send its configuration."""


@dataclass
class SpaInfo:
    mac: str
    model: str
    components: list[Component]


def split_host(text: str) -> tuple[str, int]:
    """ "192.168.1.50" or "192.168.1.50:4257" → host and port."""
    text = text.strip()
    host, sep, port = text.rpartition(":")
    if sep and port.isdigit() and host and ":" not in host:
        return host, int(port)
    return text, DEFAULT_PORT


async def probe(host: str, port: int = DEFAULT_PORT) -> SpaInfo:
    """Connect once and read the spa's identity and parts."""
    client = SpaClient(host, port)
    try:
        if not await client.connect():
            raise CannotConnect
        if not await client.async_configuration_loaded():
            raise NoConfiguration
        return SpaInfo(format_mac(client.mac_address), client.model, components_from_client(client))
    finally:
        await client.disconnect()


async def discover() -> list[DiscoveredSpa]:
    try:
        return await async_discover(timeout=DISCOVERY_SECONDS)
    except OSError as err:
        _LOGGER.debug("Spa discovery failed: %s", err)
        return []


def power_schema(components: list[Component], current: dict[str, Any]) -> vol.Schema:
    """A watt field per level of every part, then the meter and the clock."""
    fields: dict[Any, Any] = {}
    for component in components:
        for level in component.levels:
            name = POWER_PREFIX + power_key(component, level)
            fields[vol.Required(name, default=current.get(name, default_power(component, level)))] = NumberSelector(
                NumberSelectorConfig(min=0, max=MAX_POWER, step=1, unit_of_measurement="W", mode=NumberSelectorMode.BOX)
            )
    fields[vol.Optional(CONF_REFERENCE, description={"suggested_value": current.get(CONF_REFERENCE)})] = EntitySelector(
        EntitySelectorConfig(domain="sensor", device_class="power")
    )
    fields[vol.Required(CONF_USE_LEARNED, default=current.get(CONF_USE_LEARNED, True))] = BooleanSelector()
    fields[vol.Required(CONF_SYNC_TIME, default=current.get(CONF_SYNC_TIME, True))] = BooleanSelector()
    return vol.Schema(fields)


def clean_options(user_input: dict[str, Any]) -> dict[str, Any]:
    out = {k: (float(v) if k.startswith(POWER_PREFIX) else v) for k, v in user_input.items()}
    if not out.get(CONF_REFERENCE):
        out.pop(CONF_REFERENCE, None)
    return out


class BalboaEasyconfFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._port = DEFAULT_PORT
        self._info: SpaInfo | None = None
        self._found: list[DiscoveredSpa] | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> SpaOptionsFlow:
        return SpaOptionsFlow()

    async def _probe(self) -> str | None:
        """Read the spa at self._host; an error key, or None."""
        assert self._host is not None
        try:
            self._info = await probe(self._host, self._port)
        except CannotConnect:
            return "cannot_connect"
        except NoConfiguration:
            return "no_configuration"
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._host, self._port = split_host(user_input[CONF_HOST])
            if (error := await self._probe()) is None:
                assert self._info is not None
                # A DHCP discovery of the same spa may be waiting: this flow goes ahead of
                # it (the entry it makes closes the discovery) instead of aborting.
                await self.async_set_unique_id(self._info.mac, raise_on_progress=False)
                self._abort_if_unique_id_configured(updates={CONF_HOST: self._host, CONF_PORT: self._port})
                return await self.async_step_powers()
            errors["base"] = error
        if self._found is None:
            self._found = await discover()
        configured = {e.unique_id for e in self._async_current_entries()}
        fresh = [s for s in self._found if format_mac(s.mac_address) not in configured]
        default = user_input[CONF_HOST] if user_input else (fresh[0].address if fresh else "")
        found = ", ".join(f"{s.address} ({s.hostname})" for s in fresh) or "-"
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_HOST, default=default): str}),
            errors=errors,
            description_placeholders={"found": found},
        )

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> ConfigFlowResult:
        await self.async_set_unique_id(format_mac(discovery_info.macaddress))
        self._abort_if_unique_id_configured(updates={CONF_HOST: discovery_info.ip})
        self._host = discovery_info.ip
        self.context["title_placeholders"] = {"name": discovery_info.hostname or discovery_info.ip}
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if (error := await self._probe()) is None:
                return await self.async_step_powers()
            errors["base"] = error
        return self.async_show_form(
            step_id="confirm", errors=errors, description_placeholders={"host": self._host or ""}
        )

    async def async_step_powers(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._info is not None and self._host is not None
        if user_input is not None:
            data: dict[str, Any] = {
                CONF_HOST: self._host,
                CONF_MAC: self._info.mac,
                CONF_MODEL: self._info.model,
                CONF_COMPONENTS: components_to_data(self._info.components),
            }
            if self._port != DEFAULT_PORT:
                data[CONF_PORT] = self._port
            return self.async_create_entry(
                title=self._info.model or "Spa", data=data, options=clean_options(user_input)
            )
        return self.async_show_form(
            step_id="powers",
            data_schema=power_schema(self._info.components, {}),
            description_placeholders={"model": self._info.model or "Spa"},
        )


class SpaOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=clean_options(user_input))
        components = components_from_data(self.config_entry.data.get(CONF_COMPONENTS, {}))
        return self.async_show_form(
            step_id="init", data_schema=power_schema(components, dict(self.config_entry.options))
        )
