import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { ApiError, apiFetch } from '../../api/client';
import { useBatchAction, type BatchAction } from '../../api/queries';
import type { Batch } from '../../api/types';
import { ConfirmDialog } from '../../components/ConfirmDialog';

const BUTTON =
  'rounded-full border px-4 py-1.5 text-sm font-semibold hover:bg-mint disabled:opacity-50';
const ACTIVE = new Set(['RUNNING', 'PAUSED', 'READY']);

function message(error: unknown): string {
  return error instanceof ApiError ? error.message : 'Something went wrong.';
}

/** Pause, resume, retry, cancel and delete, with a question before the ones that cannot be undone. */
export function BatchActions({ batch }: { batch: Batch }) {
  const navigate = useNavigate();
  const client = useQueryClient();
  const action = useBatchAction(batch.id);
  const [asking, setAsking] = useState<'cancel' | 'delete' | null>(null);
  const deleting = useRef(false);

  const remove = useMutation({
    mutationFn: () => apiFetch(`/batches/${batch.id}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ['batches'] });
      navigate('/history');
    },
    onSettled: () => {
      deleting.current = false;
    },
  });

  const error = action.isError ? action.error : remove.isError ? remove.error : null;
  const run = (name: BatchAction) => action.run(name);
  const canCancel = ACTIVE.has(batch.status);

  function confirm() {
    const which = asking;
    setAsking(null);
    if (which === 'cancel') run('cancel');
    if (which === 'delete' && !deleting.current) {
      deleting.current = true;
      remove.mutate();
    }
  }

  return (
    <div className="space-y-3">
      {error && (
        <p role="alert" className="text-sm text-status-failed">
          {message(error)}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
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
        {canCancel && (
          <button type="button" className={BUTTON} onClick={() => setAsking('cancel')}>
            Cancel batch
          </button>
        )}
        <button
          type="button"
          className={`${BUTTON} text-status-failed`}
          onClick={() => setAsking('delete')}
        >
          Delete batch
        </button>
      </div>
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
          title="Delete this batch and its videos?"
          body="This cannot be undone."
          confirmLabel="Delete"
          cancelLabel="Keep"
          onConfirm={confirm}
          onCancel={() => setAsking(null)}
        />
      )}
    </div>
  );
}
