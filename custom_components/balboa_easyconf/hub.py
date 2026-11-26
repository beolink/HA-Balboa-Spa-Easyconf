"""One spa: its connection, the level of each part, its power and energy.

The BWA Wi-Fi module pushes a status message about once a second; pybalboa
calls back when one differs from the last. On each, the hub reads the level
of every part, works out the power per part (power.py), adds the energy since
the last change (energy.py), hands the levels to the learner (learn.py) and
tells the entities. Once a minute it does the same without a change, so the
energy entities move while nothing switches, saves the totals and the
learned measurements, asks for the fault log every ten minutes and, when
turned on, sets the spa's clock once an hour if it is off by more than a
minute.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, time as dtime, timedelta
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo, format_mac
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from pybalboa import EVENT_UPDATE, SpaClient
from pybalboa.enums import MessageType, ToggleItemCode

from .const import CONF_REFERENCE, CONF_SYNC_TIME, CONF_USE_LEARNED, DOMAIN, MANUFACTURER
from .energy import EnergyMeter
from .learn import PowerLearner
from .model import OFF, Component, components_from_client, controls_by_id, levels_from_client
from .power import component_powers, configured_powers
from .words import language, numbered_kinds

_LOGGER = logging.getLogger(__name__)

TICK = timedelta(seconds=60)
FAULT_EVERY = timedelta(minutes=10)
CLOCK_EVERY = timedelta(hours=1)
#: Shorter than TICK: a save delayed again by every tick would never happen.
SAVE_DELAY = 30
#: The module's answer to a filter cycle change does not make pybalboa call back.
REREAD_AFTER = 1.5
EXPECT_FOR = 3.0
#: Each press steps a part to its next level, off after the last. The presses
#: are counted here, from the level last asked for while the spa has not yet
#: shown it (``EXPECT_FOR``): pybalboa counts from the last status, so "on"
#: then "off" within a status message's time would leave the part on; it also
#: misreads the blower, and gives a light configured with several levels two
#: presses for off.
PRESS_CODES = {
    "pump": ToggleItemCode.PUMP_1,
    "blower": ToggleItemCode.BLOWER,
    "light": ToggleItemCode.LIGHT_1,
    "aux": ToggleItemCode.AUX_1,
    "mister": ToggleItemCode.MISTER,
}

_TO_WATTS = {"W": 1.0, "kW": 1000.0, "MW": 1_000_000.0, "mW": 0.001}


def watts_of(state: State | None) -> float | None:
    """A power sensor's state in watts, or None."""
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN, ""):
        return None
    try:
        value = float(state.state)
    except ValueError:
        return None
    factor = _TO_WATTS.get(state.attributes.get("unit_of_measurement"), 1.0)
    return value * factor


