"""Learn what each part of the spa draws, from a meter that sees the spa.

The meter is any power sensor whose reading includes the spa: the house's
consumption from the grid meter or the inverter, a phase of it, or a plug.
Other loads come and go on it too; what makes a measurement is a moment when
the spa switches something and nothing else of the spa changes around it:

* the spa's changes are grouped: changes less than ``CLUSTER_GAP`` apart are
  one event (a pump starting and the heater following it two seconds later);
* an event counts only if the spa changed nothing for ``QUIET`` seconds
  before it and after it;
* the meter's median over the quiet time before (up to a second before the
  event) is compared with its median after it (from ``SETTLE`` seconds after,
  to skip start-up surges and the meter's own delay); each reading holds until
  the next, so a meter that only reports changes works, but one that said
  nothing at all around the event is taken as stale;
* the step is shared out over the power keys that changed: when exactly one
  of them has no learned value yet, or only one changed at all, it gets what
  is left after the others' learned values.

Each key keeps its last ``MAX_SAMPLES`` measurements, and its learned power is
their median once there are ``MIN_SAMPLES``. A measurement outside
``MIN_WATTS``..``MAX_WATTS`` is dropped (another load switching at the same
moment), as is one whose sign is wrong.

Times are seconds on one clock (the hub passes ``time.monotonic()``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import statistics

from .model import OFF, Component, power_key

CLUSTER_GAP = 8.0
QUIET = 30.0
SETTLE = 5.0
#: The last second before an event is left out of the "before" median.
LEAD = 1.0
MAX_SAMPLES = 25
MIN_SAMPLES = 3
MIN_WATTS = 3.0
MAX_WATTS = 12000.0
#: How long readings are kept when no event waits for them.
KEEP = 120.0


@dataclass(frozen=True)
class Transition:
    t: float
    component: str
    old: str
    new: str


class PowerLearner:
    """Measurements per power key, from the steps of a meter."""

    def __init__(
        self,
        components: list[Component],
        samples: Mapping[str, list[float]] | None = None,
        *,
        quiet: float = QUIET,
        settle: float = SETTLE,
        cluster_gap: float = CLUSTER_GAP,
    ) -> None:
        self._components = {c.id: c for c in components if c.kind != "standby"}
        keys = {key for c in self._components.values() for key in c.power_keys}
        self.samples: dict[str, list[float]] = {
            key: [float(v) for v in values][-MAX_SAMPLES:] for key, values in (samples or {}).items() if key in keys
        }
        self.quiet = quiet
        self.settle = settle
        self.cluster_gap = cluster_gap
        self._levels: dict[str, str] | None = None
        self._since: float | None = None
        self._last_change: float | None = None
        self._pending: list[Transition] = []
        self._readings: list[tuple[float, float]] = []
        self.events = 0
        self.rejected = 0

    # -- what comes in

    def observe_levels(self, t: float, levels: Mapping[str, str]) -> None:
        """The spa's levels now; changes since the last call are events."""
        if self._levels is None:
            self._levels = {cid: levels.get(cid, OFF) for cid in self._components}
            self._since = t
            return
        for cid in self._components:
            new = levels.get(cid, OFF)
            old = self._levels.get(cid, OFF)
            if new != old:
                self._pending.append(Transition(t, cid, old, new))
                self._levels[cid] = new

    def observe_reference(self, t: float, watts: float | None) -> None:
        """A reading of the meter; None when it has none (unavailable)."""
        if watts is None:
            self._readings.clear()
            return
        self._readings.append((t, float(watts)))

    def lost(self, t: float) -> None:
        """The spa stopped answering: what it did meanwhile is unknown."""
        self._levels = None
        self._pending.clear()
        self._last_change = t

    def reset(self) -> None:
        self.samples.clear()

    # -- what comes out

    def count(self, key: str) -> int:
        return len(self.samples.get(key, ()))

    def estimate(self, key: str) -> float | None:
        values = self.samples.get(key)
        if not values or len(values) < MIN_SAMPLES:
            return None
        return float(statistics.median(values))

    def estimates(self) -> dict[str, float]:
        out = {}
        for key in self.samples:
            if (value := self.estimate(key)) is not None:
                out[key] = value
        return out

    # -- the work

    def evaluate(self, now: float) -> list[str]:
        """Measure every event whose quiet time after has passed.

        Returns the keys that got a new measurement.
        """
        learned: list[str] = []
        while self._pending:
            cluster = [self._pending[0]]
            for transition in self._pending[1:]:
                if transition.t - cluster[-1].t > self.cluster_gap:
                    break
                cluster.append(transition)
            following = self._pending[len(cluster)] if len(cluster) < len(self._pending) else None
            first, last = cluster[0].t, cluster[-1].t
            if following is None and now < last + self.quiet:
                break  # still waiting for the quiet time after
            del self._pending[: len(cluster)]
            quiet_before = (self._since is not None and first - self._since >= self.quiet) and (
                self._last_change is None or first - self._last_change >= self.quiet
            )
            quiet_after = following is None or following.t - last >= self.quiet
            self._last_change = last
            if not (quiet_before and quiet_after):
                continue
            self.events += 1
            key = self._measure(cluster, first, last)
            if key is None:
                self.rejected += 1
            else:
                learned.append(key)
        self._trim(now)
        return learned

    def _coefficients(self, cluster: list[Transition]) -> dict[str, int]:
        start: dict[str, str] = {}
        end: dict[str, str] = {}
        for transition in cluster:
            start.setdefault(transition.component, transition.old)
            end[transition.component] = transition.new
        coefficients: dict[str, int] = {}
        for cid, old in start.items():
            new = end[cid]
            if old == new:
                continue
            component = self._components[cid]
            if old != OFF and old in component.levels:
                key = power_key(component, old)
                coefficients[key] = coefficients.get(key, 0) - 1
            if new != OFF and new in component.levels:
                key = power_key(component, new)
                coefficients[key] = coefficients.get(key, 0) + 1
        return {key: c for key, c in coefficients.items() if c}

    def _measure(self, cluster: list[Transition], first: float, last: float) -> str | None:
        coefficients = self._coefficients(cluster)
        if not coefficients:
            return None
        if not any(first - self.quiet <= t <= last + self.quiet for t, _ in self._readings):
            return None  # the meter said nothing around the event: stale
        before = self._median(first - self.quiet, first - LEAD)
        after = self._median(last + self.settle, last + self.quiet)
        if before is None or after is None:
            return None
        step = after - before
        if len(coefficients) == 1:
            ((key, coefficient),) = coefficients.items()
            rest = 0.0
        else:
            unknown = [key for key in coefficients if self.estimate(key) is None]
            if len(unknown) != 1:
                return None
            key = unknown[0]
            coefficient = coefficients[key]
            rest = sum(c * (self.estimate(k) or 0.0) for k, c in coefficients.items() if k != key)
        value = (step - rest) / coefficient
        if not MIN_WATTS <= value <= MAX_WATTS:
            return None
        values = self.samples.setdefault(key, [])
        values.append(round(value, 1))
        del values[:-MAX_SAMPLES]
        return key

    def _median(self, start: float, end: float) -> float | None:
        """The meter's median over [start, end], each reading held until the next."""
        if end <= start:
            return None
        anchor: float | None = None
        inside: list[tuple[float, float]] = []
        for t, watts in self._readings:
            if t <= start:
                anchor = watts
            elif t <= end:
                inside.append((t, watts))
            else:
                break
        if anchor is None and not inside:
            return None
        # Sample once a second, holding each reading until the next one.
        values: list[float] = []
        index = 0
        current = anchor
        t = start
        while t <= end:
            while index < len(inside) and inside[index][0] <= t:
                current = inside[index][1]
                index += 1
            if current is not None:
                values.append(current)
            t += 1.0
        return float(statistics.median(values)) if values else None

    def _trim(self, now: float) -> None:
        oldest = now - KEEP
        if self._pending:
            oldest = min(oldest, self._pending[0].t - self.quiet - LEAD)
        # Keep the last reading before the cut: it holds the value at the cut.
        cut = 0
        for i, (t, _) in enumerate(self._readings):
            if t < oldest:
                cut = i
            else:
                break
        if cut:
            del self._readings[:cut]
