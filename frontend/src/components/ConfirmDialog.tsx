import { useId } from 'react';

interface Props {
  title: string;
  body?: string;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  /** True while the confirmed action runs: the confirm button is disabled. */
  pending?: boolean;
  /** A failure message shown inside the dialog; the dialog stays open. */
  error?: string | null;
}

/** Modal question for actions that cannot be undone. Escape or the cancel button closes it. */
export function ConfirmDialog({
  title,
  body,
  confirmLabel,
  cancelLabel,
  onConfirm,
  onCancel,
  pending = false,
  error = null,
}: Props) {
  const titleId = useId();
  return (
    <div className="fixed inset-0 z-20 grid place-items-center bg-black/30 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={(e) => e.key === 'Escape' && onCancel()}
        className="w-full max-w-sm space-y-4 rounded-card bg-card p-6"
      >
        <h2 id={titleId} className="text-lg font-bold">
          {title}
        </h2>
        {body && <p className="text-sm text-muted">{body}</p>}
        {error && (
          <p role="alert" className="text-sm font-semibold text-status-failed">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-3">
          <button
            type="button"
            autoFocus
            onClick={onCancel}
            className="rounded-full border px-5 py-2 font-semibold hover:bg-mint"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            disabled={pending}
            onClick={onConfirm}
            className="rounded-full bg-status-failed px-5 py-2 font-semibold text-white disabled:opacity-50"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
