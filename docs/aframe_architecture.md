# A-Frame VR MCP Architecture

## Overview
The A-Frame VR MCP integrates WebXR scenes with Model Context Protocol clients. It replaces the Blender socket workflow with a
web-native bridge that forwards commands to an active A-Frame scene running in the browser. The design follows three layers:

1. **MCP Server (`aframe_mcp.server`)** – Exposes MCP tools and resources. Tools translate requests into JSON commands for
the bridge.
2. **Websocket Bridge (`aframe_mcp.bridge_server`)** – Maintains long-lived websocket connections with both the MCP server
and the browser. The bridge multiplexes requests, routes responses, and handles timeouts.
3. **Scene Bridge Script (`web/aframe_bridge.js`)** – Injected into an A-Frame experience. It listens for bridge messages,
performs DOM/component updates, and returns structured data such as screenshots or entity metadata.

This layout keeps the MCP-facing API similar to the Blender version while swapping the execution environment to WebXR.

## Command Flow
1. An MCP tool invokes `AFrameConnection.send_command` (e.g., `create_entity`).
2. The MCP server connects to the websocket bridge, sends a JSON payload `{ type, params, requestId }`, and waits for a reply.
3. The bridge forwards the payload to the connected browser session. If no session is available, the command fails fast.
4. The injected client script executes the command in the scene context and replies with `{ requestId, status, result }`.
5. The MCP tool returns formatted data or binary artifacts (screenshots) back to the MCP client.

## Message Schema
All bridge communication uses JSON objects with the following base fields:

```json
{
  "requestId": "uuid-string",
  "type": "command-name",
  "params": { "...": "..." }
}
```

Responses contain `status` (`ok` or `error`) plus a `result` object or `message` string. Screenshots are returned as base64
PNG strings and converted to `mcp.server.fastmcp.Image` objects within the MCP server.

## Available Tools
The current tool set focuses on scene inspection, entity management, and asset orchestration:

| Tool | Description |
| --- | --- |
| `get_scene_graph` | Traverse the DOM tree and report entity/component metadata. |
| `find_entity` | Query for a selector and return serialized entity data. |
| `create_entity` | Append a new entity with component attributes under a parent node. |
| `update_component` | Merge component values on an existing entity. |
| `remove_entity` | Remove a matched entity from the scene. |
| `load_remote_asset` | Register assets in `<a-assets>` for later reuse. |
| `list_assets` | Enumerate registered assets and their source URLs. |
| `capture_view` | Capture the current WebGL canvas as a PNG screenshot. |
| `focus_camera` | Reposition the active camera to look at a target entity. |
| `execute_script` | Run ad-hoc JavaScript snippets in the scene context (use sparingly). |
| `ping_bridge` | Health-check the websocket bridge. |

## Deployment Steps
1. Start the websocket bridge:
   ```bash
   python -m aframe_mcp.bridge_server --host 0.0.0.0 --port 8765
   ```
2. Serve an A-Frame experience that includes `web/aframe_bridge.js`.
3. Launch the MCP server (`uvx aframe-mcp`), ensuring the `AFRAME_BRIDGE_URL` environment variable points at the bridge.
4. Connect with Claude, Cursor, or another MCP-compatible client.

## Future Enhancements
- Support multiple simultaneous scenes with per-session identifiers.
- Push scene deltas from the browser to the MCP server for real-time awareness.
- Extend asset loaders to integrate with popular WebXR content repositories and CDN caching strategies.
