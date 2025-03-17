import logging
import random
import threading
from typing import List, Iterator, Optional

from .alarm import Alarm
from .server import Server
from .zone import Zone
from ...event import SystemStatusEvent, ArmingUpdate, ZoneUpdate, StatusUpdate

_LOGGER = logging.getLogger(__name__)


class AlarmServer:
    _simulation_end_event: Optional[threading.Event]
    _simulation_thread: threading.Thread
    _master_code: str

    def __init__(
        self, host: str, port: int, num_zones: int = 8, master_code: str = "1234"
    ):
        self._alarm = Alarm.create(
            num_zones=num_zones,
            alarm_state_changed=self._alarm_state_changed,
            zone_state_changed=self._zone_state_changed,
        )
        self._server = Server(handle_command=self._handle_command)
        if not isinstance(host, str):
            raise ValueError("Host must be a valid string")
        if not isinstance(port, int) or port < 0 or port > 65535:
            raise ValueError("Host must be a valid integer 0-65535")
        self._host = host
        self._port = port
        self._simulation_end_event = None
        self._master_code = master_code

    def start(self, interactive: bool = True, with_simulation: bool = True) -> None:
        self._server.start(host=self._host, port=self._port)
        if with_simulation:
            self._start_simulation()

        if interactive:
            while True:
                command = input("Command: ")
                if not self.interactive_command(command):
                    _LOGGER.debug("Stopping interactive commands")
                    break

    def interactive_command(self, command: str) -> bool:
        print(f"got command {command}")

        command = command.upper().strip()
        if command == "D":
            self._alarm.disarm()
        elif command == "A" or command == "AA":
            self._alarm.arm(Alarm.ArmingMode.ARMED_AWAY)
        elif command == "AH":
            self._alarm.arm(Alarm.ArmingMode.ARMED_HOME)
        elif command == "AD":
            self._alarm.arm(Alarm.ArmingMode.ARMED_DAY)
        elif command == "AN":
            self._alarm.arm(Alarm.ArmingMode.ARMED_NIGHT)
        elif command == "AV":
            self._alarm.arm(Alarm.ArmingMode.ARMED_VACATION)
        elif command == "T":
            self._alarm.trip()
        elif command == "S":
            if self._simulation_end_event is None:
                print("Starting simulation")
                self._start_simulation()
            else:
                print("Stopping simulation")
                self._stop_simulation()
            return True
        elif command == "Q":
            self.stop()
            return False
        else:
            print("Commands:")
            print("  A  : Armed Away")
            print("  AA : Armed Away")
            print("  AH : Armed Home")
            print("  AD : Armed Day")
            print("  AN : Armed Night")
            print("  AV : Armed Vacation")
            print("  T  : Trip")
            print("  S  : Toggle simulation of random unseal activity")
            print("  Q  : Quit")

        return True

    def stop(self) -> None:
        _LOGGER.debug("Stopping AlarmServer")
        self._stop_simulation()
        self._server.stop()

    def _alarm_state_changed(
        self,
        previous_state: Alarm.ArmingState,
        state: Alarm.ArmingState,
        arming_mode: Alarm.ArmingMode | None,
    ) -> None:

        _LOGGER.debug(
            f"Alarm state change {previous_state} -> {state}  mode {arming_mode}"
        )
        if state == Alarm.ArmingState.DISARMED:
            # Simulated movement in zones only makes sense in disarmed state
            self._start_simulation()
        else:
            self._stop_simulation()

        event_list = [
            e for e in get_events_for_state_update(previous_state, state, arming_mode)
        ]
        _LOGGER.debug(f"events for state update: {event_list}")
        for event_type in event_list:
            event = SystemStatusEvent(
                type=event_type, zone=0x00, area=0x00, timestamp=None, address=0
            )
            self._server.write_event(event)

    def _zone_state_changed(self, zone_id: int, state: Zone.State) -> None:
        type: SystemStatusEvent.EventType
        if state == Zone.State.SEALED:
            type = SystemStatusEvent.EventType.SEALED
        elif state == Zone.State.UNSEALED:
            type = SystemStatusEvent.EventType.UNSEALED
        else:
            raise NotImplementedError()

        event = SystemStatusEvent(
            type=type,
            zone=zone_id,
            area=0,
            timestamp=None,
            address=0,
        )
        self._server.write_event(event)

    def _handle_command(self, command: str) -> None:
        """
        Responds to commands from a TCP client
        Handles Arm, Arm-Home, Disarm, Unsealed-Status & Arming-Status requests
        """
        _LOGGER.info("Incoming User Command: {}".format(command))
        if command == "AE" or command == f"A{self._master_code}E":
            self._alarm.arm()
        elif command == "HE" or command == f"H{self._master_code}E":
            self._alarm.arm(Alarm.ArmingMode.ARMED_HOME)
        elif command == "0E" or command == f"0{self._master_code}E":
            self._alarm.arm(Alarm.ArmingMode.ARMED_DAY)
        elif command == "*E" or command == f"*{self._master_code}E":
            _LOGGER.info("setting panic")
            self._alarm._update_state_no_mode(Alarm.ArmingState.PANIC)
        elif (
            command[0] in ["5", "6", "8", "9"]
            and command[1:] == f"{self._master_code}E"
        ):
            _LOGGER.info("setting duress")
            self._alarm._cancel_pending_update()
            self._alarm._update_state_no_mode(Alarm.ArmingState.DURESS)
        elif command == "2E":
            self._alarm._update_state_no_mode(Alarm.ArmingState.MEDICAL)
        elif command == "3E":
            self._alarm._update_state_no_mode(Alarm.ArmingState.FIRE)
        # TODO: No defined way to set Armed-Night mode, Armed-Vacation
        #       or Armed-Highest in the manual
        # TODO: add support for AUX on/off commands
        elif command == f"{self._master_code}E":
            self._alarm.disarm()
        elif command == "S00":
            self._handle_zone_input_unsealed_status_update_request()
        elif command == "S14":
            self._handle_arming_status_update_request()

    def _handle_arming_status_update_request(self) -> None:
        event = ArmingUpdate(
            status=get_arming_status(self._alarm.state),
            address=0x00,
            timestamp=None,
        )
        _LOGGER.debug(f"Received arming-status request - replying with {event}")
        self._server.write_event(event)

    def _handle_zone_input_unsealed_status_update_request(self) -> None:
        event = ZoneUpdate(
            request_id=StatusUpdate.RequestID.ZONE_INPUT_UNSEALED,
            included_zones=[
                get_zone_for_id(z.id)
                for z in self._alarm.zones
                if z.state == Zone.State.UNSEALED
            ],
            address=0x00,
            timestamp=None,
        )
        self._server.write_event(event)

    def _simulate_zone_events(self) -> None:
        """
        Randomly toggles the sealed/unsealed state of a random zone
        in a loop with pauses of 1-5 seconds between each
        """
        while (
            self._simulation_end_event is not None
            and not self._simulation_end_event.wait(random.randint(1, 5))
        ):
            zone: Zone = random.choice(self._alarm.zones)
            self._alarm.update_zone(zone.id, toggled_state(zone.state))
            _LOGGER.info("Toggled zone: %s", zone)
        _LOGGER.info("Simulation ended")

    def _stop_simulation(self) -> None:
        _LOGGER.debug("Stopping activity simulation")
        if self._simulation_end_event is not None:
            self._simulation_end_event.set()
            _LOGGER.info("set event")
            self._simulation_thread.join()
            _LOGGER.info("joined")
            self._simulation_end_event = None

    def _start_simulation(self) -> None:
        if self._simulation_end_event is None:
            self._simulation_end_event = threading.Event()
            self._simulation_thread = threading.Thread(
                target=self._simulate_zone_events, name="server unseal simulation"
            )
            self._simulation_thread.start()


