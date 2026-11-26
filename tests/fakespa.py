"""A stand-in for a BWA Wi-Fi module with a spa behind it, speaking its TCP protocol.

Built after the BP2100G1 this integration was written for (2026-11-26):
a two-speed pump 1, a one-speed pump 2, one blower, one light, no
circulation pump, Celsius, 24-hour clock. Like the real module it takes one
client at a time (a second one is closed straight away) and pushes a status
message on a timer; it answers the configuration requests pybalboa sends and
acts on toggles, set temperature, set time and filter cycle messages.

The frames are built the way pybalboa reads them (utils.read_one_message):
``~ len channel 0xAF type payload checksum ~``, len counting itself, the
three header bytes, the payload and the checksum.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field

from pybalboa.utils import calculate_checksum, read_one_message

MAC = bytes.fromhex("001527aabbcc")
MODEL = b"BP2100G1"

MT_DEVICE_PRESENT = 0x04
MT_TOGGLE = 0x11
MT_STATUS = 0x13
MT_SET_TEMPERATURE = 0x20
MT_SET_TIME = 0x21
MT_REQUEST = 0x22
MT_FILTER_CYCLE = 0x23
MT_SYSTEM_INFORMATION = 0x24
MT_SETUP_PARAMETERS = 0x25
MT_FAULT_LOG = 0x28
MT_DEVICE_CONFIGURATION = 0x2E
MT_MODULE_IDENTIFICATION = 0x94


def frame(message_type: int, payload: bytes | list[int]) -> bytes:
    data = bytes([5 + len(payload), 0xFF, 0xAF, message_type]) + bytes(payload)
    return b"~" + data + bytes([calculate_checksum(data)]) + b"~"


def as_read(message: bytes) -> bytes:
    """A frame as read_one_message hands it on: without the two ``~``."""
    return message[1:-1]


@dataclass
class SpaState:
    temperature: float = 12.0  # °C
    target: float = 12.0
    hour: int = 4
    minute: int = 8
    heat_mode: int = 0  # 0 ready, 1 rest
    high_range: bool = False
    heat_state: int = 0  # 0 off, 1 heating, 2 waiting
    pumps: list[int] = field(default_factory=lambda: [0, 0])
    pump_states: tuple[int, ...] = (3, 2)  # off/low/high, off/on
    blower: int = 0
    light: bool = False
    filter_1_running: bool = False
    filter_2_running: bool = False
    filter_cycles: list[int] = field(default_factory=lambda: [0, 0, 0, 45, 4, 0, 0, 30])
    fault: list[int] = field(default_factory=lambda: [3, 2, 19, 1, 12, 0, 0, 24, 24, 24])


def module_identification() -> bytes:
    return bytes([0, 0, 0]) + MAC + bytes(range(16))


def system_information() -> bytes:
    return bytes([100, 220, 6, 0]) + MODEL + bytes([1]) + bytes.fromhex("4d1c4a0b") + bytes([1, 0x0A, 0, 0])


def setup_parameters() -> bytes:
    # low range 50..99 °F, high range 80..104 °F, two pumps
    return bytes([0x0C, 0x14, 50, 99, 80, 104, 0, 0b11, 0])


def device_configuration(state: SpaState) -> bytes:
    pumps = 0
    for i, states in enumerate(state.pump_states):
        pumps |= (states - 1) << (2 * i)
    return bytes([pumps, 0x00, 0x01, 0x01, 0x00, 0x00])


def status(state: SpaState) -> bytes:
    data = bytearray(24)
    data[0] = 0x00
    data[2] = round(state.temperature * 2)
    data[3] = state.hour
    data[4] = state.minute
    data[5] = state.heat_mode
    data[9] = 0x01 | 0x02 | (0x04 if state.filter_1_running else 0) | (0x08 if state.filter_2_running else 0)
    data[10] = (0x04 if state.high_range else 0) | (state.heat_state << 4)
    for i, level in enumerate(state.pumps):
        data[11] |= level << (2 * i)
    # Blower 1 in bits 2-3, as the protocol has it (pybalboa reads bits 1-2).
    data[13] = state.blower << 2
    data[14] = 0x03 if state.light else 0x00
    data[20] = round(state.target * 2)
    return bytes(data)


class FakeSpa:
    """The module: a TCP server on 127.0.0.1 with one spa behind it."""

    def __init__(self, interval: float = 0.25) -> None:
        self.state = SpaState()
        self.interval = interval
        self.port = 0
        self.received: list[tuple[int, bytes]] = []
        self.refused = 0
        self.connections = 0
        self._writer: asyncio.StreamWriter | None = None
        self._server: asyncio.base_events.Server | None = None
        self._pusher: asyncio.Task | None = None

    async def start(self, port: int = 0) -> None:
        self._server = await asyncio.start_server(self._client, "127.0.0.1", port)
        self.port = self._server.sockets[0].getsockname()[1]
        self._pusher = asyncio.create_task(self._push())

    async def stop(self) -> None:
        if self._pusher:
            self._pusher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._pusher
        if self._writer is not None:
            self._writer.close()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    @property
    def connected(self) -> bool:
        return self._writer is not None

    def send(self, message_type: int, payload: bytes) -> None:
        if self._writer is not None:
            self._writer.write(frame(message_type, payload))

    async def _push(self) -> None:
        while True:
            self.send(MT_STATUS, status(self.state))
            await asyncio.sleep(self.interval)

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        # One client at a time. A client that has just left may not have been
        # noticed yet, so give it a moment before turning the new one away.
        for _ in range(20):
            if self._writer is None:
                break
            await asyncio.sleep(0.1)
        if self._writer is not None:
            self.refused += 1
            writer.close()
            return
        self.connections += 1
        self._writer = writer
        try:
            while True:
                try:
                    data = await read_one_message(reader, 3600)
                except asyncio.IncompleteReadError:
                    break
                self._handle(data[3], bytes(data[4:-1]))
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            if self._writer is writer:
                self._writer = None
            writer.close()

    def _handle(self, message_type: int, payload: bytes) -> None:
        self.received.append((message_type, payload))
        s = self.state
        if message_type == MT_DEVICE_PRESENT:
            self.send(MT_MODULE_IDENTIFICATION, module_identification())
        elif message_type == MT_REQUEST:
            code = payload[0]
            if code == 0x00:
                self.send(MT_DEVICE_CONFIGURATION, device_configuration(s))
            elif code == 0x01:
                self.send(MT_FILTER_CYCLE, bytes(s.filter_cycles))
            elif code == 0x02:
                self.send(MT_SYSTEM_INFORMATION, system_information())
            elif code == 0x04:
                self.send(MT_SETUP_PARAMETERS, setup_parameters())
            elif code == 0x20:
                self.send(MT_FAULT_LOG, bytes(s.fault))
        elif message_type == MT_TOGGLE:
            self.toggle(payload[0])
        elif message_type == MT_SET_TEMPERATURE:
            s.target = payload[0] / 2
        elif message_type == MT_SET_TIME:
            s.hour, s.minute = payload[0] & 0x7F, payload[1]
        elif message_type == MT_FILTER_CYCLE:
            s.filter_cycles = list(payload[:8])

    def toggle(self, item: int) -> None:
        s = self.state
        if 0x04 <= item < 0x04 + len(s.pumps):
            i = item - 0x04
            s.pumps[i] = (s.pumps[i] + 1) % s.pump_states[i]
        elif item == 0x0C:
            s.blower = (s.blower + 1) % 2
        elif item == 0x11:
            s.light = not s.light
        elif item == 0x51:
            s.heat_mode = 0 if s.heat_mode else 1
        elif item == 0x50:
            s.high_range = not s.high_range


def loaded_client():
    """A pybalboa SpaClient that has read the whole configuration and one status."""
    from pybalboa import SpaClient

    client = SpaClient("fake")
    state = SpaState()
    feed(client, MT_MODULE_IDENTIFICATION, module_identification())
    feed(client, MT_SYSTEM_INFORMATION, system_information())
    feed(client, MT_SETUP_PARAMETERS, setup_parameters())
    feed(client, MT_DEVICE_CONFIGURATION, device_configuration(state))
    feed(client, MT_FILTER_CYCLE, bytes(state.filter_cycles))
    feed(client, MT_STATUS, status(state))
    assert client.configuration_loaded
    return client, state


def feed(client, message_type: int, payload: bytes) -> None:
    client._process_message(as_read(frame(message_type, payload)))
