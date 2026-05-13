'use client';

/**
 * ChatPanel — the agent console.
 *
 * Talks to the backend over /ws/chat via {@link ChatClient}, mirrors every
 * message into the Zustand store, and renders the chat log + composer.
 *
 * The presentational bits (avatars, message rows, code blocks, thinking
 * indicator, empty state) live in {@link ./ChatBubbles}. This file owns:
 *
 *   - WebSocket lifecycle + health check.
 *   - Auto-scroll behavior.
 *   - Composer state: auto-growing textarea, Enter-to-send, Shift+Enter
 *     newline, paper-plane Send button with loading state.
 *   - Deriving the in-flight tool name from chat history so we can render
 *     a "calling foo…" indicator without a dedicated store flag.
 */

import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useGuiStore } from '@/lib/store';
import { ChatClient } from '@/lib/ws-client';
import { Button } from '@/components/ui';
import {
  EmptyState,
  MessageRow,
  ThinkingIndicator,
  findInFlightTool,
} from '@/components/ChatBubbles';

/** Inline paper-plane glyph for the Send button. */
function SendIcon() {
  return (
    <svg
      width={14}
      height={14}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M22 2 11 13" />
      <path d="M22 2 15 22l-4-9-9-4 20-7z" />
    </svg>
  );
}

const MAX_TEXTAREA_ROWS = 6;
const TEXTAREA_BASE_ROWS = 2;
const TEXTAREA_LINE_PX = 20; // approximate, matched to text-sm/leading-relaxed

export function ChatPanel() {
  const chatHistory = useGuiStore((s) => s.chatHistory);
  const [input, setInput] = useState('');
  const [chatAvailable, setChatAvailable] = useState<boolean | null>(null);
  const clientRef = useRef<ChatClient | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${proto}//${window.location.host}/ws/chat`;
    const client = new ChatClient(url);
    clientRef.current = client;
    client.connect();
    fetch('/api/health')
      .then((r) => r.json())
      .then((j) => setChatAvailable(Boolean(j.chat_available)))
      .catch(() => setChatAvailable(null));
    return () => client.close();
  }, []);

  // Auto-scroll to bottom when the log grows.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [chatHistory.length]);

  // Auto-grow the textarea (capped at MAX_TEXTAREA_ROWS lines).
  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    const max = MAX_TEXTAREA_ROWS * TEXTAREA_LINE_PX + 16; // include padding
    el.style.height = `${Math.min(el.scrollHeight, max)}px`;
  }, [input]);

  const inFlightTool = useMemo(() => findInFlightTool(chatHistory), [chatHistory]);
  const isStreaming = inFlightTool !== null;

  // For the "default-open code block" treatment we want only the most recent
  // tool turn expanded; older ones collapse to keep the log scannable.
  const lastToolIdx = useMemo(() => {
    for (let i = chatHistory.length - 1; i >= 0; i -= 1) {
      if (chatHistory[i].role === 'tool') return i;
    }
    return -1;
  }, [chatHistory]);

  function handleSubmit(e?: React.FormEvent) {
    e?.preventDefault();
    const text = input.trim();
    if (!text || isStreaming) return;
    clientRef.current?.send(text);
    setInput('');
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  return (
    <div className="flex h-full flex-col">
      {/* Panel header — kept slim to match the rest of the layout. */}
      <div className="px-4 py-2 border-b border-border-subtle flex items-center justify-between bg-surface/60">
        <span className="text-xs uppercase tracking-wider text-slate-500">Chat</span>
        {chatAvailable === false && (
          <span
            className="text-[10px] text-warn bg-warn/10 border border-warn/40 rounded-xs px-1.5 py-0.5"
            title="Set ANTHROPIC_API_KEY in atlc3-gui/backend/.env, or run `claude /login` once."
          >
            agent disabled — see setup
          </span>
        )}
      </div>

      {/* Message log (or empty state) */}
      {chatHistory.length === 0 ? (
        <div className="flex-1 overflow-y-auto">
          <EmptyState
            onPick={(p) => {
              setInput(p);
              // Focus the textarea so the user can edit before sending.
              setTimeout(() => textareaRef.current?.focus(), 0);
            }}
          />
        </div>
      ) : (
        <div
          ref={scrollRef}
          role="log"
          aria-live="polite"
          aria-relevant="additions"
          className="flex-1 overflow-y-auto px-3 py-3 space-y-3"
        >
          {chatHistory.map((turn, i) => (
            <MessageRow key={i} turn={turn} defaultOpen={i === lastToolIdx} />
          ))}
          {isStreaming && <ThinkingIndicator toolName={inFlightTool ?? undefined} />}
        </div>
      )}

      {/* Composer */}
      <form
        onSubmit={handleSubmit}
        className="border-t border-border-subtle p-3 bg-surface/40"
      >
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={TEXTAREA_BASE_ROWS}
          placeholder="Tell the agent what to build..."
          className="w-full resize-none bg-canvas border border-border-subtle rounded-sm px-2 py-1.5 text-sm text-slate-100 placeholder-slate-600 focus-ring"
          aria-label="Message lineforge"
        />
        <div className="flex items-center justify-between mt-1.5">
          <p className="text-[11px] text-slate-500">
            Enter to send · Shift+Enter for newline
          </p>
          <Button
            variant="primary"
            size="sm"
            type="submit"
            disabled={!input.trim() || isStreaming}
            loading={isStreaming}
            leftIcon={!isStreaming ? <SendIcon /> : undefined}
          >
            Send
          </Button>
        </div>
      </form>
    </div>
  );
}
