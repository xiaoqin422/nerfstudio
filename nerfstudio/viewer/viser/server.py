# Copyright 2022 The Nerfstudio Team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

""" Core Viser Server """
# pylint: disable=protected-access
# pylint: disable=too-many-statements


from __future__ import annotations

import asyncio
import dataclasses
import http
import mimetypes
import threading
from pathlib import Path
from typing import Callable, Type, Dict, List, Literal, Optional, Tuple

import redis
import rich
import viser.infra
import websockets.datastructures
import websockets.exceptions
import websockets.server
from rich import box, style
from rich.panel import Panel
from rich.table import Table
from typing_extensions import override
from viser.infra import (
    Message,
    ClientId,
    ClientConnection
)
from viser.infra._async_message_buffer import AsyncMessageBuffer
from viser.infra._infra import (
    error_print_wrapper,
    _client_producer,
    _broadcast_producer,
    _consumer,
    _ClientHandleState
)
from websockets.legacy.server import WebSocketServerProtocol

from .message_api import MessageApi
from nerfstudio.viewer.viser.messages import (
    NerfstudioMessage,
    GuiUpdateMessage,
)


class WebSocketServer(viser.infra.Server):
    _server_state: websockets.server

    def __init__(
            self,
            host: str,
            port: int,
            message_class: Type[NerfstudioMessage] = NerfstudioMessage,
            http_server_root: Optional[Path] = None,
            verbose: bool = True,
            client_api_version: Literal[0, 1] = 0,
    ):
        super().__init__(host, port, message_class, http_server_root, verbose, client_api_version)

    def close_websocket_server(self):
        if self._server_state.is_serving():
            self._server_state.close()

    def get_conn_port(self) -> int:
        return self._port

    def _background_worker(self, ready_sem: threading.Semaphore) -> None:
        host = self._host
        port = self._port
        message_class = self._message_class
        http_server_root = self._http_server_root

        # Need to make a new event loop for notebook compatbility.
        event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(event_loop)
        self._event_loop = event_loop
        self._broadcast_buffer = AsyncMessageBuffer(event_loop)
        ready_sem.release()

        count_lock = asyncio.Lock()
        connection_count = 0
        total_connections = 0

        async def serve(websocket: WebSocketServerProtocol) -> None:
            """Server loop, run once per connection."""

            async with count_lock:
                nonlocal connection_count
                client_id = ClientId(connection_count)
                connection_count += 1

                nonlocal total_connections
                total_connections += 1

            if self._verbose:
                rich.print(
                    f"[bold](viser)[/bold] Connection opened ({client_id},"
                    f" {total_connections} total),"
                    f" {len(self._broadcast_buffer.message_from_id)} persistent"
                    " messages"
                )

            client_state = _ClientHandleState(
                message_buffer=asyncio.Queue(),
                event_loop=event_loop,
            )
            client_connection = ClientConnection(client_id, client_state)

            def handle_incoming(message: Message) -> None:
                self._thread_executor.submit(
                    error_print_wrapper(
                        lambda: self._handle_incoming_message(client_id, message)
                    )
                )
                self._thread_executor.submit(
                    error_print_wrapper(
                        lambda: client_connection._handle_incoming_message(
                            client_id, message
                        )
                    )
                )

            # New connection callbacks.
            for cb in self._client_connect_cb:
                cb(client_connection)

            try:
                # For each client: infinite loop over producers (which send messages)
                # and consumers (which receive messages).
                await asyncio.gather(
                    _client_producer(
                        websocket,
                        client_id,
                        client_state.message_buffer.get,
                        self._client_api_version,
                    ),
                    _broadcast_producer(
                        websocket,
                        self._broadcast_buffer.window_generator(client_id).__anext__,
                        self._client_api_version,
                    ),
                    _consumer(websocket, handle_incoming, message_class),
                )
            except (
                    websockets.exceptions.ConnectionClosedOK,
                    websockets.exceptions.ConnectionClosedError,
            ):
                # Disconnection callbacks.
                for cb in self._client_disconnect_cb:
                    cb(client_connection)

                # Cleanup.
                total_connections -= 1
                if self._verbose:
                    rich.print(
                        f"[bold](viser)[/bold] Connection closed ({client_id},"
                        f" {total_connections} total)"
                    )

        # Host client on the same port as the websocket.
        async def viser_http_server(
                path: str, request_headers: websockets.datastructures.Headers
        ) -> Optional[
            Tuple[http.HTTPStatus, websockets.datastructures.HeadersLike, bytes]
        ]:
            # Ignore websocket packets.
            if request_headers.get("Upgrade") == "websocket":
                return None

            # Strip out search params, get relative path.
            path = path.partition("?")[0]
            relpath = str(Path(path).relative_to("/"))
            if relpath == ".":
                relpath = "index.html"
            assert http_server_root is not None
            source = http_server_root / relpath

            # Try to read + send over file.
            try:
                return (
                    http.HTTPStatus.OK,
                    {
                        "content-type": str(
                            mimetypes.MimeTypes().guess_type(relpath)[0]
                        ),
                    },
                    source.read_bytes(),
                )
            except FileNotFoundError:
                return http.HTTPStatus.NOT_FOUND, {}, b"404"  # type: ignore

        for _ in range(500):
            try:
                self._server_state = event_loop.run_until_complete(
                    websockets.server.serve(
                        serve,
                        host,
                        self._port,
                        process_request=(
                            viser_http_server if http_server_root is not None else None
                        ),
                    )
                )
                break
            except OSError:  # Port not available.
                self._port += 1
                continue

        if self._verbose:
            http_url = f"http://{host}:{self._port}"
            ws_url = f"ws://{host}:{self._port}"

            table = Table(
                title=None,
                show_header=False,
                box=box.MINIMAL,
                title_style=style.Style(bold=True),
            )
            if http_server_root is not None:
                table.add_row("HTTP", f"[link={http_url}]{http_url}[/link]")
            table.add_row("Websocket", f"[link={ws_url}]{ws_url}[/link]")

            rich.print(Panel(table, title="[bold]viser[/bold]", expand=False))

        event_loop.run_forever()


