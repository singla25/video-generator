import { useMutation, useQueryClient } from '@tanstack/react-query';

import { ApiError, apiFetch, apiUrl } from '../../api/client';
import type { Batch } from '../../api/types';

const BUTTON =
  'rounded-full border px-4 py-1.5 text-sm font-semibold hover:bg-mint disabled:opacity-50';

function message(error: unknown): string {
  return error instanceof ApiError ? error.message : 'Something went wrong.';
}

/** Generate a preview, watch it render, watch it and approve it (the A5 gate). */
export function PreviewPanel({ batch }: { batch: Batch }) {
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: ['batches'] });
  const state = batch.preview?.status ?? 'NONE';
  const approved = Boolean(batch.preview?.approved);

  const generate = useMutation({
    mutationFn: () => apiFetch(`/batches/${batch.id}/preview`, { method: 'POST' }),
    onSuccess: refresh,
  });
  const approve = useMutation({
    mutationFn: () => apiFetch(`/batches/${batch.id}/preview/approve`, { method: 'POST' }),
    onSuccess: refresh,
  });
  const error = generate.error ?? approve.error;

  return (
    <div className="space-y-4 rounded-card border bg-card p-5">
      <h2 className="font-semibold">Preview</h2>
      {state === 'PENDING' && <p role="status">Generating preview...</p>}
      {state === 'STALE' && (
        <p className="text-sm text-status-skipped">The preview is out of date</p>
      )}
      {state === 'FAILED' && (
        <p className="text-sm text-status-failed">The preview could not be made. Try again.</p>
      )}
      {state === 'READY' && (
        <video
          data-testid="preview-video"
          src={apiUrl(`/batches/${batch.id}/preview`)}
          controls
          className="w-full rounded-tile bg-black"
        />
      )}
      {state === 'READY' && approved && (
        <p className="text-sm font-semibold text-emerald">Preview approved</p>
      )}
      {error && (
        <p role="alert" className="text-sm text-status-failed">
          {message(error)}
        </p>
      )}
      <div className="flex gap-2">
        <button
          type="button"
          className={BUTTON}
          disabled={generate.isPending || state === 'PENDING'}
          onClick={() => generate.mutate()}
        >
          Generate preview
        </button>
        <button
          type="button"
          className={BUTTON}
          disabled={state !== 'READY' || approved || approve.isPending}
          onClick={() => approve.mutate()}
        >
          Approve preview
        </button>
      </div>
    </div>
  );
}