class SpaHub:
    """The spa behind one config entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SpaClient,
        store: Store,
        stored: dict[str, Any] | None,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.client = client
        self._store = store
        stored = stored or {}
        self.mac = format_mac(client.mac_address)
        self.components: list[Component] = components_from_client(client)
        self.lang = language(hass.config.language)
        self.numbered = numbered_kinds(self.components)
        self.learner = PowerLearner(self.components, stored.get("learned"))
        self.meter = EnergyMeter(stored.get("energy_wh"))
        self.levels: dict[str, str] = {}
        #: Watts per component now, None while the spa does not answer.
        self.powers: dict[str, float] | None = None
        self.available = False
        self.reference_watts: float | None = None
        self._listeners: list[Callable[[], None]] = []
        self._unsubs: list[Callable[[], None]] = []
        self._last_fault_request: datetime | None = None
        self._last_clock_check: datetime | None = None
        self._flush_pending = False
        #: Levels asked for and not yet shown by the spa: {id: (level, until)}.
        self._expected: dict[str, tuple[str, float]] = {}
        self._signature: tuple | None = None
        self._stopped = False

    # -- options

    @property
    def reference_entity(self) -> str | None:
        return self.entry.options.get(CONF_REFERENCE) or None

    @property
    def use_learned(self) -> bool:
        return self.reference_entity is not None and bool(self.entry.options.get(CONF_USE_LEARNED, True))

    def configured_powers(self) -> dict[str, float]:
        return configured_powers(self.components, self.entry.options)

    def effective_powers(self) -> dict[str, float]:
        powers = self.configured_powers()
        if self.use_learned:
            powers.update({k: v for k, v in self.learner.estimates().items() if k in powers})
        return powers

    def power_source(self, key: str) -> str:
        if self.use_learned and self.learner.estimate(key) is not None:
            return "learned"
        return "configured"

    # -- the spa

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.mac)},
            connections={(CONNECTION_NETWORK_MAC, self.mac)},
            manufacturer=MANUFACTURER,
            model=self.client.model,
            sw_version=self.client.software_version,
            name=self.entry.title,
        )

    def component(self, component_id: str) -> Component | None:
        return next((c for c in self.components if c.id == component_id), None)

    @property
    def total_power(self) -> float | None:
        return None if self.powers is None else sum(self.powers.values())

    # -- life cycle

    async def async_start(self) -> None:
        self._unsubs.append(self.client.on(EVENT_UPDATE, self._on_update))
        self._unsubs.append(async_track_time_interval(self.hass, self._tick, TICK))
        if (reference := self.reference_entity) is not None:
            self._unsubs.append(async_track_state_change_event(self.hass, [reference], self._on_reference))
            self._reference_reading(self.hass.states.get(reference))
        self._recompute()
        await self._housekeeping()

    async def async_stop(self) -> None:
        self._stopped = True
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        try:
            self._recompute()
            await self._store.async_save(self._data())
        finally:
            await self.client.disconnect()

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)

        def remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove

    @callback
    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    # -- updates

    @callback
    def _on_update(self, *_: Any) -> None:
        """pybalboa calls back once per changed control while it reads a
        status message, and once at its end, and for every other client in
        the process too (its listeners are shared). Work once, after it."""
        if not self._flush_pending:
            self._flush_pending = True
            self.hass.loop.call_soon(self._flush)

    @callback
    def _flush(self, force: bool = False) -> None:
        self._flush_pending = False
        if self._stopped:
            return
        signature = self._current_signature()
        if signature == self._signature and not force:
            return
        self._signature = signature
        self._recompute()
        self._notify()

    def _current_signature(self) -> tuple:
        c = self.client
        return (
            getattr(c, "_previous_status", None),
            c.available,
            c.filter_cycle_1_start,
            c.filter_cycle_1_duration,
            c.filter_cycle_2_enabled,
            c.filter_cycle_2_start,
            c.filter_cycle_2_duration,
            id(c.fault),
        )

    @callback
    def _recompute(self) -> None:
        now = time.monotonic()
        available = self.client.available
        if available:
            levels = levels_from_client(self.client, self.components)
            self.learner.observe_levels(now, levels)
            powers: dict[str, float] | None = component_powers(self.components, levels, self.effective_powers())
        else:
            if self.available:
                self.learner.lost(now)
            levels, powers = {}, None
        self.meter.update(now, powers)
        self.levels, self.powers, self.available = levels, powers, available

    @callback
    def _reference_reading(self, state: State | None) -> None:
        self.reference_watts = watts_of(state)
        self.learner.observe_reference(time.monotonic(), self.reference_watts)

    @callback
    def _on_reference(self, event: Event[EventStateChangedData]) -> None:
        self._reference_reading(event.data["new_state"])
        if self.learner.evaluate(time.monotonic()):
            self._learned()

    @callback
    def _learned(self) -> None:
        self._recompute()
        self._store.async_delay_save(self._data, SAVE_DELAY)
        self._notify()

    async def _tick(self, _now: datetime) -> None:
        self._recompute()
        if self.learner.evaluate(time.monotonic()):
            self._recompute()
        self._store.async_delay_save(self._data, SAVE_DELAY)
        self._notify()
        await self._housekeeping()

    async def _housekeeping(self) -> None:
        if not self.client.available:
            return
        now = dt_util.now()
        if self._last_fault_request is None or now - self._last_fault_request >= FAULT_EVERY:
            self._last_fault_request = now
            await self.client.request_fault_log()
        if self.entry.options.get(CONF_SYNC_TIME, True) and (
            self._last_clock_check is None or now - self._last_clock_check >= CLOCK_EVERY
        ):
            self._last_clock_check = now
            await self.async_sync_clock(only_if_off=True)

    async def async_sync_clock(self, *, only_if_off: bool = False) -> None:
        """Set the spa's clock to Home Assistant's local time."""
        now = dt_util.now()
        spa_minutes = self.client.time_hour * 60 + self.client.time_minute
        off = abs(spa_minutes - (now.hour * 60 + now.minute)) % 1440
        off = min(off, 1440 - off)
        if only_if_off and off <= 1:
            return
        _LOGGER.debug(
            "Setting the spa's clock from %02d:%02d to %s", self.client.time_hour, self.client.time_minute, now
        )
        await self.client.set_time(now.hour, now.minute)

    def _level_now(self, component_id: str) -> str:
        """The level the spa shows, or the one last asked for if it may not show it yet."""
        shown = self.levels.get(component_id, OFF)
        expected = self._expected.get(component_id)
        if expected is None:
            return shown
        level, until = expected
        if shown == level or time.monotonic() > until:
            del self._expected[component_id]
            return shown
        return level

    async def async_set_level(self, component: Component, level: str) -> None:
        """Run a pump, blower, light, aux or mister at a level (or ``off``)."""
        control = controls_by_id(self.client).get(component.id)
        code = PRESS_CODES.get(component.kind)
        current = self._level_now(component.id)
        order = [OFF, *component.levels]
        if control is None or code is None or level not in order:
            raise HomeAssistantError(f"{component.id} cannot be set to {level}")
        if current == level or current not in order:
            return
        presses = (order.index(level) - order.index(current)) % len(order)
        for _ in range(presses):
            await self.client.send_message(MessageType.TOGGLE_STATE, code + (control.index or 0))
        self._expected[component.id] = (level, time.monotonic() + EXPECT_FOR)

    @callback
    def async_reset_learned(self) -> None:
        self.learner.reset()
        self._recompute()
        self.hass.async_create_task(self._store.async_save(self._data()))
        self._notify()

    async def async_set_filter_cycle(
        self, cycle: int, *, start: dtime | None = None, end: dtime | None = None, enabled: bool | None = None
    ) -> None:
        """Change a filter cycle's start or end, or turn cycle 2 on or off.

        A new start moves the cycle and keeps its length; a new end changes
        its length. Both cycles go to the module every time, with their
        lengths in whole minutes (pybalboa's own helper reads a 24-hour cycle
        back as 0 minutes).
        """
        c = self.client
        cycles = {
            1: [c.filter_cycle_1_start, int(c.filter_cycle_1_duration.total_seconds() // 60)],
            2: [c.filter_cycle_2_start, int(c.filter_cycle_2_duration.total_seconds() // 60)],
        }
        if cycles[1][0] is None or cycles[2][0] is None:
            raise HomeAssistantError("The spa has not sent its filter cycles yet")
        if start is not None:
            cycles[cycle][0] = start
        if end is not None:
            first = cycles[cycle][0]
            cycles[cycle][1] = ((end.hour - first.hour) * 60 + end.minute - first.minute) % 1440 or 1440
        if not 15 <= cycles[cycle][1] <= 1440:
            raise HomeAssistantError(f"A filter cycle runs 15 minutes to 24 hours, not {cycles[cycle][1]} minutes")
        (s1, m1), (s2, m2) = cycles[1], cycles[2]
        await c.set_filter_cycle(
            filter_cycle_1_hour=s1.hour,
            filter_cycle_1_minute=s1.minute,
            filter_cycle_1_duration_hours=m1 // 60,
            filter_cycle_1_duration_minutes=m1 % 60,
            filter_cycle_2_enabled=c.filter_cycle_2_enabled if enabled is None else enabled,
            filter_cycle_2_hour=s2.hour,
            filter_cycle_2_minute=s2.minute,
            filter_cycle_2_duration_hours=m2 // 60,
            filter_cycle_2_duration_minutes=m2 % 60,
        )
        self.hass.loop.call_later(REREAD_AFTER, self._flush)

    def _data(self) -> dict[str, Any]:
        return {
            "energy_wh": {k: round(v, 3) for k, v in self.meter.totals_wh.items()},
            "learned": {k: list(v) for k, v in self.learner.samples.items()},
        }
