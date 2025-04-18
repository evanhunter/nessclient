"""Provides a TCP server based transport for the test alarm emulator."""

import logging
import select
import socket
import threading
from collections.abc import Callable
from typing import Any

from nessclient.event import BaseEvent
from nessclient.packet import CommandType, Packet

_LOGGER = logging.getLogger(__name__)


class Server:
    """Represents a TCP server based transport for the test alarm emulator."""

    _stopflag: bool
    _server_accept_thread: threading.Thread
    _handle_command: Callable[[str], None]
    _handle_event_lock: threading.Lock
    _listen_socket: socket.socket
    _clients_lock: threading.Lock
    _clients: list[socket.socket]

    def __init__(self, handle_command: Callable[[str], None]) -> None:
        """Create a server."""
        self._handle_command = handle_command
        self._handle_event_lock = threading.Lock()
        self._clients_lock = threading.Lock()
        self._clients = []

    def start(self, host: str, port: int) -> None:
        """Start the server loop listening on the specified host+port."""
        self._stopflag = False
        self._server_accept_thread = threading.Thread(
            target=self._loop, args=(host, port), name="Server accept loop"
        )
        self._server_accept_thread.start()

    def stop(self) -> None:
        """Stop the server listen loop, and disconnect all clients."""
        _LOGGER.debug("Stopping Server")
        self._stopflag = True
        self._server_accept_thread.join()

    def disconnect_all_clients(self) -> None:
        """Shutdown all client socket connectons."""
        _LOGGER.debug("Server disconnecting all clients")
        for conn in self._clients:
            _LOGGER.debug("Disconnecting client %s", conn)
            if conn.fileno() != -1:
                try:
                    conn.shutdown(socket.SHUT_RDWR)
                except OSError:
                    _LOGGER.debug("Shutdown while already disconnected - ignore")
                conn.close()

    def _loop(self, host: str, port: int) -> None:
        """
        Server accept loop.

        In a look: waits for a socket connection, then starts a thread to service it.
        """
        _LOGGER.debug("Server accept loop running")
        self._listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listen_socket.bind((host, port))
        self._listen_socket.listen(5)
        self._listen_socket.settimeout(0.5)
        threadlist = []

        _LOGGER.info("Server listening on %s:%s", host, port)
        while not self._stopflag:
            try:
                conn, addr = self._listen_socket.accept()
            except TimeoutError:
                continue
            _LOGGER.info("connection %s at %s", conn, addr)
            newthread = threading.Thread(
                target=self._on_client_connected,
                args=(conn, addr),
                name=f"Server thread for client@{addr}",
            )
            threadlist.append(newthread)
            newthread.start()
        _LOGGER.info("Server accept loop ending - closing sockets")
        self._listen_socket.close()
        self.disconnect_all_clients()
        for t in threadlist:
            _LOGGER.info("Server accept loop - waiting for %s to end", t)
            t.join()
        _LOGGER.info("Server accept loop ended")

    def write_event(self, event: BaseEvent) -> None:
        """Write an outgoing packet to all clients."""
        _LOGGER.debug("Server writing event %s", event)
        pkt = event.encode()
        self.write_to_all_clients(pkt.encode().encode("ascii"))

    def _on_client_connected(self, conn: socket.socket, addr: Any) -> None:
        """
        Service a client connection.

        In a loop:
        * Wait for packet data and read it from the socket
        * Call _handle_incoming_data() to process it
        """
        _LOGGER.info("Client thread started for: %s : %s", addr, conn)
        with self._clients_lock:
            self._clients.append(conn)

        conn.setblocking(False)  # noqa: FBT003 # bool arg dictatd by socket api

        while not self._stopflag:
            data: bytes | None = b""
            while (
                (not self._stopflag)
                and (conn.fileno() != -1)
                and (data is not None)
                and (b"\n" not in data)
            ):
                try:
                    read_sockets, _, x_sockets = select.select([conn], [], [conn], 0.1)
                    if len(read_sockets) > 0:
                        data_read = conn.recv(1)
                        if data_read is None:
                            _LOGGER.info("server exit")
                            break
                        data += data_read
                except (ConnectionResetError, OSError) as e:
                    _LOGGER.info("Exception during recv: %s", e)
                    data = None

            if data is None:  # or len(data) == 0:
                _LOGGER.info("client %s disconnected %s", addr, conn)
                with self._clients_lock:
                    _LOGGER.info("removing connection %s", conn)
                    self._clients.remove(conn)
                    try:
                        conn.shutdown(socket.SHUT_RDWR)
                        conn.close()
                    except OSError:
                        pass

                break

            _LOGGER.info("server data-received callback for %s : %s", conn, data)
            self._handle_incoming_data(data)

        _LOGGER.info("Client thread ending for: %s : %s", addr, conn)

    def write_to_all_clients(self, data: bytes) -> None:
        """Send data to all connected clients."""
        _LOGGER.debug("Server writing message %s to all clients", data)
        with self._clients_lock:
            for conn in self._clients:
                try:
                    conn.send(data)
                except OSError:
                    _LOGGER.exception(
                        "Connection closed - failed to send data %s", data
                    )

    def _handle_incoming_data(self, data: bytes) -> None:
        """Decode and handle packet data from a client."""
        try:
            _LOGGER.debug("Server received incoming data: %s", data)
            pkt = Packet.decode(data.decode("ascii"))
            _LOGGER.debug("Server packet is: %s", pkt)
            # Handle Incoming Command:
            if (
                pkt.command == CommandType.USER_INTERFACE
                and not pkt.is_user_interface_resp
            ):
                _LOGGER.info("Handling User interface incoming: %s", pkt.data)
                with self._handle_event_lock:
                    self._handle_command(pkt.data)
            else:
                msg = f"Packet received was not a request packet : {pkt}"
                raise NotImplementedError(msg)
        except ValueError:
            _LOGGER.warning("Invalid packet received: %s", data)
