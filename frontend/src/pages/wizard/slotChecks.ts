import type { Template } from '../../api/types';

/** Most name slots a template can have: the primary slot plus four extra ones (DD-40). */
export const MAX_SLOTS = 5;

/** Least silence between two slots, in seconds; closer slots overlap or touch (DD-40). */
export const MIN_GAP_S = 0.2;

/** Float tolerance, so that a gap of exactly MIN_GAP_S is not refused by rounding. */
const GAP_TOLERANCE_S = 1e-9;

export const OVERLAP_MESSAGE = 'Slots must not overlap or touch.';
export const ORDER_MESSAGE = 'Each slot must end after it starts.';
export const FILL_MESSAGE = 'Fill in every slot or remove it.';

/** A slot as the API takes it: [start, end] in seconds. */
export type Pair = [number, number];

/** A slot as the user typed it; NaN marks an empty or non-numeric field. */
export interface Span {
  start: number;
  end: number;
}

/** Parses a number field. An empty field is NaN. */
export function parseField(text: string): number {
  return text.trim() === '' ? Number.NaN : Number(text);
}

/** True when both ends of a slot are numbers. */
export function isComplete(span: Span): boolean {
  return !Number.isNaN(span.start) && !Number.isNaN(span.end);
}

/** Returns a plain-language problem with the primary slot, or null when it is valid. */
export function slotProblem(start: number, end: number, duration: number): string | null {
  if (Number.isNaN(start) || Number.isNaN(end)) return 'Enter both start and end.';
  if (end <= start) return 'End must be after start.';
  if (start < 0 || end > duration) return `The slot must be inside the video (${duration} s).`;
  return null;
}

/** The slots as [start, end] pairs, sorted ascending by start, the order the API expects. */
export function toPairs(spans: Span[]): Pair[] {
  return [...spans].sort((a, b) => a.start - b.start).map((s): Pair => [s.start, s.end]);
}

/** True when some two slots overlap, touch, or leave less than MIN_GAP_S between them. */
function tooClose(spans: Span[]): boolean {
  const sorted = [...spans].sort((a, b) => a.start - b.start);
  // Checking neighbours after sorting by start finds every overlap: if slots i and j overlap,
  // the slot right after i starts before i ends.
  return sorted.some(
    (next, i) => i > 0 && next.start - sorted[i - 1].end < MIN_GAP_S - GAP_TOLERANCE_S,
  );
}

/**
 * Messages about the extra slots and the slots as a whole, in display order, each shown once.
 * `extras` are the extra slots in position order; the label of extra i is "Slot i+2". The primary
 * slot's own messages stay in slotProblem. A duration of 0 or less means the video length is not known.
 */
export function extraSlotIssues(primary: Span, extras: Span[], duration: number): string[] {
  const issues: string[] = [];
  if (extras.some((s) => !isComplete(s))) issues.push(FILL_MESSAGE);
  if (extras.some((s) => isComplete(s) && s.end <= s.start)) issues.push(ORDER_MESSAGE);
  if (duration > 0) {
    extras.forEach((s, i) => {
      if (isComplete(s) && s.end > duration) issues.push(`Slot ${i + 2} ends after the video.`);
    });
  }
  if (tooClose([primary, ...extras].filter(isComplete))) issues.push(OVERLAP_MESSAGE);
  return issues;
}

/** True when the typed slots are exactly the saved ones, ignoring the order they were typed in. */
export function matchesSaved(spans: Span[], saved: Pair[]): boolean {
  const current = toPairs(spans);
  const wanted = toPairs(saved.map(([start, end]) => ({ start, end })));
  return (
    current.length === wanted.length &&
    current.every(([s, e], i) => s === wanted[i][0] && e === wanted[i][1])
  );
}

/** Changes whenever the saved slots change, so the editor remounts and shows the new values. */
export function slotStateKey(template: Template): string {
  const primary = template.slot ? `${template.slot.start_s}-${template.slot.end_s}` : 'none';
  return [primary, ...template.extra_slots.map(([s, e]) => `${s}-${e}`)].join('|');
}
