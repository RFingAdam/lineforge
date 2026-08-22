"use client";

/** Skeleton placeholder boxes for the ResultsPanel during a solve.
 *
 * Exposes three layers, additive over time:
 *   - {@link ResultSkeleton}: legacy "one big block + 6-cell grid" placeholder,
 *     kept verbatim for backwards compatibility.
 *   - {@link SkeletonRow}: low-level utility. A single shimmering line.
 *   - {@link SkeletonStat} + {@link SkeletonSection}: structured placeholders
 *     that mirror the real result layout (hero Stat + grouped Sections).
 *
 * All variants use the `.skeleton` keyframes from globals.css, which already
 * respects `prefers-reduced-motion`.
 */
export function ResultSkeleton() {
  return (
    <div className="space-y-3">
      <div className="skeleton h-20 rounded" />
      <div className="grid grid-cols-2 gap-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="skeleton h-16 rounded" />
        ))}
      </div>
    </div>
  );
}

/** Generic single-line skeleton row. */
export function SkeletonRow({ className = "" }: { className?: string }) {
  return <div className={`skeleton h-4 rounded ${className}`} />;
}

/** Placeholder that matches the dimensions of a Stat card. */
export function SkeletonStat({ hero = false }: { hero?: boolean }) {
  if (hero) {
    return (
      <div className="surface rounded-sm border-l-4 border-accent/40 px-4 py-4">
        <div className="skeleton h-3 w-16 rounded-xs" />
        <div className="skeleton mt-3 h-9 w-32 rounded-xs" />
      </div>
    );
  }
  return (
    <div className="surface-raised rounded-sm px-3 py-2">
      <div className="skeleton h-2.5 w-12 rounded-xs" />
      <div className="skeleton mt-2 h-5 w-20 rounded-xs" />
    </div>
  );
}

/** Placeholder for a results Section: title row + N-cell 2-column grid. */
export function SkeletonSection({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      <div className="skeleton h-2.5 w-28 rounded-xs" />
      <div className="grid grid-cols-2 gap-2.5">
        {Array.from({ length: rows }).map((_, i) => (
          <SkeletonStat key={i} />
        ))}
      </div>
    </div>
  );
}
