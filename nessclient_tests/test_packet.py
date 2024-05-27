import datetime
import logging
import unittest
from os import path

from nessclient import BaseEvent
from nessclient.event import SystemStatusEvent, StatusUpdate
from nessclient.packet import Packet, CommandType
from .fixtures.real_captured_test_data import (
    Output_From_Ness_Event_Data_Real_Packets,
    Output_From_Ness_Status_Update_Real_Packets,
)
from .fixtures.generate_test_packets import (
    Gemerate_Input_To_Ness_User_Interface_Valid_Packets,
    Gemerate_Output_From_Ness_Event_Data_Valid_Packets,
    Gemerate_Output_From_Ness_Status_Update_Valid_Packets,
)

_LOGGER = logging.getLogger(__name__)


def fixture_path(fixture_name: str):
    return path.join(path.dirname(__file__), "fixtures", fixture_name)


class PacketTestCase(unittest.TestCase):
    def test_decode_encode_identity(self):
        cases = [
            # '8700036100070018092118370677',
            "8300c6012345678912Ee7"
        ]

        for case in cases:
            pkt = Packet.decode(case)
            self.assertEqual(case, pkt.encode())

    def test_decode(self):
        with open(fixture_path("sample_output.txt")) as f:
            for line in f.readlines():
                line = line.strip()
                pkt = Packet.decode(line)
                _LOGGER.info("Decoded '%s' into %s", line, pkt)

    def test_user_interface_packet_decode(self):
        pkt = Packet.decode("8300c6012345678912EE7")
        self.assertEqual(pkt.start, 0x83)
        self.assertEqual(pkt.address, 0x00)
        self.assertEqual(pkt.length, 12)
        self.assertEqual(pkt.seq, 0x00)
        self.assertEqual(pkt.command, CommandType.USER_INTERFACE)
        self.assertEqual(pkt.data, "12345678912E")
        self.assertIsNone(pkt.timestamp)
        self.assertEqual(pkt.checksum, 0xE7)

    def test_system_status_packet_decode(self):
        pkt = Packet.decode("8700036100070018092118370974")
        self.assertEqual(pkt.start, 0x87)
        self.assertEqual(pkt.address, 0x00)
        self.assertEqual(pkt.length, 3)
        self.assertEqual(pkt.seq, 0x00)
        self.assertEqual(pkt.command, CommandType.SYSTEM_STATUS)
        self.assertEqual(pkt.data, "000700")
        self.assertEqual(
            pkt.timestamp,
            datetime.datetime(year=2018, month=9, day=21, hour=18, minute=37, second=9),
        )
        # self.assertEqual(pkt.checksum, 0x74)

    def test_decode_with_address_and_time(self):
        pkt = Packet.decode("8709036101050018122709413536")
        self.assertEqual(pkt.address, 0x09)
        self.assertEqual(pkt.length, 3)
        self.assertEqual(pkt.seq, 0x00)
        self.assertEqual(pkt.command, CommandType.SYSTEM_STATUS)
        self.assertEqual(pkt.data, "010500")
        self.assertEqual(
            pkt.timestamp,
            datetime.datetime(
                year=2018, month=12, day=27, hour=9, minute=41, second=35
            ),
        )
        self.assertFalse(pkt.is_user_interface_resp)

    def test_decode_without_address(self):
        pkt = Packet.decode("820361230001f6")
        self.assertIsNone(pkt.address)
        self.assertEqual(pkt.length, 3)
        self.assertEqual(pkt.seq, 0x00)
        self.assertEqual(pkt.command, CommandType.SYSTEM_STATUS)
        self.assertEqual(pkt.data, "230001")
        self.assertIsNone(pkt.timestamp)
        self.assertFalse(pkt.is_user_interface_resp)

    def test_decode_with_address(self):
        pkt = Packet.decode("820003600000001b")
        self.assertEqual(pkt.address, 0x00)
        self.assertEqual(pkt.length, 3)
        self.assertEqual(pkt.seq, 0x00)
        self.assertEqual(pkt.command, CommandType.USER_INTERFACE)
        self.assertEqual(pkt.data, "000000")
        self.assertIsNone(pkt.timestamp)
        self.assertTrue(pkt.is_user_interface_resp)

    def test_encode_decode1(self):
        pkt = Packet(
            address=0x00,
            seq=0x00,
            command=CommandType.USER_INTERFACE,
            data="A1234E",
            timestamp=None,
        )
        self.assertEqual(pkt.length, 6)
        self.assertEqual(pkt.encode(), "8300660A1234E49")

    def test_encode_cecode2(self):
        pkt = Packet(
            address=0x00,
            seq=0x00,
            command=CommandType.USER_INTERFACE,
            data="000100",
            timestamp=None,
        )
        self.assertEqual(pkt.length, 6)
        self.assertEqual(pkt.encode(), "830066000010078")
        self.assertEqual(Packet.decode(pkt.encode()), pkt)

    def test_decode_status_update_response(self):
        """
        82 00 03 60 070000 14
        """
        pkt = Packet.decode("8200036007000014")
        self.assertEqual(pkt.start, 0x82)
        self.assertEqual(pkt.address, 0x00)
        self.assertEqual(pkt.length, 3)
        self.assertEqual(pkt.seq, 0x00)
        self.assertEqual(pkt.command, CommandType.USER_INTERFACE)
        self.assertEqual(pkt.data, "070000")
        self.assertIsNone(pkt.timestamp)
        # self.assertEqual(pkt.checksum, 0x14)

    def test_bad_timestamp(self):
        pkt = Packet.decode("8700036100070019022517600057")
        self.assertEqual(pkt.start, 0x87)
        self.assertEqual(pkt.address, 0x00)
        self.assertEqual(pkt.length, 3)
        self.assertEqual(pkt.seq, 0x00)
        self.assertEqual(pkt.command, CommandType.SYSTEM_STATUS)
        self.assertEqual(pkt.data, "000700")
        self.assertEqual(
            pkt.timestamp,
            datetime.datetime(year=2019, month=2, day=25, hour=18, minute=0, second=0),
        )

    def test_decode_zone_16(self):
        pkt = Packet.decode("8700036100160019022823032274")
        self.assertEqual(pkt.start, 0x87)
        self.assertEqual(pkt.address, 0x00)
        self.assertEqual(pkt.length, 3)
        self.assertEqual(pkt.seq, 0x00)
        self.assertEqual(pkt.command, CommandType.SYSTEM_STATUS)
        self.assertEqual(pkt.data, "001600")
        self.assertEqual(
            pkt.timestamp,
            datetime.datetime(year=2019, month=2, day=28, hour=23, minute=3, second=22),
        )

    def test_decode_update(self):
        pkt = Packet.decode("820003601700867e")
        event = BaseEvent.decode(pkt)
        print(pkt)
        print(event)


