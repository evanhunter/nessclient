import logging
import unittest
import datetime

# from unittest.mock import Mock

from concurrent.futures._base import CancelledError

# import sys
from typing import Optional, Callable, cast

# sys.path.insert(0, "/home/evan/python/nessclient/")
import asyncio
import threading
import time

# import pytest

from nessclient.cli.server import AlarmServer
from nessclient.cli.server.alarm import Alarm
from nessclient.cli.server.zone import Zone
from nessclient import Client, ArmingState, ArmingMode, BaseEvent
from nessclient.client import AllStatus
from nessclient.event import StatusUpdate

# from abc import ABC, abstractmethod


localhost = "127.0.0.1"


_LOGGER = logging.getLogger(__name__)

logging.basicConfig(
    format="%(asctime)s.%(msecs)03d %(threadName)-25s %(levelname)-8s %(message)s",
    level=logging.DEBUG,
    datefmt="%Y-%m-%d %H:%M:%S",
)


class test_client_server_pair:
    test_port = 65433

    server: AlarmServer
    client: Client
    loop: asyncio.AbstractEventLoop
    loop_thread: threading.Thread
    keep_alive_task: asyncio.Task[None]
    keepalive_thread: threading.Thread

    def __init__(
        self,
        zone_change_callback: Optional[Callable[[int, bool], None]] = None,
        state_change_callback: Optional[
            Callable[[ArmingState, Optional[ArmingMode]], None]
        ] = None,
        event_received_callback: Optional[Callable[[BaseEvent], None]] = None,
        server_host: str = localhost,
        client_host: str = localhost,
        server_port: int = test_port,
        client_port: int = test_port,
    ) -> None:

        _LOGGER.info("test_client_server_pair init")

        self.server = AlarmServer(host=server_host, port=server_port)
        self.client = Client(host=client_host, port=client_port, update_interval=1)

        self.client.on_zone_change(zone_change_callback)
        self.client.on_state_change(state_change_callback)
        self.client.on_event_received(event_received_callback)

        self.loop = asyncio.new_event_loop()
        self.loop_thread = threading.Thread(
            target=lambda: self.loop.run_forever(), name="asyncio event loop"
        )
        self.loop_thread.start()

    async def keepalive_task(self) -> None:
        _LOGGER.info("keepalive_task started")
        self.keep_alive_task = self.loop.create_task(
            self.client.keepalive(), name="keepalive_task"
        )
        await self.keep_alive_task

    def do_keepalive(self) -> None:
        _LOGGER.info("do_keepalive start")
        try:
            asyncio.run_coroutine_threadsafe(self.keepalive_task(), self.loop).result()
        except CancelledError:
            _LOGGER.info("do_keepalive cancelled")
            pass  # this happens when stopping

    def run(self) -> None:
        self.server.start(interactive=False, with_simulation=False)
        time.sleep(0.05)
        self.keepalive_thread = threading.Thread(
            target=self.do_keepalive, name="client keep-alive"
        )
        self.keepalive_thread.start()

    async def _cancel(self) -> None:
        _LOGGER.info("cancel pair")
        self.keep_alive_task.cancel()
        _LOGGER.info("close client")
        await self.client.close()
        self.server.stop()
        _LOGGER.info("cancel pair done")

    def stop(self) -> None:
        _LOGGER.info("Pair stopping")
        asyncio.run_coroutine_threadsafe(self._cancel(), self.loop).result()
        self.keepalive_thread.join()
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.loop_thread.join()
        self.loop.close()
        _LOGGER.info("Pair stopped")


