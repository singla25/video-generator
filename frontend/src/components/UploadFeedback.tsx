import { ErrorState } from './states';

/** Progress bar for a file being sent (0-100). */
export function UploadProgress({ percent, label }: { percent: number; label: string }) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <span>{label}</span>
        <span>{`${percent}%`}</span>
      </div>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        className="h-2 overflow-hidden rounded-full bg-mint"
      >
        <div className="h-full bg-emerald transition-[width]" style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}

interface Props {
  pending: boolean;
  percent: number;
  error: string | null;
  label: string;
  onRetry: () => void;
}

/** What an upload shows: a progress bar while sending, or the failure with a Retry button. */
export function UploadFeedback({ pending, percent, error, label, onRetry }: Props) {
  if (pending) return <UploadProgress percent={percent} label={label} />;
  if (error) return <ErrorState title={error} onRetry={onRetry} retryLabel="Retry" />;
  return null;
}
