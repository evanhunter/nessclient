import asyncio
import datetime
import logging
import threading
import time
import unittest
from collections.abc import Callable
from concurrent.futures._base import CancelledError
from typing import cast

import pytest

from nessclient import ArmingMode, ArmingState, BaseEvent, Client
from nessclient.cli.server import AlarmServer
from nessclient.cli.server.alarm import Alarm
from nessclient.cli.server.zone import Zone
from nessclient.event import StatusUpdate

localhost = "127.0.0.1"


_LOGGER = logging.getLogger(__name__)

logging.basicConfig(
    format="%(asctime)s.%(msecs)03d %(threadName)-25s %(levelname)-8s %(message)s",
    level=logging.DEBUG,
    datefmt="%Y-%m-%d %H:%M:%S",
)


class ClientServerPair:
    """
    Provides a nessclient Client connected to a test alarm emulator.

    Facilitates end-to-end tests
    """

    test_port = 65433  # Different from the default CLI server port

    server: AlarmServer
    client: Client
    loop: asyncio.AbstractEventLoop
    loop_thread: threading.Thread
    keep_alive_task: asyncio.Task[None]
    keepalive_thread: threading.Thread

    def __init__(  # noqa: PLR0913 # Not worth reducing arg count for test
        self,
        zone_change_callback: Callable[[int, bool], None] | None = None,
        state_change_callback: Callable[[ArmingState, ArmingMode | None], None]
        | None = None,
        event_received_callback: Callable[[BaseEvent], None] | None = None,
        server_host: str = localhost,
        client_host: str = localhost,
        server_port: int = test_port,
        client_port: int = test_port,
    ) -> None:
        """Create a ness Client and emulated-alarm server pair."""
        _LOGGER.info("ClientServerPair init")

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

    def run(self) -> None:
        """Start the Client + emulated-alarm."""

        def _do_keepalive() -> None:
            """Thread function to run the Client keep-alive task."""

            async def _keepalive_task() -> None:
                """Async task for he keep-alive task."""
                _LOGGER.info("keepalive_task started")
                self.keep_alive_task = self.loop.create_task(
                    self.client.keepalive(), name="keepalive_task"
                )
                await self.keep_alive_task

            _LOGGER.info("do_keepalive start")
            try:
                asyncio.run_coroutine_threadsafe(_keepalive_task(), self.loop).result()
            except CancelledError:
                # this happens when stopping
                _LOGGER.info("do_keepalive cancelled")

        self.server.start(interactive=False, with_simulation=False)
        time.sleep(0.05)
        self.keepalive_thread = threading.Thread(
            target=_do_keepalive, name="client keep-alive"
        )
        self.keepalive_thread.start()

    def stop(self) -> None:
        """Stop and close the Client + emulated-alarm server."""

        async def _cancel() -> None:
            """Cancel pending async tasks and stop the emulated-alarm server."""
            _LOGGER.info("cancel pair")
            self.keep_alive_task.cancel()
            _LOGGER.info("close client")
            await self.client.close()
            self.server.stop()
            _LOGGER.info("cancel pair done")

        _LOGGER.info("Pair stopping")
        asyncio.run_coroutine_threadsafe(_cancel(), self.loop).result()
        self.keepalive_thread.join()
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.loop_thread.join()
        self.loop.close()
        _LOGGER.info("Pair stopped")


