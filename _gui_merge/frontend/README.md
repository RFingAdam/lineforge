# atlc3-gui frontend

Next.js 14 + React + Tailwind. Three-pane layout: chat (left, 33 %),
geometry editor (middle, 25 %), results (right, 42 %).

## Dev

```bash
pnpm install
pnpm dev    # serves http://localhost:3000, proxies /api & /ws to backend on :8000
```

The backend (`../backend/`) must be running for chat + REST to work.

## Build

```bash
pnpm build
pnpm start
```

## State management

Zustand store at `lib/store.ts` mirrors the backend `GuiState`. Both REST
calls (`lib/api.ts`) and chat WebSocket events (`lib/ws-client.ts`) push
into the same store; components subscribe via selectors.

The chat WebSocket auto-reconnects with exponential backoff (cap 10 s) so
backend bounces during dev are resilient.

## Components (C2 baseline)

- `ChatPanel` — chat history + send box. Handles user/assistant/tool/system
  bubbles, auto-scrolls, supports Enter-to-send.
- `GeometryPanel` — type dropdown + common-field inputs (W/H/T/S/B/H1/H2/er),
  Calculate Z₀ button.
- `ResultsPanel` — formatted result card (Z₀ big, then εr_eff/vp/td/L/C/α_d
  in a 2-column grid) + raw JSON in a `<details>` toggle.

C3 will add: live state-delta application from agent tool calls,
StackupEditor for multi-layer dielectric stacks, FieldRenderer canvas for
field-map PNGs, SweepChart for parameter sweeps.
