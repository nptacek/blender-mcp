# A-Frame VR MCP

A-Frame VR MCP connects WebXR scenes built with [A-Frame](https://aframe.io/) to Model Context Protocol (MCP) clients such as
Claude, Cursor, and VS Code. Agents can inspect the scene graph, spawn entities, update components, capture screenshots, and
load remote assets—all through natural-language prompts.

This project is an evolution of the original Blender MCP. The native Blender socket workflow has been replaced with a web-first
architecture composed of a Python MCP server, a websocket bridge, and an in-browser client script.

## Project Layout

| Path | Description |
| --- | --- |
| `src/aframe_mcp/server.py` | FastMCP server that exposes scene-management tools. |
| `src/aframe_mcp/bridge_server.py` | Websocket bridge between the MCP server and browsers. |
| `web/aframe_bridge.js` | Client script injected into A-Frame scenes to execute commands. |
| `examples/sample_scene.html` | Minimal scene demonstrating bridge integration. |
| `docs/aframe_architecture.md` | Architectural overview and command flow diagram. |

## Features
- Scene graph inspection with precise world transforms.
- Creation, mutation, and removal of A-Frame entities.
- Remote asset registration for models, textures, audio, and video.
- Canvas screenshot capture returned as MCP `Image` artifacts.
- Camera focus utility and generic JavaScript execution.

## Prerequisites
- Python 3.10+
- `uv` package manager ([installation guide](https://docs.astral.sh/uv/getting-started/installation/))
- Node/npm or any static server for hosting the A-Frame scene
- A modern WebXR-capable browser

Install runtime dependencies:

```bash
uv pip install -e .
```

## Running the Stack
1. **Start the websocket bridge**
   ```bash
   python -m aframe_mcp.bridge_server --host 0.0.0.0 --port 8765
   ```

2. **Serve an A-Frame scene**
   ```bash
   npx http-server examples
   ```
   Open `http://localhost:8080/sample_scene.html` in a WebXR-compatible browser. The page loads `web/aframe_bridge.js`, which
automatically connects to the bridge.

3. **Launch the MCP server**
   ```bash
   export AFRAME_BRIDGE_URL="ws://localhost:8765"
   uvx aframe-mcp
   ```

4. **Connect from an MCP client**
   Configure your MCP client to invoke `uvx aframe-mcp`. Once connected, agents can call tools like `get_scene_graph`,
`create_entity`, `capture_view`, and more.

## Configuration
Environment variables tune the runtime behaviour:

| Variable | Default | Purpose |
| --- | --- | --- |
| `AFRAME_BRIDGE_URL` | `ws://localhost:8765` | Bridge websocket endpoint used by the MCP server. |
| `AFRAME_CONNECT_TIMEOUT` | `5` | Seconds to wait for bridge connection establishment. |
| `AFRAME_RESPONSE_TIMEOUT` | `15` | Seconds to await a response per command. |
| `AFRAME_BRIDGE_HOST` | `127.0.0.1` | Host interface for the websocket bridge. |
| `AFRAME_BRIDGE_PORT` | `8765` | Port for the websocket bridge. |

## Available MCP Tools
- `get_scene_graph`
- `find_entity`
- `create_entity`
- `update_component`
- `remove_entity`
- `load_remote_asset`
- `list_assets`
- `capture_view`
- `focus_camera`
- `execute_script`
- `ping_bridge`

Detailed behaviour for each tool is documented in [docs/aframe_architecture.md](docs/aframe_architecture.md).

## Development Tips
- Use the included sample scene to test new tools before integrating with a production experience.
- Inspect websocket traffic with the browser devtools or CLI proxies if debugging command flow.
- When extending the bridge script, keep command payloads JSON serialisable for compatibility with MCP transports.

## License
MIT License. See [LICENSE](LICENSE) for details.
