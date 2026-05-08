# Phase C example — chat-driven web GUI walkthrough

The atlc3 web GUI lives in a sibling repo, `atlc3-gui`. It bundles a
FastAPI backend that wraps the atlc3 library with a Next.js + React +
Tailwind frontend. A chat panel runs on `claude-agent-sdk` against the
user's Claude Max subscription, and the agent has tools that mutate the
GUI's geometry form live as it works.

## Prerequisites

* `atlc3-gui` cloned next to `atlc3`:

  ```bash
  cd ..
  git clone https://github.com/RFingAdam/atlc3-gui
  ```

* Backend venv with FastAPI + uvicorn + claude-agent-sdk:

  ```bash
  cd atlc3-gui/backend
  python3 -m venv .venv
  .venv/bin/pip install -e ../../atlc3 fastapi 'uvicorn[standard]' \
    websockets claude-agent-sdk pytest pytest-asyncio httpx
  ```

* Frontend deps:

  ```bash
  cd ../frontend
  pnpm install     # or npm install
  ```

* Claude credentials: either set `ANTHROPIC_API_KEY=…` in your shell, or
  run `claude /login` once to store a Max subscription token locally.

## Launch

From inside the `atlc3` repo:

```bash
atlc3 gui
```

The CLI:

1. Verifies the sibling `../atlc3-gui/` directory exists.
2. Verifies the backend venv and frontend `node_modules` exist (prints setup
   commands if not).
3. Spawns `uvicorn app.main:app --port 8000` and `pnpm dev --port 3000`.
4. Opens `http://localhost:3000` in your default browser.
5. Hands you a chat panel with the atlc3 tool surface bound.

## Walkthrough — the L3 SIG1 case from the planning session

Type into the chat:

> Set up the L3 SIG1 inner-layer trace from my 8-layer board: an asymmetric
> stripline with W=3.18 mil, T=0.689 mil, Core 3.5 mil εr=4.2 above and
> Prepreg 5.3 mil εr=3.7 below, then run target_z0=48 by varying W.

Watch the agent:

1. Call `set_geometry_type("stripline_asymmetric")` — the geometry form's
   type dropdown switches.
2. Call `set_geometry_field` for each of W / T / H1 / H2 / er_above / er_below
   one by one — each input field populates live.
3. Call `target_z0` with the populated template — the right-hand Results
   panel displays Z₀ ≈ 48.000 Ω, εr_eff ≈ 4.001, the converged W ≈ 3.182 mil.

The chat shows every tool call (with input/output expanders) so the math
is fully auditable. State changes flow over `/ws/chat` as `state_delta`
messages; the Zustand store applies them and React re-renders.

## Stopping

`Ctrl-C` in the terminal where `atlc3 gui` runs — both child processes
shut down cleanly.

## Without the chat

The GUI is fully usable without the agent — switch types and edit fields
in the geometry form, hit the **Calculate Z₀** button, and the result
shows up. The chat is the productivity layer; the form is the
deterministic baseline.
