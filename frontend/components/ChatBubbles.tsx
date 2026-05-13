'use client';

/**
 * ChatBubbles — presentational helpers for {@link ChatPanel}.
 *
 * Kept in a sibling file so ChatPanel stays focused on wiring (WS client,
 * scroll behavior, composer state). Nothing here touches the Zustand store
 * directly — everything is a pure function of its props.
 */

import { Fragment, useMemo, type ReactNode, type CSSProperties } from 'react';
import type { ChatTurn } from '@/lib/store';
import { Button } from '@/components/ui';
import { Card } from '@/components/ui/Card';
import { Logo } from '@/components/Logo';

// ─────────────────────────────────────────────────────────────────────────────
// Role metadata
// ─────────────────────────────────────────────────────────────────────────────

export type Role = ChatTurn['role'];

const ROLE_LABEL: Record<Role, string> = {
  user: 'You',
  assistant: 'lineforge',
  tool: 'tool',
  system: 'system',
};

/** Left-border accent color per role. We keep bubbles transparent and lean
 *  on this single border + an avatar to communicate role — the old "three
 *  filled navy boxes" look read as visual noise. */
const ROLE_BORDER: Record<Role, string> = {
  user: 'border-l-2 border-success',
  assistant: 'border-l-2 border-accent',
  tool: 'border-l-2 border-info',
  system: 'border-l-2 border-slate-600',
};

// ─────────────────────────────────────────────────────────────────────────────
// Avatars — inline SVGs so we don't pull in an icon library.
// ─────────────────────────────────────────────────────────────────────────────

function UserAvatar() {
  return (
    <span
      className="flex items-center justify-center w-6 h-6 rounded-full bg-success/20 text-success shrink-0"
      aria-hidden="true"
    >
      <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <circle cx={12} cy={8} r={3.5} />
        <path d="M4 20c1.5-3.5 4.5-5 8-5s6.5 1.5 8 5" strokeLinecap="round" />
      </svg>
    </span>
  );
}

export function AssistantAvatar() {
  return (
    <span
      className="flex items-center justify-center w-6 h-6 rounded-full bg-surface-overlay shrink-0"
      aria-hidden="true"
    >
      <Logo size={14} />
    </span>
  );
}

function ToolAvatar() {
  return (
    <span
      className="flex items-center justify-center w-6 h-6 rounded-full bg-info/20 text-info shrink-0"
      aria-hidden="true"
    >
      <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <path
          d="M14.7 6.3a4 4 0 0 1 5 5l-3 3-5-5 3-3z"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path d="m11.7 9.3-8 8a1.5 1.5 0 0 0 0 2.1l.9.9a1.5 1.5 0 0 0 2.1 0l8-8" strokeLinejoin="round" />
      </svg>
    </span>
  );
}

