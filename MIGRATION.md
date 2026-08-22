# Migrating from atlc3 to lineforge

lineforge is the renamed, recontextualized continuation of atlc3. The
codebase, solvers, results, and behavior are unchanged: just the
project name and entry points moved. v2.0.0 is the first lineforge release.

This guide walks through the three things you need to change in your
project, in roughly the order they'll bite you.

## TL;DR. Three find/replaces

1. `import atlc3` → `import lineforge`
2. `from atlc3` → `from lineforge`
3. `atlc3` (CLI command) → `lineforge`

That's it for >90% of users. The rest of this doc covers the edge cases.

## Detailed changes

### Python package

| Was | Now |
|---|---|
| `pip install atlc3` | `pip install lineforge` |
| `import atlc3` | `import lineforge` |
| `from atlc3.analytical import microstrip` | `from lineforge.analytical import microstrip` |
| `from atlc3.geometry.types import Microstrip` | `from lineforge.geometry.types import Microstrip` |
| `atlc3.__version__` | `lineforge.__version__` |

**Function and class names are unchanged.** `microstrip(...)`, `Microstrip(...)`,
`stripline_asymmetric(...)`, etc. all keep the same signatures and return
the same `TLineResult` shape.

### CLI

| Was | Now |
|---|---|
| `atlc3 solve --type microstrip ...` | `lineforge solve --type microstrip ...` |
| `atlc3 sweep --touchstone-out ...` | `lineforge sweep --touchstone-out ...` |
| `atlc3 target-z0 --target 50 ...` | `lineforge target-z0 --target 50 ...` |
| `atlc3 run-script my.txt` | `lineforge run-script my.txt` |
| `atlc3 mcp-serve` | `lineforge mcp-serve` |
| `atlc3 gui` | `lineforge gui` |

All subcommands, options, and output formats are identical.

### MCP server (Claude Desktop, Cursor, etc.)

In your `claude_desktop_config.json`, change:

```diff
 {
   "mcpServers": {
-    "atlc3": { "command": "atlc3", "args": ["mcp-serve"] }
+    "lineforge": { "command": "lineforge", "args": ["mcp-serve"] }
   }
 }
```

The tool names exposed by the server (e.g. `calculate_impedance`,
`solve_cgp`, `target_z0`, `sweep`, `import_usermap`) are unchanged.

### Rust crate

| Was | Now |
|---|---|
| `atlc3_kernel` | `lineforge_kernel` |
| `crates/atlc3_kernel/` | `crates/lineforge_kernel/` |

If you have downstream Cargo workspaces depending on the kernel:

```diff
 [dependencies]
-atlc3_kernel = { git = "https://github.com/RFingAdam/atlc3", branch = "main" }
+lineforge_kernel = { git = "https://github.com/RFingAdam/lineforge", branch = "main" }
```

### Configuration files

| Was | Now |
|---|---|
| `.atlc3.json` | `.lineforge.json` |
| `examples/04_geometry_json.json` | (still works: same schema) |

The `.atlc3.json` file format is unchanged; just the conventional
extension is `.lineforge.json` now. Either loads correctly via
`lineforge.geometry.from_json()`.

### GitHub repo URL

The repo at `RFingAdam/atlc3` is being renamed to `RFingAdam/lineforge`.
GitHub will auto-redirect the old URL, but you should update any
hardcoded URLs in your scripts, CI config, or documentation.

## What's NOT changing

- All solver behavior (closed-form formulas, bitmap kernel, optimizer)
- atlc2-format BMP usermap drop-in compatibility (`*.bmp` + `MoreColors.txt`)
- atlc2 `.txt` script-file execution (`lineforge run-script ...`)
- The Wadell / IPC-2141A / Hammerstad-Jensen lineage and references
- Test suite. All 364 tests pass identically on v1.1.0 and v2.0.0
- Touchstone .s2p export format
- All v1.1.0 features: multi-layer dielectric stacks, three-conductor
  solver, GUI launcher, frequency-dependent materials, expanded laminate
  library, etc.

## If you have atlc3 1.x in production

You don't have to migrate right away. The `atlc3` PyPI package is **frozen
at 1.1.0** as legacy. It still installs and works. You can:

1. **Pin to atlc3 1.1.0**: `atlc3==1.1.0` in your `requirements.txt` /
   `pyproject.toml`. Keep using `import atlc3`.
2. **Migrate to lineforge 2.0.0**: `pip install lineforge`, do the three
   find/replaces above, get all future updates.

We recommend (2) for new projects and any project that's getting active
development. (1) is for "if it works, don't touch it" stability.

## Worked example

Before (atlc3 1.x):

```python
from atlc3.analytical import microstrip
from atlc3.geometry.types import Microstrip
from atlc3.touchstone import to_touchstone
from atlc3.sweep import sweep

g = Microstrip(W="6mil", T="1.4mil", H="4mil", er=4.4)
r = microstrip(g)
print(f"Z0 = {r.z0:.2f} Ω")

results = sweep(g, freq_ghz=np.linspace(0.1, 20, 401))
to_touchstone(results, "trace.s2p", line_length="1in", z_ref=50)
```

After (lineforge 2.0.0):

```python
from lineforge.analytical import microstrip
from lineforge.geometry.types import Microstrip
from lineforge.touchstone import to_touchstone
from lineforge.sweep import sweep

g = Microstrip(W="6mil", T="1.4mil", H="4mil", er=4.4)
r = microstrip(g)
print(f"Z0 = {r.z0:.2f} Ω")

results = sweep(g, freq_ghz=np.linspace(0.1, 20, 401))
to_touchstone(results, "trace.s2p", line_length="1in", z_ref=50)
```

The only differences are the `atlc3 → lineforge` replacements at the import
line. Everything else: function names, parameter names, return types,
behavior: is identical.

## Mechanical migration script

If you have a project with many files using `atlc3`, this one-liner does
the find/replace safely:

```bash
# preview what would change
grep -rln 'atlc3' your_project/ | xargs sed -n 's/atlc3/lineforge/gp' | head

# do it for real
grep -rln 'atlc3' your_project/ | xargs sed -i 's/\batlc3\b/lineforge/g'
```

The `\b` word-boundary in the second command prevents accidental matches
inside `atlc2` (the historical reference, which we keep): `\batlc3\b`
only matches the standalone token `atlc3`.

## Questions or surprises?

If you hit something that's behaving differently between atlc3 1.1.0 and
lineforge 2.0.0, that's almost certainly a bug: please open an issue at
https://github.com/RFingAdam/lineforge/issues with:

- the geometry you're solving (or a 5-line repro)
- the atlc3 1.1.0 result
- the lineforge 2.0.0 result
- expected behavior

The intent is full behavioral parity. The only intentional differences
are the names; everything else should match bit-for-bit.
