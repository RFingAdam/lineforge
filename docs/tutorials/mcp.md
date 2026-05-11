# MCP server

lineforge ships a first-class MCP server. Any client (Claude Desktop, Claude
Code, Cursor, custom integrations) can drive the analytical solvers via tool
calls and read the material database as a resource.

## Run

```bash
lineforge mcp-serve            # stdio transport (only one in Phase 0/1)
```

Phase 2 will add HTTP/SSE transport for remote use.

## Connect from Claude Desktop

Edit `claude_desktop_config.json`:

- macOS: `~/Library/Application Support/Claude/`
- Windows: `%APPDATA%\Claude\`

```json
{
  "mcpServers": {
    "lineforge": {
      "command": "lineforge",
      "args": ["mcp-serve"]
    }
  }
}
```

## Tools (Phase 1)

| Tool | Purpose |
|---|---|
| `ping` | Health check; returns version + phase. |
| `list_geometry_types` | All 8 supported geometry types with required fields. |
| `describe_geometry(name)` | JSON Schema for a single geometry type. |
| `export_geometry_schema` | Discriminated-union schema covering all geometries. |
| `calculate_impedance(geometry, frequency?)` | Closed-form solve. |

### `calculate_impedance`

Input shape:

```json
{
  "geometry": {
    "type": "microstrip",
    "W": "6mil", "H": "4mil", "T": "1.4mil", "er": 4.4
  },
  "frequency": "1GHz"
}
```

Returns:

```json
{
  "z0": 50.34,
  "eps_eff": 3.04,
  "vp": 1.72e8,
  "td_per_inch": 1.47e-10,
  "L_per_m": 2.92e-7,
  "C_per_m": 1.15e-10,
  "method": "hammerstad-jensen-microstrip",
  "frequency_hz": 1e9,
  "_kind": "TLineResult"
}
```

For differential pairs, `_kind == "DiffResult"` and the returned dict has
`z_odd`, `z_even`, `z_diff`, `z_common`.

## Resources (Phase 1)

| URI | Contents |
|---|---|
| `atlc://materials` | atlc2-compatible material database (45 colors). |
| `atlc://materials/{name}` | Single material by case-insensitive name match. |

## Phase 2 preview

Phase 2 adds the bitmap (`Usermap`) workflow with the C/Gp Laplace solver.
Long solves use the
[MCP Tasks pattern (SEP-1686)](https://modelcontextprotocol.io/seps/1686-tasks.md):
`solve_cgp` returns a `taskId`; the client polls `tasks/get` until completion;
field plots become resources at `atlc://results/{id}/field/{V|E|D}`.
