import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useId, useState } from 'react';

import { ApiError, apiFetch, apiUrl } from '../../api/client';
import type { Template } from '../../api/types';

const FIELD = 'w-full rounded-tile border px-3 py-2';

function parse(text: string): number {
  return text.trim() === '' ? Number.NaN : Number(text);
}

/** Returns a plain-language problem with the slot, or null when it is valid. */
export function slotProblem(start: number, end: number, duration: number): string | null {
  if (Number.isNaN(start) || Number.isNaN(end)) return 'Enter both start and end.';
  if (end <= start) return 'End must be after start.';
  if (start < 0 || end > duration) return `The slot must be inside the video (${duration} s).`;
  return null;
}

/** Bar for the whole video with the slot marked on it (nothing is marked until both ends are set). */
function Timeline({ start, end, duration }: { start: string; end: string; duration: number }) {
  const s = parse(start);
  const e = parse(end);
  const marked = !Number.isNaN(s) && !Number.isNaN(e) && duration > 0;
  const left = marked ? Math.min(100, Math.max(0, (s / duration) * 100)) : 0;
  const width = marked ? Math.min(100 - left, Math.max(0, ((e - s) / duration) * 100)) : 0;
  return (
    <div aria-hidden="true" className="relative h-3 rounded-full bg-page">
      {marked && (
        <div
          data-testid="slot-marker"
          data-start={start}
          data-end={end}
          className="absolute h-3 rounded-full bg-emerald"
          style={{ left: `${left}%`, width: `${width}%` }}
        />
      )}
    </div>
  );
}

/** Start/end fields for the name slot with a small timeline; saves with PUT. */
export function SlotEditor({
  template,
  showVideo = true,
}: {
  template: Template;
  showVideo?: boolean;
}) {
  const client = useQueryClient();
  const [start, setStart] = useState(template.slot ? String(template.slot.start_s) : '');
  const [end, setEnd] = useState(template.slot ? String(template.slot.end_s) : '');
  const [problem, setProblem] = useState<string | null>(null);

  const ids = useId();

  const save = useMutation({
    mutationFn: (body: { start_s: number; end_s: number }) =>
      apiFetch(`/templates/${template.id}/slot`, { method: 'PUT', body: JSON.stringify(body) }),
    onSuccess: () => client.invalidateQueries(),
  });
  // Saving a slot makes confirming it necessary again, so Confirm only acts on the saved slot.
  const confirm = useMutation({
    mutationFn: () => apiFetch(`/templates/${template.id}/slot/confirm`, { method: 'POST' }),
    onSuccess: () => client.invalidateQueries(),
  });
  const error = save.isError ? save.error : confirm.isError ? confirm.error : null;
  const saved = template.slot;
  const unsavedEdit = !saved || parse(start) !== saved.start_s || parse(end) !== saved.end_s;

  function submit() {
    const s = parse(start);
    const e = parse(end);
    const issue = slotProblem(s, e, template.duration_s);
    setProblem(issue);
    if (!issue) save.mutate({ start_s: s, end_s: e });
  }

  return (
    <div className="space-y-4 rounded-card border bg-card p-5">
      <h2 className="font-semibold">Name slot</h2>
      {template.needs_manual_slot && (
        <p className="text-sm text-status-skipped">
          The slot could not be found automatically. Set it by hand.
        </p>
      )}
      {showVideo && (
        <video
          data-testid="template-video"
          src={apiUrl(`/templates/${template.id}/video`)}
          controls
          preload="metadata"
          className="w-full rounded-tile bg-black"
        />
      )}
      <Timeline start={start} end={end} duration={template.duration_s} />
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor={`${ids}-start`} className="mb-1 block text-sm font-semibold">
            Slot start (s)
          </label>
          <input
            id={`${ids}-start`}
            type="number"
            step="0.1"
            min="0"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            className={FIELD}
          />
        </div>
        <div>
          <label htmlFor={`${ids}-end`} className="mb-1 block text-sm font-semibold">
            Slot end (s)
          </label>
          <input
            id={`${ids}-end`}
            type="number"
            step="0.1"
            min="0"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            className={FIELD}
          />
        </div>
      </div>
      {problem && <p className="text-sm text-status-failed">{problem}</p>}
      {error && (
        <p role="alert" className="text-sm text-status-failed">
          {error instanceof ApiError ? error.message : 'Something went wrong.'}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={submit}
          disabled={save.isPending}
          className="rounded-full border px-4 py-1.5 text-sm font-semibold hover:bg-mint disabled:opacity-50"
        >
          Save slot
        </button>
        {saved && !template.slot_confirmed && (
          <button
            type="button"
            onClick={() => confirm.mutate()}
            disabled={confirm.isPending || unsavedEdit}
            title={unsavedEdit ? 'Save the slot first' : undefined}
            className="rounded-full bg-lime px-4 py-1.5 text-sm font-semibold disabled:opacity-50"
          >
            Confirm slot
          </button>
        )}
        {saved && template.slot_confirmed && (
          <p className="text-sm font-semibold text-emerald">Slot confirmed</p>
        )}
      </div>
    </div>
  );
}
