from typing import Tuple, Optional, Dict, Any, List, ParamSpec
from typing_extensions import Buffer
import enum
import io
import array
import collections

_P = ParamSpec("_P")

class RS485Settings(object): ...

class SerialBase(io.RawIOBase):
    class ParitiesType(enum.Enum):
        PARITY_NONE: str = ...
        PARITY_EVEN: str = ...
        PARITY_ODD: str = ...
        PARITY_MARK: str = ...
        PARITY_SPACE: str = ...

    class ByteSizeType(enum.Enum):
        FIVEBITS: int = ...
        SIXBITS: int = ...
        SEVENBITS: int = ...
        EIGHTBITS: int = ...

    class StopBitsType(enum.Enum):
        STOPBITS_ONE: int = ...
        STOPBITS_ONE_POINT_FIVE: float = ...
        STOPBITS_TWO: int = ...

    # default values, may be overridden in subclasses that do not support all values
    BAUDRATES: Tuple[int] = ...
    BYTESIZES: Tuple[int] = ...
    PARITIES: Tuple[ParitiesType] = ...
    STOPBITS: Tuple[float] = ...

    def __init__(
        self,
        port: Optional[str] = ...,
        baudrate: int = ...,
        bytesize: ByteSizeType = ...,
        parity: ParitiesType = ...,
        stopbits: StopBitsType = ...,
        timeout: Optional[float] = ...,
        xonxoff: bool = ...,
        rtscts: bool = ...,
        write_timeout: Optional[float] = ...,
        dsrdtr: Optional[bool] = ...,
        inter_byte_timeout: Optional[float] = ...,
        exclusive: Optional[bool] = ...,
        **kwargs: Dict[str, Optional[float]]
    ) -> None: ...
    @property
    def port(self) -> Optional[str]: ...
    @port.setter
    def port(self, port: Optional[str]) -> None: ...
    @property
    def baudrate(self) -> int: ...
    @baudrate.setter
    def baudrate(self, baudrate: int) -> None: ...
    @property
    def bytesize(self) -> ByteSizeType: ...
    @bytesize.setter
    def bytesize(self, bytesize: ByteSizeType) -> None: ...
    @property
    def exclusive(self) -> Optional[bool]: ...
    @exclusive.setter
    def exclusive(self, exclusive: Optional[bool]) -> None: ...
    @property
    def parity(self) -> ParitiesType: ...
    @parity.setter
    def parity(self, parity: ParitiesType) -> None: ...
    @property
    def stopbits(self) -> StopBitsType: ...
    @stopbits.setter
    def stopbits(self, stopbits: StopBitsType) -> None: ...
    @property
    def timeout(self) -> Optional[float]: ...
    @timeout.setter
    def timeout(self, timeout: Optional[float]) -> None: ...
    @property
    def write_timeout(self) -> Optional[float]: ...
    @write_timeout.setter
    def write_timeout(self, timeout: Optional[float]) -> None: ...
    @property
    def inter_byte_timeout(self) -> Optional[float]: ...
    @inter_byte_timeout.setter
    def inter_byte_timeout(self, ic_timeout: Optional[float]) -> None: ...
    @property
    def xonxoff(self) -> bool: ...
    @xonxoff.setter
    def xonxoff(self, xonxoff: bool) -> None: ...
    @property
    def rtscts(self) -> bool: ...
    @rtscts.setter
    def rtscts(self, rtscts: bool) -> None: ...
    @property
    def dsrdtr(self) -> bool: ...
    @dsrdtr.setter
    def dsrdtr(self, dsrdtr: Optional[bool] = ...) -> None: ...
    @property
    def rts(self) -> bool: ...
    @rts.setter
    def rts(self, value: bool) -> None: ...
    @property
    def dtr(self) -> bool: ...
    @dtr.setter
    def dtr(self, value: bool) -> None: ...
    @property
    def break_condition(self) -> bool: ...
    @break_condition.setter
    def break_condition(self, value: bool) -> None: ...
    @property
    def rs485_mode(self) -> Optional[RS485Settings]: ...
    @rs485_mode.setter
    def rs485_mode(self, rs485_settings: Optional[RS485Settings]) -> None: ...
    def get_settings(self) -> Dict[str, Any]: ...
    def apply_settings(self, d: Dict[str, Any]) -> None: ...
    def __repr__(self) -> str: ...
    def readable(self) -> bool: ...
    def writable(self) -> bool: ...
    def seekable(self) -> bool: ...
    def readinto(self, b: Buffer) -> int: ...
    def send_break(self, duration: float = ...) -> None: ...
    def flushInput(self) -> None: ...
    def flushOutput(self) -> None: ...
    def inWaiting(self) -> int: ...
    def sendBreak(self, duration: float = ...) -> None: ...
    def setRTS(self, value: bool = ...) -> None: ...
    def setDTR(self, value: bool = ...) -> None: ...
    def getCTS(self) -> bool: ...
    def getDSR(self) -> bool: ...
    def getRI(self) -> bool: ...
    def getCD(self) -> bool: ...
    def setPort(self, port: Optional[str]) -> None: ...
    @property
    def writeTimeout(self) -> Optional[float]: ...
    @writeTimeout.setter
    def writeTimeout(self, timeout: Optional[float]) -> None: ...
    @property
    def interCharTimeout(self) -> Optional[float]: ...
    @interCharTimeout.setter
    def interCharTimeout(self, interCharTimeout: Optional[float]) -> None: ...
    def getSettingsDict(self) -> Dict[str, Any]: ...
    def applySettingsDict(self, d: Dict[str, Any]) -> None: ...
    def isOpen(self) -> bool: ...
    def read_all(self) -> Optional[bytes]: ...
    def read_until(self, expected: str = ..., size: Optional[int] = ...) -> bytes: ...
    def iread_until(self, *args: _P.args, **kwargs: _P.kwargs) -> bytes: ...

