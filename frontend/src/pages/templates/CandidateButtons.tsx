import { useMutation, useQueryClient } from '@tanstack/react-query';

import { clearCandidates, useCandidates } from '../../api/candidates';
import { ApiError, apiFetch } from '../../api/client';

/** Close words the analyser found when it found no slot; one click sets the slot to that word. */
export function CandidateButtons({ templateId }: { templateId: string }) {
  const client = useQueryClient();
  const candidates = useCandidates(templateId);
  const use = useMutation({
    mutationFn: (span: { start_s: number; end_s: number }) =>
      apiFetch(`/templates/${templateId}/slot`, {
        method: 'PUT',
        body: JSON.stringify({ ...span, extra_slots: [] }),
      }),
    onSuccess: async () => {
      clearCandidates(client, templateId);
      await client.invalidateQueries();
    },
  });
  if (candidates.length === 0) return null;
  return (
    <div role="group" aria-label="Closest matches" className="space-y-2">
      <p className="text-sm font-semibold">Closest matches</p>
      <ul className="space-y-2">
        {candidates.map((c) => (
          <li
            key={`${c.start_s}-${c.text}`}
            className="flex flex-wrap items-center justify-between gap-2 rounded-tile border p-2"
          >
            <span className="min-w-0 break-words text-sm">
              <span className="font-semibold">{c.text}</span>{' '}
              <span className="text-muted">
                {c.start_s.toFixed(1)}-{c.end_s.toFixed(1)} s, {Math.round(c.closeness * 100)}%
                close
              </span>
            </span>
            <button
              type="button"
              disabled={use.isPending}
              onClick={() => use.mutate({ start_s: c.start_s, end_s: c.end_s })}
              className="rounded-full border px-4 py-1.5 text-sm font-semibold hover:bg-mint disabled:opacity-50"
            >
              Use this word
            </button>
          </li>
        ))}
      </ul>
      {use.isError && (
        <p role="alert" className="text-sm text-status-failed">
          {use.error instanceof ApiError ? use.error.message : 'Something went wrong.'}
        </p>
      )}
    </div>
  );
}
