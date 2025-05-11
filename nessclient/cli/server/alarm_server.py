"""Implements a test alarm emulator with an interactive CLI UI."""

import logging
import random
import threading
from collections.abc import Iterator

from nessclient.event import (
    ArmingUpdate,
    AuxiliaryOutputsUpdate,
    StatusUpdate,
    SystemStatusEvent,
    ZoneUpdate,
)

from .alarm import Alarm
from .server import Server
from .zone import Zone

_LOGGER = logging.getLogger(__name__)


class AlarmServer:
    """Implements a test alarm emulator with an interactive CLI UI."""

    _simulation_end_event: threading.Event | None
    _simulation_thread: threading.Thread
    _master_code: str
    alarm: Alarm
    server: Server

    PORT_MIN = 0
    PORT_MAX = 65535

    def __init__(
        self, host: str, port: int, num_zones: int = 8, master_code: str = "1234"
    ) -> None:
        """Create a new test alarm emulator that listens on a specifc host+port."""
        self.alarm = Alarm.create(
            num_zones=num_zones,
            alarm_state_changed=self._alarm_state_changed,
            zone_state_changed=self._zone_state_changed,
            aux_state_changed=self._aux_state_changed,
        )
        self.server = Server(handle_command=self._handle_command)
        if not isinstance(host, str):
            msg = "Host must be a valid string"
            raise TypeError(msg)
        if (
            not isinstance(port, int)
            or port < AlarmServer.PORT_MIN
            or port > AlarmServer.PORT_MAX
        ):
            msg = "Host must be a valid integer 0-65535"
            raise ValueError(msg)
        self._host = host
        self._port = port
        self._simulation_end_event = None
        self._master_code = master_code

    def start(self, *, interactive: bool = True, with_simulation: bool = True) -> None:
        """Start running the test alarm emulator."""
        self.server.start(host=self._host, port=self._port)
        if with_simulation:
            self._start_simulation()

        if interactive:
            while True:
                command = input("Command: ")
                if not self.interactive_command(command):
                    _LOGGER.debug("Stopping interactive commands")
                    break

    def interactive_command(self, command: str) -> bool:
        """Hande a user CLI command."""
        print(f"Got command {command}")  # noqa: T201 # Valid CLI print

        command = command.upper().strip()
        if command == "D":
            self.alarm.disarm()
        elif command in ("A", "AA"):
            self.alarm.arm(Alarm.ArmingMode.ARMED_AWAY)
        elif command == "AH":
            self.alarm.arm(Alarm.ArmingMode.ARMED_HOME)
        elif command == "AD":
            self.alarm.arm(Alarm.ArmingMode.ARMED_DAY)
        elif command == "AN":
            self.alarm.arm(Alarm.ArmingMode.ARMED_NIGHT)
        elif command == "AV":
            self.alarm.arm(Alarm.ArmingMode.ARMED_VACATION)
        elif command == "T":
            self.alarm.trip()
        elif command == "S":
            if self._simulation_end_event is None:
                print("Starting simulation")  # noqa: T201 # Valid CLI print
                self._start_simulation()
            else:
                print("Stopping simulation")  # noqa: T201 # Valid CLI print
                self._stop_simulation()
            return True
        elif command == "Q":
            self.stop()
            return False
        else:
            print("Commands:")  # noqa: T201 # Valid CLI print
            print("  D  : Disarm")  # noqa: T201 # Valid CLI print
            print("  A  : Armed Away")  # noqa: T201 # Valid CLI print
            print("  AA : Armed Away")  # noqa: T201 # Valid CLI print
            print("  AH : Armed Home")  # noqa: T201 # Valid CLI print
            print("  AD : Armed Day")  # noqa: T201 # Valid CLI print
            print("  AN : Armed Night")  # noqa: T201 # Valid CLI print
            print("  AV : Armed Vacation")  # noqa: T201 # Valid CLI print
            print("  T  : Trip")  # noqa: T201 # Valid CLI print
            print(  # noqa: T201 # Valid CLI print
                "  S  : Toggle simulation of random unseal activity"
            )
            print("  Q  : Quit")  # noqa: T201 # Valid CLI print

        return True

    def stop(self) -> None:
        """Stop the test alarm emulator."""
        _LOGGER.debug("Stopping AlarmServer")
        self._stop_simulation()
        self.server.stop()

    def _alarm_state_changed(
        self,
        previous_state: Alarm.ArmingState,
        state: Alarm.ArmingState,
        arming_mode: Alarm.ArmingMode | None,
    ) -> None:
        """
        Handle zone arming status changes.

        Sends a System Status Event packet to indicate the change
        """
        _LOGGER.debug(
            "Alarm state change %s -> %s  mode %s", previous_state, state, arming_mode
        )
        if state == Alarm.ArmingState.DISARMED:
            # Simulated movement in zones only makes sense in disarmed state
            self._start_simulation()
        else:
            self._stop_simulation()

        event_list = list(
            get_events_for_state_update(previous_state, state, arming_mode)
        )
        _LOGGER.debug("events for state update: %s", event_list)
        for event_type in event_list:
            event = SystemStatusEvent(
                event_type=event_type, zone=0x00, area=0x00, timestamp=None, address=0
            )
            self.server.write_event(event)

    def _zone_state_changed(self, zone_id: int, state: Zone.State) -> None:
        """
        Handle zone sealed/unsealed changes.

        Sends a System Status Event packet to indicate the change
        """
        event_type: SystemStatusEvent.EventType
        if state == Zone.State.SEALED:
            event_type = SystemStatusEvent.EventType.SEALED
        elif state == Zone.State.UNSEALED:
            event_type = SystemStatusEvent.EventType.UNSEALED
        else:
            raise NotImplementedError

        event = SystemStatusEvent(
            event_type=event_type,
            zone=zone_id,
            area=0,
            timestamp=None,
            address=0,
        )
        self.server.write_event(event)

    def _aux_state_changed(
        self,
        aux_id: int,
        state: bool,  # noqa: FBT001 # keep bool argument due to callable
    ) -> None:
        """
        Handle aux output changes.

        Sends a System Status Event packet to indicate the change
        """
        event = SystemStatusEvent(
            event_type=(
                SystemStatusEvent.EventType.OUTPUT_ON
                if state
                else SystemStatusEvent.EventType.OUTPUT_OFF
            ),
            zone=aux_id,
            area=0,
            timestamp=None,
            address=0,
        )
        _LOGGER.debug("Aux State change - sending System Status Event: %s", event)
        self.server.write_event(event)

    def _handle_command(  # noqa: PLR0912 # no simple way to reduce branches
        self, command: str
    ) -> None:
        """
        Responds to commands from a TCP client.

        This is the main function that handles incoming packets.

        Handles Arm, Arm-Home, Disarm, Unsealed-Status & Arming-Status requests
        """
        _LOGGER.info("Incoming User Command: %s", command)

        # NOTE: No defined way to set Armed-Night mode, Armed-Vacation
        #       or Armed-Highest in the manual
        if command in ("AE", f"A{self._master_code}E"):
            self.alarm.arm()
        elif command in ("HE", f"H{self._master_code}E"):
            self.alarm.arm(Alarm.ArmingMode.ARMED_HOME)
        elif command in ("0E", f"0{self._master_code}E"):
            self.alarm.arm(Alarm.ArmingMode.ARMED_DAY)
        elif command == f"{self._master_code}E":
            self.alarm.disarm()
        elif command in ("*E", f"*{self._master_code}E"):
            self.alarm.panic()
        elif (
            command[0] in ["5", "6", "8", "9"]
            and command[1:] == f"{self._master_code}E"
        ):
            self.alarm.duress()
        elif command == "2E":
            self.alarm.medical()
        elif command == "3E":
            self.alarm.fire()
        elif command.startswith(("XE", f"X{self._master_code}E")):
            # Zone Exclude
            # Following command characters are a list where each zone has:
            # <Zone_ID> + 'E'
            # Ends with another 'E' to exit Exclude-mode
            msg = "Zone Exclude not implemented"
            raise NotImplementedError(msg)
        elif command.startswith(("VE", f"V{self._master_code}E")):
            # Event Memory
            # Following command characters should be 'V' to iterate through
            # the memory items.
            # Ends with 'E' to exit memory-mode
            msg = "Event Memory not implemented"
            raise NotImplementedError(msg)
        elif command.startswith("PE"):
            # Following command characters are a list where each zone has:
            # <Zone_ID> + 'E'
            # Ends with another 'E' to exit Exclude-mode
            msg = "Temporary Day Zones not implemented"
            raise NotImplementedError(msg)
        elif command in ["11*", "22*", "33*", "44*", "11#", "22#", "33#", "44#"]:
            # Set AUX outputs
            aux_id = int(command[0])
            aux_state = command[2] == "*"
            self.alarm.set_aux(aux_id=aux_id, aux_state=aux_state)
        elif command.startswith("S"):
            self._handle_status_update_request(command)

    def _handle_status_update_request(self, command: str) -> None:
        """Responds to status update request packets."""
        if command == "S00":
            # S00 : List unsealed Zones
            self._handle_zone_input_unsealed_status_update_request()
        # S01 : List radio unsealed zones
        # S02 : List Cbus unsealed zones
        elif command == "S03":
            # S03 : List zones in delay
            self._handle_zone_in_delay_status_update_request()
        # S04 : List zones in double trigger
        elif command == "S05":
            # S05 : List zones currently Alarming
            self._handle_zone_in_alarm_status_update_request()
        # S06 : List excluded zones
        # S07 : List auto-excluded zones
        # S08 : List zones with supervision-fail pending
        # S09 : List zones with supervision-fail
        # S10 : List zones with doors open
        # S11 : List zones with detector low battery
        # S12 : List zones with detector tamper
        # S13 : List miscellaneous alarms
        elif command == "S14":
            # S14 : Arming status update
            self._handle_arming_status_update_request()
        # S15 : List output states
        # S16 : Get View State
        # S17 : Get Firmware Version
        elif command == "S18":
            # S18 : List auxilliary output states
            self._handle_aux_status_update_request()

    def _handle_aux_status_update_request(self) -> None:
        """
        Handle a "S18" (auxilliary output state) status update request.

        Sends a Status Update response packet to indicate the current aux output states.
        """
        all_aux_outputs = list(AuxiliaryOutputsUpdate.OutputType)
        aux_list: list[AuxiliaryOutputsUpdate.OutputType] = []
        for pos, aux in enumerate(self.alarm.aux):
            if aux:
                aux_list.append(all_aux_outputs[pos])

        event = AuxiliaryOutputsUpdate(
            outputs=aux_list,
            address=0x00,
            timestamp=None,
        )
        _LOGGER.debug("Received aux-status request - replying with %s", event)
        self.server.write_event(event)

    def _handle_arming_status_update_request(self) -> None:
        """
        Handle a "S14" (arming state) status update request.

        Sends a Status Update response packet to indicate the current arming state.
        """
        event = ArmingUpdate(
            status=get_arming_status(self.alarm.state),
            address=0x00,
            timestamp=None,
        )
        _LOGGER.debug("Received arming-status request - replying with %s", event)
        self.server.write_event(event)

    def _handle_zone_input_unsealed_status_update_request(self) -> None:
        """
        Handle a "S00" (zone unsealed state) status update request.

        Sends a Status Update response packet to indicate the current sealed states.
        """
        event = ZoneUpdate(
            request_id=StatusUpdate.RequestID.ZONE_INPUT_UNSEALED,
            included_zones=[
                get_zone_for_id(z.id)
                for z in self.alarm.zones
                if z.state == Zone.State.UNSEALED
            ],
            address=0x00,
            timestamp=None,
        )
        self.server.write_event(event)

    def _handle_zone_in_delay_status_update_request(self) -> None:
        """
        Handle a "S03" (zone in-delay state) status update request.

        Sends a Status Update response packet to indicate the current in-delay states.
        """
        event = ZoneUpdate(
            request_id=StatusUpdate.RequestID.ZONE_IN_DELAY,
            included_zones=[
                get_zone_for_id(z.id) for z in self.alarm.zones if z.in_delay
            ],
            address=0x00,
            timestamp=None,
        )
        self.server.write_event(event)

    def _handle_zone_in_alarm_status_update_request(self) -> None:
        """
        Handle a "S05" (zone in-alarm state) status update request.

        Sends a Status Update response packet to indicate the current in-alarm states.
        """
        event = ZoneUpdate(
            request_id=StatusUpdate.RequestID.ZONE_IN_ALARM,
            included_zones=[
                get_zone_for_id(z.id) for z in self.alarm.zones if z.in_alarm
            ],
            address=0x00,
            timestamp=None,
        )
        self.server.write_event(event)

    def _stop_simulation(self) -> None:
        """Stop the sealed/unsealed random toggling."""
        _LOGGER.debug("Stopping activity simulation")
        if self._simulation_end_event is not None:
            self._simulation_end_event.set()
            _LOGGER.info("set event")
            self._simulation_thread.join()
            _LOGGER.info("joined")
            self._simulation_end_event = None

    def _start_simulation(self) -> None:
        """Start the sealed/unsealed random toggling."""

        def _simulate_zone_events() -> None:
            """
            Thread that randomly toggles the sealed/unsealed state of a random zones.

            Toggles in a loop with pauses of 1-5 seconds between each
            """
            while (
                self._simulation_end_event is not None
                and not self._simulation_end_event.wait(
                    random.randint(  # noqa: S311 - Random not used for cryptography
                        1, 5
                    )
                )
            ):
                # Ruff: Random not used for cryptography
                zone: Zone = random.choice(self.alarm.zones)  # noqa: S311
                self.alarm.update_zone(zone.id, toggled_state(zone.state))
                _LOGGER.info("Toggled zone: %s", zone)
            _LOGGER.info("Simulation ended")

        if self._simulation_end_event is None:
            self._simulation_end_event = threading.Event()
            self._simulation_thread = threading.Thread(
                target=_simulate_zone_events, name="server unseal simulation"
            )
            self._simulation_thread.start()


