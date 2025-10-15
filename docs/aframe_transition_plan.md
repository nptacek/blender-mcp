# A-Frame VR MCP Transition Plan

## 1. Current Blender MCP Analysis

### 1.1 Architectural Components
- **MCP Server (`src/blender_mcp/server.py`)**
  - Implements an MCP-compatible FastMCP server that manages lifecycle events and tool registration for Blender interactions.【F:src/blender_mcp/server.py†L1-L200】
  - Maintains a persistent TCP socket connection to the Blender add-on using the `BlenderConnection` helper, ensuring reliable command/response exchanges with JSON payloads and socket-level error handling.【F:src/blender_mcp/server.py†L25-L165】
  - Stores global state (connection handle, PolyHaven availability flag) so MCP tools can re-use a shared link to Blender during a session.【F:src/blender_mcp/server.py†L201-L253】
- **Blender Add-on (`addon.py`)**
  - Exposes a socket server inside Blender that accepts JSON commands, executes them on the main thread via `bpy.app.timers`, and returns structured responses.【F:addon.py†L1-L126】
  - Provides handlers for scene inspection, asset management (PolyHaven, Sketchfab, Hyper3D), material editing, and arbitrary Python execution to satisfy MCP tool requests.【F:addon.py†L127-L400】

### 1.2 Communication Flow
1. The MCP server starts and attempts to connect to Blender via TCP, logging readiness for MCP clients (Claude, Cursor, etc.).【F:src/blender_mcp/server.py†L167-L208】
2. MCP tools invoke `BlenderConnection.send_command`, which serializes a command type and parameters to JSON, forwards them over the socket, and waits for a complete JSON response (with chunking safeguards).【F:src/blender_mcp/server.py†L112-L165】
3. The Blender add-on receives the JSON payload, dispatches to the appropriate command handler, executes Blender API operations, and responds with success or error metadata.【F:addon.py†L52-L126】
4. The MCP server unwraps the result for the MCP tool, formatting data (e.g., scene info, PolyHaven search results) or converting artifacts (viewport screenshots) back into MCP-native types like `Image`.【F:src/blender_mcp/server.py†L254-L520】

### 1.3 Provided Capabilities
- **Scene Awareness**: Tools expose high-level inspection utilities (`get_scene_info`, `get_object_info`) returning JSON-formatted metadata for AI reasoning.【F:src/blender_mcp/server.py†L254-L297】
- **Visual Feedback**: `get_viewport_screenshot` orchestrates temporary file capture within Blender and returns binary image data for MCP clients.【F:src/blender_mcp/server.py†L299-L345】
- **Code Execution**: `execute_blender_code` enables scripted automation, giving Claude-style agents fine control when higher-level integrations are unavailable.【F:src/blender_mcp/server.py†L347-L365】
- **Asset Integrations**: PolyHaven, Sketchfab, and Hyper3D toolchains support discovery, download, and import workflows, leveraging add-on-side APIs and returning enriched status/messaging for human/AI guidance.【F:src/blender_mcp/server.py†L367-L760】【F:addon.py†L127-L400】
- **Operational Guidance**: The `asset_creation_strategy` prompt offers prioritized decision logic for agents, indicating when to prefer integrations versus manual modeling.【F:src/blender_mcp/server.py†L884-L954】

### 1.4 Key Constraints & Assumptions
- Requires a long-lived TCP socket to a Blender host (`BLENDER_HOST`, `BLENDER_PORT`) with the add-on actively running.【F:src/blender_mcp/server.py†L214-L236】
- Command set assumes Blender’s Python API and asset pipeline (materials, geometry) are available; many tools return Blender-specific concepts (materials, node graphs, bounding boxes).【F:addon.py†L127-L400】
- Binary artifacts (screenshots, downloads) flow through temporary files on the filesystem, leveraging Blender’s ability to write to disk.【F:src/blender_mcp/server.py†L299-L333】

## 2. Transformation Strategy for A-Frame VR MCP

### 2.1 Guiding Principles
- Preserve the MCP server paradigm so Claude-compatible clients can reuse existing configurations.
- Replace Blender-specific commands with WebXR/A-Frame equivalents, focusing on DOM-based scene manipulation, asset management, and state inspection via JavaScript bridges.
- Favor REST/WebSocket communication for browser contexts, acknowledging that A-Frame scenes typically run in web runtimes rather than native desktop apps.

### 2.2 Step-by-Step Plan
1. **Define A-Frame Control Surface**
   - Inventory target A-Frame capabilities (entity creation, component updates, asset loading, camera control) and map them to MCP tool analogs identified in §1.3.
   - Decide whether the A-Frame experience runs locally (e.g., dev server) or remotely, and document authentication/URL discovery requirements.
2. **Establish Browser Communication Channel**
   - Implement a lightweight web bridge (e.g., Node.js or Python WebSocket server) that can forward MCP commands to the browser via WebSocket or browser automation (Playwright/WebSocket API).
   - Define a message schema mirroring the Blender JSON format but tailored to A-Frame entity/component updates.
3. **Develop A-Frame Client Script**
   - Create an A-Frame/JavaScript module injected into the scene that subscribes to the command channel, executes DOM manipulations (entity creation, material updates), and emits structured responses.
   - Include screenshot support using WebGL canvas capture (e.g., `canvas.toDataURL`) to replicate the `Image` return type expected by MCP clients.
4. **Port MCP Tools**
   - Re-implement tooling functions in `src/blender_mcp/server.py` (or a new module) to issue A-Frame-specific commands: scene graph queries, entity attribute mutations, asset loading (GLTF, textures), and environment adjustments.
   - Replace Blender-centric data formatting with JSON representations of A-Frame entities/components, ensuring responses remain concise and agent-friendly.
5. **Rework Integration Workflows**
   - Adapt asset download logic to fit web consumption—e.g., preloading GLTF files via URLs, leveraging CDN-hosted resources instead of local filesystem writes.
   - Provide fallbacks for code execution by enabling remote JavaScript snippets executed within the A-Frame scene context, gated for safety.
6. **Update Prompting & Documentation**
   - Rewrite `asset_creation_strategy` (or an equivalent) to describe best practices for constructing A-Frame VR experiences, including entity hierarchies, lighting, physics, and performance considerations.
   - Produce installation/setup instructions covering how to start the MCP server, launch the A-Frame environment, and connect clients.
7. **Testing & Validation**
   - Create automated end-to-end tests that spin up the MCP server, launch an A-Frame demo scene, and verify command execution (entity creation, screenshot capture, asset loading).
   - Perform manual validation in VR-compatible browsers to confirm latency, synchronization, and rendering fidelity.
8. **Deployment & Packaging**
   - Package the new MCP server as a distributable CLI (mirroring current `uvx blender-mcp` workflow) with configuration options for the A-Frame endpoint.
   - Document upgrade paths for existing Blender MCP users who may want to run both integrations side-by-side.

### 2.3 Potential Enhancements
- Explore bi-directional state diffing so A-Frame emits scene changes back to the MCP server for agent awareness.
- Integrate analytics/logging to monitor command latency and scene complexity in VR contexts.
- Consider optional bridge modules for other WebXR frameworks to encourage reuse of the MCP communication layer.

## 3. Deliverables
- Technical architecture document describing the A-Frame bridge.
- Updated MCP server module with A-Frame tool implementations.
- Companion A-Frame client script and sample scene demonstrating end-to-end workflows.
- Revised documentation (README, setup guides) for VR usage.
