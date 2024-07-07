import datetime
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional


"""
Packets are ASCII encoded data.
    Packet layouts are similar but with important differences:

Input (to Ness) User-Interface Packet:
* Start:    2 upper case hex characters - must be "83"
* Address:  1 upper case hex character  - "0" to "F"
* Length:   2 upper case hex characters - must be "01" to "1E"
              - Note: it appears that values between 0xA-0xF do not work properly
* Command:  2 upper case hex characters - must be "60"
* Data:     N ascii characters - where N = Data Length field
              - must be from the set: "AHEXFVPDM*#0123456789S"
* Checksum: 2 upper case hex characters - hex( 0x100
              - (sum(ordinal of each hex character of previous fields) & 0xff))
* Finish:   2 characters "\r\n" (Carriage Return, Line Feed - CRLF)

Output (from Ness) Asynchronous Event Data Packet: (see SystemStatusEvent class)
* Start:    2 lower case hex characters - must be "82", "83", "86", "87"
* Address:  2 lower case hex characters - "00" to "0F"
              - only present in start mode "83" or "87"
* Length:   2 lower case hex characters - must be "03" or "83"
              - upper bit is alternating "Sequence"
* Command:  2 lower case hex characters - must be "61"
* Data:     6 lower case hex characters
              (double the length specified in the Length field)
* Timestamp: 12 ascii digit characters
              - "YYMMDDHHmmSS" - only present in start mode "86" or "87"
* Checksum: 2 lower case hex characters
              - sets the sum the integers that each hex pair
                represent to zero (excluding finish CRLF)
* Finish:   2 characters "\r\n" (Carriage Return, Line Feed - CRLF)

Output (from Ness) Status Update Packet:
    (Response to a User-Interface Status Request Packet) (see StatusUpdate class)
* Start:    2 lower case hex characters - must be "82"
* Address:  2 lower case hex characters - "00" to "0F"
              - Note: Address always present despite 0x82 start
                value that would normally indicate no-address.
* Length:   2 lower case hex characters - must be "03"
* Command:  2 lower case hex characters - must be "60"
* Data:     6 lower case hex characters
              (double the length specified in the Length field)
              - Note: Values have different meanings to Event Data Packet
* Checksum: 2 lower case hex characters
              - sets the sum the integers that each
                hex pair represent to zero (excluding finish CRLF)
* Finish:   2 characters "\r\n" (Carriage Return, Line Feed - CRLF)

"""


_LOGGER = logging.getLogger(__name__)


class CommandType(Enum):
    SYSTEM_STATUS = 0x61
    USER_INTERFACE = 0x60


def is_hex(s: str) -> bool:
    for c in s:
        if c not in "0123456789ABCDEFabcdef":
            return False
    return True


def is_valid_ui_data_char(s: str) -> bool:
    for c in s:
        if c not in "AHEXFVPDM*#0123456789S":
            return False
    return True


