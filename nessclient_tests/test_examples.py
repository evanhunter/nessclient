import unittest
import logging

from examples import listening_for_events, sending_commands

from nessclient.cli.server import AlarmServer
from nessclient.cli.__main__ import cli

from click.testing import CliRunner

_LOGGER = logging.getLogger(__name__)

logging.basicConfig(
    format="%(asctime)s.%(msecs)03d %(threadName)-25s %(levelname)-8s %(message)s",
    level=logging.DEBUG,
    datefmt="%Y-%m-%d %H:%M:%S",
)


class ExampleTests(unittest.TestCase):

    def test_listening_for_events(self) -> None:
        server = AlarmServer(
            host=listening_for_events.host, port=listening_for_events.port
        )
        server.start(interactive=False)
        listening_for_events.main(5)
        server.stop()

    def test_sending_commands(self) -> None:
        server = AlarmServer(host=sending_commands.host, port=sending_commands.port)
        server.start(interactive=False)
        sending_commands.main()
        server.stop()

    def test_cli(self) -> None:
        _LOGGER.info("CLI Test")
        host = "127.0.0.1"
        port = 65432
        server = AlarmServer(host=host, port=port)
        server.start(interactive=False)
        runner = CliRunner()
        _LOGGER.info("Invoking 1")
        runner.invoke(cli, args=["--log-level", "debug", "version"])

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

        _LOGGER.info("Test stopping server")
        server.stop()

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
