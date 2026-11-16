import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useId, useRef, useState } from 'react';

import { ApiError, apiFetch, apiUrl } from '../../api/client';
import type { Template } from '../../api/types';
import { ExtraSlotRow } from './ExtraSlotRow';
import { SlotField } from './SlotField';
import {
  MAX_SLOTS,
  type Pair,
  type Span,
  extraSlotIssues,
  matchesSaved,
  parseField,
  slotProblem,
  toPairs,
} from './slotChecks';

/** An extra slot as the user sees it; `id` keeps the rows apart when one in the middle is removed. */
interface ExtraRow {
  id: number;
  start: string;
  end: string;
}

/** Most extra slots: the primary slot plus these makes MAX_SLOTS. */
const MAX_EXTRA = MAX_SLOTS - 1;
const BUTTON =
  'rounded-full border px-4 py-1.5 text-sm font-semibold hover:bg-mint disabled:opacity-50';

function prefill(template: Template): ExtraRow[] {
  return template.extra_slots.map(([start, end], i) => ({
    id: i,
    start: String(start),
    end: String(end),
  }));
}

/** Bar for the whole video with the slot marked on it (nothing is marked until both ends are set). */
function Timeline({ start, end, duration }: { start: string; end: string; duration: number }) {
  const s = parseField(start);
  const e = parseField(end);
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

/** Name slot fields (primary plus up to four extra slots) with a timeline; saves with PUT. */
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
  const [extras, setExtras] = useState<ExtraRow[]>(() => prefill(template));
  const [freshId, setFreshId] = useState<number | null>(null);
  const nextId = useRef(template.extra_slots.length);
  const addButton = useRef<HTMLButtonElement>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const ids = useId();

  const save = useMutation({
    mutationFn: (body: { start_s: number; end_s: number; extra_slots: Pair[] }) =>
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

  const primary: Span = { start: parseField(start), end: parseField(end) };
  const spans: Span[] = extras.map((row) => ({
    start: parseField(row.start),
    end: parseField(row.end),
  }));
  const issues = extraSlotIssues(primary, spans, template.duration_s);
  const unsavedEdit =
    !saved ||
    primary.start !== saved.start_s ||
    primary.end !== saved.end_s ||
    !matchesSaved(spans, template.extra_slots);

  function submit() {
    const issue = slotProblem(primary.start, primary.end, template.duration_s);
    setProblem(issue);
    if (!issue && issues.length === 0) {
      save.mutate({ start_s: primary.start, end_s: primary.end, extra_slots: toPairs(spans) });
    }
  }

  function addSlot() {
    const id = nextId.current;
    nextId.current += 1;
    setExtras((rows) => [...rows, { id, start: '', end: '' }]);
    setFreshId(id);
  }

  function editSlot(id: number, field: 'start' | 'end', value: string) {
    setExtras((rows) => rows.map((row) => (row.id === id ? { ...row, [field]: value } : row)));
  }

  function removeSlot(id: number) {
    setExtras((rows) => rows.filter((row) => row.id !== id));
    // The removed row had the focus; move it to the add button so keyboard users keep their place.
    addButton.current?.focus();
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
        <SlotField id={`${ids}-start`} label="Slot start (s)" value={start} onChange={setStart} />
        <SlotField id={`${ids}-end`} label="Slot end (s)" value={end} onChange={setEnd} />
      </div>
      {extras.map((row, i) => (
        <ExtraSlotRow
          key={row.id}
          index={i}
          start={row.start}
          end={row.end}
          autoFocus={row.id === freshId}
          onChange={(field, value) => editSlot(row.id, field, value)}
          onRemove={() => removeSlot(row.id)}
        />
      ))}
      <button
        ref={addButton}
        type="button"
        onClick={addSlot}
        disabled={extras.length >= MAX_EXTRA}
        className={BUTTON}
      >
        Add another name slot
      </button>
      {issues.map((message) => (
        <p key={message} role="alert" className="text-sm text-status-failed">
          {message}
        </p>
      ))}
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
          disabled={save.isPending || issues.length > 0}
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
