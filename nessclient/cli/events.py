"""Provide the 'events' nessclient CLI command."""

import asyncio

import click

from nessclient.alarm import ArmingMode, ArmingState
from nessclient.client import Client
from nessclient.event import BaseEvent

from .server import DEFAULT_PORT


@click.command(help="Listen for emitted alarm events")
@click.option("--host", default="localhost")
@click.option("--port", type=int, default=DEFAULT_PORT)
@click.option("--serial", type=str, default=None)
@click.option("--update-interval", type=int, default=60)
@click.option("--infer-arming-state/--no-infer-arming-state")
def events(
    *,
    host: str | None,
    port: int | None,
    serial: str | None,
    update_interval: int,
    infer_arming_state: bool,
) -> None:
    """Add the 'events' CLI command which prints received events until cancelled."""
    if serial is not None and host == "localhost" and port == DEFAULT_PORT:
        host = None
        port = None
    loop = asyncio.get_event_loop()
    client = Client(
        host=host,
        port=port,
        serial_tty=serial,
        infer_arming_state=infer_arming_state,
        update_interval=update_interval,
    )

    @client.on_zone_change
    def on_zone_change(zone: int, triggered: bool) -> None:  # noqa: FBT001 # Bool part of Pre-defined API
        print(f"Zone {zone} changed to {triggered}")  # noqa: T201 # Valid CLI print

    @client.on_state_change
    def on_state_change(state: ArmingState, arming_mode: ArmingMode | None) -> None:
        print(f"Alarm state changed to {state} (mode: {arming_mode})")  # noqa: T201 # Valid CLI print

    @client.on_event_received
    def on_event_received(event: BaseEvent) -> None:
        print(event)  # noqa: T201 # Valid CLI print

    keepalive_task = loop.create_task(client.keepalive())
    update_task = loop.create_task(client.update())

    loop.run_forever()

    keepalive_task.cancel()
    update_task.cancel()
