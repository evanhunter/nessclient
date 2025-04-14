"""
Example that prints events received by nessclient from the NESS alarm.

Defaults to running forever - use ctrl-C to end.
"""

import asyncio

from nessclient import ArmingMode, ArmingState, BaseEvent, Client

host = "127.0.0.1"
port = 65432


def main(timeout: int = 0) -> None:
    """Register event handlers then awaits events from nessclient."""
    loop = asyncio.get_event_loop()
    client = Client(host=host, port=port)

    @client.on_zone_change
    def on_zone_change(zone: int, triggered: bool) -> None:  # noqa: FBT001 # Bool part of Pre-defined API
        print(f"Zone {zone} changed to {triggered}")  # noqa: T201 # Valid CLI print

    @client.on_state_change
    def on_state_change(state: ArmingState, mode: ArmingMode | None) -> None:
        print(f"Alarm state changed to state:{state} mode:{mode}")  # noqa: T201 # Valid CLI print

    @client.on_event_received
    def on_event_received(event: BaseEvent) -> None:
        print(f"Event received: {event}")  # noqa: T201 # Valid CLI print

    task_group: asyncio.futures.Future[tuple[None, None, None]]

    async def canceller(timeout: float = 0) -> None:  # noqa: ASYNC109 # asyncio.timeout not available in Python3.10
        if timeout != 0:
            await asyncio.sleep(timeout)
            task_group.cancel()

    task_group = asyncio.gather(
        canceller(timeout),
        client.keepalive(),
        client.update(),
    )

    try:
        loop.run_until_complete(task_group)
    except asyncio.exceptions.CancelledError:
        print("Cancelled - shutting down")  # noqa: T201 # Valid CLI print

    loop.run_until_complete(client.close())


if __name__ == "__main__":
    main()
