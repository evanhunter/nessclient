import datetime
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

_LOGGER = logging.getLogger(__name__)


class CommandType(Enum):
    SYSTEM_STATUS = 0x61
    USER_INTERFACE = 0x60


class StartByteBits(Enum):
    ADDRESS_Included = 0x01
    TIMESTAMP_Included = 0x04
    BasicHeader = 0x02 # always set
    ASCII_Format = 0x80 # always set



def is_upper_case_hex(s: str) -> bool:
    valid = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "A", "B", "C", "D", "E", "F"]
    for c in s:
        if c not in valid:
            return False
    return True

def is_valid_ui_data_char(s: str) -> bool:
    valid = ["A", "H", "E", "X", "F", "V", "P", "D", "M", "*", "#", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "S"]
    for c in s:
        if c not in valid:
            return False
    return True


@dataclass
class Packet:
    address: Optional[int]
    seq: int
    command: CommandType
    data: str
    timestamp: Optional[datetime.datetime]

    # Whether or not this packet is a USER_INTERFACE response
    is_user_interface_resp: bool = False

    def __init__(
        self,
        command: CommandType,
        data: str,
        address: Optional[int] = None,
        seq: int = 0,
        timestamp: Optional[datetime.datetime] = None,
        is_user_interface_resp: bool = False
    ) -> None:
           
        if command == CommandType.USER_INTERFACE:
            if is_user_interface_resp:
                # Output (from Ness) Status Update Packet: (Response to a User-Interface Status Request Packet
                if len(data) != 6:
                    raise ValueError(f"Data length of a User-Interface status update response must be 6 - got {len(data)}")
                if not is_upper_case_hex(data):
                    raise ValueError(f"Data of a User-Interface status update response must be upper-case hex - got {data}")
                if address is None:
                    raise ValueError(f"User-Interface status update responses must have an address - got {address}")
                if timestamp is not None:
                    raise ValueError(f"User-Interface status update responses must not have a timestamp - got {timestamp}")
                if seq != 0:
                    raise ValueError(f"User-Interface status update responses do not use sequence - it must be zero - got {seq}")
            else:
                # Input (to Ness) User-Interface Packet:
                if len(data) < 1 or len(data) > 30:
                    raise ValueError(f"Data length of a User-Interface Packet must be in the range 1 - 30 - got {len(data)}")
                if not is_valid_ui_data_char(data):
                    raise ValueError(f"Data characters of a User-Interface Packet must be one of 'AHEXFVPDM*#01234567890S' - got {data}")
                if address is None:
                    raise ValueError(f"User-Interface Packet must have an address - got {address}")
                if timestamp is not None:
                    raise ValueError(f"User-Interface Packet must not have a timestamp - got {timestamp}")
                if seq != 0:
                    raise ValueError(f"User-Interface Packet do not use sequence - it must be zero - got {seq}")
        elif command == CommandType.SYSTEM_STATUS:
            # Output (from Ness) Event Data Packet: (see SystemStatusEvent class)
                if len(data) != 6:
                    raise ValueError(f"Data length of a System Status Event Data Packet must be 6 - got {len(data)}")
                if not is_upper_case_hex(data):
                    raise ValueError(f"Data of a System Status Event Data Packet must be upper-case hex - got {data}")
        else:
            raise ValueError(f"Unknown command {command}")

        if address is not None and (address < 0 or address > 0xf):
            raise ValueError(f"Address must be in the range 0x0 - 0xf if provided - got {address}")
        
        # Validated 
        self.command = command
        self.data = data
        self.address = address
        self.seq = seq
        self.timestamp = timestamp
        self.is_user_interface_resp = is_user_interface_resp


    @property
    def start(self) -> int:
        # Always set bits
        rv = StartByteBits.BasicHeader.value | StartByteBits.ASCII_Format.value
        if self.command == CommandType.USER_INTERFACE:
            if not self.is_user_interface_resp:
                # User-Interface Packets must have start-byte 0x83
                rv |= StartByteBits.ADDRESS_Included.value
            # else: Status Update User-Interface Response Packets must have start-byte 0x82
        else:
            # System-Status Packet
            if self.address is not None:
                rv |= StartByteBits.ADDRESS_Included.value
            if self.timestamp is not None:
                rv |= StartByteBits.TIMESTAMP_Included.value

        return rv

    @property
    def length_field(self) -> int:
        return int(self.length) | (self.seq << 7)

    @property
    def length(self) -> int:
        if self.command == CommandType.USER_INTERFACE and not self.is_user_interface_resp:
            return len(self.data)
        else:
            return int(len(self.data) / 2)


    def encode(self, with_checksum: bool = True) -> str:
        del with_checksum # deprecated - no longer used
        
        data = "{:02x}".format(self.start)

        if self.address is not None:
            if self.command == CommandType.USER_INTERFACE:
                # Input (to Ness) User-Interface Packets addresses
                # have one hex digit (one nibble)
                data += "{:01x}".format(self.address)
            else:
                # Output (from Ness) System-Status Packets addresses
                # have two hex digits (one byte)
                data += "{:02x}".format(self.address)

        data += "{:02x}".format(self.length_field)
        data += "{:02x}".format(self.command.value)
        data += self.data
        if self.timestamp is not None:
            data += self.timestamp.strftime("%y%m%d%H%M%S")

        # Checksum is calculated differently depending on the packet type.
        if self.command == CommandType.USER_INTERFACE:
            # Input (to Ness) User-Interface Packets sum the
            # ordinal of each hex character, excluding the checksum and CRLF
            # e.g. '8300360S00E9\r\n'
            #      Sum = 0x38 + 0x33 + 0x30 + 0x30 + 0x33 + 0x36 + 0x30 + 0x53 + 0x30 + 0x30 = 0x217
            #      Checksum = (-Sum) & 0xff = 0xE9
            datasum = sum([ord(x) for x in data])
        else:
            # Output (from Ness) System-Status Packets sum the
            # integers that each hex pair represent, excluding the checksum and CRLF
            # e.g. '820003600000001b\r\n'
            #      Sum = 0x82 + 0x00 + 0x03 + 0x60 + 0x00 + 0x00 + 0x00 = 0xE5
            #      Checksum = (-Sum) & 0xff = 0x1b
            datasum = 0
            for pos in range(0, len(data), 2):
                datasum += int(data[pos : pos + 2], 16)
        
        data += "{:02x}\r\n".format((-datasum) & 0xff).upper()

        # print(f"data: '{data}' self.data={self.data} ")
        return data

    class Direction(Enum):
        Output_From_Ness = 1
        Input_To_Ness = 2

    @classmethod
    def decode(cls, _data: str) -> "Packet":
        """
        Packets are ASCII encoded data. Packet layouts are similar but with important differences:

        Input (to Ness) User-Interface Packet:
        * Start:    2 upper case hex characters - must be "83"
        * Address:  1 upper case hex character  - "0" to "F"
        * Length:   2 upper case hex characters - must be "01" to "1E"  ????????????????????????? TODO : check larger than 10 bytes somehow
        * Command:  2 upper case hex characters - must be "60"
        * Data:     N ascii characters - where N = Data Length field
        * Checksum: 2 upper case hex characters - hex( 0x100 - (sum(ordinal of each hex character of previous fields) & 0xff))
        * Finish:   2 characters "\r\n" (Carriage Return, Line Feed - CRLF)

        Output (from Ness) Event Data Packet: (see SystemStatusEvent class)
        * Start:    2 upper case hex characters - must be "82", "83", "86", "87"
        * Address:  2 upper case hex characters - "00" to "0F" - ??????????????????????????????????????????? TODO: only present in mode 86 ?
        * Length:   2 upper case hex characters - must be "03" or "83" - upper bit is alternating "Sequence"
        * Command:  2 upper case hex characters - must be "61"
        * Data:     6 upper case hex characters   (double the length specified in the Length field)
        * Timestamp: 12 ascii digit characters - "YYMMDDHHmmSS" - only present in start mode "86" or "87"
        * Checksum: 2 upper case hex characters - sets the sum the integers that each hex pair represent to zero (excluding finish CRLF)
        * Finish:   2 characters "\r\n" (Carriage Return, Line Feed - CRLF)

        Output (from Ness) Status Update Packet: (Response to a User-Interface Status Request Packet) (see StatusUpdate class)
        * Start:    2 upper case hex characters - must be "82"
        * Address:  2 upper case hex characters - "00" to "0F" - Note: Address always present despite 0x82 start value that would normally indicate no-address.
        * Length:   2 upper case hex characters - must be "03"
        * Command:  2 upper case hex characters - must be "60"
        * Data:     6 upper case hex characters   (double the length specified in the Length field) - Note: Values have different meanings to Event Data Packet
        * Checksum: 2 upper case hex characters - sets the sum the integers that each hex pair represent to zero (excluding finish CRLF)
        * Finish:   2 characters "\r\n" (Carriage Return, Line Feed - CRLF)


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
            raise ValueError(f"Packet data {_data!r} did not "
                             f"end with CRLF newline - ignoring  {_data[-2:]}")
        _data = _data[:-2]

        # Identify packet type via the position of the command byte
        # Input packets always have command 60 at position 5
        # Output packets always have command 61 at position 4 or 6
        is_input = (_data[5:7] =="60")
        if is_input:
            # Input (to Ness) User-Interface Packet

            # Input Packets can have a delay marker
            # Check for, and remove the delay marker
            if _data[-1:] == "?":
                _data = _data[:-1]

            # Input (to Ness) User-Interface Packets sum the
            # ordinal of each hex character, excluding the checksum and CRLF
            # e.g. '8300360S00E9\r\n'
            #      Sum = 0x38 + 0x33 + 0x30 + 0x30 + 0x33 + 0x36 + 0x30 + 0x53 + 0x30 + 0x30 = 0x217
            #      Checksum = 0x100 - (Sum & 0xff) = 0xE9
            datasum = sum([ord(x) for x in _data[:-2]])
            try:
                checksum = int(_data[-2:], 16)
            except ValueError:
                raise ValueError(f"Invalid non-hex character in checksum byte: {_data!r}")
            if ((-datasum) & 0xff) != checksum:
                raise ValueError(f"Packet checksum does not match : {_data!r}")
            
            is_user_interface_resp = False

        else:
            # Output (from Ness) System-Status Packet

            # Serial comms sometimes gets an extra invalid character at the start - check for that
            if _data[0] != "8" and _data[1] == "8":
                # Invalid start byte
                # try dropping first character
                _data = _data[1:]

            # Output (from Ness) System-Status Packets sum the
            # integers that each hex pair represent, excluding the checksum and CRLF
            # e.g. '820003600000001b\r\n'
            #      Sum = 0x82 + 0x00 + 0x03 + 0x60 + 0x00 + 0x00 + 0x00 = 0xE5
            #      Checksum = 0x100 - (Sum & 0xff) = 0x1b
            datasum = 0
            for pos in range(0, len(_data), 2):
                try:
                    datasum += int(_data[pos : pos + 2], 16)
                except ValueError:
                    raise ValueError(f"Invalid non-hex character in data: {_data!r}")
                    
            if (datasum & 0xff) != 0:
                raise ValueError(f"Packet checksum does not match : {_data!r} {hex(datasum)}")
            
            # if the Command is 0x60, then this is a Status Update Response to a User-Interface Packet
            is_user_interface_resp = (_data[6:8] =="60")

        data = DataIterator(_data)
        _LOGGER.debug("Decoding bytes: '%s'", _data)

        # Get the first 2 hex characters that are the start byte, and valdate
        start = data.take_hex()

        if (start & 0xfa) != 0x82:
            raise ValueError(f"Invalid start value {hex(start)} in packet : {_data!r}")

        # Input start byte should always be 0x83
        if is_input and start != 0x83:
            raise ValueError(f"Expected start byte 0x83, got {hex(start)}")

        # Start byte of Responses to a User Interface Status Request Packet must be 0x82 
        if is_user_interface_resp and start != 0x82:
            raise ValueError(f"Invalid start byte value {hex(start)} - expected 0x82 - in user-interface response packet : {_data!r}")

        # Get and validate the 'address' field if it exists
        address: Optional[int] = None
        if has_address(start, is_user_interface_resp):
            address = data.take_hex(half=is_input)


        # Get and validate the 'length' field
        length = data.take_hex()

        # System Status Event Packets store 'sequence' in the upper bit of 'length' 
        if not is_input and not is_user_interface_resp:
            data_length = length & 0x7F
            seq = length >> 7
        else:
            data_length = length
            seq = 0

        # Check the data length is valid
        if is_input:
            if data_length < 1 or data_length > 30:
                raise ValueError(f"User Interface packets must have length of 1..30 - not {data_length} - in packet : {_data!r}")
        else:
            if data_length != 3:
                raise ValueError(f"System Status packets must have length 3 - not {data_length} - in packet : {_data!r}")

        
        # Get and validate the 'command' field
        command_value = data.take_hex()

        command = CommandType(command_value)
        if command != CommandType.USER_INTERFACE and command != CommandType.SYSTEM_STATUS:
            raise ValueError(f"Invalid command value {hex(command)} - in packet : {_data!r}")
 

        msg_data = data.take_bytes(data_length, half=is_input)

        timestamp = None
        if has_timestamp(start):
            timestamp = decode_timestamp(data.take_bytes(6))

        _ = data.take_hex() # Consume checksum - value has already been checked

        if not data.is_consumed():
            raise ValueError("Unable to consume all data")

        return Packet(
            is_user_interface_resp=is_user_interface_resp,
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


def checksum_matches(data: bytes) -> bool:
    try:
        checksum = 0
        for pos in range(0, len(data), 2):
            checksum += int(data[pos : pos + 2], 16)
    except ValueError:
        _LOGGER.warning(f"Invalid non-hex character in data: {data!r}")
        return False

    return (checksum & 0xFF) == 0


def has_address(start: int, is_user_interface_resp: bool) -> bool:
    """
    Determine whether the packet has an "address" encoded into it.
    Status Update Responses to User Interface Packets are required to use
    start byte 0x82, which would normally indicate that no address is present.
    Regardless, these packets must contain an address
    """
    return bool(0x01 & start) or is_user_interface_resp


def has_timestamp(start: int) -> bool:
    return bool(StartByteBits.TIMESTAMP_Included.value & start)


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
