/**
 * WebSocket client for /ws/chat with auto-reconnect and message dispatch.
 *
 * Wire protocol matches backend/app/ws_chat.py:
 *   Client → Server: {role: "user", content: "..."} or
 *                    {role: "system", type: "reset"}
 *   Server → Client: assistant / tool_call / tool_result / state_delta / error
 *
 * Reconnect policy: exponential backoff, capped at 10s. Reconnects keep the
 * frontend resilient to a backend bounce during dev.
 */

import { useGuiStore } from './store';

type ServerMessage =
  | { role: 'assistant'; content: string; stream: boolean }
  | { role: 'tool_call'; name: string; input: unknown }
  | { role: 'tool_result'; name: string; output: unknown }
  | { role: 'state_delta'; patch: Record<string, unknown> }
  | { role: 'error'; content: string };

export class ChatClient {
  private ws: WebSocket | null = null;
  private url: string;
  private reconnectMs = 500;
  private isClosing = false;

  constructor(url: string) {
    this.url = url;
  }

  connect(): void {
    this.ws = new WebSocket(this.url);
    this.ws.onopen = () => {
      this.reconnectMs = 500;
    };
    this.ws.onmessage = (ev) => {
      let msg: ServerMessage;
      try {
        msg = JSON.parse(ev.data) as ServerMessage;
      } catch {
        return;
      }
      this.handle(msg);
    };
    this.ws.onclose = () => {
      if (this.isClosing) return;
      const delay = Math.min(this.reconnectMs, 10_000);
      this.reconnectMs *= 2;
      setTimeout(() => this.connect(), delay);
    };
  }

  send(content: string): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    const store = useGuiStore.getState();
    store.appendChat({ role: 'user', content });
    this.ws.send(JSON.stringify({ role: 'user', content }));
  }

  reset(): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    this.ws.send(JSON.stringify({ role: 'system', type: 'reset' }));
  }

  close(): void {
    this.isClosing = true;
    this.ws?.close();
  }

  private handle(msg: ServerMessage): void {
    const store = useGuiStore.getState();
    switch (msg.role) {
      case 'assistant':
        store.appendChat({ role: 'assistant', content: msg.content });
        break;
      case 'tool_call':
        store.appendChat({
          role: 'tool',
          content: `→ ${msg.name}`,
          toolName: msg.name,
          toolInput: msg.input,
        });
        break;
      case 'tool_result':
        store.appendChat({
          role: 'tool',
          content: `✓ ${msg.name}`,
          toolName: msg.name,
          toolOutput: msg.output,
        });
        break;
      case 'state_delta':
        // Apply known fields. C3 will broadcast richer deltas (geometry,
        // last_result, etc.): for C2 we just handle reset.
        if (msg.patch.reset) {
          store.reset();
        }
        if (msg.patch.geometry !== undefined) {
          store.setGeometry(msg.patch.geometry as Record<string, unknown>);
        }
        if (msg.patch.last_result !== undefined) {
          store.setLastResult(msg.patch.last_result as Record<string, unknown>);
        }
        break;
      case 'error':
        store.appendChat({ role: 'system', content: `error: ${msg.content}` });
        break;
    }
  }
}
