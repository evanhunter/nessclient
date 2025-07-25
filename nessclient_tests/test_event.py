"""Test encode/decode of various asyncronous events and UI-responses."""

import unittest
from typing import cast

import pytest

from nessclient.event import (
    ArmingUpdate,
    AuxiliaryOutputsUpdate,
    BaseEvent,
    MiscellaneousAlarmsUpdate,
    OutputsUpdate,
    PanelVersionUpdate,
    StatusUpdate,
    SystemStatusEvent,
    ViewStateUpdate,
    ZoneUpdate,
    pack_unsigned_short_data_enum,
)
from nessclient.packet import CommandType, Packet


class UtilsTestCase(unittest.TestCase):
    """Test utility functions."""

    def test_pack_unsigned_short_data_enum(self) -> None:
        """Test that an enum list gets paccked correctly."""
        value = [ZoneUpdate.Zone.ZONE_1, ZoneUpdate.Zone.ZONE_4]
        assert pack_unsigned_short_data_enum(value) == "0900"


class BaseEventTestCase(unittest.TestCase):
    """Test encode/decode via BaseEvent class."""

    def test_decode_system_status_event(self) -> None:
        """Test that Asynchronous System Status packets can be decoded."""
        pkt = make_packet(CommandType.SYSTEM_STATUS, "000000")
        event = BaseEvent.decode(pkt)
        assert isinstance(event, SystemStatusEvent)

    def test_decode_user_interface_event(self) -> None:
        """Test that Status Update UI responses can be decoded."""
        pkt = make_packet(CommandType.USER_INTERFACE, "000000")
        event = BaseEvent.decode(pkt)
        assert isinstance(event, StatusUpdate)

    def test_decode_unknown_event(self) -> None:
        """Test Packet constructor raises an exception for an invalid command."""
        with pytest.raises(ValueError, match=r"Unknown command .*"):
            Packet(
                address=0,
                command=cast("CommandType", 0x01),
                seq=0,
                timestamp=None,
                data="000000",
                is_user_interface_resp=True,
            )


class StatusUpdateTestCase(unittest.TestCase):
    """Test encode/decode usng StatusUpdate class."""

    def test_decode_zone_update(self) -> None:
        """Test that Zone Update UI responses can be decoded."""
        pkt = make_packet(CommandType.USER_INTERFACE, "000000")
        event = StatusUpdate.decode(pkt)
        assert isinstance(event, ZoneUpdate)

    def test_decode_misc_alarms_update(self) -> None:
        """Test that Miscellaneous Alarms Update UI responses can be decoded."""
        pkt = make_packet(CommandType.USER_INTERFACE, "130000")
        event = StatusUpdate.decode(pkt)
        assert isinstance(event, MiscellaneousAlarmsUpdate)

    def test_decode_arming_update(self) -> None:
        """Test that Arming Update UI responses can be decoded."""
        pkt = make_packet(CommandType.USER_INTERFACE, "140000")
        event = StatusUpdate.decode(pkt)
        assert isinstance(event, ArmingUpdate)

    def test_decode_outputs_update(self) -> None:
        """Test that Output Update UI responses can be decoded."""
        pkt = make_packet(CommandType.USER_INTERFACE, "150000")
        event = StatusUpdate.decode(pkt)
        assert isinstance(event, OutputsUpdate)

    def test_decode_view_state_update(self) -> None:
        """Test that View-State Update UI responses can be decoded."""
        pkt = make_packet(CommandType.USER_INTERFACE, "16F000")
        event = StatusUpdate.decode(pkt)
        assert isinstance(event, ViewStateUpdate)

    def test_decode_panel_version_update(self) -> None:
        """Test that Panel-Version Update UI responses can be decoded."""
        pkt = make_packet(CommandType.USER_INTERFACE, "170000")
        event = StatusUpdate.decode(pkt)
        assert isinstance(event, PanelVersionUpdate)

    def test_decode_auxiliary_outputs_update(self) -> None:
        """Test that Auxiliary-Outputs Update UI responses can be decoded."""
        pkt = make_packet(CommandType.USER_INTERFACE, "180000")
        event = StatusUpdate.decode(pkt)
        assert isinstance(event, AuxiliaryOutputsUpdate)

    def test_decode_unknown_update(self) -> None:
        """Test Status Update decoding raises an exception for an invalid request_id."""
        pkt = make_packet(CommandType.USER_INTERFACE, "550000")  # 55 is an invalid ID
        with pytest.raises(
            ValueError, match="55 is not a valid StatusUpdate.RequestID"
        ):
            StatusUpdate.decode(pkt)


