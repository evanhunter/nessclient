import asyncio
from dataclasses import dataclass
import datetime
import logging
from asyncio import CancelledError, TimeoutError, sleep
from typing import Optional, Callable, Dict, cast

from justbackoff import Backoff

from .alarm import ArmingState, Alarm, ArmingMode
from .connection import Connection, IP232Connection, Serial232Connection
from .event import (
    AuxiliaryOutputsUpdate,
    BaseEvent,
    MiscellaneousAlarmsUpdate,
    OutputsUpdate,
    PanelVersionUpdate,
    StatusUpdate,
    ViewStateUpdate,
    ZoneUpdate,
    ArmingUpdate,
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
    MiscellaneousAlarms: Optional[MiscellaneousAlarmsUpdate]
    Arming: Optional[ArmingUpdate]
    Outputs: Optional[OutputsUpdate]
    ViewState: Optional[ViewStateUpdate]
    PanelVersion: Optional[PanelVersionUpdate]
    AuxiliaryOutputs: Optional[AuxiliaryOutputsUpdate]


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
    _on_event_received: Optional[Callable[[BaseEvent], None]]
    _connection: Connection
    _closed: bool
    _backoff: Backoff
    _connect_lock: asyncio.Lock
    _write_lock: asyncio.Lock
    _last_recv: Optional[datetime.datetime]
    _last_sent_time: Optional[datetime.datetime]
    _update_interval: int
    _requests_awaiting_response: Dict[
        StatusUpdate.RequestID, Optional[asyncio.Future[StatusUpdate]]
    ]

    DELAY_SECONDS_BETWEEN_SENDS = 0.2

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
        for id in StatusUpdate.RequestID:
            self._requests_awaiting_response[id] = None

    async def arm_away(self, code: Optional[str] = None) -> None:
        command = "A{}E".format(code if code else "")
        return await self.send_command(command)

    async def arm_home(self, code: Optional[str] = None) -> None:
        command = "H{}E".format(code if code else "")
        return await self.send_command(command)

    async def disarm(self, code: Optional[str]) -> None:
        command = "{}E".format(code if code else "")
        return await self.send_command(command)

    async def panic(self, code: Optional[str]) -> None:
        command = "*{}E".format(code if code else "")
        return await self.send_command(command)

    async def enter_user_program_mode(self, master_code: Optional[str] = "123") -> None:
        command = "M{}E".format(master_code if master_code else "")
        return await self.send_command(command)

    async def enter_installer_program_mode(
        self, installer_code: Optional[str] = "000000"
    ) -> None:
        command = "M{}E".format(installer_code if installer_code else "")
        return await self.send_command(command)

    async def exit_program_mode(self) -> None:
        command = "ME"
        return await self.send_command(command)

    async def aux(self, output_id: int, state: bool = True) -> None:
        command = "{}{}{}".format(output_id, output_id, "*" if state else "#")
        return await self.send_command(command)

    async def update(self) -> None:
        """Force update of alarm status and zones"""
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


    async def update_wait(self) -> (list[bool], ):
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
                Optional[MiscellaneousAlarmsUpdate], miscellaneous_alarms
            ),
            Arming=cast(Optional[ArmingUpdate], arming),
            Outputs=cast(Optional[OutputsUpdate], outputs),
            ViewState=cast(Optional[ViewStateUpdate], view_state),
            PanelVersion=cast(Optional[PanelVersionUpdate], panel_version),
            AuxiliaryOutputs=cast(Optional[AuxiliaryOutputsUpdate], auxiliary_outputs),
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
                Optional[MiscellaneousAlarmsUpdate], miscellaneous_alarms
            ),
            Arming=cast(Optional[ArmingUpdate], arming),
            Outputs=cast(Optional[OutputsUpdate], outputs),
            ViewState=cast(Optional[ViewStateUpdate], view_state),
            PanelVersion=cast(Optional[PanelVersionUpdate], panel_version),
            AuxiliaryOutputs=cast(Optional[AuxiliaryOutputsUpdate], auxiliary_outputs),
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

    async def send_command(
        self,
        command: str,
        address: int = 0,
        finished_future: Optional[asyncio.Future[StatusUpdate]] = None,
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
            id = StatusUpdate.RequestID(int(command[1:]))
            current = self._requests_awaiting_response[id]
            if current is not None:
                _LOGGER.debug(f"cancelling existing {current}")
                current.cancel()
            _LOGGER.debug(f"send_command Adding future {finished_future} for {id}")
            self._requests_awaiting_response[id] = finished_future
            _LOGGER.debug(
                f"send_command added future {self._requests_awaiting_response}"
            )

        _LOGGER.debug("send_command() connecting")
        async with self._write_lock:
            await self._connect()
            payload = packet.encode()

            # Check if a delay is needed to avoid overwhelming the Ness Alarm
            now = datetime.datetime.now()
            if self._last_sent_time is not None:
                time_since_last_send_delta: datetime.timedelta = (
                    now - self._last_sent_time
                )
                time_since_last_send: float = time_since_last_send_delta.total_seconds()
                _LOGGER.debug(f"time_since_last_send = {time_since_last_send}")
                if time_since_last_send < Client.DELAY_SECONDS_BETWEEN_SENDS:
                    sleep_time = (
                        Client.DELAY_SECONDS_BETWEEN_SENDS - time_since_last_send
                    )
                    _LOGGER.debug(f"sleeping for {sleep_time} seconds from {now}")
                    await asyncio.sleep(sleep_time)
                    now = datetime.datetime.now()
                    _LOGGER.debug(f"time after sleep {now}")

            _LOGGER.debug(f"Sending packet: {packet}")
            _LOGGER.debug(f"send_command() - Sending payload: {payload}")
            # _LOGGER.debug(f"XXX: {Packet.decode(payload)}")
            self._last_sent_time = now
            return await self._connection.write(payload.encode("ascii"))

    async def request_and_wait_status_update(
        self, id: StatusUpdate.RequestID, address: int = 0, retries: int = 3
    ) -> Optional[StatusUpdate]:
        """Send a Status Update Request and wait for a response."""
        while retries > 0:
            try:
                f: asyncio.Future[StatusUpdate] = asyncio.Future()
                _LOGGER.debug(f"Adding future {f} for {id}")
                await self.send_command(
                    f"S{id.value:02}", address=address, finished_future=f
                )

                await asyncio.wait_for(f, 2.0)
                _LOGGER.debug(f"Finished waiting for status response: {f}")
                if f.done():
                    return f.result()
            except (TimeoutError, CancelledError):
                _LOGGER.warning(
                    f"Timed out waiting for response to Status Request: {id}"
                )

            retries -= 1
            _LOGGER.warning(
                f"retrying request_and_wait_status_update - retries remaining:{retries}"
            )

        return None

    async def _recv_loop(self) -> None:
        while not self._closed:
            _LOGGER.debug(f"_recv_loop() - connecting - closed={self._closed}")
            await self._connect()
            _LOGGER.debug("_recv_loop() - connected")

            while True:
                _LOGGER.debug("_recv_loop() - reading")
                data = await self._connection.read()
                _LOGGER.debug(f"_recv_loop() - read got {data!r}")
                if data is None:
                    self.disconnection_count += 1
                    _LOGGER.debug("Received None data from connection.read()")
                    break

                self._last_recv = datetime.datetime.now()
                try:
                    decoded_data = data.decode("ascii")
                except UnicodeDecodeError:
                    self.bad_received_packets += 1
                    _LOGGER.warning(f"Failed to decode data : {data!r}", exc_info=True)
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

                    _LOGGER.debug(f"Decoded event: {event}")
                    # Check if the received packet is a response to a Status Update
                    #  Request which is awaiting the response
                    if isinstance(event, StatusUpdate):
                        f = self._requests_awaiting_response[event.request_id]
                        if f is not None:
                            _LOGGER.debug(f"Waiter for {event} :  {f}")
                            try:
                                f.set_result(event)
                            except asyncio.exceptions.InvalidStateError as e:
                                _LOGGER.info(f"Waiter already set for {f} : {e}")
                            self._requests_awaiting_response[event.request_id] = None
                        else:
                            _LOGGER.debug(
                                f"No waiter {self._requests_awaiting_response}"
                            )
                    else:
                        _LOGGER.debug(f"Not StatusUpdate: {type(event)}")

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
