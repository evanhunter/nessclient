"""Provides an in-memory representation of the state of the NESS alarm device."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from .event import ArmingUpdate, BaseEvent, SystemStatusEvent, ZoneUpdate

_LOGGER = logging.getLogger(__name__)


class ArmingState(Enum):
    """Arming States used with on_state_change() callback."""

    UNKNOWN = "UNKNOWN"
    DISARMED = "DISARMED"
    ARMING = "ARMING"
    EXIT_DELAY = "EXIT_DELAY"
    ARMED = "ARMED"
    ENTRY_DELAY = "ENTRY_DELAY"
    TRIGGERED = "TRIGGERED"


class ArmingMode(Enum):
    """Armed Modes used with on_state_change() callback."""

    ARMED_AWAY = "ARMED_AWAY"
    ARMED_HOME = "ARMED_HOME"
    ARMED_DAY = "ARMED_DAY"
    ARMED_NIGHT = "ARMED_NIGHT"
    ARMED_VACATION = "ARMED_VACATION"
    ARMED_HIGHEST = "ARMED_HIGHEST"


class ZoneSealedState(Enum):
    """Zone sealed states - either sealed or unseald."""

    SEALED = False
    UNSEALED = True


ARM_EVENTS_MAP = {
    SystemStatusEvent.EventType.ARMED_AWAY: ArmingMode.ARMED_AWAY,
    SystemStatusEvent.EventType.ARMED_HOME: ArmingMode.ARMED_HOME,
    SystemStatusEvent.EventType.ARMED_DAY: ArmingMode.ARMED_DAY,
    SystemStatusEvent.EventType.ARMED_NIGHT: ArmingMode.ARMED_NIGHT,
    SystemStatusEvent.EventType.ARMED_VACATION: ArmingMode.ARMED_VACATION,
    SystemStatusEvent.EventType.ARMED_HIGHEST: ArmingMode.ARMED_HIGHEST,
}


class Alarm:
    """In-memory representation of the state of the alarm the client is connected to."""

    @dataclass
    class Zone:
        """Represents the current sealed state for an alarm zone."""

        triggered: bool | None

    def __init__(self, *, infer_arming_state: bool = False) -> None:
        """Create a new Alarm instance."""
        self._infer_arming_state = infer_arming_state
        self.arming_state: ArmingState = ArmingState.UNKNOWN
        self.zones: list[Alarm.Zone] = [Alarm.Zone(triggered=None) for _ in range(16)]

        self._arming_mode: ArmingMode | None = None

        self._on_state_change: (
            Callable[[ArmingState, ArmingMode | None], None] | None
        ) = None

        self._on_zone_change: Callable[[int, bool], None] | None = None

    def handle_event(self, event: BaseEvent) -> None:
        """
        Forward event to appropriate handlers.

        Handlers will keep alarm state up-to-date and call callbacks as needed
        """
        if isinstance(event, ArmingUpdate):
            self._handle_arming_update(event)
        elif (
            isinstance(event, ZoneUpdate)
            and event.request_id == ZoneUpdate.RequestID.ZONE_INPUT_UNSEALED
        ):
            self._handle_zone_input_update(event)
        elif (
            isinstance(event, ZoneUpdate)
            and event.request_id == ZoneUpdate.RequestID.ZONE_IN_ALARM
        ):
            self._handle_zone_alarm_update(event)
        elif isinstance(event, SystemStatusEvent):
            self._handle_system_status_event(event)
        else:
            # Other StatusUpdate types: MiscellaneousAlarmsUpdate,
            # OutputsUpdate, ViewStateUpdate, PanelVersionUpdate,
            # AuxiliaryOutputsUpdate
            _LOGGER.debug("Not handling event %s", event)

    def _handle_arming_update(self, update: ArmingUpdate) -> None:
        # Note: ArmingUpdate cannot indicate whether the alarm is currently triggered
        #       This can only be obtained from the ZONE_IN_ALARM ZoneUpdate StatusUpdate
        #       or from the ALARM System-Status Event

        _LOGGER.debug(
            "Handling ArmingUpdate - current state: %s  update: %s",
            self.arming_state,
            update,
        )
        if self.arming_state == ArmingState.TRIGGERED:
            # Skip update, since we cannot determine from this message whether the
            # alarm is still triggered
            pass
        elif update.status == [ArmingUpdate.ArmingStatus.AREA_1_ARMED]:
            self._update_arming_state(ArmingState.EXIT_DELAY)
        elif (
            ArmingUpdate.ArmingStatus.AREA_1_ARMED in update.status
            and ArmingUpdate.ArmingStatus.AREA_1_FULLY_ARMED in update.status
        ):
            self._update_arming_state(ArmingState.ARMED)
        elif self._infer_arming_state:
            # State inference is enabled. Therefore the arming state can
            # only be reverted to disarmed via a system status event.
            # This works around a bug with some panels (<v5.8) which emit
            # update.status = [] when they are armed.
            # TODO(NW): It would be ideal to find a better way to  # noqa: FIX002, TD003
            #  query this information on-demand, but for now this should
            #  resolve the issue.
            if self.arming_state == ArmingState.UNKNOWN:
                self._update_arming_state(ArmingState.DISARMED)
            else:
                pass
        else:
            # State inference is disabled, therefore we can assume the
            # panel is "disarmed" as it did not have any arming flags set
            # in the arming update status as per the documentation.
            # Note: This may not be correct and may not correctly represent
            # other modes of arming other than ARMED_AWAY.
            # TODO(NW): Perform some testing to determine how the # noqa: FIX002, TD003
            #  client handles other arming modes.
            self._update_arming_state(ArmingState.DISARMED)

    def _handle_zone_input_update(self, update: ZoneUpdate) -> None:
        """Handle Zone Unsealed updates."""
        _LOGGER.debug("Handling Zone Input Update - update: %s", update)
        for i in range(len(self.zones)):
            zone_id = i + 1
            name = f"ZONE_{zone_id}"
            zone_state = ZoneUpdate.Zone[name] in update.included_zones
            _LOGGER.debug("Zone update id:%s state:%s", zone_id, zone_state)
            self._update_zone(zone_id=zone_id, state=zone_state)

    def _handle_zone_alarm_update(self, update: ZoneUpdate) -> None:
        _LOGGER.debug("Handling Zone Alarm ZoneUpdate - update: %s", update)
        for i in range(len(self.zones)):
            zone_id = i + 1
            name = f"ZONE_{zone_id}"
            if ZoneUpdate.Zone[name] in update.included_zones:
                self._update_arming_state(ArmingState.TRIGGERED)
                return

        # No zones are in alarm - if the current state is triggered, set
        # it back to unknown so a subsequent ArmingUpdate can set it correctly
        if self.arming_state == ArmingState.TRIGGERED:
            self._update_arming_state(ArmingState.UNKNOWN)

    def _handle_system_status_event(self, event: SystemStatusEvent) -> None:  # noqa: PLR0912 # No easy way to reduce branching
        """
        Handle a system status event received from the Ness Alarm.

        Update the internal state to match the Ness Alarm

        DISARMED -> ARMED_AWAY -> EXIT_DELAY_START -> EXIT_DELAY_END
         (trip): -> ALARM -> OUTPUT_ON -> ALARM_RESTORE
            (disarm): -> DISARMED -> OUTPUT_OFF
         (disarm): -> DISARMED
         (disarm before EXIT_DELAY_END): -> DISARMED -> EXIT_DELAY_END

        TODO(NW): Check ALARM_RESTORE state transition to move back
                  into ARMED_AWAY state
        """
        _LOGGER.debug(
            "Handling ArmingUpdate - current state: %s  event: %s",
            self.arming_state,
            event,
        )

        if event.type == SystemStatusEvent.EventType.UNSEALED:
            self._update_zone(zone_id=event.zone, state=True)
        elif event.type == SystemStatusEvent.EventType.SEALED:
            self._update_zone(zone_id=event.zone, state=False)
        elif event.type == SystemStatusEvent.EventType.ALARM:
            self._update_arming_state(ArmingState.TRIGGERED)
        elif event.type == SystemStatusEvent.EventType.ALARM_RESTORE:
            if self.arming_state != ArmingState.DISARMED:
                self._update_arming_state(ArmingState.ARMED)
            else:
                pass
        elif event.type == SystemStatusEvent.EventType.ENTRY_DELAY_START:
            self._update_arming_state(ArmingState.ENTRY_DELAY)
        elif event.type == SystemStatusEvent.EventType.ENTRY_DELAY_END:
            pass
        elif event.type == SystemStatusEvent.EventType.EXIT_DELAY_START:
            self._update_arming_state(ArmingState.EXIT_DELAY)
        elif event.type == SystemStatusEvent.EventType.EXIT_DELAY_END:
            # Exit delay finished - if we were in the process of arming update
            # state to armed
            if self.arming_state == ArmingState.EXIT_DELAY:
                self._update_arming_state(ArmingState.ARMED)
            else:
                pass
        elif event.type in ARM_EVENTS_MAP:
            self._arming_mode = ARM_EVENTS_MAP[event.type]
            self._update_arming_state(ArmingState.ARMING)
        elif event.type == SystemStatusEvent.EventType.DISARMED:
            self._arming_mode = None  # Restore arming mode on disarmed.
            self._update_arming_state(ArmingState.DISARMED)
        elif event.type == SystemStatusEvent.EventType.ARMING_DELAYED:
            pass

    def _update_arming_state(self, state: ArmingState) -> None:
        if self.arming_state != state:
            self.arming_state = state
            if self._on_state_change is not None:
                self._on_state_change(state, self._arming_mode)

    def _update_zone(self, *, zone_id: int, state: bool) -> None:
        zone = self.zones[zone_id - 1]
        if zone.triggered != state:
            _LOGGER.debug("Zone %s change state:%s->%s", zone_id, zone.triggered, state)
            zone.triggered = state
            if self._on_zone_change is not None:
                self._on_zone_change(zone_id, state)

    def on_state_change(
        self, f: Callable[[ArmingState, ArmingMode | None], None] | None
    ) -> None:
        """Set the callback that receives Arming state/mode updates."""
        self._on_state_change = f

    def on_zone_change(self, f: Callable[[int, bool], None] | None) -> None:
        """Set the callback that receives Zone sealed/unsealed updates."""
        self._on_zone_change = f
