import { useMutation } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { ApiError } from '../../api/client';
import { startBatch, useBatchList } from '../../api/queries';
import { defaultFolder, folderProblem, newIdempotencyKey } from './rules';
import { VideoCountChoice } from './VideoCountChoice';
import { startBody, videoCount, type VideoChoice } from './videoCount';

const BUTTON = 'rounded-full bg-lime px-5 py-2 font-semibold disabled:opacity-50';
const GHOST = 'rounded-full border px-5 py-2 font-semibold hover:bg-mint';

interface Props {
  batchId: string;
  validRows: number;
  onBack: () => void;
}

/** Step 4: choose how many videos, the output folder, confirm and start the batch. */
export function StepOutput({ batchId, validRows, onBack }: Props) {
  const navigate = useNavigate();
  const list = useBatchList();
  const [typed, setTyped] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [choice, setChoice] = useState<VideoChoice>('all');
  const [custom, setCustom] = useState('');
  /** Videos to start, set when the user reviews the start; the dialog is open while it is set. */
  const [plan, setPlan] = useState<number | null>(null);
  const key = useRef('');
  const sent = useRef(false);

  const folder = typed ?? defaultFolder((list.data?.batches ?? []).map((b) => b.folder_name));
  const count = videoCount(choice, custom, validRows);

  const start = useMutation({
    mutationFn: (videos: number) =>
      startBatch(batchId, startBody(folder.trim(), videos, validRows), key.current),
    onSuccess: () => navigate(`/batches/${batchId}`),
    onError: () => {
      sent.current = false;
      setPlan(null);
    },
  });

  function review() {
    const issue = folderProblem(folder);
    setProblem(issue);
    if (issue || count === null) return;
    key.current = newIdempotencyKey();
    sent.current = false;
    setPlan(count);
  }

  function confirm(videos: number) {
    if (sent.current) return;
    sent.current = true;
    start.mutate(videos);
  }

  return (
    <section className="space-y-4 rounded-card border bg-card p-6">
      <VideoCountChoice
        rows={validRows}
        choice={choice}
        custom={custom}
        onChoice={setChoice}
        onCustom={setCustom}
      />
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
        <button type="button" className={BUTTON} disabled={count === null} onClick={review}>
          Review and start
        </button>
      </div>
      {plan !== null && (
        <div className="fixed inset-0 z-20 grid place-items-center bg-black/30 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirm-title"
            onKeyDown={(e) => e.key === 'Escape' && setPlan(null)}
            className="w-full max-w-sm space-y-4 rounded-card bg-card p-6"
          >
            <h2 id="confirm-title" className="text-lg font-bold">{`Start ${plan} videos?`}</h2>
            <p className="text-sm text-muted">{`They will be saved in the folder "${folder.trim()}".`}</p>
            <div className="flex justify-end gap-3">
              <button type="button" autoFocus className={GHOST} onClick={() => setPlan(null)}>
                Cancel
              </button>
              <button
                type="button"
                className={BUTTON}
                disabled={start.isPending}
                onClick={() => confirm(plan)}
              >
                Confirm and start
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
