import logging
import socket
import threading
import select
from typing import List, Callable, Any, Optional

from ...event import BaseEvent
from ...packet import Packet, CommandType

_LOGGER = logging.getLogger(__name__)


class Server:
    _stopflag: bool
    _server_accept_thread: threading.Thread
    _handle_command: Callable[[str], None]
    _handle_event_lock: threading.Lock
    _listen_Socket: socket.socket
    _clients_lock: threading.Lock
    _clients: List[socket.socket]

    def __init__(self, handle_command: Callable[[str], None]):
        self._handle_command = handle_command
        self._handle_event_lock = threading.Lock()
        self._clients_lock = threading.Lock()
        self._clients = []

    def start(self, host: str, port: int) -> None:
        self._stopflag = False
        self._server_accept_thread = threading.Thread(
            target=self._loop, args=(host, port), name="Server accept loop"
        )
        self._server_accept_thread.start()

    def stop(self) -> None:
        _LOGGER.debug("Stopping Server")
        self._stopflag = True
        self._server_accept_thread.join()

    def disconnect_all_clients(self) -> None:
        _LOGGER.debug("Server disconnecting all clients")
        for conn in self._clients:
            _LOGGER.debug(f"Disconnecting client {conn}")
            if conn.fileno() != -1:
                try:
                    conn.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass  # not connected is fine
                conn.close()

    def _loop(self, host: str, port: int) -> None:
        _LOGGER.debug("Server accept loop running")
        self._listen_Socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listen_Socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listen_Socket.bind((host, port))
        self._listen_Socket.listen(5)
        self._listen_Socket.settimeout(0.5)
        threadlist = []

        _LOGGER.info("Server listening on {}:{}".format(host, port))
        while not self._stopflag:
            try:
                conn, addr = self._listen_Socket.accept()
            except TimeoutError:
                continue
            _LOGGER.info(f"connection {conn} at {addr}")
            newthread = threading.Thread(
                target=self._on_client_connected,
                args=(conn, addr),
                name=f"Server thread for client@{addr}",
            )
            threadlist.append(newthread)
            newthread.start()
        _LOGGER.info("Server accept loop ending - closing sockets")
        self._listen_Socket.close()
        self.disconnect_all_clients()
        for t in threadlist:
            _LOGGER.info(f"Server accept loop - waiting for {t} to end")
            t.join()
        _LOGGER.info("Server accept loop ended")

    def write_event(self, event: BaseEvent) -> None:
        _LOGGER.debug(f"Server writing event {event}")
        pkt = event.encode()
        self._write_to_all_clients(pkt.encode().encode("ascii"))

    def _on_client_connected(self, conn: socket.socket, addr: Any) -> None:
        _LOGGER.info(f"Client thread started for: {addr} : {conn}")
        with self._clients_lock:
            self._clients.append(conn)

        conn.setblocking(False)

        while not self._stopflag:
            data: Optional[bytes] = b""
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
                    _LOGGER.info(f"Exception during recv: {e}")
                    data = None

            if data is None:  # or len(data) == 0:
                _LOGGER.info(f"client {addr} disconnected {conn}")
                with self._clients_lock:
                    _LOGGER.info(f"removing connection {conn}")
                    self._clients.remove(conn)
                    try:
                        conn.shutdown(socket.SHUT_RDWR)
                        conn.close()
                    except OSError:
                        pass

                break

            _LOGGER.info(f"server data-received callback for {conn} : {data!r}")
            self._handle_incoming_data(data)

        _LOGGER.info(f"Client thread ending for: {addr} : {conn}")

    def _write_to_all_clients(self, data: bytes) -> None:
        _LOGGER.debug(f"Server writing message {data!r} to all clients")
        with self._clients_lock:
            for conn in self._clients:
                try:
                    conn.send(data)
                except OSError:
                    pass  # occurs if connection was closed

    def _handle_incoming_data(self, data: bytes) -> None:
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
                raise NotImplementedError()
        except ValueError:
            pass  # Invalid packet received
