# CLI

The `atlc3` command provides every Phase-1 capability without writing Python.

## Discover

```bash
atlc3 --help
atlc3 list-geometries
atlc3 describe-geometry microstrip
atlc3 export-schema | jq .          # full discriminated-union JSON Schema
atlc3 info                          # version, native kernel, parallel status
```

## Solve

Per-field flags:

```bash
atlc3 solve --type microstrip --W 6mil --H 4mil --T 1.4mil --er 4.4
```

JSON file input:

```bash
atlc3 solve --json examples/04_geometry_json.json --frequency 1GHz
```

Machine-readable output for piping to `jq`, CSV tools, etc.:

```bash
atlc3 solve --type microstrip --W 6mil --H 4mil --T 1.4mil --er 4.4 \
    --output json | jq '.z0'
```

## All Phase-1 geometries

```bash
# Microstrip (default 50Ω, 4 mil FR4):
atlc3 solve --type microstrip --W 6mil --H 4mil --T 1.4mil --er 4.4

# Embedded (coated) microstrip with er=4.4 substrate, er=3.5 coating:
atlc3 solve --type embedded_microstrip \
    --W 6mil --H 4mil --H2 4mil --T 1.4mil --er 4.4 --er2 3.5

# Symmetric stripline:
atlc3 solve --type stripline_symmetric --W 5mil --T 1.4mil --B 14mil --er 4.4

# Asymmetric stripline:
atlc3 solve --type stripline_asymmetric \
    --W 5mil --T 1.4mil --H1 4mil --H2 8mil --er 4.4

# CPWG:
atlc3 solve --type cpwg --W 5mil --S 8mil --H 4mil --T 1.4mil --er 4.4

# Edge-coupled diff microstrip:
atlc3 solve --type edge_coupled_diff_microstrip \
    --W 4mil --S 6mil --H 4mil --T 1.4mil --er 4.4

# Edge-coupled diff stripline:
atlc3 solve --type edge_coupled_diff_stripline \
    --W 4mil --S 6mil --B 14mil --T 1.4mil --er 4.4

# Broadside-coupled diff stripline:
atlc3 solve --type broadside_coupled_diff_stripline \
    --W 5mil --H1 4mil --H-between 4mil --T 0.7mil --er 4.4
```

## MCP server

```bash
atlc3 mcp-serve              # stdio transport (only one supported in Phase 0/1)
```

See the [MCP tutorial](mcp.md).
