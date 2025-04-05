import asyncio
import datetime
import logging
from asyncio import CancelledError, sleep
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import cast

from justbackoff import Backoff

from .alarm import Alarm, ArmingMode, ArmingState, ZoneSealedState
from .connection import Connection, IP232Connection, Serial232Connection
from .event import (
    ArmingUpdate,
    AuxiliaryOutputsUpdate,
    BaseEvent,
    MiscellaneousAlarmsUpdate,
    OutputsUpdate,
    PanelVersionUpdate,
    StatusUpdate,
    ViewStateUpdate,
    ZoneUpdate,
)
from .packet import CommandType, Packet

_LOGGER = logging.getLogger(__name__)


@dataclass
class ZoneStatus:
    InputUnsealed: bool
    RadioUnsealed: bool
    CbusUnsealed: bool
    InDelay: bool
    InDoubleTrigger: bool
    InAlarm: bool
    Excluded: bool
    AutoExcluded: bool
    SupervisionFailPending: bool
    SupervsionFail: bool
    DoorsOpen: bool
    DetectorLowBattery: bool
    DetectorTamper: bool


@dataclass
class AllStatus:
    Zones: list[ZoneStatus]
    MiscellaneousAlarms: MiscellaneousAlarmsUpdate | None
    Arming: ArmingUpdate | None
    Outputs: OutputsUpdate | None
    ViewState: ViewStateUpdate | None
    PanelVersion: PanelVersionUpdate | None
    AuxiliaryOutputs: AuxiliaryOutputsUpdate | None


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

    class AuxState(Enum):
        """Auxiliary output states - either active or inactive."""

        INACTIVE = False
        ACTIVE = True

    def __init__(
        self,
        connection: Connection | None = None,
        host: str | None = None,
        port: int | None = None,
        serial_tty: str | None = None,
        update_interval: int = 60,
        infer_arming_state: bool = False,
        alarm: Alarm | None = None,
    ):
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

    async def aux(self, output_id: int, state: AuxState = AuxState.ACTIVE) -> None:
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
            # List unsealed Zones
            self.send_command("S00"),
            # List Zones currently Alarming
            self.send_command("S05"),
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

    async def update_wait(self) -> (list[bool],):
        """Force update of ZoneInputUnsealed status and Arming Status"""
        _LOGGER.debug("Requesting state update from server (S00, S14)")
        (
            zone_input_unsealed,
            arming,
        ) = await asyncio.gather(
            # List unsealed Zones
            self.request_and_wait_status_update(
                StatusUpdate.RequestID.ZONE_INPUT_UNSEALED
            ),
            self.request_and_wait_status_update(StatusUpdate.RequestID.ARMING),
        )
        zones: list[ZoneStatus] = []
        for z in ZoneUpdate.Zone:
            zones.append(
                ZoneStatus(
                    InputUnsealed=zone_input_unsealed is not None
                    and (z in cast(ZoneUpdate, zone_input_unsealed).included_zones),
                    RadioUnsealed=zone_radio_unsealed is not None
                    and (z in cast(ZoneUpdate, zone_radio_unsealed).included_zones),
                    CbusUnsealed=zone_cbus_unsealed is not None
                    and (z in cast(ZoneUpdate, zone_cbus_unsealed).included_zones),
                    InDelay=zone_radio_unsealed is not None
                    and (z in cast(ZoneUpdate, zone_in_delay).included_zones),
                    InDoubleTrigger=zone_in_double_trigger is not None
                    and (z in cast(ZoneUpdate, zone_in_double_trigger).included_zones),
                    InAlarm=zone_in_alarm is not None
                    and (z in cast(ZoneUpdate, zone_in_alarm).included_zones),
                    Excluded=zone_excluded is not None
                    and (z in cast(ZoneUpdate, zone_excluded).included_zones),
                    AutoExcluded=zone_auto_excluded is not None
                    and (z in cast(ZoneUpdate, zone_auto_excluded).included_zones),
                    SupervisionFailPending=zone_supervision_fail_pending is not None
                    and (
                        z
                        in cast(
                            ZoneUpdate, zone_supervision_fail_pending
                        ).included_zones
                    ),
                    SupervsionFail=zone_supervision_fail is not None
                    and (z in cast(ZoneUpdate, zone_supervision_fail).included_zones),
                    DoorsOpen=zone_doors_open is not None
                    and (z in cast(ZoneUpdate, zone_doors_open).included_zones),
                    DetectorLowBattery=zone_detector_low_battery is not None
                    and (
                        z in cast(ZoneUpdate, zone_detector_low_battery).included_zones
                    ),
                    DetectorTamper=zone_detector_tamper is not None
                    and (z in cast(ZoneUpdate, zone_detector_tamper).included_zones),
                )
            )

        return AllStatus(
            Zones=zones,
            MiscellaneousAlarms=cast(
                MiscellaneousAlarmsUpdate | None, miscellaneous_alarms
            ),
            Arming=cast(ArmingUpdate | None, arming),
            Outputs=cast(OutputsUpdate | None, outputs),
            ViewState=cast(ViewStateUpdate | None, view_state),
            PanelVersion=cast(PanelVersionUpdate | None, panel_version),
            AuxiliaryOutputs=cast(AuxiliaryOutputsUpdate | None, auxiliary_outputs),
        )

    async def update_all_wait(self) -> AllStatus:
        """Force update of alarm status and zones"""
        _LOGGER.debug("Requesting state update from server (S00, S14)")
        (
            zone_input_unsealed,
            zone_radio_unsealed,
            zone_cbus_unsealed,
            zone_in_delay,
            zone_in_double_trigger,
            zone_in_alarm,
            zone_excluded,
            zone_auto_excluded,
            zone_supervision_fail_pending,
            zone_supervision_fail,
            zone_doors_open,
            zone_detector_low_battery,
            zone_detector_tamper,
            miscellaneous_alarms,
            arming,
            outputs,
            view_state,
            panel_version,
            auxiliary_outputs,
        ) = await asyncio.gather(
            # List unsealed Zones
            self.request_and_wait_status_update(
                StatusUpdate.RequestID.ZONE_INPUT_UNSEALED
            ),
            self.request_and_wait_status_update(
                StatusUpdate.RequestID.ZONE_RADIO_UNSEALED
            ),
            self.request_and_wait_status_update(
                StatusUpdate.RequestID.ZONE_CBUS_UNSEALED
            ),
            self.request_and_wait_status_update(StatusUpdate.RequestID.ZONE_IN_DELAY),
            self.request_and_wait_status_update(
                StatusUpdate.RequestID.ZONE_IN_DOUBLE_TRIGGER
            ),
            self.request_and_wait_status_update(StatusUpdate.RequestID.ZONE_IN_ALARM),
            self.request_and_wait_status_update(StatusUpdate.RequestID.ZONE_EXCLUDED),
            self.request_and_wait_status_update(
                StatusUpdate.RequestID.ZONE_AUTO_EXCLUDED
            ),
            self.request_and_wait_status_update(
                StatusUpdate.RequestID.ZONE_SUPERVISION_FAIL_PENDING
            ),
            self.request_and_wait_status_update(
                StatusUpdate.RequestID.ZONE_SUPERVISION_FAIL
            ),
            self.request_and_wait_status_update(StatusUpdate.RequestID.ZONE_DOORS_OPEN),
            self.request_and_wait_status_update(
                StatusUpdate.RequestID.ZONE_DETECTOR_LOW_BATTERY
            ),
            self.request_and_wait_status_update(
                StatusUpdate.RequestID.ZONE_DETECTOR_TAMPER
            ),
            self.request_and_wait_status_update(
                StatusUpdate.RequestID.MISCELLANEOUS_ALARMS
            ),
            self.request_and_wait_status_update(StatusUpdate.RequestID.ARMING),
            self.request_and_wait_status_update(StatusUpdate.RequestID.OUTPUTS),
            self.request_and_wait_status_update(StatusUpdate.RequestID.VIEW_STATE),
            self.request_and_wait_status_update(StatusUpdate.RequestID.PANEL_VERSION),
            self.request_and_wait_status_update(
                StatusUpdate.RequestID.AUXILIARY_OUTPUTS
            ),
        )
        zones: list[ZoneStatus] = []
        for z in ZoneUpdate.Zone:
            zones.append(
                ZoneStatus(
                    InputUnsealed=zone_input_unsealed is not None
                    and (z in cast(ZoneUpdate, zone_input_unsealed).included_zones),
                    RadioUnsealed=zone_radio_unsealed is not None
                    and (z in cast(ZoneUpdate, zone_radio_unsealed).included_zones),
                    CbusUnsealed=zone_cbus_unsealed is not None
                    and (z in cast(ZoneUpdate, zone_cbus_unsealed).included_zones),
                    InDelay=zone_radio_unsealed is not None
                    and (z in cast(ZoneUpdate, zone_in_delay).included_zones),
                    InDoubleTrigger=zone_in_double_trigger is not None
                    and (z in cast(ZoneUpdate, zone_in_double_trigger).included_zones),
                    InAlarm=zone_in_alarm is not None
                    and (z in cast(ZoneUpdate, zone_in_alarm).included_zones),
                    Excluded=zone_excluded is not None
                    and (z in cast(ZoneUpdate, zone_excluded).included_zones),
                    AutoExcluded=zone_auto_excluded is not None
                    and (z in cast(ZoneUpdate, zone_auto_excluded).included_zones),
                    SupervisionFailPending=zone_supervision_fail_pending is not None
                    and (
                        z
                        in cast(
                            ZoneUpdate, zone_supervision_fail_pending
                        ).included_zones
                    ),
                    SupervsionFail=zone_supervision_fail is not None
                    and (z in cast(ZoneUpdate, zone_supervision_fail).included_zones),
                    DoorsOpen=zone_doors_open is not None
                    and (z in cast(ZoneUpdate, zone_doors_open).included_zones),
                    DetectorLowBattery=zone_detector_low_battery is not None
                    and (
                        z in cast(ZoneUpdate, zone_detector_low_battery).included_zones
                    ),
                    DetectorTamper=zone_detector_tamper is not None
                    and (z in cast(ZoneUpdate, zone_detector_tamper).included_zones),
                )
            )

        return AllStatus(
            Zones=zones,
            MiscellaneousAlarms=cast(
                MiscellaneousAlarmsUpdate | None, miscellaneous_alarms
            ),
            Arming=cast(ArmingUpdate | None, arming),
            Outputs=cast(OutputsUpdate | None, outputs),
            ViewState=cast(ViewStateUpdate | None, view_state),
            PanelVersion=cast(PanelVersionUpdate | None, panel_version),
            AuxiliaryOutputs=cast(AuxiliaryOutputsUpdate | None, auxiliary_outputs),
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
                    self._last_recv = datetime.datetime.now(tz=datetime.UTC)
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

        # Check if this is a Status Update Request
        is_status_request = (
            (len(command) == 3)
            and (command[0] == "S")
            and (command[1:].isnumeric())
            and (int(command[1:]) <= 18)
        )
        if is_status_request and finished_future is not None:
            # Look up list of existing requests awaiting responses
            req_id = StatusUpdate.RequestID(int(command[1:]))
            current = self._requests_awaiting_response[req_id]
            if current is not None:
                _LOGGER.debug("cancelling existing %s", current)
                current.cancel()
            _LOGGER.debug(
                "send_command Adding future %S for %s", finished_future, req_id
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
            now = datetime.datetime.now(tz=datetime.UTC)
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
                    now = datetime.datetime.now(tz=datetime.UTC)
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
            except (TimeoutError, CancelledError):
                _LOGGER.warning(
                    "Timed out waiting for response to Status Request: %s", req_id
                )

            retries -= 1
            _LOGGER.warning(
                "retrying request_and_wait_status_update - retries remaining:%s",
                retries,
            )

        return None

    async def _recv_loop(self) -> None:
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

                self._last_recv = datetime.datetime.now(tz=datetime.UTC)
                try:
                    decoded_data = data.decode("ascii")
                except UnicodeDecodeError:
                    self.bad_received_packets += 1
                    _LOGGER.warning("Failed to decode data : %s", data, exc_info=True)
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
                            _LOGGER.debug(
                                "No waiter %s", self._requests_awaiting_response
                            )
                    else:
                        _LOGGER.debug("Not StatusUpdate: %s", type(event))

                    if self._on_event_received is not None:
                        self._on_event_received(event)

                    self.alarm.handle_event(event)

    def _should_reconnect(self) -> bool:
        now = datetime.datetime.now(tz=datetime.UTC)
        _LOGGER.debug("now=%s last_recv=%s", now, self._last_recv)
        return (
            self._last_recv is not None
            and self._last_recv
            < now - datetime.timedelta(seconds=self._update_interval + 30)
        )

    async def _update_loop(self) -> None:
        """Schedule a state update to keep the connection alive."""
        _LOGGER.debug("_update_loop sleeping for %s", self._update_interval)
        await asyncio.sleep(self._update_interval)
        while not self._closed:
            await self.update()
            _LOGGER.debug("_update_loop sleeping for %s", self._update_interval)
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
        self, f: Callable[[ArmingState, ArmingMode | None], None] | None
    ) -> Callable[[ArmingState, ArmingMode | None], None] | None:
        self.alarm.on_state_change(f)
        return f

    def on_zone_change(
        self, f: Callable[[int, ZoneSealedState], None] | None
    ) -> Callable[[int, ZoneSealedState], None] | None:
        self.alarm.on_zone_change(f)
        return f

    def on_event_received(
        self, f: Callable[[BaseEvent], None] | None
    ) -> Callable[[BaseEvent], None] | None:
        self._on_event_received = f
        return f
