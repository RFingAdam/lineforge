# atlc3-gui

A web GUI for [`atlc3`](https://github.com/RFingAdam/atlc3), the open-source
MCP-enabled transmission-line calculator. Built on FastAPI + Next.js.

## Layout

This repo is a *sibling* to atlc3 itself. The Python library + CLI + MCP server
stay in atlc3 and ship as `pip install atlc3`. atlc3-gui is the optional
graphical front-end:

```
atlc3-gui/
├── backend/        ← FastAPI app + WebSockets (this commit, C1)
│   └── app/
│       ├── main.py        — FastAPI app, CORS, route registration
│       ├── state.py       — Single-user in-memory GUI state
│       ├── ws_chat.py     — /ws/chat endpoint (Claude agent stream)
│       ├── ws_progress.py — /ws/progress endpoint (long-solve progress)
│       ├── api_geometries.py — REST: list/describe geometries
│       ├── api_solve.py   — REST: calculate / sweep / target_z0
│       └── tools.py       — Agent tool registrations (placeholder)
└── frontend/       ← Next.js 14 + React + Tailwind (next, C2)
```

## Phases

* **C1 (this commit)** — FastAPI scaffolding. REST endpoints for the
  existing atlc3 library + two WebSocket placeholders. Tests verify all
  endpoints respond. No agent logic yet; chat returns a stub.
* **C2** — Next.js frontend shell with three-pane layout (chat | geometry
  editor | results / field renderer / sweep chart).
* **C3** — `claude-agent-sdk` wired into the chat WebSocket; the agent
  gets tools that drive the GUI state.

## Running

The fastest path is `atlc3 gui` from the parent atlc3 repo (it boots
both the backend and frontend with sensible defaults). Manual setup:

### Backend

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -e ../../atlc3 fastapi 'uvicorn[standard]' \
  websockets python-dotenv claude-agent-sdk scikit-rf pytest pytest-asyncio httpx
cp .env.example .env  # then fill in ANTHROPIC_API_KEY if you want chat
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
pnpm install
pnpm dev --port 3000
```

Then `curl http://localhost:8000/api/geometries` to see the available
TL cross-sections, or `wscat -c ws://localhost:8000/ws/chat` to hit the
chat WebSocket.

## Setting up the chat agent

The `/ws/chat` endpoint drives Claude through `claude-agent-sdk`. Three
ways to provide credentials, in order of preference:

1. **API key** — get one at <https://console.anthropic.com/>, then put
   `ANTHROPIC_API_KEY=sk-ant-...` in `backend/.env` (the backend loads
   .env on startup).

2. **Claude Max / Pro subscription** — run `claude /login` once on this
   host and the SDK picks up the stored token automatically. No env var
   needed.

3. **Stub mode** — set `ATLC3_GUI_CHAT_STUB=1` in `.env` to skip the
   real agent and use the echo handler. Used by CI / tests.

When neither (1) nor (2) is configured, the chat panel header shows a
small amber "agent disabled — see setup" badge linking back to this
section, and POSTs are answered by the stub.

The `/api/health` endpoint exposes a `chat_available: bool` flag for
external monitoring.

## License

MIT. Same as atlc3.
