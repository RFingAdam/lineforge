# Phase C example: chat-driven web GUI walkthrough

The lineforge web GUI ships inside the lineforge repo: a FastAPI backend
(`lineforge.web`, under `src/lineforge/web/`) that wraps the library, and a
Next.js + React + Tailwind frontend under `frontend/`. A chat panel runs on
`claude-agent-sdk` against the user's Claude Max subscription, and the agent
has tools that mutate the GUI's geometry form live as it works.

## Prerequisites

* A lineforge clone installed with the GUI extras (FastAPI, uvicorn,
  claude-agent-sdk). pip builds the Rust core, so you need a Rust toolchain
  on your PATH:

  ```bash
  git clone https://github.com/RFingAdam/lineforge.git
  cd lineforge
  pip install -e ".[gui]"
  ```

* Node.js and pnpm on your PATH (npm works as a fallback). `lineforge gui`
  installs the frontend deps in `frontend/` on first run.

* Claude credentials: either set `ANTHROPIC_API_KEY=…` in your shell, or
  run `claude /login` once to store a Max subscription token locally.

## Launch

From inside the `lineforge` repo:

```bash
lineforge gui
```

The CLI:

1. Verifies the repo's `frontend/` directory exists (`--frontend-dir`
   points it elsewhere).
2. Checks for Node and pnpm, and installs the frontend `node_modules` if
   they are missing.
3. Spawns `uvicorn lineforge.web.app:app --port 8000 --reload` and
   `pnpm dev` on port 3000 (either moves to a free port if busy).
4. Opens `http://localhost:3000` in your default browser.
5. Hands you a chat panel with the lineforge tool surface bound.

## Walkthrough: the L3 SIG1 case from the planning session

Type into the chat:

> Set up the L3 SIG1 inner-layer trace from my 8-layer board: an asymmetric
> stripline with W=3.18 mil, T=0.689 mil, Core 3.5 mil εr=4.2 above and
> Prepreg 5.3 mil εr=3.7 below, then run target_z0=48 by varying W.

Watch the agent:

1. Call `set_geometry_type("stripline_asymmetric")`. The geometry form's
   type dropdown switches.
2. Call `set_geometry_field` for each of W / T / H1 / H2 / er_above / er_below
   one by one. Each input field populates live.
3. Call `target_z0` with the populated template. The right-hand Results
   panel displays Z₀ ≈ 48.000 Ω, εr_eff ≈ 4.001, the converged W ≈ 3.182 mil.

The chat shows every tool call (with input/output expanders) so the math
is fully auditable. State changes flow over `/ws/chat` as `state_delta`
messages; the Zustand store applies them and React re-renders.

## Stopping

`Ctrl-C` in the terminal where `lineforge gui` runs. Both child processes
shut down cleanly.

## Without the chat

The GUI is fully usable without the agent: switch types and edit fields
in the geometry form, hit the **Calculate Z₀** button, and the result
shows up. The chat is the productivity layer; the form is the
deterministic baseline.
