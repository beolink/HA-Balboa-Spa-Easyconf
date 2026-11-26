"""The spa's parts that use electricity, and the level each is at.

A component is one thing that draws power: the heater, each pump, each
blower, the circulation pump, each light, aux and mister, and the controller
itself (``standby``, always on while the spa answers). Each has the levels it
can run at besides off: ``("on",)`` for a one-speed pump, ``("low", "high")``
for a two-speed one.

A power key names one level's power: the component id alone when it has one
level (``heater``, ``pump_2``), else id and level (``pump_1_low``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pybalboa.enums import HeatState

if TYPE_CHECKING:
    from pybalboa import SpaClient, SpaControl

OFF = "off"

#: Component kinds in the order they are listed.
KINDS = ("heater", "pump", "blower", "circulation_pump", "light", "aux", "mister", "standby")
#: Kinds that are only ever on or off in the status message, whatever their
#: configuration says (a light's two configuration bits can be 2 or 3).
ON_OFF_KINDS = frozenset({"light", "aux", "mister", "circulation_pump"})
#: Kinds that come numbered (pybalboa gives these an index).
NUMBERED = frozenset({"pump", "blower", "light", "aux", "mister"})


@dataclass(frozen=True)
class Component:
    """One part of the spa that uses electricity."""

    id: str
    kind: str
    number: int | None
    levels: tuple[str, ...]

    @classmethod
    def from_id(cls, component_id: str, levels: list[str] | tuple[str, ...]) -> Component:
        kind, _, tail = component_id.rpartition("_")
        if kind in NUMBERED and tail.isdigit():
            return cls(component_id, kind, int(tail), tuple(levels))
        return cls(component_id, component_id, None, tuple(levels))

    @property
    def power_keys(self) -> list[str]:
        return [power_key(self, level) for level in self.levels]


def power_key(component: Component, level: str) -> str:
    """The key of one level's power."""
    if len(component.levels) == 1:
        return component.id
    return f"{component.id}_{level}"


def _levels(control: SpaControl) -> tuple[str, ...]:
    return tuple(option.name.lower() for option in control.options if option.value > 0)


def _control_id(control: SpaControl, kind: str) -> str:
    if kind in NUMBERED:
        return f"{kind}_{(control.index or 0) + 1}"
    return kind


def controls_by_id(client: SpaClient) -> dict[str, SpaControl]:
    """The client's power-drawing controls under our component ids."""
    out: dict[str, SpaControl] = {}
    for kind, controls in (
        ("pump", client.pumps),
        ("blower", client.blowers),
        ("circulation_pump", [c for c in [client.circulation_pump] if c is not None]),
        ("light", client.lights),
        ("aux", client.aux),
        ("mister", client.misters),
    ):
        for control in controls:
            out[_control_id(control, kind)] = control
    return out


def components_from_client(client: SpaClient) -> list[Component]:
    """Every component the spa's configuration lists."""
    components = [Component("heater", "heater", None, ("on",))]
    for component_id, control in controls_by_id(client).items():
        component = Component.from_id(component_id, ("on",))
        if component.kind not in ON_OFF_KINDS:
            component = Component.from_id(component_id, _levels(control) or ("on",))
        components.append(component)
    components.append(Component("standby", "standby", None, ("on",)))
    return sort_components(components)


def sort_components(components: list[Component]) -> list[Component]:
    return sorted(components, key=lambda c: (KINDS.index(c.kind), c.number or 0))


def components_to_data(components: list[Component]) -> dict[str, list[str]]:
    return {c.id: list(c.levels) for c in components}


def components_from_data(data: dict[str, Any]) -> list[Component]:
    return sort_components([Component.from_id(cid, levels) for cid, levels in data.items()])


def levels_from_client(client: SpaClient, components: list[Component]) -> dict[str, str]:
    """The level each component is at now: one of its levels, or ``off``."""
    controls = controls_by_id(client)
    status: bytes | None = getattr(client, "_previous_status", None)
    out: dict[str, str] = {}
    for component in components:
        if component.kind == "heater":
            out[component.id] = "on" if client.heat_state == HeatState.HEATING else OFF
        elif component.kind == "standby":
            out[component.id] = "on"
        elif component.kind == "blower" and status is not None and len(status) > STATUS_BLOWERS:
            out[component.id] = blower_level(status, component)
        elif (control := controls.get(component.id)) is not None:
            out[component.id] = level_of(control, component)
        else:
            out[component.id] = OFF
    return out


#: The status message's byte with the circulation pump (bit 1) and the blowers.
STATUS_BLOWERS = 13


def blower_level(status: bytes, component: Component) -> str:
    """A blower's level, read from the status message itself.

    The blower sits in bits 2-3 of byte 13 (bit 1 is the circulation pump).
    pybalboa 1.1 reads bits 1-2, so a one-speed blower that runs shows as
    unknown there (seen on a BP2100G1 while priming); read it here instead.
    """
    shift = 2 + 2 * ((component.number or 1) - 1)
    value = (status[STATUS_BLOWERS] >> shift) & 0x03
    if value == 0:
        return OFF
    return component.levels[min(value, len(component.levels)) - 1]


def level_of(control: SpaControl, component: Component) -> str:
    state = control.state
    if state.value <= 0:
        return OFF
    name = state.name.lower()
    if name in component.levels:
        return name
    # A state outside the levels the configuration listed: count it as the top one.
    return component.levels[-1]
