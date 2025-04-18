"""Test the API of the nessclient Client class."""

from unittest.mock import AsyncMock, Mock

import pytest

from nessclient import Client
from nessclient.alarm import Alarm
from nessclient.connection import Connection


@pytest.fixture
def alarm() -> Alarm:
    """Mock alarm object fixture within the Client fixture."""
    return Mock()


@pytest.fixture
def connection() -> Connection:
    """Mock connection object fixture within the Client fixture."""
    return AsyncMock(Connection)


@pytest.fixture
def client(connection: AsyncMock, alarm: Alarm) -> Client:
    """Client object fixture for tests."""
    return Client(connection=connection, alarm=alarm)


def _get_data(pkt: bytes) -> bytes:
    """Get the data part from a UI request packet."""
    return pkt[7:-5]


@pytest.mark.asyncio
async def test_arm_away(connection: AsyncMock, client: Client) -> None:
    """Test that the arm_away() method sends the correct packet data."""
    await client.arm_away("1234")
    assert connection.write.call_count == 1
    assert _get_data(connection.write.call_args[0][0]) == b"A1234E"


@pytest.mark.asyncio
async def test_arm_home(connection: AsyncMock, client: Client) -> None:
    """Test that the arm_home() method sends the correct packet data."""
    await client.arm_home("1234")
    assert connection.write.call_count == 1
    assert _get_data(connection.write.call_args[0][0]) == b"H1234E"


@pytest.mark.asyncio
async def test_disarm(connection: AsyncMock, client: Client) -> None:
    """Test that the disarm() method sends the correct packet data."""
    await client.disarm("1234")
    assert connection.write.call_count == 1
    assert _get_data(connection.write.call_args[0][0]) == b"1234E"


@pytest.mark.asyncio
async def test_panic(connection: AsyncMock, client: Client) -> None:
    """Test that the panic() method sends the correct packet data."""
    await client.panic("1234")
    assert connection.write.call_count == 1
    assert _get_data(connection.write.call_args[0][0]) == b"*1234E"


@pytest.mark.asyncio
async def test_aux_on(connection: AsyncMock, client: Client) -> None:
    """Test that the aux() method (turn on) sends the correct packet data."""
    await client.aux(1, state=True)
    assert connection.write.call_count == 1
    assert _get_data(connection.write.call_args[0][0]) == b"11*"


@pytest.mark.asyncio
async def test_aux_off(connection: AsyncMock, client: Client) -> None:
    """Test that the aux() method (turn off) sends the correct packet data."""
    await client.aux(1, state=False)
    assert connection.write.call_count == 1
    assert _get_data(connection.write.call_args[0][0]) == b"11#"


@pytest.mark.asyncio
async def test_update(connection: AsyncMock, client: Client) -> None:
    """Test that the update() method sends the correct Status Request packet data."""
    await client.update()
    assert connection.write.call_count == 3  # noqa: PLR2004 # Magic value not worth a constant
    commands = {
        _get_data(connection.write.call_args_list[0][0][0]),
        _get_data(connection.write.call_args_list[1][0][0]),
        _get_data(connection.write.call_args_list[2][0][0]),
    }
    assert commands == {b"S00", b"S05", b"S14"}


@pytest.mark.asyncio
async def test_send_command(connection: AsyncMock, client: Client) -> None:
    """Test that the send_command sends the requested packet data."""
    await client.send_command("AHEXFVPDM")
    assert connection.write.call_count == 1
    assert _get_data(connection.write.call_args[0][0]) == b"AHEXFVPDM"


@pytest.mark.asyncio
async def test_send_command_has_newlines(connection: AsyncMock, client: Client) -> None:
    """Test that the send_command sends packet with CRLF ending."""
    await client.send_command("A1234E")
    assert connection.write.call_count == 1
    assert connection.write.call_args[0][0][-2:] == b"\r\n"


@pytest.mark.asyncio
async def test_send_command_2(connection: AsyncMock, client: Client) -> None:
    """Test that the send_command sends the requested packet data (with '*', '#')."""
    await client.send_command("V*#3468DM")
    assert connection.write.call_count == 1

    assert _get_data(connection.write.call_args[0][0]) == b"V*#3468DM"


def test_keepalive_bad_data_does_not_crash(
    client: Client, alarm: AsyncMock, connection: AsyncMock
) -> None:
    """Check that"""
    client.received_data(b"garbage\r\n")

    assert alarm.handle_event.call_count == 0

    connection.return_value.read.return_value = b"garbage\r\n"

    # @patch('')

    # task_group: asyncio.futures.Future[tuple[None, None]]

    # async def canceller(timeout: float = 0) -> None:  # noqa: ASYNC109 # asyncio.timeout not available in Python3.10
    #     if timeout != 0:
    #         await asyncio.sleep(timeout)
    #         task_group.cancel()

    # task_group = asyncio.gather(canceller(timeout=2), client.keepalive())

    # assert alarm.handle_event.call_count == 0


def test_keepalive_unknown_event_does_not_crash() -> None:
    # TODO(NW): Find a way to test this functionality inside the recv loop
    pass


def test_keepalive_polls_alarm_connection() -> None:
    # TODO(NW): Find a way to test this functionality inside the send loop
    pass


def test_on_event_received_callback() -> None:
    # TODO(NW): Find a way to test this functionality inside the recv loop
    pass


def test_on_state_change_callback_is_registered(client: Client, alarm: Mock) -> None:
    """Check on_state_change() callback gets provided to the alarm class."""
    cb = Mock()
    client.on_state_change(cb)
    assert alarm.on_state_change.call_count == 1
    assert alarm.on_state_change.call_args[0][0] == cb


def test_on_zone_change_callback_is_registered(client: Client, alarm: Mock) -> None:
    """Check on_zone_change() callback gets provided to the alarm class."""
    cb = Mock()
    client.on_zone_change(cb)
    assert alarm.on_zone_change.call_count == 1
    assert alarm.on_zone_change.call_args[0][0] == cb


def test_bad_args() -> None:
    """Check that bad arguments are rejected by Client constructor."""
    with pytest.raises(
        ValueError,
        match=r"Must provide host\+port or serial_tty or connection object",
    ):
        Client(host=None, port=1234)
    with pytest.raises(
        ValueError,
        match=r"Must provide host\+port or serial_tty or connection object",
    ):
        Client(host="test123", port=None)


@pytest.mark.asyncio
async def test_close(connection: AsyncMock, client: Client) -> None:
    """Check close() method calls the connection close method."""
    await client.close()
    assert connection.close.call_count == 1
