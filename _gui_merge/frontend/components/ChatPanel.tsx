'use client';

import { useEffect, useRef, useState } from 'react';
import { useGuiStore } from '@/lib/store';
import { ChatClient } from '@/lib/ws-client';

export function ChatPanel() {
  const chatHistory = useGuiStore((s) => s.chatHistory);
  const [input, setInput] = useState('');
  const [chatAvailable, setChatAvailable] = useState<boolean | null>(null);
  const clientRef = useRef<ChatClient | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${proto}//${window.location.host}/ws/chat`;
    const client = new ChatClient(url);
    clientRef.current = client;
    client.connect();
    // Check whether the backend has Anthropic credentials.
    fetch('/api/health')
      .then((r) => r.json())
      .then((j) => setChatAvailable(Boolean(j.chat_available)))
      .catch(() => setChatAvailable(null));
    return () => client.close();
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [chatHistory]);

  function send() {
    const text = input.trim();
    if (!text) return;
    clientRef.current?.send(text);
    setInput('');
  }

  return (
    <div className="flex h-full flex-col bg-navy-950 border-r border-navy-800">
      <div className="px-4 py-2 border-b border-navy-800 flex items-center justify-between">
        <span className="text-xs uppercase tracking-wider text-slate-500">Chat</span>
        {chatAvailable === false && (
          <span
            className="text-[10px] text-amber-300 bg-amber-950/50 border border-amber-800 rounded px-1.5 py-0.5"
            title="Set ANTHROPIC_API_KEY in atlc3-gui/backend/.env, or run `claude /login` once."
          >
            agent disabled — see setup
          </span>
        )}
      </div>
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-3">
        {chatHistory.length === 0 && (
          <div className="text-slate-500 text-sm">
            Ask the agent to set up your stackup and run the solver. e.g.
            <span className="block mt-2 italic text-slate-400">
              &quot;set up an asymmetric stripline at L3 with W=3.18 mil, T=0.689 mil,
              Core 3.5 mil εr=4.2 above, Prepreg 5.3 mil εr=3.7 below, then target 48
              Ω.&quot;
            </span>
          </div>
        )}
        {chatHistory.map((turn, i) => (
          <ChatBubble key={i} turn={turn} />
        ))}
      </div>
      <div className="p-3 border-t border-navy-800 flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          placeholder="Tell the agent what to build..."
          className="flex-1 bg-navy-900 border border-navy-700 rounded px-3 py-2 text-sm text-slate-100 placeholder-slate-500"
        />
        <button
          onClick={send}
          className="bg-emerald-600 hover:bg-emerald-500 text-white text-sm px-4 rounded"
        >
          Send
        </button>
      </div>
    </div>
  );
}

function ChatBubble({ turn }: { turn: ReturnType<typeof useGuiStore.getState>['chatHistory'][0] }) {
  const colorMap = {
    user: 'bg-blue-900/30 border-blue-700',
    assistant: 'bg-emerald-900/30 border-emerald-700',
    tool: 'bg-amber-900/30 border-amber-700',
    system: 'bg-rose-900/30 border-rose-700',
  } as const;
  const cls = colorMap[turn.role];
  return (
    <div className={`border rounded px-3 py-2 text-sm ${cls}`}>
      <div className="text-xs uppercase text-slate-400 mb-1">{turn.role}</div>
      <div className="whitespace-pre-wrap">{turn.content}</div>
      {turn.toolInput !== undefined && (
        <pre className="mt-2 text-xs bg-navy-950/40 p-2 rounded overflow-x-auto">
          {JSON.stringify(turn.toolInput, null, 2)}
        </pre>
      )}
      {turn.toolOutput !== undefined && (
        <pre className="mt-2 text-xs bg-navy-950/40 p-2 rounded overflow-x-auto">
          {JSON.stringify(turn.toolOutput, null, 2)}
        </pre>
      )}
    </div>
  );
}