class ClientHandler(MessageApi):
    id: int
    _server: viser.infra.Server
    _state: viser.infra.ClientConnection

    def __init__(
            self,
            client_id: int,
            websocket_server: viser.infra.Server,
            conn: viser.infra.ClientConnection
    ):
        super().__init__()

        self.id = client_id
        self._server = websocket_server
        self._state = conn

    @override
    def _queue(self, message: NerfstudioMessage) -> None:
        """Implements message enqueue required by MessageApi.

        Pushes a message onto a broadcast queue."""
        # print(f"===服务器发送客户端消息{type(message)}===")
        self._state.send(message)

    def send_server_msg(self, message: NerfstudioMessage) -> None:
        self._server.broadcast(message)

    def send_client_msg(self, message: NerfstudioMessage) -> None:
        self._queue(message)

    def register_server_handler(self, message_type: Type[NerfstudioMessage],
                                handler: Callable[[NerfstudioMessage], None]) -> None:
        self._server.register_handler(message_type, lambda client_id, msg: handler(msg))

    def register_client_handler(self, message_type: Type[NerfstudioMessage],
                                handler: Callable[[int, NerfstudioMessage], None]) -> None:
        self._state.register_handler(message_type, lambda client_id, msg: handler(client_id, msg))

    def get_client_conn(self) -> ClientConnection:
        return self._state

    def get_server(self) -> viser.infra.Server:
        return self._server


