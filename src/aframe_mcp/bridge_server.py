"""Standalone websocket bridge between the MCP server and an A-Frame scene."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Dict, Optional

import websockets
from websockets.server import WebSocketServerProtocol

logger = logging.getLogger("AFrameBridge")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

DEFAULT_HOST = os.getenv("AFRAME_BRIDGE_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("AFRAME_BRIDGE_PORT", "8765"))
RESPONSE_TIMEOUT = float(os.getenv("AFRAME_BRIDGE_RESPONSE_TIMEOUT", "20"))


@dataclass
class PendingMessage:
    future: asyncio.Future
    client: WebSocketServerProtocol


class BridgeServer:
    """Routes commands between MCP clients and a connected A-Frame scene."""

    def __init__(self) -> None:
        self.scene: Optional[WebSocketServerProtocol] = None
        self.scene_id: Optional[str] = None
        self.pending: Dict[str, PendingMessage] = {}
        self.scene_lock = asyncio.Lock()

    async def handler(self, websocket: WebSocketServerProtocol) -> None:
        """Handle new websocket connections."""
        try:
            raw = await asyncio.wait_for(websocket.recv(), timeout=5)
        except asyncio.TimeoutError:
            await websocket.close(code=4000, reason="Handshake timeout")
            return
        except websockets.ConnectionClosed:
            return

        try:
            handshake = json.loads(raw)
        except json.JSONDecodeError:
            await websocket.close(code=4001, reason="Invalid handshake payload")
            return

        role = handshake.get("role")
        if role == "scene":
            await self._register_scene(websocket, handshake)
        elif role == "mcp":
            await self._register_mcp(websocket)
        else:
            await websocket.close(code=4002, reason="Unknown role")

    async def _register_scene(
        self, websocket: WebSocketServerProtocol, handshake: Dict[str, str]
    ) -> None:
        async with self.scene_lock:
            if self.scene is not None:
                await websocket.send(
                    json.dumps(
                        {
                            "status": "error",
                            "message": "A scene is already connected",
                        }
                    )
                )
                await websocket.close(code=4003, reason="Scene already connected")
                return
            self.scene = websocket
            self.scene_id = handshake.get("sceneId") or "default"

        await websocket.send(json.dumps({"status": "ready", "sceneId": self.scene_id}))
        logger.info("Scene connected: %s", self.scene_id)

        try:
            async for raw in websocket:
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("Invalid message from scene: %s", raw[:200])
                    continue

                request_id = message.get("requestId")
                if not request_id:
                    logger.warning("Scene message missing requestId: %s", message)
                    continue

                pending = self.pending.pop(request_id, None)
                if not pending:
                    logger.warning("No pending request for id %s", request_id)
                    continue

                pending.future.set_result(message)
        except websockets.ConnectionClosed:
            logger.info("Scene connection closed")
        finally:
            async with self.scene_lock:
                self.scene = None
                self.scene_id = None
            self._flush_pending("Scene disconnected")

    async def _register_mcp(self, websocket: WebSocketServerProtocol) -> None:
        await websocket.send(json.dumps({"status": "ok"}))
        logger.info("MCP client connected")
        try:
            async for raw in websocket:
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send(
                        json.dumps(
                            {
                                "status": "error",
                                "message": "Invalid command payload",
                            }
                        )
                    )
                    continue

                request_id = message.get("requestId")
                if not request_id:
                    await websocket.send(
                        json.dumps(
                            {
                                "status": "error",
                                "message": "Commands must include requestId",
                            }
                        )
                    )
                    continue

                if self.scene is None:
                    await websocket.send(
                        json.dumps(
                            {
                                "requestId": request_id,
                                "status": "error",
                                "message": "No A-Frame scene is connected",
                            }
                        )
                    )
                    continue

                future = asyncio.get_running_loop().create_future()
                self.pending[request_id] = PendingMessage(future=future, client=websocket)

                try:
                    await self.scene.send(json.dumps(message))
                except websockets.ConnectionClosed:
                    await websocket.send(
                        json.dumps(
                            {
                                "requestId": request_id,
                                "status": "error",
                                "message": "Scene disconnected",
                            }
                        )
                    )
                    self.pending.pop(request_id, None)
                    continue

                try:
                    response = await asyncio.wait_for(future, timeout=RESPONSE_TIMEOUT)
                except asyncio.TimeoutError:
                    await websocket.send(
                        json.dumps(
                            {
                                "requestId": request_id,
                                "status": "error",
                                "message": "Timed out waiting for scene response",
                            }
                        )
                    )
                    self.pending.pop(request_id, None)
                    continue

                await websocket.send(json.dumps(response))
                self.pending.pop(request_id, None)
        except websockets.ConnectionClosed:
            logger.info("MCP client disconnected")
        finally:
            to_cancel = [key for key, value in self.pending.items() if value.client == websocket]
            for key in to_cancel:
                pending = self.pending.pop(key)
                pending.future.cancel()

    def _flush_pending(self, message: str) -> None:
        for key, pending in list(self.pending.items()):
            if not pending.future.done():
                pending.future.set_result(
                    {
                        "requestId": key,
                        "status": "error",
                        "message": message,
                    }
                )
            self.pending.pop(key, None)

    async def run(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
        logger.info("Starting bridge on ws://%s:%s", host, port)
        async with websockets.serve(self.handler, host, port):
            await asyncio.Future()  # Run forever


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the A-Frame MCP websocket bridge")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Interface to bind (default: %(default)s)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind (default: %(default)s)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = BridgeServer()
    asyncio.run(server.run(args.host, args.port))


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
