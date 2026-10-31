import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { ApiError, apiFetch, apiUrl } from '../../api/client';
import { useConfirmSpelling, useSystemStatus } from '../../api/queries';
import type { Batch, SystemStatus } from '../../api/types';
import { SLOW_PREVIEW_MS_FAKE, SLOW_PREVIEW_MS_LOCAL } from '../../config';
import { PreviewProgress } from './PreviewProgress';
import { FakeAiNote, FirstRunNote } from './PreviewNotes';

const FIELD_ID = 'spoken-name';
const HINT_ID = 'spoken-name-hint';
const BUTTON =
  'rounded-full border px-4 py-1.5 text-sm font-semibold hover:bg-mint disabled:opacity-50';

function message(error: unknown): string {
  return error instanceof ApiError ? error.message : 'Something went wrong.';
}

/** Local models load slowly, so a local preview gets a longer wait before it counts as slow. */
function slowPreviewMs(aiMode: SystemStatus['ai_mode']): number {
  return aiMode === 'local' ? SLOW_PREVIEW_MS_LOCAL : SLOW_PREVIEW_MS_FAKE;
}

/**
 * True once the preview has been pending for `delayMs`. A new `restart` value or delay starts a
 * fresh wait that is not slow yet.
 */
function useSlowPending(pending: boolean, restart: number, delayMs: number): boolean {
  // Key the timeout by restart and delay, so a new wait is not slow until its own timer fires.
  const waitKey = `${restart}:${delayMs}`;
  const [timedOut, setTimedOut] = useState<string | null>(null);
  useEffect(() => {
    if (!pending) return undefined;
    const timer = setTimeout(() => setTimedOut(waitKey), delayMs);
    return () => clearTimeout(timer);
  }, [pending, waitKey, delayMs]);
  return pending && timedOut === waitKey;
}

interface SpokenNameProps {
  batch: Batch;
  text: string;
  onText: (value: string) => void;
  /** Runs once the spelling is saved: a new preview is asked for with it (DD-38). */
  onConfirmed: () => void;
}

/** Editable spoken name; Approve stays locked until this exact text is confirmed. */
function SpokenName({ batch, text, onText, onConfirmed }: SpokenNameProps) {
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
          aria-describedby={HINT_ID}
          onChange={(e) => onText(e.target.value)}
          className="flex-1 rounded-tile border px-3 py-1.5 text-sm"
        />
        <button
          type="button"
          className={BUTTON}
          disabled={!trimmed || confirm.isPending}
          onClick={() => confirm.mutate(trimmed, { onSuccess: onConfirmed })}
        >
          Confirm spelling
        </button>
      </div>
      <p id={HINT_ID} className="text-sm text-muted">
        Confirm to hear the preview with this spelling.
      </p>
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
  // One status read serves the AI mode and the worker health; undefined while loading or failing.
  const status = useSystemStatus().data;
  const aiMode = status?.ai_mode;
  const localAi = aiMode === 'local';
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
  const slow = useSlowPending(state === 'PENDING', generate.submittedAt, slowPreviewMs(aiMode));
  // Only a successful status read may blame the worker; a failing call stays silent.
  const workerDown = status?.worker_alive === false;

  return (
    <div className="space-y-4 rounded-card border bg-card p-5">
      <h2 className="font-semibold">Preview</h2>
      {state === 'PENDING' && (
        <>
          <p role="status">Generating preview...</p>
          <PreviewProgress stage={batch.preview?.stage} />
          {localAi && <FirstRunNote />}
        </>
      )}
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
        <SpokenName
          batch={batch}
          text={spoken}
          onText={setSpoken}
          onConfirmed={() => generate.mutate()}
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
      {aiMode === 'fake' && <FakeAiNote />}
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
