"""Module file for a test alarm emulator with an interactive CLI UI."""

import click

from .alarm import Alarm
from .alarm_server import AlarmServer

DEFAULT_PORT = 65432

__all__ = ["Alarm", "AlarmServer"]


@click.command(help="Run a dummy server")
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=DEFAULT_PORT)
def server(host: str, port: int) -> None:
    s = AlarmServer(host=host, port=port)
    s.start()
