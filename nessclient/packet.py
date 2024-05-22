import datetime
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

_LOGGER = logging.getLogger(__name__)


class CommandType(Enum):
    SYSTEM_STATUS = 0x61
    USER_INTERFACE = 0x60


@dataclass
class Packet:
    address: Optional[int]
    seq: int
    command: CommandType
    data: str
    timestamp: Optional[datetime.datetime]

    # Whether or not this packet is a USER_INTERFACE response
    is_user_interface_resp: bool = False

    @property
    def start(self) -> int:
        rv = 0x02 | 0x80
        if self.address is not None and not self.is_user_interface_resp:
            rv |= 0x01
        if self.timestamp is not None:
            rv |= 0x04

        return rv

    @property
    def length_field(self) -> int:
        return int(self.length) | (self.seq << 7)

    @property
    def length(self) -> int:
        if is_user_interface_req(self.start, self.command):
            return len(self.data)
        else:
            return int(len(self.data) / 2)

    @property
    def checksum(self) -> int:
        bytes = self.encode(with_checksum=False).strip()

        # Checksum is calculated differently depending on the packet type.
        if is_user_interface_req(self.start, self.command):
            # Input (to Ness) User-Interface Packets sum the
            # ordinal of each hex character, excluding the checksum and CRLF
            # e.g. '8300360S00E9\r\n'
            #      Sum = 0x38 + 0x33 + 0x30 + 0x30 + 0x33 +
            #            0x36 + 0x30 + 0x53 + 0x30 + 0x30 = 0x217
            #      Checksum = (-Sum) & 0xff = 0xE9
            total = sum([ord(x) for x in bytes])
        else:
            # Output (from Ness) System-Status Packets sum the
            # integers that each hex pair represent, excluding the checksum and CRLF
            # e.g. '820003600000001b\r\n'
            #      Sum = 0x82 + 0x00 + 0x03 + 0x60 + 0x00 + 0x00 + 0x00 = 0xE5
            #      Checksum = (-Sum) & 0xff = 0x1b
            total = 0
            for pos in range(0, len(bytes), 2):
                total += int(bytes[pos : pos + 2], 16)

        return (256 - total) % 256

    def encode(self, with_checksum: bool = True) -> str:
        data = ""
        data += "{:02x}".format(self.start)

        if self.address is not None:
            if is_user_interface_req(self.start, self.command):
                data += "{:01x}".format(self.address)
            else:
                data += "{:02x}".format(self.address)

        data += "{:02x}".format(self.length_field)
        data += "{:02x}".format(self.command.value)
        data += self.data
        if self.timestamp is not None:
            data += self.timestamp.strftime("%y%m%d%H%M%S")

        if with_checksum:
            data += "{:02x}".format(self.checksum)

        return data

    @classmethod
    def decode(cls, _data: str) -> "Packet":
        """
        Packets are ASCII encoded data. Packet layout is as follows:

        +---------------------------------------------------------------------------+
        | start | address | length | command | data | timestamp | checksum | finish |
        | hex   | hex     | hex    | hex     | str  | dec       | hex      | crlf   |
        | 1     | 1       | 1      | 1       | n    | 6         | 1        |        |
        +---------------------------------------------------------------------------+

        Timestamp:
            Timestamps are formatted in the following format, where each field is
            decimal encoded:

            YY MM DD HH MM SS

        Checksum:
            Calculated by...?

        Since data is ASCII encoded, each byte uses 2 ASCII character to be
        represented. However, we cannot simply do a hex decode on the entire
        message, since the timestamp and data fields are represented using a
        non-hex representation and therefore must be manually decoded.
        """

        # TODO(NW): Figure out checksum validation
        # if not is_data_valid(_data.decode('ascii')):
        #     raise ValueError("Unable to decode: checksum verification failed")

        # Decoding of Length requires knowledge of the packet type, which
        # normally is specified by the start byte and command type.
        # Since the command cannot be decoded until after the length
        # there is a circular dependency
        # Instead, identify packet type via the position of the command byte
        # Input (to Ness) User-Interface Packet always have command 60 at position 5
        # Output packets always have command 61 at position 4 or 6
        is_input_ui_req = _data[5:7] == "60"

        data = DataIterator(_data)
        _LOGGER.debug("Decoding bytes: '%s'", _data)

        start = data.take_hex()

        address = None
        if has_address(start, len(_data)):
            address = data.take_hex(half=is_input_ui_req)

        length = data.take_hex()
        data_length = length & 0x7F
        seq = length >> 7
        command = CommandType(data.take_hex())
        msg_data = data.take_bytes(data_length, half=is_input_ui_req)
        timestamp = None
        if has_timestamp(start):
            timestamp = decode_timestamp(data.take_bytes(6))

        # TODO(NW): Figure out checksum validation
        checksum = data.take_hex()  # noqa

        if not data.is_consumed():
            raise ValueError("Unable to consume all data")

        return Packet(
            is_user_interface_resp=is_user_interface_resp(start, command),
            address=address,
            seq=seq,
            command=command,
            data=msg_data,
            timestamp=timestamp,
        )


class DataIterator:
    def __init__(self, data: str):
        self._data = data
        self._position = 0

    def take_bytes(self, n: int, half: bool = False) -> str:
        multi = 2 if not half else 1
        position = self._position
        self._position += n * multi
        if self._position > len(self._data):
            raise ValueError("Unable to take more data than exists")

        return self._data[position : self._position]

    def take_hex(self, half: bool = False) -> int:
        return int(self.take_bytes(1, half), 16)

    def take_dec(self, half: bool = False) -> int:
        return int(self.take_bytes(1, half), 10)

    def is_consumed(self) -> bool:
        return self._position >= len(self._data)


def has_address(start: int, data_length: int) -> bool:
    """
    Determine whether the packet has an "address" encoded into it.
    There exists an undocumented bug/edge case in the spec - some packets
    with 0x82 as _start_, still encode the address into the packet, and thus
    throws off decoding. This edge case is handled explicitly.
    """
    return bool(0x01 & start) or (start == 0x82 and data_length == 16)


def has_timestamp(start: int) -> bool:
    return bool(0x04 & start)


def is_user_interface_req(start: int, command: CommandType) -> bool:
    return start == 0x83 and command == CommandType.USER_INTERFACE


def is_user_interface_resp(start: int, command: CommandType) -> bool:
    return start == 0x82 and command == CommandType.USER_INTERFACE


def decode_timestamp(data: str) -> datetime.datetime:
    """
    Decode timestamp using bespoke decoder.
    Cannot use simple strptime since the ness panel contains a bug
    that P199E zone and state updates emitted on the hour cause a minute
    value of `60` to be sent, causing strptime to fail. This decoder handles
    this edge case.
    """
    year = 2000 + int(data[0:2])
    month = int(data[2:4])
    day = int(data[4:6])
    hour = int(data[6:8])
    minute = int(data[8:10])
    second = int(data[10:12])
    if minute == 60:
        minute = 0
        hour += 1

    return datetime.datetime(
        year=year, month=month, day=day, hour=hour, minute=minute, second=second
    )
