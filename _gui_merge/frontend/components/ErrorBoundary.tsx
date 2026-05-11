"use client";

import { Component, type ReactNode } from "react";

type Props = { children: ReactNode; label?: string };
type State = { error: Error | null };

/**
 * React error boundary that wraps each pane. Catches renders that throw
 * (e.g. a buggy result format) so the rest of the GUI keeps working.
 * Shows a recoverable error card with a "Try again" button that clears
 * local state without reloading the page.
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error: Error): State {
    return { error };
  }
  override componentDidCatch(error: Error): void {
    // eslint-disable-next-line no-console
    console.error(`[atlc3-gui] ${this.props.label ?? "panel"} error:`, error);
  }
  override render(): ReactNode {
    if (this.state.error) {
      return (
        <div className="h-full flex items-center justify-center bg-navy-950 p-4">
          <div className="bg-rose-950/40 border border-rose-800 rounded p-4 max-w-md text-sm space-y-2">
            <div className="text-rose-300 font-semibold">
              ❌ Render error in {this.props.label ?? "this panel"}
            </div>
            <div className="text-xs text-rose-200 break-words font-mono">
              {this.state.error.message}
            </div>
            <button
              onClick={() => this.setState({ error: null })}
              className="text-xs bg-rose-700 hover:bg-rose-600 text-white px-3 py-1 rounded"
            >
              Try again
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
