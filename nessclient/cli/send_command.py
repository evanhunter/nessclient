"""Provide the 'send_command' nessclient CLI command."""

import asyncio
import logging

import click

from nessclient.client import Client

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
    """Add the 'send_command' CLI command which sends a command packet."""
    _LOGGER.debug("send_command %s %s %s %s", host, port, serial, command)
    loop = asyncio.get_event_loop()
    client = Client(host=host, port=port, serial_tty=serial)

    loop.run_until_complete(client.send_command(command))
    loop.run_until_complete(client.close())
    loop.close()
