import asyncio
import datetime
import logging
from asyncio import sleep
from typing import Optional, Callable

from justbackoff import Backoff

from .alarm import ArmingState, Alarm, ArmingMode
from .connection import Connection, IP232Connection, Serial232Connection
from .event import BaseEvent, StatusUpdate
from .packet import CommandType, Packet

_LOGGER = logging.getLogger(__name__)


class Client:
    """
    :param update_interval: Frequency (in seconds) to trigger a full state
        refresh
    :param infer_arming_state: Infer the `DISARMED` arming state only via
        system status events. This works around a bug with some panels
        (`<v5.8`) which emit `update.status = []` when they are armed.
    """

    connected_count: int
    bad_received_packets: int
    disconnection_count: int

    def __init__(
        self,
        connection: Optional[Connection] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        serial_tty: Optional[str] = None,
        update_interval: int = 60,
        infer_arming_state: bool = False,
        alarm: Optional[Alarm] = None,
    ):
        if connection is None:
            if host is not None and port is not None:
                connection = IP232Connection(host=host, port=port)
            elif serial_tty is not None:
                connection = Serial232Connection(tty_path=serial_tty)
            else:
                raise ValueError(
                    "Must provide host+port or serial_tty or connection object"
                )

        if alarm is None:
            alarm = Alarm(infer_arming_state=infer_arming_state)

        self.alarm = alarm
        self._on_event_received: Optional[Callable[[BaseEvent], None]] = None
        self._connection = connection
        self._closed = False
        self._backoff = Backoff()
        self._connect_lock = asyncio.Lock()
        self._last_recv: Optional[datetime.datetime] = None
        self._update_interval = update_interval
        self._awaited_status_updates: list[
            tuple[StatusUpdate.RequestID, asyncio.Future[StatusUpdate]]
        ] = []
        self.connected_count = 0
        self.disconnection_count = 0
        self.bad_received_packets = 0

    async def arm_away(self, code: Optional[str] = None) -> None:
        command = "A{}E".format(code if code else "")
        return await self.send_command(command)

    async def arm_home(self, code: Optional[str] = None) -> None:
        command = "H{}E".format(code if code else "")
        return await self.send_command(command)

    async def disarm(self, code: str) -> None:
        command = "{}E".format(code)
        return await self.send_command(command)

    async def panic(self, code: str) -> None:
        command = "*{}E".format(code)
        return await self.send_command(command)

    async def enter_user_program_mode(self, master_code: str = "123") -> None:
        command = f"M{master_code}E"
        return await self.send_command(command)

    async def enter_installer_program_mode(
        self, installer_code: str = "000000"
    ) -> None:
        command = f"M{installer_code}E"
        return await self.send_command(command)

    async def exit_program_mode(self) -> None:
        command = "ME"
        return await self.send_command(command)

    async def aux(self, output_id: int, state: bool = True) -> None:
        command = "{}{}{}".format(output_id, output_id, "*" if state else "#")
        return await self.send_command(command)

    async def update(self) -> None:
        """Force update of alarm status and zones"""
        _LOGGER.debug("Requesting state update from server (S00, S14)")
        await asyncio.gather(
            # List unsealed Zones
            self.send_command("S00"),
            # Arming status update
            self.send_command("S14"),
            # List unsealed Zones
            # self.send_command("S00"),
            # self.send_command("S01"),
            # self.send_command("S02"),
            # self.send_command("S03"),
            # self.send_command("S04"),
            # self.send_command("S05"),
            # self.send_command("S06"),
            # self.send_command("S07"),
            # self.send_command("S08"),
            # self.send_command("S09"),
            # self.send_command("S10"),
            # self.send_command("S11"),
            # self.send_command("S12"),
            # self.send_command("S13"),
            # self.send_command("S14"),
            # self.send_command("S15"),
            # self.send_command("S16"),
            # self.send_command("S17"),
            # self.send_command("S18"),
            # Arming status update
            # self.send_command("S14"),
        )

    async def _connect(self) -> None:
        _LOGGER.debug("_connect() - Doing _connect()")
        async with self._connect_lock:
            if self._should_reconnect():
                _LOGGER.debug("_connect() - Closing stale connection and reconnecting")
                await self._connection.close()

            # was_closed = self._connection.connected
            while not self._connection.connected:
                _LOGGER.debug("_connect() - Attempting to connect")
                try:
                    await self._connection.connect()
                    self.connected_count += 1
                    _LOGGER.debug("_connect() - connected")
                    self._last_recv = datetime.datetime.now()
                except (ConnectionRefusedError, OSError) as e:
                    _LOGGER.warning(
                        f"Failed to connect: {e} - "
                        f"sleeping backoff {self._backoff.duration()}"
                    )
                    try:
                        await sleep(self._backoff.duration())
                    except asyncio.CancelledError:
                        pass  # cancelled = closing

            self._backoff.reset()
        _LOGGER.debug("_connect() - unlocked")

    async def send_command(self, command: str, address: int = 0) -> None:
        # Input Commands must use:
        # Start byte: 0x83
        # Command byte: 0x60
        # One-character Address only (different to Output Commands)
        # No timestamp
        #
        packet = Packet(
            address=address & 0xF,
            seq=0x00,  # TODO: sequence should be alternating
            command=CommandType.USER_INTERFACE,
            data=command,
            timestamp=None,
            has_delay_marker=True,
        )
        _LOGGER.debug("send_command() connecting")
        await self._connect()
        payload = packet.encode()
        _LOGGER.debug(f"Sending packet: {packet}")
        _LOGGER.debug(f"send_command() - Sending payload: {payload}")
        # _LOGGER.debug(f"XXX: {Packet.decode(payload)}")
        return await self._connection.write(payload.encode("ascii"))

    async def _recv_loop(self) -> None:
        while not self._closed:
            _LOGGER.debug(f"_recv_loop() - connecting - closed={self._closed}")
            await self._connect()
            _LOGGER.debug("_recv_loop() - connected")

            while True:
                _LOGGER.debug("_recv_loop() - reading")
                data = await self._connection.read()
                _LOGGER.debug(f"_recv_loop() - read got {data!r}")
                print(f"_recv_loop() - read got {data!r}")
                if data is None:
                    self.disconnection_count += 1
                    _LOGGER.debug("Received None data from connection.read()")
                    break

                self._last_recv = datetime.datetime.now()
                try:
                    decoded_data = data.decode("ascii")
                except UnicodeDecodeError:
                    self.bad_received_packets += 1
                    _LOGGER.warning("Failed to decode data", exc_info=True)
                    continue

                _LOGGER.debug("Decoding data: '%s'", decoded_data)
                if len(decoded_data) > 0:
                    try:
                        pkt = Packet.decode(decoded_data)
                        event = BaseEvent.decode(pkt)
                    except Exception:
                        self.bad_received_packets += 1
                        _LOGGER.warning("Failed to decode packet", exc_info=True)
                        continue

                    if self._on_event_received is not None:
                        self._on_event_received(event)

                    self.alarm.handle_event(event)

    def _should_reconnect(self) -> bool:
        now = datetime.datetime.now()
        _LOGGER.debug(f"now={now} last_recv={self._last_recv}")
        return (
            self._last_recv is not None
            and self._last_recv
            < now - datetime.timedelta(seconds=self._update_interval + 30)
        )

    async def _update_loop(self) -> None:
        """Schedule a state update to keep the connection alive"""
        _LOGGER.debug(f"_update_loop sleeping for {self._update_interval}")
        await asyncio.sleep(self._update_interval)
        while not self._closed:
            await self.update()
            _LOGGER.debug(f"_update_loop sleeping for {self._update_interval}")
            await asyncio.sleep(self._update_interval)

    async def keepalive(self) -> None:
        _LOGGER.debug("keepalive start")
        await asyncio.gather(
            self._recv_loop(),
            self._update_loop(),
        )
        _LOGGER.debug("keepalive end")

    async def close(self) -> None:
        _LOGGER.debug("Closing Client")
        self._closed = True
        await self._connection.close()

    def on_state_change(
        self, f: Optional[Callable[[ArmingState, ArmingMode | None], None]]
    ) -> Optional[Callable[[ArmingState, ArmingMode | None], None]]:
        self.alarm.on_state_change(f)
        return f

    def on_zone_change(
        self, f: Optional[Callable[[int, bool], None]]
    ) -> Optional[Callable[[int, bool], None]]:
        self.alarm.on_zone_change(f)
        return f

    def on_event_received(
        self, f: Optional[Callable[[BaseEvent], None]]
    ) -> Optional[Callable[[BaseEvent], None]]:
        self._on_event_received = f
        return f
