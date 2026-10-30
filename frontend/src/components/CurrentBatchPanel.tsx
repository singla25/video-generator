import { useState } from 'react';
import { Link } from 'react-router-dom';

import { useBatchAction, useDeleteDraft, type BatchAction } from '../api/queries';
import type { Batch, BatchStatus } from '../api/types';
import { ApiError } from '../api/client';
import { etaLabel, formatNumber } from '../format';
import { ConfirmDialog } from './ConfirmDialog';
import { ProgressRing } from './ProgressRing';

const BUTTON =
  'rounded-full border px-4 py-1.5 text-sm font-semibold hover:bg-mint disabled:opacity-50';
const MAIN_ACTION = 'block rounded-full bg-lime px-4 py-2.5 text-center font-semibold';

/** Side panel: progress ring, ETA, counts and the batch controls. */
export function CurrentBatchPanel({ batch, status }: { batch: Batch; status: BatchStatus }) {
  const action = useBatchAction(batch.id);
  const remove = useDeleteDraft(batch.id);
  const [asking, setAsking] = useState<'cancel' | 'delete' | null>(null);
  const run = (name: BatchAction) => action.run(name);
  const pending = action.isPending || remove.isPending;
  const { counts } = status;
  const isDraft = batch.status === 'DRAFT';
  const canCancel = batch.status === 'RUNNING' || batch.status === 'PAUSED';
  const error = action.isError ? action.error : remove.isError ? remove.error : null;
  const failure = error instanceof ApiError ? error.message : 'Something went wrong.';

  function confirm() {
    const which = asking;
    setAsking(null);
    if (which === 'cancel') run('cancel');
    if (which === 'delete') remove.run();
  }

  return (
    <section data-testid="current-batch" className="min-w-0 rounded-card border bg-card p-5">
      <h2 className="font-semibold">Current batch</h2>
      <p className="truncate text-sm text-muted">{batch.sheet_name ?? batch.folder_name ?? ''}</p>
      <div className="my-4 flex items-center gap-5">
        <ProgressRing percent={status.progress_percent} />
        <div className="text-sm">
          <p className="font-semibold">{etaLabel(batch.status, status.eta_seconds)}</p>
          <p className="text-muted">
            {formatNumber(counts.completed)} completed /{' '}
            {formatNumber(counts.total - counts.skipped)}
          </p>
          <p className="text-muted">{formatNumber(counts.failed)} failed</p>
          <p className="text-muted">{formatNumber(counts.skipped)} skipped</p>
        </div>
      </div>
      {error && (
        <p role="alert" className="mb-3 text-sm text-status-failed">
          {failure}
        </p>
      )}
      {isDraft ? (
        <div className="mb-3 flex flex-wrap gap-2">
          <button
            type="button"
            className={`${BUTTON} text-status-failed`}
            disabled={pending}
            onClick={() => setAsking('delete')}
          >
            Delete draft
          </button>
        </div>
      ) : (
        <div className="mb-3 flex flex-wrap gap-2">
          {batch.status === 'RUNNING' && (
            <button
              type="button"
              className={BUTTON}
              disabled={pending}
              onClick={() => run('pause')}
            >
              Pause
            </button>
          )}
          {batch.status === 'PAUSED' && (
            <button
              type="button"
              className={BUTTON}
              disabled={pending}
              onClick={() => run('resume')}
            >
              Resume
            </button>
          )}
          <button
            type="button"
            className={BUTTON}
            disabled={pending}
            onClick={() => run('retry-failed')}
          >
            Retry failed
          </button>
          {canCancel && (
            <button
              type="button"
              className={BUTTON}
              disabled={pending}
              onClick={() => setAsking('cancel')}
            >
              Cancel batch
            </button>
          )}
        </div>
      )}
      {isDraft ? (
        <Link to={`/batches/new?batch=${batch.id}`} className={MAIN_ACTION}>
          Start batch
        </Link>
      ) : (
        <Link to={`/batches/${batch.id}`} className={MAIN_ACTION}>
          View batch
        </Link>
      )}
      {asking === 'cancel' && (
        <ConfirmDialog
          title="Cancel this batch?"
          body="Videos that are not finished yet will not be made."
          confirmLabel="Yes, cancel batch"
          cancelLabel="Keep running"
          onConfirm={confirm}
          onCancel={() => setAsking(null)}
        />
      )}
      {asking === 'delete' && (
        <ConfirmDialog
          title="Delete this draft?"
          body="The uploaded rows will be removed. This cannot be undone."
          confirmLabel="Delete"
          cancelLabel="Keep"
          onConfirm={confirm}
          onCancel={() => setAsking(null)}
        />
      )}
    </section>
  );
}
