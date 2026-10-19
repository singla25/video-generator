import { useMutation } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { ApiError, apiFetch } from '../../api/client';
import { useBatchList } from '../../api/queries';
import { defaultFolder, folderProblem, newIdempotencyKey } from './rules';

const BUTTON = 'rounded-full bg-lime px-5 py-2 font-semibold disabled:opacity-50';
const GHOST = 'rounded-full border px-5 py-2 font-semibold hover:bg-mint';

interface Props {
  batchId: string;
  validRows: number;
  onBack: () => void;
}

/** Step 4: choose the output folder, confirm and start the batch. */
export function StepOutput({ batchId, validRows, onBack }: Props) {
  const navigate = useNavigate();
  const list = useBatchList();
  const [typed, setTyped] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const key = useRef('');
  const sent = useRef(false);

  const folder = typed ?? defaultFolder((list.data?.batches ?? []).map((b) => b.folder_name));

  const start = useMutation({
    mutationFn: () =>
      apiFetch(`/batches/${batchId}/start`, {
        method: 'POST',
        headers: { 'Idempotency-Key': key.current },
        body: JSON.stringify({ folder_name: folder.trim() }),
      }),
    onSuccess: () => navigate(`/batches/${batchId}`),
    onError: () => {
      sent.current = false;
      setConfirming(false);
    },
  });

  function review() {
    const issue = folderProblem(folder);
    setProblem(issue);
    if (issue) return;
    key.current = newIdempotencyKey();
    sent.current = false;
    setConfirming(true);
  }

  function confirm() {
    if (sent.current) return;
    sent.current = true;
    start.mutate();
  }

  return (
    <section className="space-y-4 rounded-card border bg-card p-6">
      <div>
        <label htmlFor="folder" className="mb-1 block text-sm font-semibold">
          Output folder
        </label>
        <input
          id="folder"
          type="text"
          value={folder}
          onChange={(e) => setTyped(e.target.value)}
          className="w-full rounded-tile border px-3 py-2"
        />
      </div>
      {problem && <p className="text-sm text-status-failed">{problem}</p>}
      {start.isError && (
        <p role="alert" className="text-sm text-status-failed">
          {start.error instanceof ApiError ? start.error.message : 'Something went wrong.'}
        </p>
      )}
      <div className="flex justify-between">
        <button type="button" className={GHOST} onClick={onBack}>
          Back
        </button>
        <button type="button" className={BUTTON} onClick={review}>
          Review and start
        </button>
      </div>
      {confirming && (
        <div className="fixed inset-0 z-20 grid place-items-center bg-black/30 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirm-title"
            onKeyDown={(e) => e.key === 'Escape' && setConfirming(false)}
            className="w-full max-w-sm space-y-4 rounded-card bg-card p-6"
          >
            <h2 id="confirm-title" className="text-lg font-bold">{`Start ${validRows} videos?`}</h2>
            <p className="text-sm text-muted">{`They will be saved in the folder "${folder.trim()}".`}</p>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                autoFocus
                className={GHOST}
                onClick={() => setConfirming(false)}
              >
                Cancel
              </button>
              <button type="button" className={BUTTON} disabled={start.isPending} onClick={confirm}>
                Confirm and start
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
