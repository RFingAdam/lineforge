# MCP server end-to-end verification

This is the manual verification procedure that closes AUDIT.md item #6
(MCP server tested only programmatically, not via a real MCP client).

## What's already automated

`tests/test_mcp_server.py` exercises the server programmatically — it builds
the FastMCP instance and calls `server.call_tool(...)` directly. That covers:

- All 14 tools register correctly
- `ping` returns ``{"status": "ok"}``
- `calculate_impedance` returns sensible Z₀ for standard geometries
- `list_geometry_types` enumerates 8 types
- Error paths (unknown geometry, malformed input) return JSON errors
- Resources (`atlc://materials`, etc.) are reachable

## What needs manual verification

The end-to-end client roundtrip:

- stdio transport ↔ Claude Desktop framing
- Tool descriptions visible + actionable in the client UI
- Async Tasks lifecycle (`solve_cgp` → poll `tasks_get` → render field plot)
- Resource URI display + read

## Procedure

### 1. Install lineforge from the repo

```bash
git clone https://github.com/RFingAdam/lineforge.git
cd lineforge
python -m venv .venv
.venv/Scripts/activate    # Windows
# or: source .venv/bin/activate   # macOS / Linux
pip install -e .
```

Verify the CLI is on your PATH:

```bash
lineforge --version
# lineforge 0.1.0
#   native kernel: 0.1.0 (parallel=on)
```

### 2. Configure Claude Desktop

Edit:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Add an `lineforge` entry under `mcpServers`. The `command` should point to the
`lineforge` script in your venv (the venv must be the one where you ran
`pip install -e .`):

```json
{
  "mcpServers": {
    "lineforge": {
      "command": "F:\\Personal\\_Projects\\_live\\lineforge\\.venv\\Scripts\\lineforge.exe",
      "args": ["mcp-serve"]
    }
  }
}
```

(macOS / Linux: replace with the absolute path to your `.venv/bin/lineforge`.)

Restart Claude Desktop.

### 3. Smoke tests

In a new conversation, you should see "lineforge" listed under "Connected
servers" (gear icon → MCP).

Run these three queries verbatim and confirm the response shape:

#### Test 3a — synchronous analytical solve

> Calculate the characteristic impedance of a 6 mil wide microstrip on
> 4 mil FR4 with 1.4 mil copper, εr=4.4. Use the calculate_impedance tool.

Expected: Claude calls `calculate_impedance` with the right geometry dict,
gets back ``Z0 ≈ 51.93Ω`` and ``εeff ≈ 3.31``, and explains the answer.

**Pass criteria:**
- Tool call shows up in the message timeline.
- Response JSON has `z0` between 40 and 60.
- Response includes `_kind: "TLineResult"`.

#### Test 3b — geometry introspection

> What geometries does lineforge support? Show me their required dimensional fields.

Expected: Claude calls `list_geometry_types` and renders the result as a
table or list. Should show all 8: microstrip, embedded_microstrip,
stripline_symmetric, stripline_asymmetric, cpwg, edge_coupled_diff_microstrip,
edge_coupled_diff_stripline, broadside_coupled_diff_stripline.

#### Test 3c — async bitmap solve

This exercises the SEP-1686 Tasks pattern.

> I have a microstrip cross-section bitmap. Use the rasterize tool to
> create a Usermap from a 6mil/4mil/1.4mil/εr=4.4 microstrip, then call
> solve_cgp on the resulting URI. Render the V field plot when done.

Expected sequence:

1. Claude calls `rasterize({"type": "microstrip", ...})`. Response includes
   `uri: atlc://geometries/<uuid>` and `shape: [H, W]`.
2. Claude calls `solve_cgp(usermap_uri="atlc://geometries/...", render_fields=["V"])`.
   Response is `{"taskId": "<uuid>", "status": "submitted"}`.
3. Claude calls `tasks_get(<task_id>)` one or more times. After ~1-3
   seconds, status flips to `completed` and `result` contains a CGPResult
   with `z0`, `eps_eff`, `L_per_m`, `C_per_m`.
4. Claude reads `atlc://results/<task_id>/field/V` to fetch the PNG.

**Pass criteria:**
- All four tool calls happen in sequence.
- `tasks_get` shows status transitioning `submitted → working → completed`.
- Final Z₀ is within 10% of the analytical 51.93Ω.
- The V-field PNG is base64-decodable and ~1-10 KB.

### 4. Common failure modes

**Tools don't show up in Claude Desktop's MCP panel:**

- Check the `command` path resolves to the right `lineforge` script.
- Check the venv has the package installed: `<venv>/Scripts/lineforge --version`
  should work from a terminal.
- Look at Claude Desktop's MCP log for stderr from the server.

**`lineforge mcp-serve` exits immediately:**

- Run from a terminal: `lineforge mcp-serve` should hang waiting for stdio
  input. If it exits, the package import is broken — usually a missing
  native kernel (`maturin develop` not run).

**`solve_cgp` returns `{"error": ...}`:**

- The geometry dict is malformed. Use `describe_geometry("<name>")` to see
  the JSON Schema first.
- Pixel widths must be either floats (in meters) or unit strings like
  ``"0.1mm"``.

## What this validates

After all three tests pass:

- ✅ stdio MCP transport works end-to-end with a real client
- ✅ Tool definitions render correctly in the UI
- ✅ Sync tools (analytical) return parseable JSON
- ✅ Async tools (bitmap solver) follow the SEP-1686 Tasks lifecycle
- ✅ Resource URIs are dereferenceable
- ✅ Field-plot PNGs are base64-encoded in resource bodies

That closes AUDIT.md item #6.

## Future automation

A live-client integration test would require driving an MCP client process
and asserting its tool-call telemetry. This isn't yet wired into CI; the
issue [audit] Document MCP-via-Claude-Desktop verification procedure
tracks the gap.