class ClientServerConnectionTests(unittest.TestCase):
    zone_changes: int = 0
    state_changes: int = 0
    events_recieved: int = 0

    def test_basic_connection(self) -> None:
        _LOGGER.info("Basic Connection Test")
        pair = ClientServerPair()
        pair.run()
        time.sleep(1)
        assert pair.client.connected_count == 1
        pair.stop()
        _LOGGER.info("Basic Connection Test Complete")

    def test_exercise_connection(self) -> None:
        def _on_event_received_test(event: BaseEvent) -> None:
            """Event Received callback that counts calls to it."""
            _LOGGER.info(event)
            self.events_recieved += 1

        def _on_state_change_test(
            state: ArmingState, arming_mode: ArmingMode | None
        ) -> None:
            """State change callback that counts calls to it."""
            _LOGGER.info("Alarm state changed to %s (mode: %s)", state, arming_mode)
            self.state_changes += 1

        def _on_zone_change_test(zone: int, triggered: bool) -> None:  # noqa: FBT001 # Bool part of Pre-defined API
            """Zone change callback that counts calls to it."""
            _LOGGER.info("Zone %s changed to %s", zone, triggered)
            self.zone_changes += 1

        _LOGGER.info("Exercise Connection Test")
        pair = ClientServerPair(
            zone_change_callback=_on_zone_change_test,
            state_change_callback=_on_state_change_test,
            event_received_callback=_on_event_received_test,
        )

        pair.run()
        time.sleep(1)
        assert pair.client.connected_count == 1

        pair.server.server.write_to_all_clients(b"\xf5\xf5\xf5\xf5\r\n")

        # Exercise zone update function get_zone_state_event_type()
        pair.server.alarm.update_zone(5, Zone.State.SEALED)
        pair.server.alarm.update_zone(5, Zone.State.UNSEALED)

        with pytest.raises(NotImplementedError):
            pair.server.alarm.update_zone(5, cast("Zone.State", 5))

        # TODO: check that reconnect works
        # time.sleep(1)
        # pair.client._last_recv = (
        #     datetime.datetime.now()  # noqa: DTZ005 - local timezone - No function available
        #     - datetime.timedelta(seconds=120)
        # )

        pair.server.alarm.EXIT_DELAY = 2
        pair.server.alarm.ENTRY_DELAY = 2

        async def testcommands() -> None:
            await pair.client.send_command("S00")

            # Test waiting for status update response
            event = await pair.client.request_and_wait_status_update(
                StatusUpdate.RequestID.ZONE_INPUT_UNSEALED
            )
            _LOGGER.debug("Waited for %s", event)
            assert event is not None
            assert event.request_id == StatusUpdate.RequestID.ZONE_INPUT_UNSEALED

            # Test waiting for status update response - this should timeout
            event = await pair.client.request_and_wait_status_update(
                StatusUpdate.RequestID.ZONE_CBUS_UNSEALED
            )
            assert event is None

            # Test Client.arm_away() call causes alarm-emulator to initially
            # go to EXIT_DELAY state, then to ARMED_AWAY
            _LOGGER.debug("arming away")
            await pair.client.arm_away("1234")
            await asyncio.sleep(1)
            assert pair.server.alarm.state == Alarm.ArmingState.EXIT_DELAY
            # wait for exit delay to finish
            await asyncio.sleep(2)
            await pair.client.send_command("S00")
            await pair.client.send_command("S14")
            assert pair.server.alarm.state == Alarm.ArmingState.ARMED
            assert pair.server.alarm.arming_mode == Alarm.ArmingMode.ARMED_AWAY

            # Check the Client.trip() method can trigger the alarm immediately
            # to TRIPPED state. (i.e. without an entry-delay)
            pair.server.alarm.trip(delay=False)
            await asyncio.sleep(0.5)
            await pair.client.send_command("S14")
            assert pair.server.alarm.state == Alarm.ArmingState.TRIPPED

            # Check the Client.disarm() method when in a tripped state sets the
            # alarm to DISARMED state
            _LOGGER.debug("disarming")
            await pair.client.disarm("1234")
            await asyncio.sleep(0.5)
            await pair.client.send_command("S14")
            assert pair.server.alarm.state == Alarm.ArmingState.DISARMED

            # Test Client.arm_away() call causes alarm-emulator to initially
            # go to EXIT_DELAY state, then to ARMED_HOME
            _LOGGER.debug("arming home")
            await pair.client.arm_home("1234")
            await asyncio.sleep(1)
            await pair.client.send_command("S14")
            assert pair.server.alarm.state == Alarm.ArmingState.EXIT_DELAY
            # wait for exit delay to finish
            await asyncio.sleep(2)
            await pair.client.send_command("S14")
            assert pair.server.alarm.state == Alarm.ArmingState.ARMED
            assert pair.server.alarm.arming_mode == Alarm.ArmingMode.ARMED_HOME

            # Check the Client.trip() method can trigger the alarm, initially to
            # an ENTRY_DELAY state, then to TRIPPED state
            pair.server.alarm.trip()
            await asyncio.sleep(1)
            await pair.client.send_command("S14")
            assert pair.server.alarm.state == Alarm.ArmingState.ENTRY_DELAY
            # wait for entry delay to finish
            await asyncio.sleep(2)
            await pair.client.send_command("S14")
            assert pair.server.alarm.state == Alarm.ArmingState.TRIPPED

            # Check a 'duress' prefix whilst disarming sets the alarm
            # to DURESS state
            _LOGGER.debug("disarming under duress")
            await pair.client.send_command("51234E")
            await asyncio.sleep(0.5)
            await pair.client.send_command("S14")
            assert pair.server.alarm.state == Alarm.ArmingState.DURESS

            # Check that AUX on / off set the alarm auxilliary outputs
            _LOGGER.debug("aux on")
            await pair.client.aux(1, state=True)
            await asyncio.sleep(0.5)
            _LOGGER.debug("pair.server.alarm.aux = %s", pair.server.alarm.aux)
            assert pair.server.alarm.aux[0]
            _LOGGER.debug("aux off")
            await pair.client.aux(1, state=False)
            await asyncio.sleep(0.5)
            _LOGGER.debug("pair.server.alarm.aux = %s", pair.server.alarm.aux)
            assert not pair.server.alarm.aux[0]

            # Check the Client.panic() method sets the alarm to PANIC state
            _LOGGER.debug("panic")
            await pair.client.panic("1234")
            await asyncio.sleep(0.5)
            await pair.client.send_command("S14")
            assert pair.server.alarm.state == Alarm.ArmingState.PANIC

            # Check the 'medical' code sets the alarm to MEDICAL state
            _LOGGER.debug("Medical")
            await pair.client.send_command("2E")
            await asyncio.sleep(0.5)
            await pair.client.send_command("S14")
            assert pair.server.alarm.state == Alarm.ArmingState.MEDICAL

            # Check the 'fire' code sets the alarm to MEDICAL state
            _LOGGER.debug("Fire")
            await pair.client.send_command("3E")
            await asyncio.sleep(0.5)
            await pair.client.send_command("S14")
            assert pair.server.alarm.state == Alarm.ArmingState.FIRE

            _LOGGER.debug("testcommands done")

        asyncio.run_coroutine_threadsafe(testcommands(), pair.loop).result()

        ####################################################################
        # Test that the emulated-alarm server interactive CLI works properly

        # Arm the alarm from the emulated-alarm server console
        # Check that it goes initially to EXIT_DELAY state
        # Then to the ARMED_AWAY
        pair.server.interactive_command("A")
        time.sleep(1)
        assert pair.server.alarm.state == Alarm.ArmingState.EXIT_DELAY
        # wait for exit delay to finish
        time.sleep(2)
        assert pair.server.alarm.state == Alarm.ArmingState.ARMED
        assert pair.server.alarm.arming_mode == Alarm.ArmingMode.ARMED_AWAY

        # Disarm the alarm from the emulated-alarm server console
        # Check that it goes to DISARMED state
        pair.server.interactive_command("D")
        time.sleep(0.5)
        assert pair.server.alarm.state == Alarm.ArmingState.DISARMED

        # Arm-Home the alarm from the emulated-alarm server console
        # Check that it goes initially to EXIT_DELAY state
        # Then to the ARMED_HOME
        pair.server.interactive_command("AH")
        time.sleep(1)
        assert pair.server.alarm.state == Alarm.ArmingState.EXIT_DELAY
        # wait for exit delay to finish
        time.sleep(2)
        assert pair.server.alarm.state == Alarm.ArmingState.ARMED
        assert pair.server.alarm.arming_mode == Alarm.ArmingMode.ARMED_HOME

        # Arm-Day the alarm from the emulated-alarm server console
        # Check that it goes initially to EXIT_DELAY state
        # Then to the ARMED_DAY
        pair.server.interactive_command("AD")
        time.sleep(1)
        assert pair.server.alarm.state == Alarm.ArmingState.EXIT_DELAY
        # wait for exit delay to finish
        time.sleep(2)
        assert pair.server.alarm.state == Alarm.ArmingState.ARMED
        assert pair.server.alarm.arming_mode == Alarm.ArmingMode.ARMED_DAY

        # Arm-Night the alarm from the emulated-alarm server console
        # Check that it goes initially to EXIT_DELAY state
        # Then to the ARMED_NIGHT
        pair.server.interactive_command("AN")
        time.sleep(1)
        assert pair.server.alarm.state == Alarm.ArmingState.EXIT_DELAY
        # wait for exit delay to finish
        time.sleep(2)
        assert pair.server.alarm.state == Alarm.ArmingState.ARMED
        assert pair.server.alarm.arming_mode == Alarm.ArmingMode.ARMED_NIGHT

        # Arm-Vacation the alarm from the emulated-alarm server console
        # Check that it goes initially to EXIT_DELAY state
        # Then to the ARMED_VACATION
        pair.server.interactive_command("AV")
        time.sleep(1)
        assert pair.server.alarm.state == Alarm.ArmingState.EXIT_DELAY
        # wait for exit delay to finish
        time.sleep(2)
        assert pair.server.alarm.state == Alarm.ArmingState.ARMED
        assert pair.server.alarm.arming_mode == Alarm.ArmingMode.ARMED_VACATION

        # Trip the alarm from the emulated-alarm server console
        # Check that it goes initially to ENTRY_DELAY state
        # Then to the TRIPPED
        pair.server.interactive_command("T")
        time.sleep(1)
        assert pair.server.alarm.state == Alarm.ArmingState.ENTRY_DELAY
        # wait for exit delay to finish
        time.sleep(2)
        assert pair.server.alarm.state == Alarm.ArmingState.TRIPPED

        # Enable zone-activity simulation for the
        # alarm from the emulated-alarm server console
        # Check activity was detected
        self.zone_changes = 0
        pair.server.interactive_command("S")
        time.sleep(5.5)
        assert self.zone_changes > 0

        # Disable zone-activity simulation for the
        # alarm from the emulated-alarm server console
        # Check no activity was detected
        self.zone_changes = 0
        pair.server.interactive_command("S")
        time.sleep(5.5)
        assert self.zone_changes == 0

        # Quit the emulated-alarm server console
        # Causes the emulated-alarm to stop and close
        pair.server.interactive_command("Q")

        # Tear down everything
        time.sleep(0.5)
        pair.stop()
        _LOGGER.info("Exercise Connection Test Complete")

    def test_refused_connection(self) -> None:
        _LOGGER.info("Connection Refused Test")
        pair = ClientServerPair(
            client_port=ClientServerPair.test_port + 1
        )  # ensure connection refused
        pair.run()
        time.sleep(5)
        assert pair.client.connected_count == 0
        pair.stop()
        _LOGGER.info("Connection Refused Test Complete")

    def test_disconnect_connection(self) -> None:
        _LOGGER.info("Disconnection Test")
        pair = ClientServerPair()
        pair.run()
        time.sleep(1)
        pair.server.server.disconnect_all_clients()
        time.sleep(1)

        asyncio.run_coroutine_threadsafe(pair.client._connect(), pair.loop).result()
        assert pair.client.disconnection_count == 1

        pair.stop()
        _LOGGER.info("Disconnection Test Complete")
