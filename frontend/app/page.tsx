import { ChatPanel } from '@/components/ChatPanel';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { GeometryPanel } from '@/components/GeometryPanel';
import { Logo } from '@/components/Logo';
import { ResultsPanel } from '@/components/ResultsPanel';
import { Tour } from '@/components/Tour';
import { UnitToggle } from '@/components/UnitToggle';

export default function Page() {
  return (
    <div className="h-screen flex flex-col bg-navy-950">
      <header className="bg-header-gradient border-b border-navy-800 px-4 py-2 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Logo size={26} />
          <div className="flex items-baseline gap-2">
            <span className="text-emerald-400 font-bold tracking-wider text-base">
              atlc3
            </span>
            <span className="text-slate-400 text-xs">
              Transmission-Line Design Studio
            </span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Tour />
          <UnitToggle />
        </div>
      </header>
      <main className="flex-1 grid grid-cols-12 overflow-hidden">
        <div className="col-span-4 h-full">
          <ErrorBoundary label="chat panel">
            <ChatPanel />
          </ErrorBoundary>
        </div>
        <div className="col-span-3 h-full">
          <ErrorBoundary label="geometry panel">
            <GeometryPanel />
          </ErrorBoundary>
        </div>
        <div className="col-span-5 h-full">
          <ErrorBoundary label="results panel">
            <ResultsPanel />
          </ErrorBoundary>
        </div>
      </main>
    </div>
  );
}
