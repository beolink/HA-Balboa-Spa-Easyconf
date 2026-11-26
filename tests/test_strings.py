"""The translations are generated (scripts/build_strings.py) and cover every entity."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "custom_components" / "balboa_easyconf"


def test_generated_files_are_current():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_strings.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_swedish_has_every_english_key():
    def keys(node, prefix=""):
        if isinstance(node, dict):
            for key, value in node.items():
                yield from keys(value, f"{prefix}/{key}")
        else:
            yield prefix

    en = json.loads((PACKAGE / "translations" / "en.json").read_text())
    sv = json.loads((PACKAGE / "translations" / "sv.json").read_text())
    assert set(keys(en)) == set(keys(sv))


def test_fault_states_match_the_sensor():
    from custom_components.balboa_easyconf.sensor import FAULT_OPTIONS

    en = json.loads((PACKAGE / "translations" / "en.json").read_text())
    assert sorted(en["entity"]["sensor"]["last_fault"]["state"]) == FAULT_OPTIONS
