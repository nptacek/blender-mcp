"""A-Frame VR MCP server implementation."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, Optional

from mcp.server.fastmcp import Context, FastMCP, Image, Resource

try:  # Optional dependency for typing
    import websockets
except ImportError as exc:  # pragma: no cover - handled at runtime
    raise RuntimeError(
        "The 'websockets' package is required to run the A-Frame MCP server."
    ) from exc


logger = logging.getLogger("AFrameMCP")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

DEFAULT_BRIDGE_URL = os.getenv("AFRAME_BRIDGE_URL", "ws://localhost:8765")
CONNECT_TIMEOUT = float(os.getenv("AFRAME_CONNECT_TIMEOUT", "5"))
RESPONSE_TIMEOUT = float(os.getenv("AFRAME_RESPONSE_TIMEOUT", "15"))


@dataclass
class AFrameConnection:
    """Simple websocket client used to talk to the bridge server."""

    bridge_url: str = DEFAULT_BRIDGE_URL

    async def _send(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send a payload to the bridge and await the response."""
        request_id = payload.setdefault("requestId", str(uuid.uuid4()))
        async with websockets.connect(
            self.bridge_url,
            open_timeout=CONNECT_TIMEOUT,
            close_timeout=CONNECT_TIMEOUT,
            ping_timeout=None,
        ) as websocket:
            handshake = {"role": "mcp", "client": "aframe-mcp"}
            await websocket.send(json.dumps(handshake))

            try:
                ack_raw = await asyncio.wait_for(
                    websocket.recv(), timeout=RESPONSE_TIMEOUT
                )
                ack = json.loads(ack_raw)
                if ack.get("status") not in {"ok", "ready"}:
                    raise RuntimeError(
                        ack.get("message", "Bridge rejected MCP connection")
                    )
            except asyncio.TimeoutError as exc:
                raise TimeoutError(
                    "Timed out waiting for bridge acknowledgement"
                ) from exc

            await websocket.send(json.dumps(payload))

            try:
                response_raw = await asyncio.wait_for(
                    websocket.recv(), timeout=RESPONSE_TIMEOUT
                )
            except asyncio.TimeoutError as exc:
                raise TimeoutError(
                    f"Timed out waiting for response to {payload.get('type')}"
                ) from exc

            response = json.loads(response_raw)
            if response.get("requestId") != request_id:
                raise RuntimeError(
                    "Received mismatched response from A-Frame bridge"
                )

            if response.get("status") == "error":
                raise RuntimeError(response.get("message", "Unknown bridge error"))
            return response.get("result", {})

    def send_command(self, command_type: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send a command synchronously, hiding asyncio plumbing."""

        async def runner() -> Dict[str, Any]:
            payload = {"type": command_type, "params": params or {}}
            return await self._send(payload)

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(runner())
        finally:
            loop.close()


def get_connection() -> AFrameConnection:
    """Return a lazily created connection singleton."""

    global _connection
    if _connection is None:
        _connection = AFrameConnection()
    return _connection


_connection: Optional[AFrameConnection] = None


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    """Attempt an eager handshake to validate the bridge."""

    conn = get_connection()
    try:
        conn.send_command("ping")
        logger.info("Connected to A-Frame bridge at %s", conn.bridge_url)
    except Exception as exc:  # pragma: no cover - connection optional at startup
        logger.warning("A-Frame bridge not reachable on startup: %s", exc)
        logger.warning("Commands will fail until a scene connects to the bridge")

    yield {}


mcp = FastMCP("AFrameMCP", lifespan=lifespan)


@mcp.resource("asset_strategy")
def asset_strategy() -> Resource:
    """Return guidance for agents manipulating A-Frame scenes."""

    body = """
# A-Frame Asset Creation Strategy

1. Prefer reusing existing entities – inspect the scene graph with `get_scene_graph` before spawning new nodes.
2. Use `load_remote_asset` for glTF, images, and audio hosted on CDNs. The bridge automatically places assets into `<a-assets>`.
3. When remote assets are unavailable, build simple primitives with `create_entity` using basic components like `geometry`, `material`, `light`, or `animation`.
4. Apply incremental updates through `update_component` to avoid overwriting user-authored attributes.
5. Capture screenshots frequently with `capture_view` to validate layout and scale.
6. Prefer declarative component values over free-form `execute_script`. Reserve scripts for complex logic and wrap them in idempotent functions.
    """.strip()
    return Resource(mime_type="text/markdown", text=body)


@mcp.tool()
def get_scene_graph(ctx: Context) -> str:
    """Retrieve the full A-Frame scene graph as structured JSON."""

    conn = get_connection()
    result = conn.send_command("get_scene_graph")
    return json.dumps(result, indent=2)


@mcp.tool()
def find_entity(ctx: Context, selector: str) -> str:
    """Query for an entity using a CSS selector and return its attributes."""

    conn = get_connection()
    result = conn.send_command("find_entity", {"selector": selector})
    return json.dumps(result, indent=2)


@mcp.tool()
def create_entity(
    ctx: Context,
    tag: str,
    parent_selector: str = "a-scene",
    attributes: Optional[Dict[str, Any]] = None,
) -> str:
    """Create a new entity and attach it to the scene."""

    conn = get_connection()
    result = conn.send_command(
        "create_entity",
        {
            "tag": tag,
            "parentSelector": parent_selector,
            "attributes": attributes or {},
        },
    )
    return json.dumps(result, indent=2)


@mcp.tool()
def update_component(
    ctx: Context,
    selector: str,
    component: str,
    data: Dict[str, Any],
) -> str:
    """Update an entity component by merging provided data."""

    conn = get_connection()
    result = conn.send_command(
        "update_component",
        {
            "selector": selector,
            "component": component,
            "data": data,
        },
    )
    return json.dumps(result, indent=2)


@mcp.tool()
def remove_entity(ctx: Context, selector: str) -> str:
    """Remove an entity that matches the selector."""

    conn = get_connection()
    result = conn.send_command("remove_entity", {"selector": selector})
    return json.dumps(result, indent=2)


@mcp.tool()
def load_remote_asset(
    ctx: Context,
    asset_id: str,
    asset_type: str,
    url: str,
    options: Optional[Dict[str, Any]] = None,
) -> str:
    """Register a remote asset inside `<a-assets>` and return the element id."""

    conn = get_connection()
    result = conn.send_command(
        "load_remote_asset",
        {
            "assetId": asset_id,
            "assetType": asset_type,
            "url": url,
            "options": options or {},
        },
    )
    return json.dumps(result, indent=2)


@mcp.tool()
def execute_script(ctx: Context, code: str) -> str:
    """Execute a sandboxed JavaScript snippet inside the scene context."""

    conn = get_connection()
    result = conn.send_command("execute_script", {"code": code})
    return json.dumps(result, indent=2)


@mcp.tool()
def capture_view(ctx: Context, width: int = 1280, height: int = 720) -> Image:
    """Capture a screenshot of the active canvas."""

    conn = get_connection()
    result = conn.send_command(
        "capture_view",
        {
            "width": width,
            "height": height,
        },
    )
    image_b64 = result.get("image")
    if not image_b64:
        raise RuntimeError("Bridge returned no image data")
    return Image(data=base64.b64decode(image_b64), format="png")


@mcp.tool()
def list_assets(ctx: Context) -> str:
    """List assets currently registered in `<a-assets>`."""

    conn = get_connection()
    result = conn.send_command("list_assets")
    return json.dumps(result, indent=2)


@mcp.tool()
def focus_camera(ctx: Context, selector: str) -> str:
    """Move the default camera to focus on the target entity."""

    conn = get_connection()
    result = conn.send_command("focus_camera", {"selector": selector})
    return json.dumps(result, indent=2)


@mcp.tool()
def ping_bridge(ctx: Context) -> str:
    """Perform a liveness probe on the A-Frame bridge."""

    conn = get_connection()
    result = conn.send_command("ping")
    return json.dumps(result, indent=2)


def main() -> None:
    """Entry point for CLI usage."""

    logger.info("Starting A-Frame MCP server")
    mcp.run()


if __name__ == "__main__":  # pragma: no cover - CLI usage
    main()
