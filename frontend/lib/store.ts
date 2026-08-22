/**
 * Zustand store mirroring the backend GuiState.
 *
 * State is the single source of truth; both REST endpoint responses and
 * /ws/chat state-delta messages converge here. Components subscribe to
 * slices via selectors to minimize re-renders.
 */

import { create } from 'zustand';
import type { LengthUnit } from './units';

export type ChatTurn = {
  role: 'user' | 'assistant' | 'tool' | 'system';
  content: string;
  toolName?: string;
  toolInput?: unknown;
  toolOutput?: unknown;
};

/** One point of a parameter sweep: params dict + result dict. Mirrors
 * the backend's SweepPoint shape in the /api/solve/sweep response. */
export type SweepPoint = {
  params: Record<string, number>;
  result: Record<string, unknown> | null;
};

export type GuiState = {
  geometry: Record<string, unknown> | null;
  sweepConfig: { parameter: string; values: number[]; solver: string } | null;
  sweepResults: SweepPoint[] | null;
  lastResult: Record<string, unknown> | null;
  lastFieldPlotUri: string | null;
  chatHistory: ChatTurn[];
  unit: LengthUnit;
  isSolving: boolean;
  /** User-typed frequency string ('1GHz', '5e9', etc.). Persisted across
   * reloads via localStorage. Empty/null means "no frequency: analytical
   * only" so loss/dispersion fields stay null. */
  frequency: string;
};

export type GuiActions = {
  setGeometry: (geometry: Record<string, unknown> | null) => void;
  setLastResult: (result: Record<string, unknown> | null) => void;
  setSweepConfig: (sweep: GuiState['sweepConfig']) => void;
  setSweepResults: (points: SweepPoint[] | null) => void;
  setUnit: (unit: LengthUnit) => void;
  setIsSolving: (busy: boolean) => void;
  setFrequency: (frequency: string) => void;
  appendChat: (turn: ChatTurn) => void;
  setChatHistory: (history: ChatTurn[]) => void;
  reset: () => void;
  hydrate: (state: Partial<GuiState>) => void;
};

const FREQ_STORAGE_KEY = 'atlc3-gui:frequency';

function _initialFrequency(): string {
  if (typeof window === 'undefined') return '';
  return window.localStorage.getItem(FREQ_STORAGE_KEY) ?? '';
}

const initial: GuiState = {
  geometry: null,
  sweepConfig: null,
  sweepResults: null,
  lastResult: null,
  lastFieldPlotUri: null,
  chatHistory: [],
  unit: 'mil',
  isSolving: false,
  frequency: '',
};

export const useGuiStore = create<GuiState & GuiActions>((set) => ({
  ...initial,
  frequency: _initialFrequency(),
  setGeometry: (geometry) => set({ geometry }),
  setLastResult: (lastResult) => set({ lastResult }),
  setSweepConfig: (sweepConfig) => set({ sweepConfig }),
  setSweepResults: (sweepResults) => set({ sweepResults }),
  setUnit: (unit) => set({ unit }),
  setIsSolving: (isSolving) => set({ isSolving }),
  setFrequency: (frequency) => {
    if (typeof window !== 'undefined') {
      try {
        window.localStorage.setItem(FREQ_STORAGE_KEY, frequency);
      } catch {
        /* storage may be disabled: silently no-op */
      }
    }
    set({ frequency });
  },
  appendChat: (turn) =>
    set((s) => ({ chatHistory: [...s.chatHistory, turn] })),
  setChatHistory: (chatHistory) => set({ chatHistory }),
  reset: () => set({ ...initial, unit: useGuiStore.getState?.().unit ?? 'mil' }),
  hydrate: (state) => set(state),
}));
