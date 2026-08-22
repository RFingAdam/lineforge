# Quick Start

Three-minute path from `pip install` to your first impedance answer.

## Install

```bash
pip install lineforge
```

You'll need a Rust toolchain ([rustup.rs](https://rustup.rs/)) only if installing
from source. The wheels on PyPI are pre-built.

## Pick your surface

=== "Python"

    ```python
    import lineforge

    r = lineforge.microstrip(W="6mil", H="4mil", T="1.4mil", er=4.4)
    print(f"Z0 = {r.z0:.2f} Ω, εeff = {r.eps_eff:.3f}")
    ```

=== "CLI"

    ```bash
    lineforge solve --type microstrip --W 6mil --H 4mil --T 1.4mil --er 4.4
    ```

=== "MCP (Claude Desktop)"

    Add to your `claude_desktop_config.json`:

    ```json
    {
      "mcpServers": {
        "lineforge": { "command": "lineforge", "args": ["mcp-serve"] }
      }
    }
    ```

    Then in Claude:

    > What's the impedance of a 6 mil microstrip on 4 mil FR4?

## Length suffixes

Anywhere lineforge expects a length, you can pass:

- a raw number in **meters** (`1.5e-4`)
- a string with a unit suffix: `"6mil"`, `"4mm"`, `"0.05in"`, `"0.1m"`
- an **AWG** wire spec: `"30AWG"`, `"30 AWG"`

## Frequency suffixes

Anywhere lineforge expects a frequency, you can pass a number in Hz or a string
like `"1GHz"`, `"100MHz"`, `"2.4GHz"`.

## What's next?

- [Geometry reference](reference/geometries.md). Every supported geometry and
  its dimensional fields.
- [Python tutorial](tutorials/python.md): full API walkthrough.
- [Analytical theory](theory/analytical.md): what's actually being computed.
