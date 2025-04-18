"""Provides the user API for communicating with a NESS alarm."""

import asyncio
import datetime
import logging
from asyncio import CancelledError, sleep
from collections.abc import Callable

from justbackoff import Backoff

from .alarm import Alarm, ArmingMode, ArmingState
from .connection import Connection, IP232Connection, Serial232Connection
from .event import (
    BaseEvent,
    StatusUpdate,
)
from .packet import CommandType, Packet

_LOGGER = logging.getLogger(__name__)


class Client:
    """Main class that contains the user API for communicating with a NESS alarm."""

    connected_count: int
    bad_received_packets: int
    disconnection_count: int
    alarm: Alarm
    _on_event_received: Callable[[BaseEvent], None] | None
    _connection: Connection
    _closed: bool
    _backoff: Backoff
    _connect_lock: asyncio.Lock
    _write_lock: asyncio.Lock
    _last_recv: datetime.datetime | None
    _last_sent_time: datetime.datetime | None
    _update_interval: int
    _requests_awaiting_response: dict[
        StatusUpdate.RequestID, asyncio.Future[StatusUpdate] | None
    ]

    DELAY_SECONDS_BETWEEN_SENDS = 0.2

    USER_INTERFACE_REQUEST_STATUS_UPDATE_DATA_SIZE = 3
    USER_INTERFACE_STATUS_UPDATE_MAX_ID = 18

    def __init__(  # noqa: PLR0913 # Cannot easily reduce argument count on public API
        self,
        *,
        connection: Connection | None = None,
        host: str | None = None,
        port: int | None = None,
        serial_tty: str | None = None,
        update_interval: int = 60,
        infer_arming_state: bool = False,
        alarm: Alarm | None = None,
    ) -> None:
        """
        Create a Ness Client for a specific NESS alarm device.

        Uses specified communicationsconnction details.

        :param update_interval: Frequency (in seconds) to trigger a full state
            refresh
        :param infer_arming_state: Infer the `DISARMED` arming state only via
            system status events. This works around a bug with some panels
            (`<v5.8`) which emit `update.status = []` when they are armed.
        """
        if connection is None:
            if host is not None and port is not None:
                connection = IP232Connection(host=host, port=port)
            elif serial_tty is not None:
                connection = Serial232Connection(tty_path=serial_tty)
            else:
                msg = "Must provide host+port or serial_tty or connection object"
                raise ValueError(msg)

        if alarm is None:
            alarm = Alarm(infer_arming_state=infer_arming_state)

        self.alarm = alarm
        self._on_event_received = None
        self._connection = connection
        self._closed = False
        self._backoff = Backoff()
        self._connect_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        self._last_recv = None
        self._last_sent_time = None
        self._update_interval = update_interval
        self.connected_count = 0
        self.disconnection_count = 0
        self.bad_received_packets = 0

        _LOGGER.debug("Client init() _requests_awaiting_response")
        self._requests_awaiting_response = {}
        for req_id in StatusUpdate.RequestID:
            self._requests_awaiting_response[req_id] = None

    async def arm_away(self, code: str | None = None) -> None:
        """
        Send the 'Arm-away' command to the Ness alarm device.

        :param code: The user code to send
        """
        command = "A{}E".format(code if code else "")
        return await self.send_command(command)

    async def arm_home(self, code: str | None = None) -> None:
        """
        Send the 'Arm-home' command to the Ness alarm device.

        :param code: The user code to send
        """
        command = "H{}E".format(code if code else "")
        return await self.send_command(command)

    async def disarm(self, code: str | None) -> None:
        """
        Send the 'Disarm' command to the Ness alarm device.

        :param code: The user code to send
        """
        command = "{}E".format(code if code else "")
        return await self.send_command(command)

    async def panic(self, code: str | None) -> None:
        """
        Send the 'Panic' command to the Ness alarm device.

        :param code: The user code to send
        """
        command = "*{}E".format(code if code else "")
        return await self.send_command(command)

    async def enter_user_program_mode(self, master_code: str | None = "123") -> None:
        """
        Switch to 'user-program' mode.

        :param master_code: The master code for the alarm
                            (User-code 1) (Factory default '123')
        """
        command = "M{}E".format(master_code if master_code else "")
        return await self.send_command(command)

    async def enter_installer_program_mode(
        self, installer_code: str | None = "000000"
    ) -> None:
        """
        Switch to 'installer-program' mode.

        :param installer_code: The installer code for the alarm
                               (Factory default '000000')
        """
        command = "M{}E".format(installer_code if installer_code else "")
        return await self.send_command(command)

    async def exit_program_mode(self) -> None:
        """
        Exit user-program or installer-program mode.

        Switches to operating mode
        """
        command = "ME"
        return await self.send_command(command)

    async def aux(self, output_id: int, *, state: bool = True) -> None:
        """
        Set one of the auxilliary outputs.

        :param output_id: Which aux output to change.
                          (1, 2, 3, or 4)
        :param state: if true, set aux active, otherwise inactive
        """
        command = "{}{}{}".format(output_id, output_id, "*" if state else "#")
        return await self.send_command(command)

    async def update(self) -> None:
        """Force update of alarm status and zones."""
        _LOGGER.debug("Requesting state update from server (S00, S05, S14)")
        await asyncio.gather(
            # S00 : List unsealed Zones
            self.send_command("S00"),
            # S01 : List radio unsealed zones
            # S02 : List Cbus unsealed zones
            # S03 : List zones in delay
            # S04 : List zones in double trigger
            # S05 : List zones currently Alarming
            self.send_command("S05"),
            # S06 : List excluded zones
            # S07 : List auto-excluded zones
            # S08 : List zones with supervision-fail pending
            # S09 : List zones with supervision-fail
            # S10 : List zones with doors open
            # S11 : List zones with detector low battery
            # S12 : List zones with detector tamper
            # S13 : List miscellaneous alarms
            # S14 : Arming status update
            self.send_command("S14"),
            # S15 : List output states
            # S16 : Get View State
            # S17 : Get Firmware Version
            # S18 : List auxilliary output states
        )

    async def _connect(self) -> None:
        _LOGGER.debug("_connect() - Doing _connect()")
        async with self._connect_lock:
            if self._should_reconnect():
                _LOGGER.debug("_connect() - Closing stale connection and reconnecting")
                await self._connection.close()

            while not self._connection.connected:
                _LOGGER.debug("_connect() - Attempting to connect")
                try:
                    await self._connection.connect()
                    self.connected_count += 1
                    _LOGGER.debug("_connect() - connected")
                    self._last_recv = datetime.datetime.now()  # noqa: DTZ005 - local timezone - No function available

                except (ConnectionRefusedError, OSError) as e:
                    _LOGGER.warning(
                        "Failed to connect: %s - sleeping backoff %s",
                        e,
                        self._backoff.duration(),
                    )
                    try:
                        await sleep(self._backoff.duration())
                    except asyncio.CancelledError as e:
                        # Cancelled - closing
                        _LOGGER.debug("Ignoring exception during closing : %s", e)

            self._backoff.reset()
        _LOGGER.debug("_connect() - unlocked")

    async def send_command(
        self,
        command: str,
        address: int = 0,
        finished_future: asyncio.Future[StatusUpdate] | None = None,
    ) -> None:
        """
        Send a command to the NESS alarm.

        Commands are strings containing either
        * Keypad entry sequences
        * Status update requests
        """
        # The spec requires thtatInput Commands must use:
        # Start byte: 0x83
        # Command byte: 0x60
        # One-character Address only (different to Output Commands)
        # No timestamp
        #
        packet = Packet(
            address=address & 0xF,
            command=CommandType.USER_INTERFACE,
            data=command,
            timestamp=None,
            has_delay_marker=True,
        )

        # Check if this is a Status Update Request
        is_status_request = (
            (len(command) == Client.USER_INTERFACE_REQUEST_STATUS_UPDATE_DATA_SIZE)
            and (command[0] == "S")
            and (command[1:].isnumeric())
            and (int(command[1:]) <= Client.USER_INTERFACE_STATUS_UPDATE_MAX_ID)
        )
        if is_status_request and finished_future is not None:
            # Look up list of existing requests awaiting responses
            req_id = StatusUpdate.RequestID(int(command[1:]))
            current = self._requests_awaiting_response[req_id]
            if current is not None:
                _LOGGER.debug("cancelling existing %s", current)
                current.cancel()
            _LOGGER.debug(
                "send_command Adding future %s for %s", finished_future, req_id
            )
            self._requests_awaiting_response[req_id] = finished_future
            _LOGGER.debug(
                "send_command added future %s", self._requests_awaiting_response
            )

        _LOGGER.debug("send_command() connecting")
        async with self._write_lock:
            await self._connect()
            payload = packet.encode()

            # Check if a delay is needed to avoid overwhelming the Ness Alarm
            now = datetime.datetime.now()  # noqa: DTZ005 - local timezone - No function available
            if self._last_sent_time is not None:
                time_since_last_send_delta: datetime.timedelta = (
                    now - self._last_sent_time
                )
                time_since_last_send: float = time_since_last_send_delta.total_seconds()
                _LOGGER.debug("time_since_last_send = %s", time_since_last_send)
                if time_since_last_send < Client.DELAY_SECONDS_BETWEEN_SENDS:
                    sleep_time = (
                        Client.DELAY_SECONDS_BETWEEN_SENDS - time_since_last_send
                    )
                    _LOGGER.debug("sleeping for %s seconds from %s", sleep_time, now)
                    await asyncio.sleep(sleep_time)
                    now = datetime.datetime.now()  # noqa: DTZ005 - local timezone - No function available
                    _LOGGER.debug("time after sleep %s", now)

            _LOGGER.debug("Sending packet: %s", packet)
            _LOGGER.debug("send_command() - Sending payload: %s", payload)

            self._last_sent_time = now
            return await self._connection.write(payload.encode("ascii"))

    async def request_and_wait_status_update(
        self, req_id: StatusUpdate.RequestID, address: int = 0, retries: int = 3
    ) -> StatusUpdate | None:
        """Send a Status Update Request and wait for a response."""
        while retries > 0:
            try:
                f: asyncio.Future[StatusUpdate] = asyncio.Future()
                _LOGGER.debug("Adding future %s for %s", f, req_id)
                await self.send_command(
                    f"S{req_id.value:02}", address=address, finished_future=f
                )

                await asyncio.wait_for(f, 2.0)
                _LOGGER.debug("Finished waiting for status response: %s", f)
                if f.done():
                    return f.result()
            except (asyncio.exceptions.TimeoutError, CancelledError):
                _LOGGER.warning(
                    "Timed out waiting for response to Status Request: %s", req_id
                )

            retries -= 1
            _LOGGER.warning(
                "retrying request_and_wait_status_update - retries remaining:%s",
                retries,
            )

        return None

    async def _recv_loop(self) -> None:  # noqa: PLR0912 # No easy way to reduce branch count
        while not self._closed:
            _LOGGER.debug("_recv_loop() - connecting - closed=%s", self._closed)
            await self._connect()
            _LOGGER.debug("_recv_loop() - connected")

            while True:
                _LOGGER.debug("_recv_loop() - reading")
                data = await self._connection.read()
                _LOGGER.debug("_recv_loop() - read got %s", data)
                if data is None:
                    self.disconnection_count += 1
                    _LOGGER.debug("Received None data from connection.read()")
                    break

                self._process_received_data(data)

    def _process_received_data(self, data: bytes) -> None:
        """Process a received packet."""
        self._last_recv = datetime.datetime.now()  # noqa: DTZ005 - local timezone - No function available
        try:
            decoded_data = data.decode("ascii")
        except UnicodeDecodeError:
            self.bad_received_packets += 1
            _LOGGER.warning("Failed to decode data : %s", data, exc_info=True)
            return

        _LOGGER.debug("Decoding data: '%s'", decoded_data)
        if len(decoded_data) > 0:
            try:
                pkt = Packet.decode(decoded_data)
                event = BaseEvent.decode(pkt)
            except ValueError:
                self.bad_received_packets += 1
                _LOGGER.warning("Failed to decode packet", exc_info=True)
                return
            except RuntimeError:
                _LOGGER.exception("Error whilst decoding packet")
                return

            _LOGGER.debug("Decoded event: %s", event)
            # Check if the received packet is a response to a Status Update
            #  Request which is awaiting the response
            if isinstance(event, StatusUpdate):
                f = self._requests_awaiting_response[event.request_id]
                if f is not None:
                    _LOGGER.debug("Waiter for %s :  %s", event, f)
                    try:
                        f.set_result(event)
                    except asyncio.exceptions.InvalidStateError as e:
                        _LOGGER.info("Waiter already set for %s : %s", f, e)
                    self._requests_awaiting_response[event.request_id] = None
                else:
                    _LOGGER.debug("No waiter %s", self._requests_awaiting_response)
            else:
                _LOGGER.debug("Not StatusUpdate: %s", type(event))

            if self._on_event_received is not None:
                self._on_event_received(event)

            self.alarm.handle_event(event)

    def _should_reconnect(self) -> bool:
        now = datetime.datetime.now()  # noqa: DTZ005 - local timezone - No function available
        _LOGGER.debug("now=%s last_recv=%s", now, self._last_recv)
        reconnect_time = now - datetime.timedelta(seconds=self._update_interval + 30)
        return self._last_recv is not None and self._last_recv < reconnect_time

    async def _update_loop(self) -> None:
        """Schedule a state update to keep the connection alive."""
        _LOGGER.debug("_update_loop sleeping for %s", self._update_interval)
        await asyncio.sleep(self._update_interval)
        while not self._closed:
            await self.update()
            _LOGGER.debug("_update_loop sleeping for %s", self._update_interval)
            await asyncio.sleep(self._update_interval)

    async def keepalive(self) -> None:
        """
        Run the long-running receive and update loops.

        This will run until Client.close() or asyncio_task.cancel() is called.
        """
        _LOGGER.debug("keepalive start")
        await asyncio.gather(
            self._recv_loop(),
            self._update_loop(),
        )
        _LOGGER.debug("keepalive end")

    async def close(self) -> None:
        """
        Stop the nessclient.

        Closes comms connection and stops receive and update loops.
        """
        _LOGGER.debug("Closing Client")
        self._closed = True
        await self._connection.close()

    def on_state_change(
        self, f: Callable[[ArmingState, ArmingMode | None], None] | None
    ) -> Callable[[ArmingState, ArmingMode | None], None] | None:
        """
        Provide a decorator @client.on_state_change for alarm state-change handlers.

        Can also be called directly to set the state-change handler
        """
        self.alarm.on_state_change(f)
        return f

    def on_zone_change(
        self, f: Callable[[int, bool], None] | None
    ) -> Callable[[int, bool], None] | None:
        """
        Provide a decorator @client.on_zone_change for alarm zone-sealed handlers.

        Can also be called directly to set the zone-sealed handler
        """
        self.alarm.on_zone_change(f)
        return f

    def on_event_received(
        self, f: Callable[[BaseEvent], None] | None
    ) -> Callable[[BaseEvent], None] | None:
        """
        Provide a decorator @client.on_event_received for alarm general event handler.

        Can also be called directly to set the general event handler
        """
        self._on_event_received = f
        return f
