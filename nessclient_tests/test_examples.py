"""Test the examples and the nessclient CLI tool."""

import logging

from click.testing import CliRunner

from examples import listening_for_events, sending_commands
from nessclient.cli.__main__ import cli
from nessclient.cli.server import AlarmServer

_LOGGER = logging.getLogger(__name__)

logging.basicConfig(
    format="%(asctime)s.%(msecs)03d %(threadName)-25s %(levelname)-8s %(message)s",
    level=logging.DEBUG,
    datefmt="%Y-%m-%d %H:%M:%S",
)


def test_listening_for_events() -> None:
    """Test the listening_for_events.py example operation."""
    # Start an alarm-emulation server which will send events to the example
    server = AlarmServer(host=listening_for_events.host, port=listening_for_events.port)
    server.start(interactive=False, with_simulation=True)

    # Run the example for 5 seconds
    listening_for_events.main(timeout=5)

    # Shutdown
    server.stop()


def test_sending_commands() -> None:
    """Test the sending_commands.py example operation."""
    # Start an alarm-emulation server which will receive commands
    server = AlarmServer(host=sending_commands.host, port=sending_commands.port)
    server.start(interactive=False)

    # Run the example
    sending_commands.main()

    # Shutdown
    server.stop()


def test_cli() -> None:
    """Test the nessclient CLI tool operation."""
    _LOGGER.info("CLI Test")
    runner = CliRunner()

    # Test the version command and log-level argument
    # Run equivalent of python3 -m nessclient.cli --log-level debug version
    _LOGGER.info("Invoking 1")
    runner.invoke(cli, args=["--log-level", "debug", "version"])

    # Setup a alarm-emulator server to allow testing of 'send-command' command
    host = "127.0.0.1"
    port = 65432
    server = AlarmServer(host=host, port=port)
    server.start(interactive=False)

    # Test the send-command command and with host:port
    # Run equivalent of:
    # python3 -m nessclient.cli --log-level info send-command \
    #     --host 127.0.0.1 --port 65432 TESTING
    _LOGGER.info("Invoking 2")
    runner.invoke(
        cli,
        args=[
            "--log-level",
            "info",
            "send-command",
            "--host",
            host,
            "--port",
            str(port),
            "TESTING",
        ],
    )

    # stop the alarm-emulator server to allow testing of the 'server' command next
    _LOGGER.info("Test stopping server")
    server.stop()

    # Test the send-command command and with host:port
    # Run equivalent of:
    # python3 -m nessclient.cli --log-level info server \
    #     --host 127.0.0.1 --port 65432
    # Sending a series of interactive CLI alarm-emulator server commands
    _LOGGER.info("Invoking 3")
    runner.invoke(
        cli,
        args=[
            "--log-level",
            "info",
            "server",
            "--host",
            host,
            "--port",
            str(port),
        ],
        input="A\nAA\nAH\nAD\nAN\nAV\nT\nS\nQ\n",
    )

    _LOGGER.info("CLI Test Complete")