class ViserServer(MessageApi):
    """Core visualization server. Communicates asynchronously with client applications
    via websocket connections.

    By default, all messages (eg `server.add_frame()`) are broadcasted to all connected
    clients.

    To send messages to an individual client, we can grab a client ID -> handle mapping
    via `server.get_clients()`, and then call `client.add_frame()` on the handle.
    """
    _client_connects: Dict[int, ClientHandler] = dataclasses.field(default_factory=dict)
    client_lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)
    timeout = threading.Event()

    def __init__(
            self,
            host: str = "localhost",
            port: int = 8080
    ):
        super().__init__()
        self._client_connect_cb: List[Callable[[ClientHandler], None]] = []
        self._client_disconnect_cb: List[Callable[[ClientHandler], None]] = []
        self.client_lock = threading.Lock()
        self._client_connects = {}
        # self._ws_server = viser.infra.Server(host, port, http_server_root=None, verbose=True)
        self._ws_server = WebSocketServer(host, port, http_server_root=None, verbose=True)
        self._ws_server.register_handler(GuiUpdateMessage, self._handle_gui_updates)

        self._ws_server.on_client_connect(self._client_connection)
        self._ws_server.on_client_disconnect(self._client_disconnection)
        self._ws_server.start()
        self.timeout.set()

    def close_server(self):
        self._ws_server.close_websocket_server()

    def get_server_port(self) -> int:
        return self._ws_server.get_conn_port()


    @override
    def _queue(self, message: NerfstudioMessage) -> None:
        """Implements message enqueue required by MessageApi.

        Pushes a message onto a broadcast queue."""
        self._ws_server.broadcast(message)

    def get_clients(self) -> Dict[int, ClientHandler]:
        """Creates and returns a copy of the mapping from connected client IDs to
        handles."""
        with self.client_lock:
            clients = self._client_connects.copy()
        return clients

    def register_handler(
            self, message_type: Type[NerfstudioMessage], handler: Callable[[NerfstudioMessage], None]
    ) -> None:
        """Register a handler for incoming messages.

        Args:
            handler: A function that takes a message, and does something
        """
        self._ws_server.register_handler(message_type, lambda client_id, msg: handler(msg))

    def register_client_connect_handler(
            self, cb: Callable[[ClientHandler], None]
    ) -> Callable[[ClientHandler], None]:
        """Attach a callback to run for newly connected clients."""
        with self.client_lock:
            clients = self._client_connects.copy().values()
            self._client_connect_cb.append(cb)

        # Trigger callback on any already-connected clients.
        # If we have:
        #
        #     server = viser.ViserServer()
        #     server.on_client_connect(...)
        #
        # This makes sure that the the callback is applied to any clients that
        # connect between the two lines.
        for client in clients:
            cb(client)
        return cb

    def register_client_disconnect_handler(
            self, cb: Callable[[ClientHandler], None]
    ) -> Callable[[ClientHandler], None]:
        """Attach a callback to run when clients disconnect."""
        self._client_disconnect_cb.append(cb)
        return cb

    def _client_disconnection(
            self, conn: viser.infra.ClientConnection
    ) -> None:
        print(f"===客户端{conn.client_id}断开连接===")
        with self.client_lock:
            # if self._server_id is not None:
            #     redis_client.decrby(f"{flask_conf.redis.nerf_viewer_key}:{self._server_id}")
            if conn.client_id not in self._client_connects:
                return
            handle = self._client_connects.pop(conn.client_id)
            for cb in self._client_disconnect_cb:
                cb(handle)
            if len(self._client_connects) == 0:
                self.timeout.set()

    def _client_connection(
            self, conn: viser.infra.ClientConnection,
    ) -> None:
        """Attach a callback to run for newly connected clients."""
        print(f"===客户端连接事件触发==={conn.__str__()}")
        if self.timeout.is_set():
            self.timeout.clear()
        with self.client_lock:
            # if self._server_id is not None:
            #     redis_client.incrby(f"{flask_conf.redis.nerf_viewer_key}:{self._server_id}")
            client = ClientHandler(conn.client_id, self._ws_server, conn)
            self._client_connects[conn.client_id] = client
            for cb in self._client_connect_cb:
                cb(client)
