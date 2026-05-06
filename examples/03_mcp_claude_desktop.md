# Phase 1 example — MCP server in Claude Desktop

This example connects atlc3.0 to Claude Desktop (or any MCP-aware client) via
the stdio transport and demonstrates the analytical-solver tools.

## 1. Install atlc3

```bash
pip install atlc3
```

Verify the CLI is on your PATH:

```bash
atlc3 --version
```

## 2. Configure Claude Desktop

Edit your `claude_desktop_config.json`:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Add atlc3 to `mcpServers`:

```json
{
  "mcpServers": {
    "atlc3": {
      "command": "atlc3",
      "args": ["mcp-serve"]
    }
  }
}
```

Restart Claude Desktop.

## 3. Try it

In a new Claude conversation, you should now see the atlc3 tools available.
Try prompts like:

> What's the characteristic impedance of a 6 mil wide microstrip on 4 mil FR4
> with 1.4 mil copper?

Claude will call `calculate_impedance` with the right geometry and report
something like:

```
Z0 ≈ 50 Ω, εeff ≈ 3.0, propagation delay ≈ 145 ps/inch.
```

Other prompts to try:

> Find a 100 Ω differential pair geometry on 4 mil FR4. I'm using 1 oz copper.

> What materials are in your database that have εr near 4.4?
> *(Claude will read `atlc://materials` and search.)*

> List every supported geometry type and tell me which ones I'd use for a
> coplanar waveguide design.
> *(Claude will call `list_geometry_types`.)*

## 4. Tools exposed in Phase 1

| Tool | Purpose |
|---|---|
| `ping` | Health check |
| `list_geometry_types` | Enumerate the 8 standard PCB geometries |
| `describe_geometry` | JSON Schema for a single geometry type |
| `export_geometry_schema` | Discriminated-union schema across all geometries |
| `calculate_impedance` | Closed-form analytical solve |

## 5. Resources exposed in Phase 1

| Resource | Contents |
|---|---|
| `atlc://materials` | atlc2-compatible material database (45 standard colors) |
| `atlc://materials/{name}` | Single material lookup by name (substring) |

## 6. Phase 2+ preview

Phase 2 will add bitmap (`Usermap`) workflows and the C/Gp Laplace solver.
At that point the long-running `solve_cgp` tool will use MCP's
[Tasks pattern (SEP-1686)](https://modelcontextprotocol.io/seps/1686-tasks.md):
the tool returns immediately with a `taskId`, and Claude polls `tasks/get`
until the solve completes.