def mode_to_event(mode: Alarm.ArmingMode | None) -> SystemStatusEvent.EventType:
    """Convert a Alarm.ArmingMode to a SystemStatusEvent.EventType mode."""
    if mode == Alarm.ArmingMode.ARMED_AWAY:
        return SystemStatusEvent.EventType.ARMED_AWAY
    if mode == Alarm.ArmingMode.ARMED_HOME:
        return SystemStatusEvent.EventType.ARMED_HOME
    if mode == Alarm.ArmingMode.ARMED_DAY:
        return SystemStatusEvent.EventType.ARMED_DAY
    if mode == Alarm.ArmingMode.ARMED_NIGHT:
        return SystemStatusEvent.EventType.ARMED_NIGHT
    if mode == Alarm.ArmingMode.ARMED_VACATION:
        return SystemStatusEvent.EventType.ARMED_VACATION

    msg = "Unknown alarm mode"
    raise AssertionError(msg)


def get_events_for_state_update(
    previous_state: Alarm.ArmingState,
    state: Alarm.ArmingState,
    arming_mode: Alarm.ArmingMode | None,
) -> Iterator[SystemStatusEvent.EventType]:
    """Determine which async events should be sent upon state changes."""
    if state == Alarm.ArmingState.DISARMED:
        yield SystemStatusEvent.EventType.DISARMED
    if state == Alarm.ArmingState.EXIT_DELAY:
        yield mode_to_event(arming_mode)
        yield SystemStatusEvent.EventType.EXIT_DELAY_START

    _LOGGER.debug(
        "get_events_for_state_update - state: %s   arming_mode: %s", state, arming_mode
    )
    if state == Alarm.ArmingState.TRIPPED:
        yield SystemStatusEvent.EventType.ALARM

    # When state transitions from EXIT_DELAY, trigger EXIT_DELAY_END.
    if (
        (previous_state == Alarm.ArmingState.EXIT_DELAY) and (state != previous_state)
    ) or (state == Alarm.ArmingState.ARMED):
        yield SystemStatusEvent.EventType.EXIT_DELAY_END

    if state == Alarm.ArmingState.ENTRY_DELAY:
        yield SystemStatusEvent.EventType.ENTRY_DELAY_START

    # When state transitions from ENTRY_DELAY, trigger ENTRY_DELAY_END
    if previous_state == Alarm.ArmingState.ENTRY_DELAY and state != previous_state:
        yield SystemStatusEvent.EventType.ENTRY_DELAY_END


def get_arming_status(state: Alarm.ArmingState) -> list[ArmingUpdate.ArmingStatus]:
    """
    Get a list of ArmingStatus items for the current armed status.

    Appropriate to pass to ArmingUpdate() constructor
    """
    if state == Alarm.ArmingState.ARMED:
        return [
            ArmingUpdate.ArmingStatus.AREA_1_ARMED,
            ArmingUpdate.ArmingStatus.AREA_1_FULLY_ARMED,
        ]
    if state == Alarm.ArmingState.EXIT_DELAY:
        return [ArmingUpdate.ArmingStatus.AREA_1_ARMED]

    return []


def toggled_state(state: Zone.State) -> Zone.State:
    """Invert the supplied sealed/unsealed zone state."""
    if state == Zone.State.SEALED:
        return Zone.State.UNSEALED

    return Zone.State.SEALED


def get_zone_for_id(zone_id: int) -> ZoneUpdate.Zone:
    """Get the zone details matching the supplied zone ID."""
    key = f"ZONE_{zone_id}"
    return ZoneUpdate.Zone[key]
