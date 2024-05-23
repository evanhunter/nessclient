import asyncio

from nessclient import Client, ArmingState, ArmingMode, BaseEvent

loop = asyncio.get_event_loop()
host = "127.0.0.1"
port = 65432
client = Client(host=host, port=port)


@client.on_zone_change
def on_zone_change(zone: int, triggered: bool) -> None:
    print("Zone {} changed to {}".format(zone, triggered))


@client.on_state_change
def on_state_change(state: ArmingState, mode: ArmingMode | None) -> None:
    print("Alarm state changed to {}".format(state))


@client.on_event_received
def on_event_received(event: BaseEvent) -> None:
    print("Event received:", event)


loop.run_until_complete(
    asyncio.gather(
        client.keepalive(),
        client.update(),
    )
)

loop.run_until_complete(client.close())
loop.close()
