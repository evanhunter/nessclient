"""Provides the state machine logic for the test alarm emulator."""

import logging
import threading
import time
import uuid
from collections.abc import Callable
from enum import Enum

from .zone import Zone

_LOGGER = logging.getLogger(__name__)


class Alarm:
    """Represents the state machine of the test alarm emulator."""

    class ArmingState(Enum):
        """The arming states for an alarm."""

        DISARMED = "DISARMED"
        EXIT_DELAY = "EXIT_DELAY"
        ARMED = "ARMED"
        ENTRY_DELAY = "ENTRY_DELAY"
        TRIPPED = "TRIPPED"
        PANIC = "PANIC"
        DURESS = "DURESS"
        MEDICAL = "MEDICAL"
        FIRE = "FIRE"

    class ArmingMode(Enum):
        """The armed modes for an alarm."""

        ARMED_AWAY = "ARMED_AWAY"
        ARMED_HOME = "ARMED_HOME"
        ARMED_DAY = "ARMED_DAY"
        ARMED_NIGHT = "ARMED_NIGHT"
        ARMED_VACATION = "ARMED_VACATION"

    EXIT_DELAY: int = 10
    ENTRY_DELAY: int = 10

    AUX_ID_MIN = 1
    AUX_ID_MAX = 1

    state: ArmingState
    zones: list[Zone]
    _alarm_state_changed: Callable[[ArmingState, ArmingState, ArmingMode | None], None]
    _zone_state_changed: Callable[[int, Zone.State], None]
    _aux_state_changed: Callable[[int, bool], None]
    aux: list[bool]
    _pending_event: str | None
    arming_mode: ArmingMode | None
    _scheduled_threads: list[threading.Thread]

    def __init__(
        self,
        state: ArmingState,
        zones: list[Zone],
        alarm_state_changed: Callable[
            [ArmingState, ArmingState, ArmingMode | None], None
        ],
        zone_state_changed: Callable[[int, Zone.State], None],
        aux_state_changed: Callable[[int, bool], None],
    ) -> None:
        """Create an alarm object."""
        self.state = state
        self.zones = zones
        self.arming_mode = None
        self._alarm_state_changed = alarm_state_changed
        self._zone_state_changed = zone_state_changed
        self._aux_state_changed = aux_state_changed
        self._pending_event = None
        self._scheduled_threads = []
        self.aux = [
            False,
            False,
            False,
            False,
        ]

    @staticmethod
    def create(
        num_zones: int,
        alarm_state_changed: Callable[
            [ArmingState, ArmingState, ArmingMode | None], None
        ],
        zone_state_changed: Callable[[int, Zone.State], None],
        aux_state_changed: Callable[[int, bool], None],
    ) -> "Alarm":
        """Create an alarm object with a a default set of zone objects."""
        return Alarm(
            state=Alarm.ArmingState.DISARMED,
            zones=Alarm._generate_zones(num_zones),
            alarm_state_changed=alarm_state_changed,
            zone_state_changed=zone_state_changed,
            aux_state_changed=aux_state_changed,
        )

    @staticmethod
    def _generate_zones(num_zones: int) -> list[Zone]:
        """Create a list of zones for the create() method."""
        return [
            Zone(id=i + 1, state=Zone.State.SEALED, in_alarm=False, in_delay=False)
            for i in range(num_zones)
        ]

    def arm(self, mode: ArmingMode = ArmingMode.ARMED_AWAY) -> None:
        """
        Arm the alarm - with the specified arming mode.

        Set the state to EXIT_DELAY, and schedules
        an update to ARMED
        """
        self._update_state(Alarm.ArmingState.EXIT_DELAY, mode)
        for z in self.zones:
            z.in_alarm = False
            z.in_delay = True

        def _arm_complete() -> None:
            """Set the arming state to ARMED - callback after exit delay."""
            _LOGGER.debug("Arm completed")
            for z in self.zones:
                z.in_alarm = False
                z.in_delay = False
            self._update_state_no_mode(Alarm.ArmingState.ARMED)

        self._schedule(self.EXIT_DELAY, _arm_complete)

    def disarm(self) -> None:
        """Disarm the alarm."""
        self._cancel_pending_update()

        _LOGGER.info("Disarming!")
        for z in self.zones:
            z.in_alarm = False
            z.in_delay = False
        self._update_state(Alarm.ArmingState.DISARMED, None)

    def trip(self, *, delay: bool = True, zone: int = 1) -> None:
        """
        Trip (trigger, unseal) one of the zones.

        If delay == False: zone is immediately set to 'In-Alarm' state
        If delay == False: zone is set to 'In-Delay' state, then transitions
            to 'In-Alarm' state after the standard Entry delay time
        """
        if delay:
            self._update_state_no_mode(Alarm.ArmingState.ENTRY_DELAY)
            self.zones[zone - 1].in_delay = True

            def _trip_complete() -> None:
                _LOGGER.debug("Trip completed")
                self.zones[zone - 1].in_delay = False
                self.zones[zone - 1].in_alarm = True
                self._update_state_no_mode(Alarm.ArmingState.TRIPPED)
                _LOGGER.debug("Tripped %s", self)

            self._schedule(self.ENTRY_DELAY, _trip_complete)
        else:
            self._update_state_no_mode(Alarm.ArmingState.TRIPPED)
            self.zones[zone - 1].in_delay = False
            self.zones[zone - 1].in_alarm = True

    def update_zone(self, zone_id: int, state: Zone.State) -> None:
        """Set the sealed/unsealed state of a zone."""
        zone = next(z for z in self.zones if z.id == zone_id)
        zone.state = state
        if self._zone_state_changed is not None:
            self._zone_state_changed(zone_id, state)

        if self.state == Alarm.ArmingState.ARMED and state == Zone.State.UNSEALED:
            self.trip()

    def panic(self) -> None:
        """Put alarm into Panic alarm state."""
        _LOGGER.info("setting panic")
        self._update_state_no_mode(Alarm.ArmingState.PANIC)

    def duress(self) -> None:
        """Put alarm into Duress alarm state."""
        _LOGGER.info("setting duress")
        self._cancel_pending_update()
        self._update_state_no_mode(Alarm.ArmingState.DURESS)

    def medical(self) -> None:
        """Put alarm into Medical alarm state."""
        self._update_state_no_mode(Alarm.ArmingState.MEDICAL)

    def fire(self) -> None:
        """Put alarm into Fire alarm state."""
        self._update_state_no_mode(Alarm.ArmingState.FIRE)

    def set_aux(self, *, aux_id: int, aux_state: bool) -> None:
        """Set the state of an auxilliary output."""
        if aux_id < Alarm.AUX_ID_MIN or aux_id > Alarm.AUX_ID_MAX:
            msg = "Invalid aux id"
            raise ValueError(msg)
        if self.aux[aux_id - 1] != aux_state:
            self._aux_state_changed(aux_id, aux_state)
        _LOGGER.info("set Aux %s to %s", aux_id, aux_state)
        self.aux[aux_id - 1] = aux_state

    def _cancel_pending_update(self) -> None:
        """Cancel scheduled changes for entry/exit delays."""
        if self._pending_event is not None:
            self._pending_event = None

    def _schedule(self, delay: int, fn: Callable[[], None]) -> None:
        """Schedule a change after a delay - for entry/exit delays."""
        self._cancel_pending_update()
        event = uuid.uuid4().hex
        self._pending_event = event

        def _run() -> None:
            """Run the specified function after a delay."""
            _LOGGER.debug("Alarm._schedule()._run() sleeping for %s", delay)
            time.sleep(delay)
            if event == self._pending_event:
                fn()

        t = threading.Thread(target=_run, name=f"server schedule {fn}")
        t.start()
        self._scheduled_threads.append(t)

    def _update_state(
        self,
        state: ArmingState,
        arming_mode: ArmingMode | None,
    ) -> None:
        """Set the arming state and arming mode."""
        if self._alarm_state_changed is not None:
            self._alarm_state_changed(self.state, state, arming_mode)

        _LOGGER.debug("setting arming state to %s & mode to %s", state, arming_mode)
        self.state = state
        self.arming_mode = arming_mode

    def _update_state_no_mode(
        self,
        state: ArmingState,
    ) -> None:
        """Set the arming state without changing the arming mode."""
        if self._alarm_state_changed is not None:
            self._alarm_state_changed(self.state, state, self.arming_mode)

        _LOGGER.debug("setting arming state to %s", state)
        self.state = state

    def get_state(self) -> ArmingState:
        """Get the current Alarm State."""
        return self.state

    def get_arming_mode(self) -> ArmingMode | None:
        """Get the current Arming Mode."""
        return self.arming_mode
