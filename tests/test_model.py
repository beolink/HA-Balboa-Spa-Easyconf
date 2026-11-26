"""The parts and levels read off a real pybalboa client fed the BP2100G1's messages."""

from __future__ import annotations

from pybalboa.enums import UnknownState

from custom_components.balboa_easyconf.model import (
    OFF,
    Component,
    components_from_client,
    components_from_data,
    components_to_data,
    levels_from_client,
    power_key,
)
from tests.fakespa import MT_STATUS, feed, loaded_client, status


def test_parts_of_a_bp2100g1():
    client, _ = loaded_client()
    components = components_from_client(client)
    assert [(c.id, c.levels) for c in components] == [
        ("heater", ("on",)),
        ("pump_1", ("low", "high")),
        ("pump_2", ("on",)),
        ("blower_1", ("on",)),
        ("light_1", ("on",)),
        ("standby", ("on",)),
    ]
    assert [k for c in components for k in c.power_keys] == [
        "heater",
        "pump_1_low",
        "pump_1_high",
        "pump_2",
        "blower_1",
        "light_1",
        "standby",
    ]
    assert client.model == "BP2100G1"


def test_parts_survive_the_entry():
    client, _ = loaded_client()
    components = components_from_client(client)
    assert components_from_data(components_to_data(components)) == components
    assert Component.from_id("circulation_pump", ["on"]).kind == "circulation_pump"
    assert Component.from_id("pump_3", ["low", "high"]) == Component("pump_3", "pump", 3, ("low", "high"))


def test_levels_follow_the_status():
    client, state = loaded_client()
    components = components_from_client(client)
    levels = levels_from_client(client, components)
    assert levels == {
        "heater": OFF,
        "pump_1": OFF,
        "pump_2": OFF,
        "blower_1": OFF,
        "light_1": OFF,
        "standby": "on",
    }
    state.pumps = [1, 1]
    state.heat_state = 1
    state.light = True
    feed(client, MT_STATUS, status(state))
    assert levels_from_client(client, components) == {
        "heater": "on",
        "pump_1": "low",
        "pump_2": "on",
        "blower_1": OFF,
        "light_1": "on",
        "standby": "on",
    }
    state.pumps = [2, 0]
    state.heat_state = 2  # waiting for heat: the element is off
    feed(client, MT_STATUS, status(state))
    levels = levels_from_client(client, components)
    assert levels["pump_1"] == "high"
    assert levels["pump_2"] == OFF
    assert levels["heater"] == OFF


def test_blower_is_read_from_the_status_byte():
    """pybalboa reads a running one-speed blower as unknown; the hub must not."""
    client, state = loaded_client()
    components = components_from_client(client)
    state.blower = 1
    feed(client, MT_STATUS, status(state))
    assert levels_from_client(client, components)["blower_1"] == "on"
    # What pybalboa 1.1.3 makes of the same byte (the reason for blower_level).
    assert client.blowers[0].state in (UnknownState.UNKNOWN, client.blowers[0].options[1])


def test_power_key_names():
    two = Component("pump_1", "pump", 1, ("low", "high"))
    one = Component("pump_2", "pump", 2, ("on",))
    assert power_key(two, "low") == "pump_1_low"
    assert power_key(one, "on") == "pump_2"


def test_a_light_with_several_configured_levels_is_on_or_off():
    from tests.fakespa import MT_DEVICE_CONFIGURATION, device_configuration

    _, state = loaded_client()
    config = bytearray(device_configuration(state))
    config[2] = 0x03  # light 1's two configuration bits at 3: pybalboa gives it off/low/medium/high
    fresh, _ = loaded_client()
    fresh._device_configuration_loaded = False
    fresh._controls = fresh._controls[:2]
    feed(fresh, MT_DEVICE_CONFIGURATION, bytes(config))
    light = next(c for c in components_from_client(fresh) if c.kind == "light")
    assert light.levels == ("on",)
