"""Diagnostics: the spa's configuration, the levels, powers and what was learned."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import SpaConfigEntry

REDACT = {"mac", "idigi_device_id"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: SpaConfigEntry) -> dict[str, Any]:
    hub = entry.runtime_data
    client = hub.client
    return {
        "entry": {"data": async_redact_data(dict(entry.data), REDACT), "options": dict(entry.options)},
        "spa": {
            "model": client.model,
            "software_version": client.software_version,
            "configuration_signature": client.configuration_signature,
            "voltage": client.voltage,
            "heater_type": client.heater_type,
            "dip_switch": client.dip_switch,
            "pump_count": client.pump_count,
            "temperature_unit": client.temperature_unit.name,
            "state": client.state.name,
            "available": client.available,
            "controls": [repr(control) for control in client.controls],
        },
        "components": {c.id: list(c.levels) for c in hub.components},
        "levels": hub.levels,
        "powers_w": hub.powers,
        "configured_powers_w": hub.configured_powers(),
        "effective_powers_w": hub.effective_powers(),
        "energy_wh": hub.meter.totals_wh,
        "learning": {
            "meter": hub.reference_entity,
            "meter_w": hub.reference_watts,
            "use_learned": hub.use_learned,
            "events_measured": hub.learner.events,
            "events_rejected": hub.learner.rejected,
            "samples_w": hub.learner.samples,
        },
    }
