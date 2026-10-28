import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { ApiError, apiFetch, apiUrl } from '../../api/client';
import { useConfirmSpelling, useSystemStatus } from '../../api/queries';
import type { Batch } from '../../api/types';
import { SLOW_PREVIEW_MS } from '../../config';

const FIELD_ID = 'spoken-name';
const BUTTON =
  'rounded-full border px-4 py-1.5 text-sm font-semibold hover:bg-mint disabled:opacity-50';

function message(error: unknown): string {
  return error instanceof ApiError ? error.message : 'Something went wrong.';
}

/** True once the preview has been pending for SLOW_PREVIEW_MS; a new `restart` value resets the clock. */
function useSlowPending(pending: boolean, restart: number): boolean {
  // Remember which wait timed out, so a new wait starts as not slow without resetting state in the effect.
  const [timedOut, setTimedOut] = useState<number | null>(null);
  useEffect(() => {
    if (!pending) return undefined;
    const timer = setTimeout(() => setTimedOut(restart), SLOW_PREVIEW_MS);
    return () => clearTimeout(timer);
  }, [pending, restart]);
  return pending && timedOut === restart;
}

interface SpokenNameProps {
  batch: Batch;
  text: string;
  onText: (value: string) => void;
}

/** Editable spoken name; Approve stays locked until this exact text is confirmed. */
function SpokenName({ batch, text, onText }: SpokenNameProps) {
  const confirm = useConfirmSpelling(batch.id);
  const trimmed = text.trim();
  return (
    <div className="space-y-2">
      <label htmlFor={FIELD_ID} className="block text-sm font-semibold">
        Spoken name
      </label>
      <div className="flex gap-2">
        <input
          id={FIELD_ID}
          type="text"
          lang="hi"
          value={text}
          onChange={(e) => onText(e.target.value)}
          className="flex-1 rounded-tile border px-3 py-1.5 text-sm"
        />
        <button
          type="button"
          className={BUTTON}
          disabled={!trimmed || confirm.isPending}
          onClick={() => confirm.mutate(trimmed)}
        >
          Confirm spelling
        </button>
      </div>
      {confirm.error && (
        <p role="alert" className="text-sm text-status-failed">
          {message(confirm.error)}
        </p>
      )}
    </div>
  );
}

/** Generate a preview, watch it render, watch it and approve it (the A5 gate). */
export function PreviewPanel({ batch }: { batch: Batch }) {
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: ['batches'] });
  const state = batch.preview?.status ?? 'NONE';
  const approved = Boolean(batch.preview?.approved);
  const localAi = useSystemStatus().data?.ai_mode === 'local';
  const [spoken, setSpoken] = useState(
    batch.preview?.spoken_name ?? batch.preview?.suggested_spoken_name ?? '',
  );
  const spellingOk =
    !localAi ||
    (Boolean(batch.preview?.spoken_name_confirmed) && spoken.trim() === batch.preview?.spoken_name);

  const generate = useMutation({
    mutationFn: () => apiFetch(`/batches/${batch.id}/preview`, { method: 'POST' }),
    onSuccess: refresh,
  });
  const approve = useMutation({
    mutationFn: () => apiFetch(`/batches/${batch.id}/preview/approve`, { method: 'POST' }),
    onSuccess: refresh,
  });
  const error = generate.error ?? approve.error;
  const slow = useSlowPending(state === 'PENDING', generate.submittedAt);
  // Only a successful status read may blame the worker; a failing call stays silent.
  const workerDown = useSystemStatus().data?.worker_alive === false;

  return (
    <div className="space-y-4 rounded-card border bg-card p-5">
      <h2 className="font-semibold">Preview</h2>
      {state === 'PENDING' && <p role="status">Generating preview...</p>}
      {state === 'PENDING' && slow && (
        <div className="flex flex-wrap items-center gap-3">
          <p role="status" className="text-sm text-status-skipped">
            Preview is taking longer than expected.
            {workerDown && ' The background worker is not running.'}
          </p>
          <button
            type="button"
            className={BUTTON}
            disabled={generate.isPending}
            onClick={() => generate.mutate()}
          >
            Retry
          </button>
        </div>
      )}
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
      {state === 'READY' && localAi && !approved && (
        <SpokenName batch={batch} text={spoken} onText={setSpoken} />
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
          disabled={state !== 'READY' || approved || approve.isPending || !spellingOk}
          onClick={() => approve.mutate()}
        >
          Approve preview
        </button>
      </div>
    </div>
  );
}
