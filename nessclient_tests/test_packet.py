"""Test encode/decode of Packets."""

import datetime
import logging
import unittest
from pathlib import Path

import pytest

from nessclient import BaseEvent
from nessclient.event import PanelVersionUpdate, StatusUpdate, SystemStatusEvent
from nessclient.packet import CommandType, Packet
from nessclient_tests.fixtures.generate_test_packets import (
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
    """Test many constant packets."""

    def test_decode_encode_identity(self) -> None:
        """Test decoding and re-encoding a simple packet."""
        cases = ["8300C6012345678912E07\r\n"]

        for case in cases:
            pkt = Packet.decode(case)
            assert case == pkt.encode()

    def test_decode(self) -> None:
        """Test decoding of packets in the sample_output.txt file."""
        samples_fixture = Path(__file__).parent / "fixtures" / "sample_output.txt"
        with Path.open(samples_fixture) as f:
            for line in f:
                fixed_line = line.strip() + "\r\n"
                pkt = Packet.decode(fixed_line)
                _LOGGER.info("Decoded '%s' into %s", fixed_line, pkt)

    def test_create_bad_packets(self) -> None:
        """Test various bad UI request packets and check exceptions."""
        # Bad Input (to Ness) User-Interface Packets
        # Zero Length
        with pytest.raises(
            ValueError,
            match=r"Data length of a User-Interface Packet must be in the range .*",
        ):
            Packet(address=0, command=CommandType.USER_INTERFACE, data="")

        # Too Long (37 chars)
        with pytest.raises(
            ValueError,
            match=r"Data length of a User-Interface Packet must be in the range .*",
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
        with pytest.raises(
            ValueError,
            match=r"User-Interface Packet must have an address - got None",
        ):
            Packet(
                address=None, command=CommandType.USER_INTERFACE, data="12345678912E"
            )

        # Has a Timestamp (not allowed)
        with pytest.raises(
            ValueError,
            match=r"User-Interface Packet must not have a timestamp .*",
        ):
            Packet(
                address=0,
                command=CommandType.USER_INTERFACE,
                timestamp=datetime.datetime(  # noqa: DTZ001 - local timezone, No fn
                    year=2018, month=9, day=21, hour=18, minute=37, second=9
                ),
                data="12345678912E",
            )

        # Has a non-zero sequence
        with pytest.raises(
            ValueError,
            match=r"User-Interface Packet do not use sequence - it must be zero.*",
        ):
            Packet(
                address=0,
                command=CommandType.USER_INTERFACE,
                data="12345678912E",
                seq=1,
            )

        # Address too large
        with pytest.raises(
            ValueError,
            match=r"Address must be in the range 0- 15 if provided - got 30",
        ):
            Packet(address=30, command=CommandType.USER_INTERFACE, data="12345678912E")

        # Bad Output (from Ness) Status Update Packets
        # (Response to a User-Interface Status Request Packet)
        # Wrong length (!=6)
        with pytest.raises(
            ValueError,
            match=r"Data length of a User-Interface status update response must be 6*",
        ):
            Packet(
                address=0,
                command=CommandType.USER_INTERFACE,
                data="0000000000",
                is_user_interface_resp=True,
            )

        # Non-Hex character 'X'
        with pytest.raises(
            ValueError,
            match=r"Data of a User-Interface status update response must be hex.*",
        ):
            Packet(
                address=0,
                command=CommandType.USER_INTERFACE,
                data="X00000",
                is_user_interface_resp=True,
            )

        # Has address = None
        with pytest.raises(
            ValueError,
            match=r"User-Interface status update responses must have an address.*",
        ):
            Packet(
                address=None,
                command=CommandType.USER_INTERFACE,
                data="000000",
                is_user_interface_resp=True,
            )

        # Has a Timestamp (not allowed)
        with pytest.raises(
            ValueError,
            match=r"User-Interface status update responses must not have a timestamp.*",
        ):
            Packet(
                address=0,
                command=CommandType.USER_INTERFACE,
                timestamp=datetime.datetime(  # noqa: DTZ001 - local timezone - No fn
                    year=2018, month=9, day=21, hour=18, minute=37, second=9
                ),
                data="000000",
                is_user_interface_resp=True,
            )

        # Has a non-zero sequence
        with pytest.raises(
            ValueError,
            match=r"User-Interface status update responses do not use sequence.*",
        ):
            Packet(
                address=0,
                command=CommandType.USER_INTERFACE,
                data="000000",
                is_user_interface_resp=True,
                seq=1,
            )

        # Address too large
        with pytest.raises(
            ValueError,
            match=r"Address must be in the range 0- 15 if provided - got 30",
        ):
            Packet(
                address=30,
                command=CommandType.USER_INTERFACE,
                data="000000",
                is_user_interface_resp=True,
            )

        # Has dis-allowed delay marker
        with pytest.raises(
            ValueError,
            match=r"User-Interface status update responses do not use delay markers",
        ):
            Packet(
                address=0,
                command=CommandType.USER_INTERFACE,
                data="000000",
                is_user_interface_resp=True,
                has_delay_marker=True,
            )

        # Bad Output (from Ness) Event Data Packets
        # Wrong length (!=6)
        with pytest.raises(
            ValueError,
            match=r"Data length of a System Status Event Data Packet must be 6.*",
        ):
            Packet(address=0, command=CommandType.SYSTEM_STATUS, data="0000000000")

        # Non-Hex character 'X'
        with pytest.raises(
            ValueError,
            match=r"Data of a System Status Event Data Packet must be hex - got X00000",
        ):
            Packet(address=0, command=CommandType.SYSTEM_STATUS, data="X00000")

        # Address too large
        with pytest.raises(
            ValueError,
            match=r"Address must be in the range 0- 15 if provided - got 30",
        ):
            Packet(address=30, command=CommandType.SYSTEM_STATUS, data="000000")

        # Has dis-allowed delay marker
        with pytest.raises(
            ValueError,
            match=r"System Status Event Data Packet must not use delay markers",
        ):
            Packet(
                address=0,
                command=CommandType.SYSTEM_STATUS,
                data="000000",
                has_delay_marker=True,
            )

    def test_decode_bad_packets(self) -> None:
        """Test a variety of bad packets that should cause exceptions."""
        cases = [
            # UI request packets
            ("8300c60", r"Packet data too short.*"),  # short packet truncated
            (
                "8300c6012345678912EE7",
                r".*did not end with CRLF newline.*",
            ),  # missing CRLF
            (
                "8300f6012345678912EE4\r\n",
                r"Unable to take more data than exists",
            ),  # length too long for data
            (
                "830056012345678912E15\r\n",
                r"Unable to consume all data",
            ),  # length too short for data
            (
                "8300c6012345678912EX7\r\n",
                r"Invalid non-hex character in checksum byte",
            ),  # Non Hex character in checksum
            (
                "8300c6012345678912EE8\r\n",
                r"Packet checksum does not match",
            ),  # Bad checksum (should be E7)
            (
                "8300c6012345678912Ee7\r\n",
                r"Packet checksum for input request must be upper case",
            ),  # Bad checksum (must be upper case)
            (
                "8300C60B2345678912EF6\r\n",
                r"Data characters of a User-Interface Packet must be one of",
            ),  # Has a disallowed 'B' character
            (
                "8300c60\xaa2345678912E6E\r\n",
                r"Data characters of a User-Interface Packet must be one of",
            ),  # Has a disallowed '\xAA' character
            (
                "83000609F\r\n",
                r"Data length of a User-Interface Packet must be in the range",
            ),  # Zero length
            (
                "8302560AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA33\r\n",
                r"Data length of a User-Interface Packet must be in the range",
            ),  # 37 length: too long
            # Bad Output (from Ness) Status Update Packets
            # Bad checksum
            ("820003600000001a\r\n", r"Packet checksum does not match"),
            # Wrong length (!=6)
            # Length messes up packet type determination: error message not very useful
            ("82000460000000001a\r\n", r"is not a valid CommandType"),
            # Length messes up packet type determination
            # Non-Hex character 'X'
            # checksum is also wrong, since it can't be calculated here
            ("82000360X000001b\r\n", r"Invalid non-hex character in data"),
            # Has a Timestamp (not allowed)
            # Length messes up packet type determination: error message not very useful
            (
                "82000360000000061201074300b8\r\n",
                r"is not a valid CommandType",
            ),
            # Has a non-zero sequence
            (
                "820083600000009b\r\n",
                r"User-Interface status update responses do not use sequence",
            ),
            # Address too large
            ("8215036000000006\r\n", r"Address must be in the range"),
            # Has dis-allowed delay marker
            ("820003600000001b?\r\n", r"Invalid non-hex character in data"),
            # Bad Output (from Ness) Event Data Packets
            # Bad checksum
            ("8204610000000018\r\n", r"Packet checksum does not match"),
            ("830004610000000017\r\n", r"Packet checksum does not match"),
            ("860461000000180921183709007a\r\n", r"Packet checksum does not match"),
            ("870004610000001809211837090079\r\n", r"Packet checksum does not match"),
            # Wrong length (!=6)
            # Length messes up packet type determination: error message not very useful
            (
                "8204610000000019\r\n",
                r"is not a valid CommandType",
            ),
            (
                "830004610000000018\r\n",
                r"Data length of a System Status Event Data Packet must be 6",
            ),
            (
                "860461000000180921183709007b\r\n",
                r"month must be in",
            ),
            (
                "87000461000000180921183709007a\r\n",
                r"month must be in",
            ),
            # Non-Hex character 'X'
            # checksum is also wrong, since it can't be calculated here
            ("820361X000001a\r\n", r"Invalid non-hex character in data"),
            ("83000361X0000019\r\n", r"Invalid non-hex character in data"),
            ("860361X000001809211837097c\r\n", r"Invalid non-hex character in data"),
            ("87000361X000001809211837097b\r\n", r"Invalid non-hex character in data"),
            # Address too large
            ("8315036100000004\r\n", r"Address must be in the range"),
            ("8715036100000018092118370966\r\n", r"Address must be in the range"),
            # Has dis-allowed delay marker
            ("8203610000001a?\r\n", r"Invalid non-hex character in data"),
            ("8300036100000019?\r\n", r"Invalid non-hex character in data"),
            ("8603610000001809211837097c?\r\n", r"Invalid non-hex character in data"),
            ("870003610000001809211837097b?\r\n", r"Invalid non-hex character in data"),
        ]

        for data, err_str in cases:
            with pytest.raises(
                ValueError,
                match=err_str,
            ):
                Packet.decode(data)

    def test_user_interface_packet_decode(self) -> None:
        """Test decoding a specific UI Request with address."""
        pkt = Packet.decode("8300C6012345678912E07\r\n")
        assert (
            pkt.start
            == Packet.START_BYTE_BASIC_HEADER
            | Packet.START_BYTE_ASCII_FORMAT
            | Packet.START_BYTE_ADDRESS_INCLUDED
        )
        assert pkt.address == 0x00
        assert pkt.length == 12  # noqa: PLR2004 # Magic value not worth a constant
        assert pkt.seq == 0x00
        assert pkt.command == CommandType.USER_INTERFACE
        assert pkt.data == "12345678912E"
        assert pkt.timestamp is None
        assert pkt.checksum == 0x07  # noqa: PLR2004 # Magic value not worth a constant

    def test_system_status_packet_decode(self) -> None:
        """Test decoding a specific System Status Event with address and timestamp."""
        pkt = Packet.decode("8700036100070018092118370974\r\n")
        assert (
            pkt.start
            == Packet.START_BYTE_BASIC_HEADER
            | Packet.START_BYTE_ASCII_FORMAT
            | Packet.START_BYTE_ADDRESS_INCLUDED
            | Packet.START_BYTE_TIMESTAMP_INCLUDED
        )
        assert pkt.address == 0x00
        assert pkt.length == Packet.SYSTEM_STATUS_DATA_SIZE / 2
        assert pkt.seq == 0x00
        assert pkt.command == CommandType.SYSTEM_STATUS
        assert pkt.data == "000700"

        assert (  # comment to keep ruff from fighting black
            pkt.timestamp
            == datetime.datetime(  # noqa: DTZ001 - local timezone - No function available
                year=2018, month=9, day=21, hour=18, minute=37, second=9
            )
        )
        assert not pkt.is_user_interface_resp
        assert pkt.checksum == 0x74  # noqa: PLR2004 # Magic value not worth a constant

    def test_decode_with_address_and_time(self) -> None:
        """Test decoding another System Status Event with address and timestamp."""
        pkt = Packet.decode("8709036101050018122709413536\r\n")
        assert pkt.address == 0x09  # noqa: PLR2004 # Magic value not worth a constant
        assert pkt.length == Packet.SYSTEM_STATUS_DATA_SIZE / 2
        assert pkt.seq == 0x00
        assert pkt.command == CommandType.SYSTEM_STATUS
        assert pkt.data == "010500"
        assert (  # comment to keep ruff from fighting black
            pkt.timestamp
            == datetime.datetime(  # noqa: DTZ001 - local timezone - No function available
                year=2018, month=12, day=27, hour=9, minute=41, second=35
            )
        )
        assert not pkt.is_user_interface_resp

    def test_decode_without_address(self) -> None:
        """Test decoding a specific System Status Event with no address."""
        pkt = Packet.decode("820361230001f6\r\n")
        assert pkt.address is None
        assert pkt.length == Packet.SYSTEM_STATUS_DATA_SIZE / 2
        assert pkt.seq == 0x00
        assert pkt.command == CommandType.SYSTEM_STATUS
        assert pkt.data == "230001"
        assert pkt.timestamp is None
        assert not pkt.is_user_interface_resp

    def test_decode_with_address(self) -> None:
        """Test decoding a Status Update UI response packet with an address."""
        pkt = Packet.decode("820003600000001b\r\n")
        assert pkt.address == 0x00
        assert pkt.length == Packet.USER_INTERFACE_RESPONSE_DATA_SIZE / 2
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
        assert pkt.is_user_interface_resp

    def test_bad_timestamp(self) -> None:
        """Test decoding a specific System Status Event with a bad timestamp."""
        pkt = Packet.decode("8700036100070019022517600057\r\n")
        assert (
            pkt.start
            == Packet.START_BYTE_BASIC_HEADER
            | Packet.START_BYTE_ASCII_FORMAT
            | Packet.START_BYTE_ADDRESS_INCLUDED
            | Packet.START_BYTE_TIMESTAMP_INCLUDED
        )
        assert pkt.address == 0x00
        assert pkt.length == Packet.SYSTEM_STATUS_DATA_SIZE / 2
        assert pkt.seq == 0x00
        assert pkt.command == CommandType.SYSTEM_STATUS
        assert pkt.data == "000700"
        assert (  # comment to keep ruff from fighting black
            pkt.timestamp
            == datetime.datetime(  # noqa: DTZ001 - local timezone - No function available
                year=2019, month=2, day=25, hour=18, minute=0, second=0
            )
        )
        assert not pkt.is_user_interface_resp

    def test_decode_zone_16(self) -> None:
        """Test decoding specific System Status Event with zone=16."""
        pkt = Packet.decode("8700036100160019022823032274\r\n")
        assert (
            pkt.start
            == Packet.START_BYTE_BASIC_HEADER
            | Packet.START_BYTE_ASCII_FORMAT
            | Packet.START_BYTE_ADDRESS_INCLUDED
            | Packet.START_BYTE_TIMESTAMP_INCLUDED
        )
        assert pkt.address == 0x00
        assert pkt.length == Packet.SYSTEM_STATUS_DATA_SIZE / 2
        assert pkt.seq == 0x00
        assert pkt.command == CommandType.SYSTEM_STATUS
        assert pkt.data == "001600"
        assert (  # comment to keep ruff from fighting black
            pkt.timestamp
            == datetime.datetime(  # noqa: DTZ001 - local timezone - No function available
                year=2019, month=2, day=28, hour=23, minute=3, second=22
            )
        )
        assert not pkt.is_user_interface_resp

    def test_decode_update(self) -> None:
        """Test decoding a specific UI response packet gives correct data."""
        pkt = Packet.decode("820003601700867e\r\n")
        event = BaseEvent.decode(pkt)
        assert (
            pkt.start == Packet.START_BYTE_BASIC_HEADER | Packet.START_BYTE_ASCII_FORMAT
        )
        assert pkt.address == 0x00
        assert pkt.length == Packet.USER_INTERFACE_RESPONSE_DATA_SIZE / 2
        assert pkt.seq == 0x00
        assert pkt.command == CommandType.USER_INTERFACE
        assert pkt.data == "170086"
        assert pkt.is_user_interface_resp

        assert isinstance(event, PanelVersionUpdate)
        assert event.model == PanelVersionUpdate.Model.D16X
        assert (
            event.major_version == 8  # noqa: PLR2004 # Magic value not worth a constant
        )
        assert (
            event.minor_version == 6  # noqa: PLR2004 # Magic value not worth a constant
        )


class PacketTestRealPackets(unittest.TestCase):
    """Test decoding and re-encoding real captured packets."""

    def test_decode_encode_real_event_packets(self) -> None:
        """Test decoding and re-encoding the real Event packets."""
        for pktdata in Output_From_Ness_Event_Data_Real_Packets:
            pkt = Packet.decode(pktdata.decode("ascii"))
            event = BaseEvent.decode(pkt)
            assert isinstance(event, SystemStatusEvent)
            assert event.encode().encode().encode("ascii") == pktdata

    def test_decode_encode_real_status_packets(self) -> None:
        """Test decoding and re-encoding the real Status Update packets."""
        for pktdata in Output_From_Ness_Status_Update_Real_Packets:
            pkt = Packet.decode(pktdata.decode("ascii"))
            event = BaseEvent.decode(pkt)
            assert isinstance(event, StatusUpdate)
            assert event.encode().encode().encode("ascii") == pktdata


class PacketTestGeneratedPackets(unittest.TestCase):
    """Test decoding and re-encoding all packet types."""

    def test_decode_encode_generated_ui_input_packets(self) -> None:
        """Test decoding and re-encoding UI request packets."""
        for test_item in gemerate_input_to_ness_user_interface_valid_packets():
            pkt = Packet.decode(test_item.packet_chars)
            assert pkt.encode() == test_item.packet_chars

    def test_decode_encode_generated_ui_response_packets(self) -> None:
        """Test decoding and re-encoding Status Update Responses."""
        for test_pkt in gemerate_output_from_ness_status_update_valid_packets():
            pkt = Packet.decode(test_pkt.packet_chars)
            event = BaseEvent.decode(pkt)
            assert isinstance(event, StatusUpdate)
            assert pkt.encode() == test_pkt.packet_chars

    def test_decode_encode_generated_status_packets(self) -> None:
        """Test decoding and re-encoding System Status Output Events."""
        for test_pkt in gemerate_output_from_ness_event_data_valid_packets():
            pkt = Packet.decode(test_pkt.packet_chars)
            event = BaseEvent.decode(pkt)
            assert isinstance(event, SystemStatusEvent)
            assert event.encode().encode() == test_pkt.packet_chars
