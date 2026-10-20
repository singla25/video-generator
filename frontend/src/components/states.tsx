import type { ReactNode } from 'react';

/** Grey pulsing placeholder shown while data loads. */
export function Skeleton({ className = 'h-24' }: { className?: string }) {
  return (
    <div
      data-testid="skeleton"
      aria-hidden="true"
      className={`animate-pulse rounded-tile bg-slate-200 motion-reduce:animate-none ${className}`}
    />
  );
}

/** Human error message with an optional retry button. */
export function ErrorState({ title, onRetry }: { title: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-card border bg-card p-6 text-center">
      <p className="font-semibold text-status-failed">{title}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded-full border px-4 py-1.5 text-sm font-semibold hover:bg-mint"
        >
          Try again
        </button>
      )}
    </div>
  );
}

/** Friendly empty state with an optional call to action. */
export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-card border bg-card p-8 text-center">
      <p className="font-semibold">{title}</p>
      {children && <div className="mt-3">{children}</div>}
    </div>
  );
}
