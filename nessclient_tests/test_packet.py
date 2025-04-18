import datetime
import logging
import unittest
from pathlib import Path

import pytest

from nessclient import BaseEvent
from nessclient.event import PanelVersionUpdate, StatusUpdate, SystemStatusEvent
from nessclient.packet import CommandType, Packet
from nessclient_tests.fixtures.generate_test_packets import (
    TestPacketWithDescription,
    gemerate_input_to_ness_user_interface_valid_packets,
    gemerate_output_from_ness_event_data_valid_packets,
    gemerate_output_from_ness_status_update_valid_packets,
)
from nessclient_tests.fixtures.real_captured_test_data import (
    Output_From_Ness_Event_Data_Real_Packets,
    Output_From_Ness_Status_Update_Real_Packets,
)

_LOGGER = logging.getLogger(__name__)

logging.basicConfig(
    format="%(asctime)s.%(msecs)03d %(threadName)-25s %(levelname)-8s %(message)s",
    level=logging.DEBUG,
    datefmt="%Y-%m-%d %H:%M:%S",
)


class PacketTestCase(unittest.TestCase):
    def test_decode_encode_identity(self) -> None:
        cases = ["8300C6012345678912E07\r\n"]

        for case in cases:
            pkt = Packet.decode(case)
            assert case == pkt.encode()

    def test_decode(self) -> None:
        samples_fixture = Path(__file__).parent / "fixtures" / "sample_output.txt"
        with Path.open(samples_fixture) as f:
            for line in f:
                fixed_line = line.strip() + "\r\n"
                pkt = Packet.decode(fixed_line)
                _LOGGER.info("Decoded '%s' into %s", fixed_line, pkt)

    def test_create_bad_packets(self) -> None:
        # Bad Input (to Ness) User-Interface Packets
        # Zero Length
        with pytest.raises(
            ValueError,
            match=r"Data length of a User-Interface "
            r"Packet must be in the range .*",
        ):
            Packet(address=0, command=CommandType.USER_INTERFACE, data="")

        # Too Long (37 chars)
        with pytest.raises(
            ValueError,
            match=r"Data length of a User-Interface "
            r"Packet must be in the range .*",
        ):
            Packet(
                address=0,
                command=CommandType.USER_INTERFACE,
                data="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            )

        # Has a disallowed 'B' character
        with pytest.raises(
            ValueError,
            match=r"Data characters of a User-Interface Packet must be one of.*",
        ):
            Packet(address=0, command=CommandType.USER_INTERFACE, data="B2345678912E")

        # Has a disallowed '\xAA' character
        with pytest.raises(
            ValueError,
            match=r"Data characters of a User-Interface Packet must be one of.*",
        ):
            Packet(
                address=0, command=CommandType.USER_INTERFACE, data="\xaa2345678912E"
            )

        # Has address = None
        self.assertRaises(
            ValueError,
            lambda: Packet(
                address=None, command=CommandType.USER_INTERFACE, data="12345678912E"
            ),
        )
        # Has a Timestamp (not allowed)
        self.assertRaises(
            ValueError,
            lambda: Packet(
                address=0,
                command=CommandType.USER_INTERFACE,
                timestamp=datetime.datetime(  # noqa: DTZ001 - local timezone - No function available
                    year=2018, month=9, day=21, hour=18, minute=37, second=9
                ),
                data="12345678912E",
            ),
        )
        # Has a non-zero sequence
        self.assertRaises(
            ValueError,
            lambda: Packet(
                address=0,
                command=CommandType.USER_INTERFACE,
                data="12345678912E",
                seq=1,
            ),
        )
        # Address too large
        self.assertRaises(
            ValueError,
            lambda: Packet(
                address=30, command=CommandType.USER_INTERFACE, data="12345678912E"
            ),
        )

        # Bad Output (from Ness) Status Update Packets
        # (Response to a User-Interface Status Request Packet)
        # Wrong length (!=6)
        self.assertRaises(
            ValueError,
            lambda: Packet(
                address=0,
                command=CommandType.USER_INTERFACE,
                data="0000000000",
                is_user_interface_resp=True,
            ),
        )
        # Non-Hex character 'X'
        self.assertRaises(
            ValueError,
            lambda: Packet(
                address=0,
                command=CommandType.USER_INTERFACE,
                data="X00000",
                is_user_interface_resp=True,
            ),
        )
        # Has address = None
        self.assertRaises(
            ValueError,
            lambda: Packet(
                address=None,
                command=CommandType.USER_INTERFACE,
                data="000000",
                is_user_interface_resp=True,
            ),
        )
        # Has a Timestamp (not allowed)
        self.assertRaises(
            ValueError,
            lambda: Packet(
                address=0,
                command=CommandType.USER_INTERFACE,
                timestamp=datetime.datetime(  # noqa: DTZ001 - local timezone - No function available
                    year=2018, month=9, day=21, hour=18, minute=37, second=9
                ),
                data="000000",
                is_user_interface_resp=True,
            ),
        )
        # Has a non-zero sequence
        self.assertRaises(
            ValueError,
            lambda: Packet(
                address=0,
                command=CommandType.USER_INTERFACE,
                data="000000",
                is_user_interface_resp=True,
                seq=1,
            ),
        )
        # Address too large
        self.assertRaises(
            ValueError,
            lambda: Packet(
                address=30,
                command=CommandType.USER_INTERFACE,
                data="000000",
                is_user_interface_resp=True,
            ),
        )
        # Has dis-allowed delay marker
        self.assertRaises(
            ValueError,
            lambda: Packet(
                address=0,
                command=CommandType.USER_INTERFACE,
                data="000000",
                is_user_interface_resp=True,
                has_delay_marker=True,
            ),
        )

        # Bad Output (from Ness) Event Data Packets
        # Wrong length (!=6)
        self.assertRaises(
            ValueError,
            lambda: Packet(
                address=0, command=CommandType.SYSTEM_STATUS, data="0000000000"
            ),
        )
        # Non-Hex character 'X'
        self.assertRaises(
            ValueError,
            lambda: Packet(address=0, command=CommandType.SYSTEM_STATUS, data="X00000"),
        )
        # Address too large
        self.assertRaises(
            ValueError,
            lambda: Packet(
                address=30, command=CommandType.SYSTEM_STATUS, data="000000"
            ),
        )
        # Has dis-allowed delay marker
        self.assertRaises(
            ValueError,
            lambda: Packet(
                address=0,
                command=CommandType.SYSTEM_STATUS,
                data="000000",
                has_delay_marker=True,
            ),
        )

    def test_decode_bad_packets(self) -> None:
        cases = [
            # UI request packets
            "8300c60",  # short packet truncated
            "8300c6012345678912EE7",  # missing CRLF
            "8300f6012345678912EE4\r\n",  # length too long for data
            "830056012345678912E15\r\n",  # length too short for data
            "8300c6012345678912EX7\r\n",  # Non Hex character in checksum
            "8300c6012345678912EE8\r\n",  # Bad checksum (should be E7)
            "8300c6012345678912Ee7\r\n",  # Bad checksum (must be upper case)
            "8300c60B2345678912E42A\r\n",  # Has a disallowed 'B' character
            "8300c60\xaa2345678912E92\r\n",  # Has a disallowed '\xAA' character
            "83000609F\r\n",  # Zero length
            "8302560AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA33\r\n",  # 37 length  (too long)
            # Bad Output (from Ness) Status Update Packets
            # Bad checksum
            "820003600000001a\r\n",
            # Wrong length (!=6)
            "82000460000000001a\r\n",
            # Non-Hex character 'X'
            # checksum is also wrong, since it can't be calculated here
            "82000360X000001b\r\n",
            # Has a Timestamp (not allowed)
            "82000360000000061201074300b8\r\n",
            # Has a non-zero sequence
            "820083600000009b\r\n",
            # Address too large
            "8215036000000006\r\n",
            # Has dis-allowed delay marker
            "820003600000001b?\r\n",
            # Bad Output (from Ness) Event Data Packets
            # Bad checksum
            "8204610000000018\r\n"
            "830004610000000017\r\n"
            "860461000000180921183709007a\r\n"
            "870004610000001809211837090079\r\n"
            # Wrong length (!=6)
            "8204610000000019\r\n"
            "830004610000000018\r\n"
            "860461000000180921183709007b\r\n"
            "87000461000000180921183709007a\r\n"
            # Non-Hex character 'X'
            # checksum is also wrong, since it can't be calculated here
            "820361X000001a\r\n"
            "83000361X0000019\r\n"
            "860361X000001809211837097c\r\n"
            "87000361X000001809211837097b\r\n"
            # Address too large
            "8315036100000004\r\n"
            "8715036100000018092118370966\r\n"
            # Has dis-allowed delay marker
            "8203610000001a?\r\n"
            "8300036100000019?\r\n"
            "8603610000001809211837097c?\r\n"
            "870003610000001809211837097b?\r\n",
        ]

        for case in cases:
            self.assertRaises(ValueError, lambda: Packet.decode(case))

    def test_user_interface_packet_decode(self) -> None:
        pkt = Packet.decode("8300C6012345678912E07\r\n")
        assert pkt.start == 0x83
        assert pkt.address == 0x00
        assert pkt.length == 12
        assert pkt.seq == 0x00
        assert pkt.command == CommandType.USER_INTERFACE
        assert pkt.data == "12345678912E"
        assert pkt.timestamp is None
        assert pkt.checksum == 0x07

    def test_system_status_packet_decode(self) -> None:
        pkt = Packet.decode("8700036100070018092118370974\r\n")
        assert pkt.start == 0x87
        assert pkt.address == 0x00
        assert pkt.length == 3
        assert pkt.seq == 0x00
        assert pkt.command == CommandType.SYSTEM_STATUS
        assert pkt.data == "000700"
        assert pkt.timestamp == datetime.datetime(  # noqa: DTZ001 - local timezone - No function available
            year=2018, month=9, day=21, hour=18, minute=37, second=9
        )
        # assert pkt.checksum, 0x74)

    def test_decode_with_address_and_time(self) -> None:
        pkt = Packet.decode("8709036101050018122709413536\r\n")
        assert pkt.address == 0x09
        assert pkt.length == 3
        assert pkt.seq == 0x00
        assert pkt.command == CommandType.SYSTEM_STATUS
        assert pkt.data == "010500"
        assert pkt.timestamp == datetime.datetime(  # noqa: DTZ001 - local timezone - No function available
            year=2018, month=12, day=27, hour=9, minute=41, second=35
        )
        assert not pkt.is_user_interface_resp

    def test_decode_without_address(self) -> None:
        pkt = Packet.decode("820361230001f6\r\n")
        assert pkt.address is None
        assert pkt.length == 3
        assert pkt.seq == 0x00
        assert pkt.command == CommandType.SYSTEM_STATUS
        assert pkt.data == "230001"
        assert pkt.timestamp is None
        assert not pkt.is_user_interface_resp

    def test_decode_with_address(self) -> None:
        pkt = Packet.decode("820003600000001b\r\n")
        assert pkt.address == 0x00
        assert pkt.length == 3
        assert pkt.seq == 0x00
        assert pkt.command == CommandType.USER_INTERFACE
        assert pkt.data == "000000"
        assert pkt.timestamp is None
        assert pkt.is_user_interface_resp

    def test_encode_decode1(self) -> None:
        """Tests encoding then decoding a UI request packet."""
        data = "A1234E"
        pkt = Packet(
            address=0x00,
            seq=0x00,
            command=CommandType.USER_INTERFACE,
            data=data,
            timestamp=None,
        )
        assert pkt.length == len(data)
        assert pkt.encode() == "8300660A1234E49\r\n"

    def test_encode_decode2(self) -> None:
        """Tests encoding then decoding another UI request packet."""
        data = "000100"
        pkt = Packet(
            address=0x00,
            seq=0x00,
            command=CommandType.USER_INTERFACE,
            data=data,
            timestamp=None,
        )
        assert pkt.length == len(data)
        assert pkt.encode() == "830066000010078\r\n"
        assert Packet.decode(pkt.encode()) == pkt

    def test_decode_status_update_response(self) -> None:
        """Test decoding a Status Update UI response packet."""
        pkt = Packet.decode("8200036007000014\r\n")
        assert (
            pkt.start == Packet.START_BYTE_ASCII_FORMAT | Packet.START_BYTE_BASIC_HEADER
        )
        assert pkt.address == 0x00
        assert pkt.length == Packet.USER_INTERFACE_RESPONSE_DATA_SIZE / 2
        assert pkt.seq == 0x00
        assert pkt.command == CommandType.USER_INTERFACE
        assert pkt.data == "070000"
        assert pkt.timestamp is None
        # assert pkt.checksum, 0x14)

    def test_bad_timestamp(self) -> None:
        pkt = Packet.decode("8700036100070019022517600057\r\n")
        assert pkt.start == 0x87
        assert pkt.address == 0x00
        assert pkt.length == 3
        assert pkt.seq == 0x00
        assert pkt.command == CommandType.SYSTEM_STATUS
        assert pkt.data == "000700"
        assert pkt.timestamp == datetime.datetime(  # noqa: DTZ001 - local timezone - No function available
            year=2019, month=2, day=25, hour=18, minute=0, second=0
        )

    def test_decode_zone_16(self) -> None:
        pkt = Packet.decode("8700036100160019022823032274\r\n")
        assert pkt.start == 0x87
        assert pkt.address == 0x00
        assert pkt.length == 3
        assert pkt.seq == 0x00
        assert pkt.command == CommandType.SYSTEM_STATUS
        assert pkt.data == "001600"
        assert pkt.timestamp == datetime.datetime(  # noqa: DTZ001 - local timezone - No function available
            year=2019, month=2, day=28, hour=23, minute=3, second=22
        )

    def test_decode_update(self) -> None:
        pkt = Packet.decode("820003601700867e\r\n")
        event = BaseEvent.decode(pkt)
        assert pkt.start == 0x82
        assert pkt.address == 0x00
        assert pkt.length == 3
        assert pkt.seq == 0x00
        assert pkt.command == CommandType.USER_INTERFACE
        assert pkt.data == "170086"
        assert pkt.is_user_interface_resp

        assert isinstance(event, PanelVersionUpdate)
        assert event.model == PanelVersionUpdate.Model.D16X
        assert event.major_version == 8
        assert event.minor_version == 6


class PacketTestRealPackets(unittest.TestCase):
    def test_decode_encode_real_event_packets(self) -> None:
        for pktdata in Output_From_Ness_Event_Data_Real_Packets:
            pkt = Packet.decode(pktdata.decode("ascii"))
            event = BaseEvent.decode(pkt)
            assert isinstance(event, SystemStatusEvent)
            assert event.encode().encode().encode("ascii") == pktdata

    def test_decode_encode_real_status_packets(self) -> None:
        for pktdata in Output_From_Ness_Status_Update_Real_Packets:
            pkt = Packet.decode(pktdata.decode("ascii"))
            event = BaseEvent.decode(pkt)
            assert isinstance(event, StatusUpdate)
            assert event.encode().encode().encode("ascii") == pktdata


class PacketTestGeneratedPackets(unittest.TestCase):
    def test_decode_encode_generated_ui_input_packets(self) -> None:
        for test_item in gemerate_input_to_ness_user_interface_valid_packets():
            pkt = Packet.decode(test_item.packet_chars)
            assert pkt.encode() == test_item.packet_chars

    def test_decode_encode_generated_ui_response_packets(self) -> None:
        for test_pkt in gemerate_output_from_ness_status_update_valid_packets():
            pkt = Packet.decode(test_pkt.packet_chars)
            event = BaseEvent.decode(pkt)
            assert isinstance(event, StatusUpdate)
            assert pkt.encode() == test_pkt.packet_chars

    def test_decode_encode_generated_status_packets(self) -> None:
        for test_pkt in gemerate_output_from_ness_event_data_valid_packets():
            pkt = Packet.decode(test_pkt.packet_chars)
            event = BaseEvent.decode(pkt)
            assert isinstance(event, SystemStatusEvent)
            assert event.encode().encode() == test_pkt.packet_chars