class ArmingUpdateTestCase(unittest.TestCase):
    """Test encode/decode of ArmingUpdate."""

    def test_encode(self) -> None:
        """Test that Arming Update UI responses can be encoded with areas."""
        event = ArmingUpdate(
            status=[ArmingUpdate.ArmingStatus.AREA_1_FULLY_ARMED],
            timestamp=None,
            address=0x00,
        )
        pkt = event.encode()
        assert pkt.command == CommandType.USER_INTERFACE
        assert pkt.data == "140400"
        assert pkt.is_user_interface_resp

    def test_area1_armed(self) -> None:
        """Test that Arming Update UI responses can be decoded with areas."""
        pkt = make_packet(CommandType.USER_INTERFACE, "140500")
        event = ArmingUpdate.decode(pkt)
        assert event.status == [
            ArmingUpdate.ArmingStatus.AREA_1_ARMED,
            ArmingUpdate.ArmingStatus.AREA_1_FULLY_ARMED,
        ]


class ZoneUpdateTestCase(unittest.TestCase):
    """Test encode/decode of ZoneUpdate."""

    def test_encode(self) -> None:
        """Test that Zone Unsealed UI responses can be encoded with zones."""
        event = ZoneUpdate(
            included_zones=[ZoneUpdate.Zone.ZONE_1, ZoneUpdate.Zone.ZONE_3],
            request_id=StatusUpdate.RequestID.ZONE_INPUT_UNSEALED,
            timestamp=None,
            address=0x00,
        )
        pkt = event.encode()
        assert pkt.command == CommandType.USER_INTERFACE
        assert pkt.data == "000500"
        assert pkt.is_user_interface_resp

    def test_zone_in_delay_no_zones(self) -> None:
        """Test that Zone In-Delay UI responses can be decoded with no zones."""
        pkt = make_packet(CommandType.USER_INTERFACE, "030000")
        event = ZoneUpdate.decode(pkt)
        assert event.request_id == ZoneUpdate.RequestID.ZONE_IN_DELAY
        assert event.included_zones == []

    def test_zone_in_delay_with_zones(self) -> None:
        """Test that Zone In-Delay UI responses can be decoded with zones."""
        pkt = make_packet(CommandType.USER_INTERFACE, "030500")
        event = ZoneUpdate.decode(pkt)
        assert event.request_id == ZoneUpdate.RequestID.ZONE_IN_DELAY
        assert event.included_zones == [ZoneUpdate.Zone.ZONE_1, ZoneUpdate.Zone.ZONE_3]

    def test_zone_in_alarm_with_zones(self) -> None:
        """Test that Zone In-Alarm UI responses can be decoded with zones."""
        pkt = make_packet(CommandType.USER_INTERFACE, "051400")
        event = ZoneUpdate.decode(pkt)
        assert event.request_id == ZoneUpdate.RequestID.ZONE_IN_ALARM
        assert event.included_zones == [ZoneUpdate.Zone.ZONE_3, ZoneUpdate.Zone.ZONE_5]


class ViewStateUpdateTestCase(unittest.TestCase):
    """Test encode/decode of ViewStateUpdate."""

    def test_normal_state(self) -> None:
        """Test that View-State UI responses can be decoded when Normal."""
        pkt = make_packet(CommandType.USER_INTERFACE, "16F000")
        event = ViewStateUpdate.decode(pkt)
        assert event.state == ViewStateUpdate.State.NORMAL


class OutputsUpdateTestCase(unittest.TestCase):
    """Test encode/decode of OutputsUpdate."""

    def test_some_outputs(self) -> None:
        """Test that Outputs-State UI responses can be decoded with a few outputs."""
        pkt = make_packet(CommandType.USER_INTERFACE, "157100")
        event = OutputsUpdate.decode(pkt)
        assert event.outputs == [
            OutputsUpdate.OutputType.SIREN_LOUD,
            OutputsUpdate.OutputType.STROBE,
            OutputsUpdate.OutputType.RESET,
            OutputsUpdate.OutputType.SONALART,
        ]


class MiscellaneousAlarmsUpdateTestCase(unittest.TestCase):
    """Test encode/decode of MiscellaneousAlarmsUpdate."""

    def test_misc_alarms_install_end(self) -> None:
        """Test that Misc-Alarms UI responses can be decoded with Install-End."""
        pkt = make_packet(CommandType.USER_INTERFACE, "131000")
        event = MiscellaneousAlarmsUpdate.decode(pkt)
        assert event.included_alarms == [
            MiscellaneousAlarmsUpdate.AlarmType.INSTALL_END
        ]

    def test_misc_alarms_panic(self) -> None:
        """Test that Misc-Alarms UI responses can be decoded with Panic."""
        pkt = make_packet(CommandType.USER_INTERFACE, "130200")
        event = MiscellaneousAlarmsUpdate.decode(pkt)
        assert event.included_alarms == [MiscellaneousAlarmsUpdate.AlarmType.PANIC]

    def test_misc_alarms_multi(self) -> None:
        """Test that Misc-Alarms UI responses can be decoded with several items."""
        pkt = make_packet(CommandType.USER_INTERFACE, "131500")
        event = MiscellaneousAlarmsUpdate.decode(pkt)
        assert event.included_alarms == [
            MiscellaneousAlarmsUpdate.AlarmType.DURESS,
            MiscellaneousAlarmsUpdate.AlarmType.MEDICAL,
            MiscellaneousAlarmsUpdate.AlarmType.INSTALL_END,
        ]