@dataclass
class Packet:
    address: Optional[int]
    seq: int
    command: CommandType
    data: str
    timestamp: Optional[datetime.datetime]
    has_delay_marker: bool

    # Whether or not this packet is a USER_INTERFACE response
    is_user_interface_resp: bool = False

    def __init__(
        self,
        command: CommandType,
        data: str,
        address: Optional[int] = None,
        seq: int = 0,
        timestamp: Optional[datetime.datetime] = None,
        is_user_interface_resp: bool = False,
        has_delay_marker: bool = False,
    ) -> None:
        if command == CommandType.USER_INTERFACE:
            if is_user_interface_resp:
                # Output (from Ness) Status Update Packet:
                # (Response to a User-Interface Status Request Packet)
                if len(data) != 6:
                    raise ValueError(
                        "Data length of a User-Interface status "
                        f"update response must be 6 - got {len(data)}"
                    )
                if not is_hex(data):
                    raise ValueError(
                        "Data of a User-Interface status update "
                        f"response must be hex - got {data}"
                    )
                if address is None:
                    raise ValueError(
                        "User-Interface status update responses "
                        f"must have an address - got {address}"
                    )
                if timestamp is not None:
                    raise ValueError(
                        "User-Interface status update responses "
                        f"must not have a timestamp - got {timestamp}"
                    )
                if seq != 0:
                    raise ValueError(
                        "User-Interface status update responses do "
                        f"not use sequence - it must be zero - got {seq}"
                    )
                if has_delay_marker:
                    raise ValueError(
                        "User-Interface status update responses do "
                        "not use delay markers"
                    )
            else:
                # Input (to Ness) User-Interface (Request) Packet:
                if len(data) < 1 or len(data) > 30:
                    raise ValueError(
                        "Data length of a User-Interface Packet "
                        f"must be in the range 1 - 30 - got {len(data)}"
                    )
                if not is_valid_ui_data_char(data):
                    raise ValueError(
                        "Data characters of a User-Interface Packet must "
                        f"be one of 'AHEXFVPDM*#01234567890S' - got {data}"
                    )
                if address is None:
                    raise ValueError(
                        "User-Interface Packet must have an address " f"- got {address}"
                    )
                if timestamp is not None:
                    raise ValueError(
                        "User-Interface Packet must not have a timestamp "
                        f"- got {timestamp}"
                    )
                if seq != 0:
                    raise ValueError(
                        "User-Interface Packet do not use sequence "
                        f"- it must be zero - got {seq}"
                    )
        elif command == CommandType.SYSTEM_STATUS:
            # Output (from Ness) Event Data Packet: (see SystemStatusEvent class)
            if len(data) != 6:
                raise ValueError(
                    "Data length of a System Status Event Data Packet "
                    f"must be 6 - got {len(data)}"
                )
            if not is_hex(data):
                raise ValueError(
                    "Data of a System Status Event Data Packet must "
                    f"be hex - got {data}"
                )
            if has_delay_marker:
                raise ValueError(
                    "System Status Event Data Packet must " "not use delay markers"
                )
        else:
            raise ValueError(f"Unknown command {command}")

        if address is not None and (address < 0 or address > 0xF):
            raise ValueError(
                f"Address must be in the range 0x0 - 0xf if provided - got {address}"
            )

        # Validated
        self.command = command
        self.data = data
        self.address = address
        self.seq = seq
        self.timestamp = timestamp
        self.is_user_interface_resp = is_user_interface_resp
        self.has_delay_marker = has_delay_marker

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
                # Request address should be upper case
                # according to D8-D16SerialInterface.exe
                data += f"{self.address:01X}"
            else:
                data += f"{self.address:02x}"

        if is_user_interface_req(self.start, self.command):
            # Request length & command should be upper case
            # according to D8-D16SerialInterface.exe
            data += f"{self.length_field:02X}{self.command.value:02X}"
        else:
            data += f"{self.length_field:02x}{self.command.value:02x}"
        data += self.data

        if self.timestamp is not None:
            data += self.timestamp.strftime("%y%m%d%H%M%S")

        if with_checksum:
            checksum_str = "{:02x}".format(self.checksum)
            if is_user_interface_req(self.start, self.command):
                # NOTE: Checksum for UI Input Request packets MUST be upper case
                #       Otherwise packets will be ignored by NESS
                data += checksum_str.upper()
            else:
                data += checksum_str

            data += "?" if self.has_delay_marker else ""

        return data + "\r\n"

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

        # Check minimum data size (Start:2, Length:1, Command:2, Checksum:2, Finish:2)
        if len(_data) < 9:
            raise ValueError(f"Packet data too short : {_data!r}")

        # Check and remove the finish marker
        if _data[-2:] != "\r\n":
            raise ValueError(
                f"Packet data {_data!r} did not "
                f"end with CRLF newline - ignoring  {_data[-2:]}"
            )
        _data = _data[:-2]

        has_delay_marker = False

        # Decoding of Length requires knowledge of the packet type, which
        # normally is specified by the start byte and command type.
        # Since the command cannot be decoded until after the length
        # there is a circular dependency
        # Instead, identify packet type via the position of the command byte
        # Input (to Ness) User-Interface Packet always have command 60 at position 5
        # Output packets always have command 61 at position 4 or 6
        is_input_ui_req = _data[5:7] == "60"
        if is_input_ui_req:
            # Input (to Ness) User-Interface Packet

            # Input Packets can have a command separator delay marker
            # Check for, and remove the delay marker
            if _data[-1:] == "?":
                _data = _data[:-1]
                has_delay_marker = True

            # Input (to Ness) User-Interface Packets sum the
            # ordinal of each hex character, excluding the checksum and CRLF
            # e.g. '8300360S00E9\r\n'
            #      Sum = 0x38 + 0x33 + 0x30 + 0x30 + 0x33 +
            #            0x36 + 0x30 + 0x53 + 0x30 + 0x30 = 0x217
            #      Checksum = 0x100 - (Sum & 0xff) = 0xE9
            datasum = sum([ord(x) for x in _data[:-2]])
            try:
                checksum = int(_data[-2:], 16)
            except ValueError:
                raise ValueError(
                    f"Invalid non-hex character in checksum byte: {_data!r}"
                )
            if f"{checksum:02X}" != _data[-2:]:
                raise ValueError(
                    f"Packet checksum for input request must be upper case : {_data!r}"
                )
            if ((-datasum) & 0xFF) != checksum:
                raise ValueError(
                    f"Packet checksum does not match : {_data!r} : "
                    f"0x{((-datasum) & 0xFF):02X} != 0x{checksum:02X}"
                )

        else:
            # Output (from Ness) System-Status Packet
            # or
            # Output (from Ness) Status Update Packet
            #    (Response to a User-Interface Status Request Packet)

            # Output packets sum the integers that each hex pair
            # represent, excluding the checksum and CRLF
            # e.g. '820003600000001b\r\n'
            #      Sum = 0x82 + 0x00 + 0x03 + 0x60 + 0x00 + 0x00 + 0x00 = 0xE5
            #      Checksum = 0x100 - (Sum & 0xff) = 0x1b
            datasum = 0
            for pos in range(0, len(_data), 2):
                try:
                    datasum += int(_data[pos : pos + 2], 16)
                except ValueError:
                    raise ValueError(f"Invalid non-hex character in data: {_data!r}")

            if (datasum & 0xFF) != 0:
                raise ValueError(
                    f"Packet checksum does not match : {_data!r} {hex(datasum)}"
                )

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
            has_delay_marker=has_delay_marker,
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
