#!/usr/bin/env python3
"""Set the integration up under a real Home Assistant, against a stand-in BWA module.

The stand-in (tests/fakespa.py) is the BP2100G1 it was built on: a two-speed pump 1,
a one-speed pump 2, a blower and a light, behind a module that speaks the BWA
protocol on TCP and takes one client at a time.

In order: the config flow (search result offered, a dead address refused, the
powers form with a field per level of every part, an entry); the entry set up
with every platform; the entities and their Swedish names; the power with
the heater and pumps running; pumps, blower, light, thermostat, filter cycle
and temperature range driven from Home Assistant and seen arriving at the
module; the clock set; the fault log; learning from a meter (with the quiet
times shortened); energy counted; the options flow; diagnostics; unloading.

Usage: <venv with homeassistant and pybalboa>/bin/python scripts/smoke_real_ha.py
Ends with os._exit: Python 3.14 crashes on shutdown after Home Assistant's C
extensions are loaded, once the work is done.
"""

from __future__ import annotations

import asyncio
from datetime import time as dtime
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pybalboa.discovery import DiscoveredSpa  # noqa: E402

from tests.fakespa import FakeSpa  # noqa: E402

DOMAIN = "balboa_easyconf"
TRUE_WATTS = {"heater": 2950.0, "pump_1_low": 435.0, "pump_1_high": 1700.0, "pump_2": 2000.0, "blower": 650.0}

failures: list[str] = []


def check(condition: bool, what: str) -> None:
    print(("ok    " if condition else "FAIL  ") + what)
    if not condition:
        failures.append(what)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def spa_watts(fake: FakeSpa) -> float:
    s = fake.state
    watts = TRUE_WATTS["heater"] if s.heat_state == 1 else 0.0
    watts += {0: 0.0, 1: TRUE_WATTS["pump_1_low"], 2: TRUE_WATTS["pump_1_high"]}[s.pumps[0]]
    watts += TRUE_WATTS["pump_2"] if s.pumps[1] else 0.0
    watts += TRUE_WATTS["blower"] if s.blower else 0.0
    return watts


async def until(condition, seconds: float = 5.0) -> bool:
    for _ in range(int(seconds / 0.05)):
        if condition():
            return True
        await asyncio.sleep(0.05)
    return condition()


