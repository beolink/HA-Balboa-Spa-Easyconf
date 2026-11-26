#!/usr/bin/env python3
"""Write strings.json and translations/{en,sv}.json from the texts below.

The power fields of the set-up and options forms are one per level of every
part a Balboa spa can have, so their labels are made from words.py rather
than typed out. Run after changing a text; ``--check`` fails when the files
on disk differ (the tests run it).
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custom_components.balboa_easyconf.const import (  # noqa: E402
    CONF_REFERENCE,
    CONF_SYNC_TIME,
    CONF_USE_LEARNED,
    POWER_PREFIX,
)
from custom_components.balboa_easyconf.model import Component, power_key  # noqa: E402
from custom_components.balboa_easyconf.words import capitalized, level_words  # noqa: E402

PACKAGE = ROOT / "custom_components" / "balboa_easyconf"


def every_component() -> list[Component]:
    """Every part pybalboa can report, with every level it can have."""
    out = [Component("heater", "heater", None, ("on",))]
    for kind, count in (("pump", 8), ("blower", 2)):
        for n in range(1, count + 1):
            out.append(Component(f"{kind}_{n}", kind, n, ("on",)))
            out.append(Component(f"{kind}_{n}", kind, n, ("low", "medium", "high")))
    out.append(Component("circulation_pump", "circulation_pump", None, ("on",)))
    for kind, count in (("light", 4), ("aux", 4), ("mister", 3)):
        for n in range(1, count + 1):
            out.append(Component(f"{kind}_{n}", kind, n, ("on",)))
    out.append(Component("standby", "standby", None, ("on",)))
    return out


def power_labels(lang: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    for component in every_component():
        for level in component.levels:
            labels[POWER_PREFIX + power_key(component, level)] = capitalized(level_words(component, level, lang))
    return labels


T = {
    "sv": {
        "user_title": "Balboa-spabad",
        "user_desc": (
            "Adressen till spabadets Wi-Fi-modul (BWA). Hittat i nätet: {found}\n\n"
            "Modulen tar bara emot en anslutning åt gången. Ta först bort eller inaktivera Home Assistants "
            "egen Balboa-integration för samma spabad, och stäng andra appar som är anslutna till det."
        ),
        "host": "Värdnamn eller IP-adress",
        "host_desc": "Till exempel 192.168.1.50. Lägg till :port bara om modulen nås på en annan port än 4257.",
        "confirm_title": "Spabad hittat",
        "confirm_desc": "Ett Balboa-spabad finns på {host}. Lägga till det?",
        "powers_title": "Vad delarna drar",
        "powers_desc": (
            "{model} har de här delarna. Ange vad varje del drar i watt när den går: spabadets effekt och "
            "energi räknas ut från vilka delar som går just då. Förslagen är typiska för ett spabad på 230 V; "
            "byt till det som står på typskylten eller det du har mätt.\n\n"
            "Välj en elmätare som ser spabadet (husets förbrukning, en fas av den, eller ett mätande uttag) "
            "så lär sig integrationen vad varje del drar: varje gång en del slås på eller av medan resten av "
            "spabadet står still i 30 sekunder före och efter, mäts hoppet på mätaren."
        ),
        "options_title": "Effekter och inlärning",
        "reference": "Elmätare att lära av",
        "reference_desc": "En effektsensor vars värde innefattar spabadet. Den bör uppdateras minst var tionde sekund.",
        "use_learned": "Använd inlärda effekter",
        "use_learned_desc": "När en del har mätts minst tre gånger används medianen av mätningarna i stället för värdet ovan.",
        "sync_time": "Håll spabadets klocka rätt",
        "sync_time_desc": "Ställer spabadets klocka efter Home Assistant en gång i timmen om den går fel med mer än en minut. Filtercyklerna går efter den klockan.",
        "cannot_connect": (
            "Inget svar från spabadet. Modulen tar bara en anslutning åt gången: är Home Assistants egen "
            "Balboa-integration eller en app ansluten till det?"
        ),
        "no_configuration": "Spabadet svarade men skickade inte sin konfiguration. Försök igen om en stund.",
        "already_configured": "Spabadet är redan tillagt.",
        "ready": "Klar",
        "rest": "Vila",
        "pump": "Pump{number}",
        "blower": "Blåsare{number}",
        "light": "Belysning{number}",
        "aux": "Aux{number}",
        "mister": "Dimma{number}",
        "filter_cycle_2_enabled": "Filtercykel 2 aktiverad",
        "heat_mode": "Värmeläge",
        "temperature_range": "Temperaturområde",
        "low": "Låg",
        "high": "Hög",
        "fc1_start": "Filtercykel 1 start",
        "fc1_end": "Filtercykel 1 slut",
        "fc2_start": "Filtercykel 2 start",
        "fc2_end": "Filtercykel 2 slut",
        "heater": "Värmare",
        "fc1": "Filtercykel 1",
        "fc2": "Filtercykel 2",
        "circulation_pump": "Cirkulationspump",
        "water_temperature": "Vattentemperatur",
        "heat_state": "Värme",
        "hs_off": "Av",
        "hs_heating": "Värmer",
        "hs_waiting": "Väntar",
        "last_fault": "Senaste fel",
        "power": "Effekt",
        "energy": "Energi",
        "part_power": "Effekt {part}",
        "part_energy": "Energi {part}",
        "learned_power": "Inlärd effekt {part}",
        "sync_clock": "Ställ klockan",
        "forget_learned": "Glöm inlärda effekter",
        "faults": {
            "sensors_out_of_sync": "Givarna visar olika",
            "low_flow": "Lågt flöde",
            "flow_failed": "Inget flöde",
            "settings_reset": "Inställningarna återställda",
            "priming_mode": "Uppstart (priming)",
            "clock_failed": "Klockan har stannat",
            "memory_failure": "Minnesfel",
            "service_sensor_sync": "Givarna visar olika, kontakta service",
            "heater_dry": "Värmaren är torr",
            "heater_may_be_dry": "Värmaren kan vara torr",
            "water_too_hot": "Vattnet är för varmt",
            "heater_too_hot": "Värmaren är för varm",
            "sensor_a_fault": "Fel på givare A",
            "sensor_b_fault": "Fel på givare B",
            "pump_stuck": "En pump kan ha fastnat i påslaget läge",
            "hot_fault": "Överhettning",
            "gfci_test_failed": "Jordfelsbrytartestet misslyckades",
            "standby_mode": "Standby (hold)",
            "unknown": "Okänt fel",
        },
    },
    "en": {
        "user_title": "Balboa spa",
        "user_desc": (
            "The address of the spa's Wi-Fi module (BWA). Found on the network: {found}\n\n"
            "The module takes one connection at a time. First remove or disable Home Assistant's own Balboa "
            "integration for the same spa, and close other apps connected to it."
        ),
        "host": "Host name or IP address",
        "host_desc": "Such as 192.168.1.50. Add :port only if the module is reached on another port than 4257.",
        "confirm_title": "Spa found",
        "confirm_desc": "There is a Balboa spa at {host}. Add it?",
        "powers_title": "What the parts draw",
        "powers_desc": (
            "{model} has these parts. Enter what each draws in watts while it runs: the spa's power and energy "
            "are worked out from which parts run at the moment. The suggestions are typical of a spa on 230 V; "
            "change them to what the rating plate says or what you have measured.\n\n"
            "Pick a power meter that sees the spa (the house's consumption, one phase of it, or a metering "
            "plug) and the integration learns what each part draws: each time a part switches on or off while "
            "the rest of the spa stays as it is for 30 seconds before and after, the step on the meter is measured."
        ),
        "options_title": "Powers and learning",
        "reference": "Power meter to learn from",
        "reference_desc": "A power sensor whose reading includes the spa. It should update at least every ten seconds.",
        "use_learned": "Use learned powers",
        "use_learned_desc": "Once a part has been measured three times, the median of the measurements replaces the figure above.",
        "sync_time": "Keep the spa's clock right",
        "sync_time_desc": "Sets the spa's clock from Home Assistant once an hour when it is more than a minute off. The filter cycles run by that clock.",
        "cannot_connect": (
            "No answer from the spa. The module takes one connection at a time: is Home Assistant's own Balboa "
            "integration or an app connected to it?"
        ),
        "no_configuration": "The spa answered but did not send its configuration. Try again in a moment.",
        "already_configured": "The spa is already added.",
        "ready": "Ready",
        "rest": "Rest",
        "pump": "Pump{number}",
        "blower": "Blower{number}",
        "light": "Light{number}",
        "aux": "Aux{number}",
        "mister": "Mister{number}",
        "filter_cycle_2_enabled": "Filter cycle 2 enabled",
        "heat_mode": "Heat mode",
        "temperature_range": "Temperature range",
        "low": "Low",
        "high": "High",
        "fc1_start": "Filter cycle 1 start",
        "fc1_end": "Filter cycle 1 end",
        "fc2_start": "Filter cycle 2 start",
        "fc2_end": "Filter cycle 2 end",
        "heater": "Heater",
        "fc1": "Filter cycle 1",
        "fc2": "Filter cycle 2",
        "circulation_pump": "Circulation pump",
        "water_temperature": "Water temperature",
        "heat_state": "Heat",
        "hs_off": "Off",
        "hs_heating": "Heating",
        "hs_waiting": "Waiting",
        "last_fault": "Last fault",
        "power": "Power",
        "energy": "Energy",
        "part_power": "{part} power",
        "part_energy": "{part} energy",
        "learned_power": "Learned power, {part}",
        "sync_clock": "Set the clock",
        "forget_learned": "Forget learned powers",
        "faults": {
            "sensors_out_of_sync": "Sensors are out of sync",
            "low_flow": "The water flow is low",
            "flow_failed": "The water flow has failed",
            "settings_reset": "The settings have been reset",
            "priming_mode": "Priming mode",
            "clock_failed": "The clock has failed",
            "memory_failure": "Program memory failure",
            "service_sensor_sync": "Sensors are out of sync, call for service",
            "heater_dry": "The heater is dry",
            "heater_may_be_dry": "The heater may be dry",
            "water_too_hot": "The water is too hot",
            "heater_too_hot": "The heater is too hot",
            "sensor_a_fault": "Sensor A fault",
            "sensor_b_fault": "Sensor B fault",
            "pump_stuck": "A pump may be stuck on",
            "hot_fault": "Hot fault",
            "gfci_test_failed": "The GFCI test failed",
            "standby_mode": "Standby (hold mode)",
            "unknown": "Unknown fault",
        },
    },
}


def power_step(t: dict, lang: str, title: str) -> dict:
    return {
        "title": t[title],
        "description": t["powers_desc"],
        "data": {
            **power_labels(lang),
            CONF_REFERENCE: t["reference"],
            CONF_USE_LEARNED: t["use_learned"],
            CONF_SYNC_TIME: t["sync_time"],
        },
        "data_description": {
            CONF_REFERENCE: t["reference_desc"],
            CONF_USE_LEARNED: t["use_learned_desc"],
            CONF_SYNC_TIME: t["sync_time_desc"],
        },
    }


def build(lang: str) -> dict:
    t = T[lang]
    named = lambda key: {"name": t[key]}  # noqa: E731
    return {
        "config": {
            "flow_title": "{name}",
            "step": {
                "user": {
                    "title": t["user_title"],
                    "description": t["user_desc"],
                    "data": {"host": t["host"]},
                    "data_description": {"host": t["host_desc"]},
                },
                "confirm": {"title": t["confirm_title"], "description": t["confirm_desc"]},
                "powers": power_step(t, lang, "powers_title"),
            },
            "error": {"cannot_connect": t["cannot_connect"], "no_configuration": t["no_configuration"]},
            "abort": {"already_configured": t["already_configured"]},
        },
        "options": {"step": {"init": power_step(t, lang, "options_title")}},
        "entity": {
            "climate": {
                "spa": {
                    "state_attributes": {
                        "preset_mode": {"state": {"ready": t["ready"], "rest": t["rest"]}},
                    }
                }
            },
            "fan": {"pump": named("pump"), "blower": named("blower")},
            "light": {"light": named("light")},
            "switch": {
                "filter_cycle_2_enabled": named("filter_cycle_2_enabled"),
                "aux": named("aux"),
                "mister": named("mister"),
            },
            "select": {
                "heat_mode": {"name": t["heat_mode"], "state": {"ready": t["ready"], "rest": t["rest"]}},
                "temperature_range": {
                    "name": t["temperature_range"],
                    "state": {"low": t["low"], "high": t["high"]},
                },
            },
            "time": {
                "filter_cycle_1_start": named("fc1_start"),
                "filter_cycle_1_end": named("fc1_end"),
                "filter_cycle_2_start": named("fc2_start"),
                "filter_cycle_2_end": named("fc2_end"),
            },
            "binary_sensor": {
                "heater": named("heater"),
                "filter_cycle_1": named("fc1"),
                "filter_cycle_2": named("fc2"),
                "circulation_pump": named("circulation_pump"),
            },
            "sensor": {
                "water_temperature": named("water_temperature"),
                "heat_state": {
                    "name": t["heat_state"],
                    "state": {"off": t["hs_off"], "heating": t["hs_heating"], "heat_waiting": t["hs_waiting"]},
                },
                "last_fault": {"name": t["last_fault"], "state": dict(sorted(t["faults"].items()))},
                "power": named("power"),
                "energy": named("energy"),
                "part_power": named("part_power"),
                "part_energy": named("part_energy"),
                "learned_power": named("learned_power"),
            },
            "button": {"sync_clock": named("sync_clock"), "forget_learned": named("forget_learned")},
        },
    }


def render(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def outputs() -> dict[Path, str]:
    en = render(build("en"))
    return {
        PACKAGE / "strings.json": en,
        PACKAGE / "translations" / "en.json": en,
        PACKAGE / "translations" / "sv.json": render(build("sv")),
    }


def main() -> int:
    check = "--check" in sys.argv
    stale = []
    for path, text in outputs().items():
        if path.exists() and path.read_text(encoding="utf-8") == text:
            continue
        if check:
            stale.append(path.relative_to(ROOT))
        else:
            path.write_text(text, encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT)}")
    if stale:
        print("out of date (run scripts/build_strings.py):", *stale, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