class PlatformSpecificBase(object): ...
class PlatformSpecific(PlatformSpecificBase): ...

class Serial(SerialBase, PlatformSpecific):
    def open(self) -> None: ...
    def close(self) -> None: ...
    @property
    def in_waiting(self) -> int: ...
    def read(self, size: int = ...) -> bytes: ...
    def cancel_read(self) -> None: ...
    def cancel_write(self) -> None: ...
    def write(self, data: Buffer) -> int: ...
    def flush(self) -> None: ...
    def reset_input_buffer(self) -> None: ...
    def reset_output_buffer(self) -> None: ...
    def send_break(self, duration: float = ...) -> None: ...
    @property
    def cts(self) -> bool: ...
    @property
    def dsr(self) -> bool: ...
    @property
    def ri(self) -> bool: ...
    @property
    def cd(self) -> bool: ...

PARITY_NONE = SerialBase.ParitiesType.PARITY_NONE
PARITY_EVEN = SerialBase.ParitiesType.PARITY_EVEN
PARITY_ODD = SerialBase.ParitiesType.PARITY_ODD
PARITY_MARK = SerialBase.ParitiesType.PARITY_MARK
PARITY_SPACE = SerialBase.ParitiesType.PARITY_SPACE

FIVEBITS = SerialBase.ByteSizeType.FIVEBITS
SIXBITS = SerialBase.ByteSizeType.SIXBITS
SEVENBITS = SerialBase.ByteSizeType.SEVENBITS
EIGHTBITS = SerialBase.ByteSizeType.EIGHTBITS

STOPBITS_ONE = SerialBase.StopBitsType.STOPBITS_ONE
STOPBITS_ONE_POINT_FIVE = SerialBase.StopBitsType.STOPBITS_ONE_POINT_FIVE
STOPBITS_TWO = SerialBase.StopBitsType.STOPBITS_TWO