async def main() -> int:
    from homeassistant import auth as ha_auth, bootstrap, config_entries, loader
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import entity_registry as er
    from homeassistant.setup import async_setup_component
    from homeassistant.util import dt as dt_util

    logging.basicConfig(level=logging.WARNING)
    fake = FakeSpa(interval=0.1)
    await fake.start()
    host = f"127.0.0.1:{fake.port}"

    with tempfile.TemporaryDirectory() as config_dir:
        os.makedirs(f"{config_dir}/custom_components")
        os.symlink(ROOT / "custom_components" / DOMAIN, f"{config_dir}/custom_components/{DOMAIN}")
        hass = HomeAssistant(config_dir)
        hass.config.language = "sv"
        await hass.config.async_set_time_zone("Europe/Stockholm")
        loader.async_setup(hass)
        hass.config_entries = config_entries.ConfigEntries(hass, {})
        await hass.config_entries.async_initialize()
        assert await bootstrap.async_load_base_functionality(hass)
        hass.auth = await ha_auth.auth_manager_from_config(hass, [{"type": "homeassistant"}], [])
        assert await async_setup_component(hass, "homeassistant", {})
        assert await async_setup_component(hass, "http", {"http": {"server_port": free_port()}})
        hass.states.async_set("sensor.house_power", "1500", {"unit_of_measurement": "W", "device_class": "power"})

        # A DHCP discovery of the same spa waits in the background, as it can on a real network.
        from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

        waiting = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "dhcp"},
            data=DhcpServiceInfo(ip="127.0.0.1", hostname="bwgspa_aabbcc", macaddress="001527aabbcc"),
        )
        check(waiting.get("step_id") == "confirm", f"a DHCP discovery waits ({waiting.get('step_id')})")

        found = [DiscoveredSpa("127.0.0.1", fake.port, "00:15:27:AA:BB:CC", "BWGSPA_AABBCC")]

        async def fake_discover():
            return found

        flow = hass.config_entries.flow
        with patch(f"custom_components.{DOMAIN}.config_flow.discover", fake_discover):
            result = await flow.async_init(DOMAIN, context={"source": "user"})
        check(result["step_id"] == "user", "the address form")
        default = next(k.default() for k in result["data_schema"].schema if k == "host")
        check(default == "127.0.0.1", f"the spa found on the network is offered ({default})")
        check("BWGSPA_AABBCC" in result["description_placeholders"]["found"], "and named in the text")

        dead = await flow.async_configure(result["flow_id"], {"host": f"127.0.0.1:{free_port()}"})
        check(dead.get("errors") == {"base": "cannot_connect"}, f"a dead address is refused ({dead.get('errors')})")

        result = await flow.async_configure(result["flow_id"], {"host": host})
        check(result.get("step_id") == "powers", f"the powers form follows ({result.get('step_id')})")
        fields = [str(k) for k in result["data_schema"].schema]
        check(
            fields
            == [
                "power_heater",
                "power_pump_1_low",
                "power_pump_1_high",
                "power_pump_2",
                "power_blower_1",
                "power_light_1",
                "power_standby",
                "reference_sensor",
                "use_learned",
                "sync_time",
            ],
            f"a field per level of every part ({fields})",
        )
        result = await flow.async_configure(
            result["flow_id"],
            {
                "power_heater": 2950,
                "power_pump_1_low": 435,
                "power_pump_1_high": 1500,
                "power_pump_2": 2000,
                "power_blower_1": 700,
                "power_light_1": 10,
                "power_standby": 10,
                "reference_sensor": "sensor.house_power",
                "use_learned": True,
                "sync_time": True,
            },
        )
        check(result["type"] == "create_entry", f"entry created: {result.get('title')}")
        entry = result["result"]
        check(entry.title == "BP2100G1", f"titled by the model ({entry.title})")
        await hass.async_block_till_done()
        check(
            not [f for f in hass.config_entries.flow.async_progress() if f["handler"] == DOMAIN],
            "the waiting discovery was closed by the entry",
        )
        check(entry.unique_id == "00:15:27:aa:bb:cc", f"unique by MAC ({entry.unique_id})")
        await hass.async_block_till_done()
        check(entry.state is config_entries.ConfigEntryState.LOADED, f"entry loaded ({entry.state})")
        hub = entry.runtime_data

        registry = er.async_get(hass)
        ours = {
            e.unique_id.removeprefix("00:15:27:aa:bb:cc_"): e
            for e in registry.entities.values()
            if e.platform == DOMAIN
        }
        enabled = [e for e in ours.values() if not e.disabled]
        print(f"      {len(ours)} entities, {len(enabled)} enabled by default")

        def state(key: str):
            return hass.states.get(ours[key].entity_id)

        check(state("climate") is not None and state("climate").name == "BP2100G1", "the thermostat is the spa")
        check(state("power").name == "BP2100G1 Effekt", f"Swedish names ({state('power').name})")
        check(state("heater_power").name == "BP2100G1 Effekt värmare", f"part names ({state('heater_power').name})")
        check(state("pump_1").name == "BP2100G1 Pump 1", f"pump name ({state('pump_1').name})")
        check(
            state("blower_1").name == "BP2100G1 Blåsare", f"a single blower is not numbered ({state('blower_1').name})"
        )
        check(ours["standby_power"].disabled, "the controller's own power starts disabled")
        check(state("pump_2_learned_power").name == "BP2100G1 Inlärd effekt pump 2", "a learned power per level")

        check(float(state("power").state) == 10, f"idle: only the controller ({state('power').state} W)")
        check(float(state("water_temperature").state) == 12.0, "water temperature")

        # The spa heats: pump 1 on low, the heater on.
        fake.state.pumps[0] = 1
        fake.state.heat_state = 1
        await until(lambda: hub.levels.get("heater") == "on")
        await hass.async_block_till_done()
        check(
            float(state("power").state) == 2950 + 435 + 10,
            f"heating: heater + pump 1 low + controller ({state('power').state} W)",
        )
        check(state("heater").state == "on", "the heater binary sensor")
        check(state("heat_state").state == "heating", "heat state")
        check(state("climate").attributes.get("hvac_action") == "heating", "the thermostat says heating")
        fake.state.pumps[0] = 0
        fake.state.heat_state = 0

        # Driven from Home Assistant, seen arriving at the module.
        await hass.services.async_call("fan", "turn_on", {"entity_id": state("pump_2").entity_id}, blocking=True)
        check(await until(lambda: fake.state.pumps[1] == 1), "pump 2 on")
        await until(lambda: hub.levels.get("pump_2") == "on")
        await hass.async_block_till_done()
        check(float(state("pump_2_power").state) == 2000, f"pump 2's power ({state('pump_2_power').state} W)")
        await hass.services.async_call(
            "fan", "set_percentage", {"entity_id": state("pump_1").entity_id, "percentage": 100}, blocking=True
        )
        check(await until(lambda: fake.state.pumps[0] == 2), "pump 1 to high: two presses from off")
        await until(lambda: hub.levels.get("pump_1") == "high")
        await hass.async_block_till_done()
        check(state("pump_1").attributes.get("percentage") == 100, "pump 1 reads 100 %")
        await hass.services.async_call("fan", "turn_off", {"entity_id": state("pump_1").entity_id}, blocking=True)
        await hass.services.async_call("fan", "turn_off", {"entity_id": state("pump_2").entity_id}, blocking=True)
        check(await until(lambda: fake.state.pumps == [0, 0]), "both pumps off")

        await hass.services.async_call("fan", "turn_on", {"entity_id": state("blower_1").entity_id}, blocking=True)
        check(await until(lambda: fake.state.blower == 1), "blower on")
        await until(lambda: hub.levels.get("blower_1") == "on")
        await hass.async_block_till_done()
        check(state("blower_1").state == "on", "the blower reads on (decoded from the status byte)")
        presses = sum(1 for t, p in fake.received if t == 0x11 and p[0] == 0x0C)
        await hass.services.async_call("fan", "turn_on", {"entity_id": state("blower_1").entity_id}, blocking=True)
        await asyncio.sleep(0.3)
        check(
            sum(1 for t, p in fake.received if t == 0x11 and p[0] == 0x0C) == presses and fake.state.blower == 1,
            "turning a running blower on does not toggle it off",
        )
        await hass.services.async_call("fan", "turn_off", {"entity_id": state("blower_1").entity_id}, blocking=True)
        check(await until(lambda: fake.state.blower == 0), "blower off")

        await hass.services.async_call("light", "turn_on", {"entity_id": state("light_1").entity_id}, blocking=True)
        check(await until(lambda: fake.state.light), "light on")
        await hass.services.async_call("light", "turn_off", {"entity_id": state("light_1").entity_id}, blocking=True)
        check(await until(lambda: not fake.state.light), "light off")

        climate = state("climate").entity_id
        await hass.services.async_call(
            "climate", "set_temperature", {"entity_id": climate, "temperature": 36.5}, blocking=True
        )
        check(await until(lambda: fake.state.target == 36.5), f"set temperature 36.5 °C ({fake.state.target})")
        await hass.services.async_call(
            "climate", "set_preset_mode", {"entity_id": climate, "preset_mode": "rest"}, blocking=True
        )
        check(await until(lambda: fake.state.heat_mode == 1), "rest mode")
        await until(lambda: hub.client.heat_mode.state == 1)
        await hass.async_block_till_done()
        check(state("heat_mode").state == "rest", "the heat mode select follows")
        await hass.services.async_call(
            "select", "select_option", {"entity_id": state("heat_mode").entity_id, "option": "ready"}, blocking=True
        )
        check(await until(lambda: fake.state.heat_mode == 0), "ready again from the select")
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": state("temperature_range").entity_id, "option": "high"},
            blocking=True,
        )
        check(await until(lambda: fake.state.high_range), "high temperature range")
        await hass.services.async_call(
            "time",
            "set_value",
            {"entity_id": state("filter_cycle_1_start").entity_id, "time": "01:30:00"},
            blocking=True,
        )
        check(
            await until(lambda: fake.state.filter_cycles == [1, 30, 0, 45, 4, 0, 0, 30]),
            f"filter cycle 1 moved to 01:30, still 45 min, cycle 2 untouched ({fake.state.filter_cycles})",
        )
        check(await until(lambda: hub.client.filter_cycle_1_start == dtime(1, 30)), "and read back")
        check(
            await until(
                lambda: (
                    state("filter_cycle_1_start").state == "01:30:00"
                    and state("filter_cycle_1_end").state == "02:15:00"
                )
            ),
            f"the time entities follow ({state('filter_cycle_1_start').state}-{state('filter_cycle_1_end').state})",
        )
        await hass.services.async_call(
            "time", "set_value", {"entity_id": state("filter_cycle_1_end").entity_id, "time": "02:00:00"}, blocking=True
        )
        check(
            await until(lambda: fake.state.filter_cycles[:4] == [1, 30, 0, 30]),
            f"a new end shortens it to 30 min ({fake.state.filter_cycles})",
        )
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": state("filter_cycle_2_enabled").entity_id}, blocking=True
        )
        check(
            await until(lambda: fake.state.filter_cycles[4:] == [0x84, 0, 0, 30]),
            f"filter cycle 2 turned on ({fake.state.filter_cycles})",
        )
        check(await until(lambda: state("filter_cycle_2_enabled").state == "on"), "and its switch reads on")
        try:
            await hass.services.async_call(
                "time",
                "set_value",
                {"entity_id": state("filter_cycle_1_end").entity_id, "time": "01:35:00"},
                blocking=True,
            )
            refused = False
        except Exception:
            refused = True
        check(refused and fake.state.filter_cycles[:4] == [1, 30, 0, 30], "a 5-minute cycle is refused")

        now = dt_util.now()
        check(
            (fake.state.hour, fake.state.minute) in ((now.hour, now.minute), (now.hour, (now.minute - 1) % 60)),
            f"the spa's clock set from 04:08 to Home Assistant's ({fake.state.hour:02d}:{fake.state.minute:02d})",
        )
        await until(lambda: hub.client.fault is not None)
        hub._notify()
        check(state("last_fault").state == "priming_mode", f"the fault log's last entry ({state('last_fault').state})")

        # Learning, with the quiet times cut to seconds and the meter fed 5 times a second.
        hub.learner.quiet, hub.learner.settle, hub.learner.cluster_gap = 1.5, 0.3, 0.2
        hub.learner.lost(0)  # start watching afresh under the short times
        hub._recompute()  # pybalboa only calls back on a change: take the levels now

        async def meter() -> None:
            wobble = 0.0
            while True:  # a meter that never reads quite the same twice
                wobble = 0.5 - wobble
                hass.states.async_set(
                    "sensor.house_power", str(1500 + wobble + spa_watts(fake)), {"unit_of_measurement": "W"}
                )
                await asyncio.sleep(0.2)

        feeding = asyncio.create_task(meter())
        await asyncio.sleep(2)
        for on in (True, False, True, False):
            fake.state.pumps[1] = 1 if on else 0
            await asyncio.sleep(2.5)
        check(hub.learner.count("pump_2") == 4, f"pump 2 measured on the meter ({hub.learner.samples.get('pump_2')})")
        learned = hub.learner.estimate("pump_2")
        check(learned is not None and abs(learned - 2000) < 1, f"learned 2000 W ({learned})")
        check(hub.power_source("pump_2") == "learned", "the learned power is used")
        await hass.async_block_till_done()
        check(abs(float(state("pump_2_learned_power").state) - 2000) < 1, "shown on its diagnostic sensor")
        fake.state.blower = 1
        await asyncio.sleep(2.5)
        fake.state.blower = 0
        await asyncio.sleep(2.5)
        check(
            hub.learner.count("blower_1") == 2,
            f"the blower measured from the decoded status ({hub.learner.samples.get('blower_1')})",
        )
        feeding.cancel()

        check(hub.meter.kwh() > 0, f"energy counted ({hub.meter.kwh() * 1000:.3f} Wh)")
        check(hub.meter.kwh("heater") > 0 and hub.meter.kwh("pump_2") > 0, "per part")
        await hass.async_block_till_done()
        check(float(state("energy").state) > 0, f"the energy sensor ({state('energy').state} kWh)")

        from custom_components.balboa_easyconf.diagnostics import async_get_config_entry_diagnostics

        diag = await async_get_config_entry_diagnostics(hass, entry)
        check(diag["spa"]["model"] == "BP2100G1" and "pump_2" in diag["learning"]["samples_w"], "diagnostics")
        check(
            "mac" not in str(diag["entry"]["data"]).lower() or "REDACTED" in str(diag["entry"]["data"]), "MAC redacted"
        )

        options = await hass.config_entries.options.async_init(entry.entry_id)
        check(options["step_id"] == "init", "the options form")
        current = {
            str(k): k.default() for k in options["data_schema"].schema if hasattr(k, "default") and callable(k.default)
        }
        check(
            current.get("power_heater") == 2950,
            f"the options form shows the set powers ({current.get('power_heater')})",
        )
        connections = fake.connections
        result = await hass.config_entries.options.async_configure(
            options["flow_id"],
            {
                **{k: v for k, v in current.items() if k.startswith("power_")},
                "power_heater": 3000,
                "use_learned": True,
                "sync_time": False,
            },
        )
        check(result["type"] == "create_entry", "options saved")
        await hass.async_block_till_done()
        check(
            await until(lambda: entry.state is config_entries.ConfigEntryState.LOADED, 20), f"reloaded ({entry.state})"
        )
        hub = entry.runtime_data
        check(fake.connections == connections + 1, "reconnected once")
        check(hub.configured_powers()["heater"] == 3000, "the new heater power is used")
        check(hub.reference_entity is None, "the meter was cleared")
        check(hub.learner.count("pump_2") >= 3, "learned values were kept")
        check(
            registry.async_get(ours["pump_2_learned_power"].entity_id) is not None,
            "the learned sensor's registry entry stays",
        )

        check(await hass.config_entries.async_unload(entry.entry_id), "unloads")
        check(await until(lambda: not fake.connected), "and lets go of the module")
        await hass.async_stop(force=True)
    await fake.stop()
    print("\nFAILED: " + "; ".join(failures) if failures else "\nall passed")
    return 1 if failures else 0


if __name__ == "__main__":
    rc = asyncio.run(main())
    logging.shutdown()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(rc)
