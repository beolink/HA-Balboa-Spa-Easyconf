"""Energy per part of the spa: its power held until the next change, summed.

The spa's power only changes when a part switches, so holding each power
until the next update and adding power times time is exact for the model. The
hub calls ``update`` on every change and once a minute; while the spa does not
answer (powers None) nothing is added, since what it did is unknown.
"""

from __future__ import annotations

from collections.abc import Mapping

#: A longer gap between two updates than this is not counted (a stalled clock).
MAX_STEP = 3600.0


class EnergyMeter:
    """Watt-hours per component, from the powers handed in over time."""

    def __init__(self, totals_wh: Mapping[str, float] | None = None) -> None:
        self.totals_wh: dict[str, float] = {k: float(v) for k, v in (totals_wh or {}).items()}
        self._t: float | None = None
        self._powers: dict[str, float] | None = None

    def update(self, t: float, powers: Mapping[str, float] | None) -> None:
        """Count the powers held since the last update, then hold these."""
        if self._t is not None and self._powers is not None:
            dt = t - self._t
            if 0 < dt <= MAX_STEP:
                for key, watts in self._powers.items():
                    self.totals_wh[key] = self.totals_wh.get(key, 0.0) + watts * dt / 3600.0
        self._t = t
        self._powers = dict(powers) if powers is not None else None

    def kwh(self, key: str | None = None) -> float:
        if key is None:
            return sum(self.totals_wh.values()) / 1000.0
        return self.totals_wh.get(key, 0.0) / 1000.0