class PacketTestRealPackets(unittest.TestCase):
    def test_decode_encode_real_event_packets(self):
        for pktdata in Output_From_Ness_Event_Data_Real_Packets:
            pkt = Packet.decode(pktdata.decode("ascii").strip())
            event = BaseEvent.decode(pkt)
            self.assertTrue(isinstance(event, SystemStatusEvent))
            self.assertEqual(event.encode().encode().encode("ascii") + b"\r\n", pktdata)

    def test_decode_encode_real_status_packets(self):
        for pktdata in Output_From_Ness_Status_Update_Real_Packets:
            pkt = Packet.decode(pktdata.decode("ascii").strip())
            event = BaseEvent.decode(pkt)
            self.assertTrue(isinstance(event, StatusUpdate))
            self.assertEqual(event.encode().encode().encode("ascii") + b"\r\n", pktdata)


class PacketTestGeneratedPackets(unittest.TestCase):
    def test_decode_encode_generated_ui_input_packets(self):
        for pktdata, desc in Gemerate_Input_To_Ness_User_Interface_Valid_Packets():
            pkt = Packet.decode(pktdata)
            self.assertEqual(pkt.encode(), pktdata)

    def test_decode_encode_generated_ui_response_packets(self):
        for pktdata, desc in Gemerate_Output_From_Ness_Status_Update_Valid_Packets():
            pkt = Packet.decode(pktdata)
            event = BaseEvent.decode(pkt)
            self.assertTrue(isinstance(event, StatusUpdate))
            self.assertEqual(pkt.encode(), pktdata)

    def test_decode_encode_generated_status_packets(self):
        for pktdata, desc in Gemerate_Output_From_Ness_Event_Data_Valid_Packets():
            pkt = Packet.decode(pktdata)
            event = BaseEvent.decode(pkt)
            self.assertTrue(isinstance(event, SystemStatusEvent))
            self.assertEqual(event.encode().encode(), pktdata)
