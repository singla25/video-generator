import { Link } from 'react-router-dom';

import { useBatchAction, type BatchAction } from '../api/queries';
import type { Batch, BatchStatus } from '../api/types';
import { ApiError } from '../api/client';
import { etaLabel, formatNumber } from '../format';
import { ProgressRing } from './ProgressRing';

const BUTTON =
  'rounded-full border px-4 py-1.5 text-sm font-semibold hover:bg-mint disabled:opacity-50';
const MAIN_ACTION = 'block rounded-full bg-lime px-4 py-2.5 text-center font-semibold';

/** Side panel: progress ring, ETA, counts and the batch controls. */
export function CurrentBatchPanel({ batch, status }: { batch: Batch; status: BatchStatus }) {
  const action = useBatchAction(batch.id);
  const run = (name: BatchAction) => action.run(name);
  const { counts } = status;
  const isDraft = batch.status === 'DRAFT';
  const failure = action.error instanceof ApiError ? action.error.message : 'Something went wrong.';

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
      {action.isError && (
        <p role="alert" className="mb-3 text-sm text-status-failed">
          {failure}
        </p>
      )}
      {!isDraft && (
        <div className="mb-3 flex flex-wrap gap-2">
          {batch.status === 'RUNNING' && (
            <button
              type="button"
              className={BUTTON}
              disabled={action.isPending}
              onClick={() => run('pause')}
            >
              Pause
            </button>
          )}
          {batch.status === 'PAUSED' && (
            <button
              type="button"
              className={BUTTON}
              disabled={action.isPending}
              onClick={() => run('resume')}
            >
              Resume
            </button>
          )}
          <button
            type="button"
            className={BUTTON}
            disabled={action.isPending}
            onClick={() => run('retry-failed')}
          >
            Retry failed
          </button>
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
    </section>
  );
}