function SystemAvatar() {
  // Square (not circular) to make system / meta rows feel different from chat.
  return (
    <span
      className="flex items-center justify-center w-6 h-6 rounded-xs bg-surface-raised text-slate-400 shrink-0"
      aria-hidden="true"
    >
      <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
        <circle cx={12} cy={12} r={3} />
        <path
          d="M19 12a7 7 0 0 0-.1-1.2l2-1.5-2-3.4-2.3.9a7 7 0 0 0-2-1.2l-.4-2.4h-4l-.4 2.4a7 7 0 0 0-2 1.2l-2.3-.9-2 3.4 2 1.5A7 7 0 0 0 5 12c0 .4 0 .8.1 1.2l-2 1.5 2 3.4 2.3-.9a7 7 0 0 0 2 1.2l.4 2.4h4l.4-2.4a7 7 0 0 0 2-1.2l2.3.9 2-3.4-2-1.5c.1-.4.1-.8.1-1.2z"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}

function RoleAvatar({ role }: { role: Role }) {
  if (role === 'user') return <UserAvatar />;
  if (role === 'assistant') return <AssistantAvatar />;
  if (role === 'tool') return <ToolAvatar />;
  return <SystemAvatar />;
}

// ─────────────────────────────────────────────────────────────────────────────
// Lightweight JSON syntax tinting.
//
// Walks a pretty-printed JSON string with `matchAll` and yields
// {text, className} tokens. We render those as <span> children — all
// React-native nodes, no raw HTML injection.
// ─────────────────────────────────────────────────────────────────────────────

const JSON_TINT_RE =
  /("(?:[^"\\]|\\.)*"\s*:)|("(?:[^"\\]|\\.)*")|\b(true|false|null)\b|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g;

type Token = { text: string; cls?: string };

function tokenizeJson(raw: string): Token[] {
  const out: Token[] = [];
  let lastIndex = 0;
  for (const m of raw.matchAll(JSON_TINT_RE)) {
    const idx = m.index ?? 0;
    if (idx > lastIndex) {
      out.push({ text: raw.slice(lastIndex, idx) });
    }
    const [match, key, str, kw, num] = m;
    if (key) out.push({ text: key, cls: 'text-info' });
    else if (str) out.push({ text: str, cls: 'text-success' });
    else if (kw) out.push({ text: kw, cls: 'text-warn' });
    else if (num) out.push({ text: num, cls: 'text-warn' });
    else out.push({ text: match });
    lastIndex = idx + match.length;
  }
  if (lastIndex < raw.length) {
    out.push({ text: raw.slice(lastIndex) });
  }
  return out;
}

function JsonBlock({ value }: { value: unknown }) {
  const tokens = useMemo(() => {
    let raw: string;
    try {
      raw = JSON.stringify(value, null, 2);
    } catch {
      raw = String(value);
    }
    return tokenizeJson(raw);
  }, [value]);
  return (
    <pre className="text-[11px] font-mono bg-surface-raised border border-border-subtle rounded-xs px-2 py-1.5 overflow-x-auto mt-1.5">
      <code>
        {tokens.map((t, i) =>
          t.cls ? (
            <span key={i} className={t.cls}>
              {t.text}
            </span>
          ) : (
            <Fragment key={i}>{t.text}</Fragment>
          ),
        )}
      </code>
    </pre>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Inline `code` segments in plain content. Splits on backticks and renders
// odd-indexed chunks as <code>. Markdown beyond this is out of scope.
// ─────────────────────────────────────────────────────────────────────────────

function renderInlineContent(content: string): ReactNode[] {
  const parts = content.split('`');
  return parts.map((chunk, i) => {
    if (i % 2 === 1) {
      return (
        <code
          key={i}
          className="font-mono text-[12.5px] bg-surface-overlay px-1 rounded-xs"
        >
          {chunk}
        </code>
      );
    }
    return <span key={i}>{chunk}</span>;
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Tool-name badge — used by tool_call (→ prefix), tool_result (✓ / ✗ prefix).
// ─────────────────────────────────────────────────────────────────────────────

function ToolBadge({
  name,
  status,
}: {
  name: string;
  status?: 'pending' | 'ok' | 'error';
}) {
  const glyph =
    status === 'ok'
      ? '✓ '
      : status === 'error'
        ? '✗ '
        : status === 'pending'
          ? '→ '
          : '';
  return (
    <span className="inline-flex items-center gap-1 text-[11px] font-mono px-1.5 py-0.5 rounded-xs bg-info/15 text-info border border-info/30">
      <span>
        {glyph}
        {name}
      </span>
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// One row in the message log.
// ─────────────────────────────────────────────────────────────────────────────

export function MessageRow({
  turn,
  defaultOpen,
}: {
  turn: ChatTurn;
  defaultOpen: boolean;
}) {
  const isUser = turn.role === 'user';
  // System rows render tighter + dimmer so they read as meta-information.
  const isSystem = turn.role === 'system';
  const isTool = turn.role === 'tool';

  // Tool messages can carry either an input (tool_call) or an output (tool_result).
  const hasToolInput = turn.toolInput !== undefined;
  const hasToolOutput = turn.toolOutput !== undefined;

  return (
    <article
      className={`group flex gap-2 ${isUser ? 'flex-row-reverse' : ''}`}
      aria-label={`${ROLE_LABEL[turn.role]} message`}
    >
      <RoleAvatar role={turn.role} />
      <div
        className={[
          'flex-1 min-w-0 pl-3',
          ROLE_BORDER[turn.role],
          isUser ? 'pr-0' : '',
          isSystem ? 'opacity-75' : '',
        ]
          .filter(Boolean)
          .join(' ')}
      >
        <header className="flex items-center gap-2 text-[11px] text-slate-500">
          <span
            className={
              isUser
                ? 'font-medium text-success'
                : turn.role === 'assistant'
                  ? 'font-medium text-accent'
                  : isTool
                    ? 'font-medium text-info'
                    : 'font-medium text-slate-400'
            }
          >
            {ROLE_LABEL[turn.role]}
          </span>
          {isTool && turn.toolName && (
            <ToolBadge
              name={turn.toolName}
              status={hasToolOutput ? 'ok' : hasToolInput ? 'pending' : undefined}
            />
          )}
          {/* No client-side timestamp: the ChatTurn schema doesn't carry one.
              Per the spec we skip the <time> element rather than fake it. */}
        </header>

        {/* Plain message body. For tool rows we suppress the redundant
            "→ foo" / "✓ foo" text — that information is in the badge above. */}
        {turn.content && !isTool && (
          <div
            className={`text-sm leading-relaxed mt-0.5 whitespace-pre-wrap break-words ${
              isSystem ? 'text-slate-400' : 'text-slate-200'
            }`}
          >
            {renderInlineContent(turn.content)}
          </div>
        )}

        {hasToolInput && (
          <details open={defaultOpen} className="mt-1.5">
            <summary className="text-[11px] text-slate-500 cursor-pointer select-none hover:text-slate-300">
              input
            </summary>
            <JsonBlock value={turn.toolInput} />
          </details>
        )}
        {hasToolOutput && (
          <details open={defaultOpen} className="mt-1.5">
            <summary className="text-[11px] text-slate-500 cursor-pointer select-none hover:text-slate-300">
              output
            </summary>
            <JsonBlock value={turn.toolOutput} />
          </details>
        )}
      </div>
    </article>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Thinking indicator — three bouncing dots + the in-flight tool name.
// ─────────────────────────────────────────────────────────────────────────────

export function ThinkingIndicator({ toolName }: { toolName?: string }) {
  const dot = (delay: number): CSSProperties => ({
    animationDelay: `${delay}ms`,
  });
  return (
    <article className="group flex gap-2" aria-label="lineforge is working">
      <AssistantAvatar />
      <div className="flex-1 min-w-0 pl-3 border-l-2 border-accent">
        <header className="flex items-center gap-2 text-[11px] text-slate-500">
          <span className="font-medium text-accent">{ROLE_LABEL.assistant}</span>
        </header>
        <div className="flex items-center gap-2 mt-1 text-sm text-slate-400">
          <span className="inline-flex items-center gap-1" aria-hidden="true">
            <span
              className="inline-block w-1.5 h-1.5 bg-accent rounded-full animate-bounce"
              style={dot(0)}
            />
            <span
              className="inline-block w-1.5 h-1.5 bg-accent rounded-full animate-bounce"
              style={dot(150)}
            />
            <span
              className="inline-block w-1.5 h-1.5 bg-accent rounded-full animate-bounce"
              style={dot(300)}
            />
          </span>
          <span className="italic text-slate-500">
            {toolName ? (
              <>
                calling{' '}
                <code className="font-mono text-info not-italic">{toolName}</code>
                …
              </>
            ) : (
              'thinking…'
            )}
          </span>
        </div>
      </div>
    </article>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Empty-state card with two example prompts.
// ─────────────────────────────────────────────────────────────────────────────

const EXAMPLE_PROMPTS = [
  'Design a 50 Ω microstrip on 4 mil Megtron 6',
  'Sweep Z₀ vs trace width from 4 to 12 mil',
] as const;

export function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  return (
    <Card tone="raised" className="m-4 p-6 text-center">
      <div className="flex justify-center">
        <AssistantAvatar />
      </div>
      <h2 className="font-display text-base text-slate-200 mt-3">Ask lineforge</h2>
      <p className="text-xs text-slate-500 mt-1">
        Describe a stackup, ask for a sweep, or tell the agent what to build.
      </p>
      <div className="flex flex-col gap-1.5 mt-4">
        {EXAMPLE_PROMPTS.map((p) => (
          <Button
            key={p}
            variant="ghost"
            size="sm"
            className="w-full justify-start text-left"
            onClick={() => onPick(p)}
          >
            <span className="text-slate-400 mr-2 shrink-0" aria-hidden="true">
              ›
            </span>
            <span className="truncate text-slate-300">{p}</span>
          </Button>
        ))}
      </div>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// In-flight tool detection.
//
// The store doesn't expose a streaming flag, but we can derive one cleanly
// from the chat history: an open tool call is a `tool` turn with
// `toolInput !== undefined && toolOutput === undefined` whose matching
// result hasn't arrived yet. We pair calls and results in FIFO order by
// toolName so multiple back-to-back invocations of the same tool still
// resolve correctly.
// ─────────────────────────────────────────────────────────────────────────────

export function findInFlightTool(history: ChatTurn[]): string | null {
  const openByName: Record<string, number> = {};
  let lastOpenedName: string | null = null;
  for (const t of history) {
    if (t.role !== 'tool' || !t.toolName) continue;
    if (t.toolInput !== undefined && t.toolOutput === undefined) {
      openByName[t.toolName] = (openByName[t.toolName] ?? 0) + 1;
      lastOpenedName = t.toolName;
    } else if (t.toolOutput !== undefined) {
      if (openByName[t.toolName]) {
        openByName[t.toolName] -= 1;
        if (openByName[t.toolName] <= 0) delete openByName[t.toolName];
      }
    }
  }
  // Surface the most recently opened still-pending tool — if it's already
  // resolved, fall back to any other open name; otherwise return null.
  if (lastOpenedName && openByName[lastOpenedName]) return lastOpenedName;
  const remaining = Object.keys(openByName);
  return remaining.length > 0 ? remaining[remaining.length - 1] : null;
}
