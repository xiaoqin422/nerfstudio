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

import math
from typing import Callable, Type, Any, Dict, List

import numpy as np
import viser.infra
from typing_extensions import override
from viser.infra import ClientConnection

from .message_api import MessageApi
from .messages import GuiUpdateMessage, NerfstudioMessage, PositionMessage


class ViserServer(MessageApi):
    """Core visualization server. Communicates asynchronously with client applications
    via websocket connections.

    By default, all messages (eg `server.add_frame()`) are broadcasted to all connected
    clients.

    To send messages to an individual client, we can grab a client ID -> handle mapping
    via `server.get_clients()`, and then call `client.add_frame()` on the handle.
    """

    _client_connect: Dict[int, ClientConnection] = {}

    def __init__(
            self,
            host: str = "localhost",
            port: int = 8080,
    ):
        super().__init__()
        self._ws_server = viser.infra.Server(host, port, http_server_root=None, verbose=True)
        self._ws_server.register_handler(GuiUpdateMessage, self._handle_gui_updates)
        self._ws_server.on_client_connect(self.client_connection_handler)
        self._ws_server.on_client_disconnect(self.client_disconnection_handler)
        self._ws_server.start()

    @override
    def _queue(self, message: NerfstudioMessage) -> None:
        """Implements message enqueue required by MessageApi.

        Pushes a message onto a broadcast queue."""
        self._ws_server.broadcast(message)

    def get_clients(self) -> List[ClientConnection]:
        return list(self._client_connect.values())

    def send_client_msg(self, client_id: int, message: NerfstudioMessage) -> None:
        if client_id in self._client_connect:
            client = self._client_connect.get(client_id)
            client.send(message)

    def register_handler(
            self, message_type: Type[NerfstudioMessage], handler: Callable[[NerfstudioMessage], None]
    ) -> None:
        """Register a handler for incoming messages.

        Args:
            handler: A function that takes a message, and does something
        """
        self._ws_server.register_handler(message_type, lambda client_id, msg: handler(msg))

    def _handle_pose_transfer(
            self,
            client_id: int,
            message: PositionMessage,
    ) -> None:
        assert isinstance(message, PositionMessage)
        print("_handle_pose_transfer 调用", {message.__str__()})
        self.send_client_msg(client_id, matrix_to_pose(message.matrix))

    def client_connection_handler(
            self, client: ClientConnection
    ) -> None:
        """Register a handler for client connection.

                Args:
                    handler: A function that takes a message, and does something
                """
        self._client_connect[client.client_id] = client
        print("client_connection_handler 调用", {client.__str__()})
        client.register_handler(PositionMessage, self._handle_pose_transfer)

    def client_disconnection_handler(
            self, client: ClientConnection
    ) -> None:
        self._client_connect.pop(client.client_id)


def is_rotation_matrix(R):
    rt = np.transpose(R)
    n = np.linalg.norm(np.identity(3, dtype=R.dtype) - np.dot(rt, R))
    return n < 1e-6


def eulerangles_to_rotation_matrix(theta):
    r_x = np.array([[1, 0, 0],
                    [0, math.cos(theta[0]), -math.sin(theta[0])],
                    [0, math.sin(theta[0]), math.cos(theta[0])]
                    ])

    r_y = np.array([[math.cos(theta[1]), 0, math.sin(theta[1])],
                    [0, 1, 0],
                    [-math.sin(theta[1]), 0, math.cos(theta[1])]
                    ])

    r_z = np.array([[math.cos(theta[2]), -math.sin(theta[2]), 0],
                    [math.sin(theta[2]), math.cos(theta[2]), 0],
                    [0, 0, 1]
                    ])

    return np.dot(r_z, np.dot(r_y, r_x))


def rotation_matrix_to_eulerangles(R):
    assert (is_rotation_matrix(R))
    sy = math.sqrt(R[0, 0] * R[0, 0] + R[1, 0] * R[1, 0])
    singular = sy < 1e-6

    if not singular:
        x = math.atan2(R[2, 1], R[2, 2])
        y = math.atan2(-R[2, 0], sy)
        z = math.atan2(R[1, 0], R[0, 0])
    else:
        x = math.atan2(-R[1, 2], R[1, 1])
        y = math.atan2(-R[2, 0], sy)
        z = 0

    return np.array([x, y, z])


def matrix_to_pose(matrix) -> PositionMessage:
    if len(matrix) != 16:
        raise ValueError("Input array must have a length of 16")
    print(matrix)
    rot_r = np.array(matrix)
    rot_r = rot_r.reshape(4, 4)
    rotation_matrix = np.array([[rot_r[0, 0], rot_r[0, 1], rot_r[0, 2]],
                                [rot_r[1, 0], rot_r[1, 1], rot_r[1, 2]],
                                [rot_r[2, 0], rot_r[2, 1], rot_r[2, 2]]
                                ])

    # 输出欧拉角
    euler = rotation_matrix_to_eulerangles(rotation_matrix)

    pose = {
        "translation": {
            "x": rot_r[0, 3],
            "y": rot_r[1, 3],
            "z": rot_r[2, 3]
        },
        "rotation": {
            "x": euler[0],
            "y": euler[1],
            "z": euler[2],
        }
    }
    pose_info = PositionMessage(matrix=matrix, pose=pose)
    return pose_info