def mode_to_event(mode: Alarm.ArmingMode | None) -> SystemStatusEvent.EventType:
    if mode == Alarm.ArmingMode.ARMED_AWAY:
        return SystemStatusEvent.EventType.ARMED_AWAY
    elif mode == Alarm.ArmingMode.ARMED_HOME:
        return SystemStatusEvent.EventType.ARMED_HOME
    elif mode == Alarm.ArmingMode.ARMED_DAY:
        return SystemStatusEvent.EventType.ARMED_DAY
    elif mode == Alarm.ArmingMode.ARMED_NIGHT:
        return SystemStatusEvent.EventType.ARMED_NIGHT
    elif mode == Alarm.ArmingMode.ARMED_VACATION:
        return SystemStatusEvent.EventType.ARMED_VACATION
    else:
        raise AssertionError("Unknown alarm mode")


def get_events_for_state_update(
    previous_state: Alarm.ArmingState,
    state: Alarm.ArmingState,
    arming_mode: Alarm.ArmingMode | None,
) -> Iterator[SystemStatusEvent.EventType]:
    if state == Alarm.ArmingState.DISARMED:
        yield SystemStatusEvent.EventType.DISARMED
    if state == Alarm.ArmingState.EXIT_DELAY:
        yield mode_to_event(arming_mode)
        yield SystemStatusEvent.EventType.EXIT_DELAY_START

    _LOGGER.debug(f"get_events_for_state_update - state: {state}   arming_mode: {arming_mode}")
    if state == Alarm.ArmingState.TRIPPED:
        yield SystemStatusEvent.EventType.ALARM

    # When state transitions from EXIT_DELAY, trigger EXIT_DELAY_END.
    if (
        previous_state == Alarm.ArmingState.EXIT_DELAY
        and state != previous_state
        or state == Alarm.ArmingState.ARMED
    ):
        yield SystemStatusEvent.EventType.EXIT_DELAY_END

    if state == Alarm.ArmingState.ENTRY_DELAY:
        yield SystemStatusEvent.EventType.ENTRY_DELAY_START

    # When state transitions from ENTRY_DELAY, trigger ENTRY_DELAY_END
    if previous_state == Alarm.ArmingState.ENTRY_DELAY and state != previous_state:
        yield SystemStatusEvent.EventType.ENTRY_DELAY_END


def get_arming_status(state: Alarm.ArmingState) -> List[ArmingUpdate.ArmingStatus]:
    if state == Alarm.ArmingState.ARMED:
        return [
            ArmingUpdate.ArmingStatus.AREA_1_ARMED,
            ArmingUpdate.ArmingStatus.AREA_1_FULLY_ARMED,
        ]
    elif state == Alarm.ArmingState.EXIT_DELAY:
        return [ArmingUpdate.ArmingStatus.AREA_1_ARMED]
    else:
        return []


def toggled_state(state: Zone.State) -> Zone.State:
    if state == Zone.State.SEALED:
        return Zone.State.UNSEALED
    else:
        return Zone.State.SEALED


def get_zone_for_id(zone_id: int) -> ZoneUpdate.Zone:
    key = "ZONE_{}".format(zone_id)
    return ZoneUpdate.Zone[key]
