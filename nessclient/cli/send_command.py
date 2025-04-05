import asyncio
import logging

import click

from ..client import Client

_LOGGER = logging.getLogger(__name__)

logging.basicConfig(
    format="%(asctime)s.%(msecs)03d %(threadName)-25s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


@click.command(help="Send a command")
@click.option("--host", default=None)
@click.option("--port", type=int, default=None)
@click.option("--serial", type=str, default=None)
@click.argument("command")
def send_command(host: str, port: int, serial: str, command: str) -> None:
    _LOGGER.debug(f"send_command {host} {port} {serial} {command}")
    loop = asyncio.get_event_loop()
    client = Client(host=host, port=port, serial_tty=serial)

    loop.run_until_complete(client.send_command(command))
    loop.run_until_complete(client.close())
    loop.close()