class ClientServerConnectionTests(unittest.TestCase):

    zone_changes: int = 0
    state_changes: int = 0
    events_recieved: int = 0

    def on_zone_change_test(self, zone: int, triggered: bool) -> None:
        print(f"Zone {zone} changed to {triggered}")
        self.zone_changes += 1

    def on_state_change_test(
        self, state: ArmingState, arming_mode: ArmingMode | None
    ) -> None:
        print(f"Alarm state changed to {state} (mode: {arming_mode})")
        self.state_changes += 1

    def on_event_received_test(self, event: BaseEvent) -> None:
        print(event)
        self.events_recieved += 1

    def test_basic_connection(self) -> None:
        _LOGGER.info("Basic Connection Test")
        pair = test_client_server_pair()
        pair.run()
        time.sleep(1)
        self.assertEqual(pair.client.connected_count, 1)
        pair.stop()
        _LOGGER.info("Basic Connection Test Complete")

    def test_exercise_connection(self) -> None:
        _LOGGER.info("Exercise Connection Test")
        pair = test_client_server_pair(
            zone_change_callback=lambda zone, triggered: self.on_zone_change_test(
                zone, triggered
            ),
            state_change_callback=lambda state, arming_mode: self.on_state_change_test(
                state, arming_mode
            ),
            event_received_callback=lambda event: self.on_event_received_test(event),
        )

        pair.run()
        time.sleep(1)
        self.assertEqual(pair.client.connected_count, 1)

        pair.server._server._write_to_all_clients(b"\xf5\xf5\xf5\xf5\r\n")

        # Exercise zone update function get_zone_state_event_type()
        pair.server._alarm.update_zone(5, Zone.State.SEALED)
        pair.server._alarm.update_zone(5, Zone.State.UNSEALED)

        self.assertRaises(
            NotImplementedError,
            lambda: pair.server._alarm.update_zone(5, cast(Zone.State, 5)),
        )

        time.sleep(1)
        pair.client._last_recv = datetime.datetime.now() - datetime.timedelta(
            seconds=120
        )

        pair.server._alarm.EXIT_DELAY = 2
        pair.server._alarm.ENTRY_DELAY = 2

        async def testcommands() -> None:
            await pair.client.send_command("S00")

            # Test waiting for status update response
            event = await pair.client.request_and_wait_status_update(
                StatusUpdate.RequestID.ZONE_INPUT_UNSEALED
            )
            _LOGGER.debug(f"Waited for {event}")
            assert (
                event is not None
                and event.request_id == StatusUpdate.RequestID.ZONE_INPUT_UNSEALED
            )

            # Test waiting for status update response - this should timeout
            event = await pair.client.request_and_wait_status_update(
                StatusUpdate.RequestID.ZONE_CBUS_UNSEALED
            )
            assert event is None

            # Test waiting for all status responses
            all_status: AllStatus = await pair.client.update_all_wait()
            _LOGGER.debug(f"Waited for {all_status}")
            assert all_status.Arming is not None

            _LOGGER.debug("arming")
            await pair.client.arm_away("1234")
            await asyncio.sleep(1)
            self.assertEqual(pair.server._alarm.state, Alarm.ArmingState.EXIT_DELAY)
            # wait for exit delay to finish
            await asyncio.sleep(2)
            await pair.client.send_command("S00")
            await pair.client.send_command("S14")
            self.assertEqual(pair.server._alarm.state, Alarm.ArmingState.ARMED)
            self.assertEqual(
                pair.server._alarm._arming_mode, Alarm.ArmingMode.ARMED_AWAY
            )

            # trip the alarm immediate
            pair.server._alarm.trip(False)
            await asyncio.sleep(0.5)
            await pair.client.send_command("S14")
            self.assertEqual(pair.server._alarm.state, Alarm.ArmingState.TRIPPED)

            _LOGGER.debug("disarming")
            await pair.client.disarm("1234")
            await asyncio.sleep(0.5)
            await pair.client.send_command("S14")
            self.assertEqual(pair.server._alarm.state, Alarm.ArmingState.DISARMED)

            _LOGGER.debug("arming home")
            await pair.client.arm_home("1234")
            await asyncio.sleep(1)
            await pair.client.send_command("S14")
            self.assertEqual(pair.server._alarm.state, Alarm.ArmingState.EXIT_DELAY)
            # wait for exit delay to finish
            await asyncio.sleep(2)
            await pair.client.send_command("S14")
            self.assertEqual(pair.server._alarm.state, Alarm.ArmingState.ARMED)
            self.assertEqual(
                pair.server._alarm._arming_mode, Alarm.ArmingMode.ARMED_HOME
            )

            # trip the alarm with entry delay
            pair.server._alarm.trip()
            await asyncio.sleep(1)
            await pair.client.send_command("S14")
            self.assertEqual(pair.server._alarm.state, Alarm.ArmingState.ENTRY_DELAY)
            # wait for entry delay to finish
            await asyncio.sleep(2)
            await pair.client.send_command("S14")
            self.assertEqual(pair.server._alarm.state, Alarm.ArmingState.TRIPPED)

            _LOGGER.debug("disarming under duress")
            await pair.client.send_command("51234E")
            await asyncio.sleep(0.5)
            await pair.client.send_command("S14")
            self.assertEqual(pair.server._alarm.state, Alarm.ArmingState.DURESS)

            _LOGGER.debug("aux on")
            await pair.client.aux(1, True)
            await asyncio.sleep(0.5)
            _LOGGER.debug("aux off")
            await pair.client.aux(1, False)
            # TODO: needs checking of state in server

            _LOGGER.debug("panic")
            await pair.client.panic("1234")
            await asyncio.sleep(0.5)
            await pair.client.send_command("S14")
            self.assertEqual(pair.server._alarm.state, Alarm.ArmingState.PANIC)

            _LOGGER.debug("Medical")
            await pair.client.send_command("2E")
            await asyncio.sleep(0.5)
            await pair.client.send_command("S14")
            self.assertEqual(pair.server._alarm.state, Alarm.ArmingState.MEDICAL)

            _LOGGER.debug("Fire")
            await pair.client.send_command("3E")
            await asyncio.sleep(0.5)
            await pair.client.send_command("S14")
            self.assertEqual(pair.server._alarm.state, Alarm.ArmingState.FIRE)

            _LOGGER.debug("testcommands done")

        asyncio.run_coroutine_threadsafe(testcommands(), pair.loop).result()

        # Server console Arm
        pair.server.interactive_command("A")
        time.sleep(1)
        self.assertEqual(pair.server._alarm.state, Alarm.ArmingState.EXIT_DELAY)
        # wait for exit delay to finish
        time.sleep(2)
        self.assertEqual(pair.server._alarm.state, Alarm.ArmingState.ARMED)
        self.assertEqual(pair.server._alarm._arming_mode, Alarm.ArmingMode.ARMED_AWAY)

        # Server console Disarm
        pair.server.interactive_command("D")
        time.sleep(0.5)
        self.assertEqual(pair.server._alarm.state, Alarm.ArmingState.DISARMED)

        # Server console Arm-Home
        pair.server.interactive_command("AH")
        time.sleep(1)
        self.assertEqual(pair.server._alarm.state, Alarm.ArmingState.EXIT_DELAY)
        # wait for exit delay to finish
        time.sleep(2)
        self.assertEqual(pair.server._alarm.state, Alarm.ArmingState.ARMED)
        self.assertEqual(pair.server._alarm._arming_mode, Alarm.ArmingMode.ARMED_HOME)

        # Server console Arm-Day
        pair.server.interactive_command("AD")
        time.sleep(1)
        self.assertEqual(pair.server._alarm.state, Alarm.ArmingState.EXIT_DELAY)
        # wait for exit delay to finish
        time.sleep(2)
        self.assertEqual(pair.server._alarm.state, Alarm.ArmingState.ARMED)
        self.assertEqual(pair.server._alarm._arming_mode, Alarm.ArmingMode.ARMED_DAY)

        # Server console Arm-Night
        pair.server.interactive_command("AN")
        time.sleep(1)
        self.assertEqual(pair.server._alarm.state, Alarm.ArmingState.EXIT_DELAY)
        # wait for exit delay to finish
        time.sleep(2)
        self.assertEqual(pair.server._alarm.state, Alarm.ArmingState.ARMED)
        self.assertEqual(pair.server._alarm._arming_mode, Alarm.ArmingMode.ARMED_NIGHT)

        # Server console Arm-Vacation
        pair.server.interactive_command("AV")
        time.sleep(1)
        self.assertEqual(pair.server._alarm.state, Alarm.ArmingState.EXIT_DELAY)
        # wait for exit delay to finish
        time.sleep(2)
        self.assertEqual(pair.server._alarm.state, Alarm.ArmingState.ARMED)
        self.assertEqual(
            pair.server._alarm._arming_mode, Alarm.ArmingMode.ARMED_VACATION
        )

        # Server console Trip
        pair.server.interactive_command("T")
        time.sleep(1)
        self.assertEqual(pair.server._alarm.state, Alarm.ArmingState.ENTRY_DELAY)
        # wait for exit delay to finish
        time.sleep(2)
        self.assertEqual(pair.server._alarm.state, Alarm.ArmingState.TRIPPED)

        # Server console toggle Simulation
        pair.server.interactive_command("S")
        time.sleep(0.5)
        pair.server.interactive_command("S")
        # TODO: check if simulation started/stopped

        # Server console quit
        pair.server.interactive_command("Q")

        time.sleep(0.5)
        pair.stop()
        _LOGGER.info("Exercise Connection Test Complete")

    def test_refused_connection(self) -> None:
        _LOGGER.info("Connection Refused Test")
        pair = test_client_server_pair(
            client_port=test_client_server_pair.test_port + 1
        )  # ensure connection refused
        pair.run()
        time.sleep(5)
        self.assertEqual(pair.client.connected_count, 0)
        pair.stop()
        _LOGGER.info("Connection Refused Test Complete")

    def test_disconnect_connection(self) -> None:
        _LOGGER.info("Disconnection Test")
        pair = test_client_server_pair()
        pair.run()
        time.sleep(1)
        pair.server._server.disconnect_all_clients()
        time.sleep(1)

        asyncio.run_coroutine_threadsafe(pair.client._connect(), pair.loop).result()
        self.assertEqual(pair.client.disconnection_count, 1)

        pair.stop()
        _LOGGER.info("Disconnection Test Complete")