class SystemStatusEventTestCase(unittest.TestCase):
    """Test encode/decode of async SystemStatusEvent packets."""

    def test_exit_delay_end(self) -> None:
        """Test that Exit-Delay-End events can be decoded for area+zone."""
        pkt = make_packet(CommandType.SYSTEM_STATUS, "230001")
        event = SystemStatusEvent.decode(pkt)
        assert event.area == 1
        assert event.zone == 0
        assert event.type == SystemStatusEvent.EventType.EXIT_DELAY_END

    def test_zone_sealed(self) -> None:
        """Test that Zone-Sealed events can be decoded for zone."""
        pkt = make_packet(CommandType.SYSTEM_STATUS, "010500")
        event = SystemStatusEvent.decode(pkt)
        assert event.area == 0
        assert event.zone == 5  # noqa: PLR2004
        assert event.type == SystemStatusEvent.EventType.SEALED

    def test_zone_unsealed_with_zone_15(self) -> None:
        """Test that Zone-Unsealed events can be decoded for high zone."""
        pkt = make_packet(CommandType.SYSTEM_STATUS, "001500")
        event = SystemStatusEvent.decode(pkt)
        assert event.area == 0
        assert event.zone == 15  # noqa: PLR2004
        assert event.type == SystemStatusEvent.EventType.UNSEALED

    def test_zone_unsealed_with_zone_16(self) -> None:
        """Test that Zone-Unsealed events can be decoded for last zone."""
        pkt = make_packet(CommandType.SYSTEM_STATUS, "001600")
        event = SystemStatusEvent.decode(pkt)
        assert event.area == 0
        assert event.zone == 16  # noqa: PLR2004
        assert event.type == SystemStatusEvent.EventType.UNSEALED


class PanelVersionUpdateTestCase(unittest.TestCase):
    """Test encode/decode of PanelVersionUpdate class."""

    def test_model(self) -> None:
        """Test that Panel-Version response can be decoded for D16X."""
        pkt = make_packet(CommandType.USER_INTERFACE, "160000")
        event = PanelVersionUpdate.decode(pkt)
        assert event.model == PanelVersionUpdate.Model.D16X

    def test_3g_model(self) -> None:
        """Test that Panel-Version response can be decoded for D16X-3G."""
        pkt = make_packet(CommandType.USER_INTERFACE, "160400")
        event = PanelVersionUpdate.decode(pkt)
        assert event.model == PanelVersionUpdate.Model.D16X_3G

    def test_sw_version(self) -> None:
        """Test that Panel-Version response can be decoded for particular version."""
        pkt = make_packet(CommandType.USER_INTERFACE, "160086")
        event = PanelVersionUpdate.decode(pkt)
        assert event.major_version == 8  # noqa: PLR2004
        assert event.minor_version == 6  # noqa: PLR2004
        assert event.version == "8.6"


class AuxiliaryOutputsUpdateTestCase(unittest.TestCase):
    """Test encode/decode of async AuxiliaryOutputsUpdate packets."""

    def test_aux_output_1(self) -> None:
        """Test that Aux-Outputs events can be decoded with one output."""
        pkt = make_packet(CommandType.USER_INTERFACE, "170001")
        event = AuxiliaryOutputsUpdate.decode(pkt)
        assert event.outputs == [
            AuxiliaryOutputsUpdate.OutputType.AUX_1,
        ]

    def test_aux_output_4(self) -> None:
        """Test that Aux-Outputs events can be decoded with a different output."""
        pkt = make_packet(CommandType.USER_INTERFACE, "170008")
        event = AuxiliaryOutputsUpdate.decode(pkt)
        assert event.outputs == [
            AuxiliaryOutputsUpdate.OutputType.AUX_4,
        ]

    def test_aux_output_multi(self) -> None:
        """Test that Aux-Outputs events can be decoded with two outputs."""
        pkt = make_packet(CommandType.USER_INTERFACE, "170088")
        event = AuxiliaryOutputsUpdate.decode(pkt)
        assert event.outputs == [
            AuxiliaryOutputsUpdate.OutputType.AUX_4,
            AuxiliaryOutputsUpdate.OutputType.AUX_8,
        ]


def make_packet(command: CommandType, data: str) -> Packet:
    """Make a test packet - convenience function."""
    return Packet(
        address=0,
        command=command,
        seq=0,
        timestamp=None,
        data=data,
        is_user_interface_resp=True,
    )
