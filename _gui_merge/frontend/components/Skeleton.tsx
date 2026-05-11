"use client";

/** Skeleton placeholder boxes for the ResultsPanel during a solve. */
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
