import type { Counts } from './api/types';

const NUMBER = new Intl.NumberFormat('en-US');
const SECONDS_PER_MINUTE = 60;
const SECONDS_PER_HOUR = 3600;
/** Decimal megabytes, as file managers show them. */
const BYTES_PER_MB = 1_000_000;

/** Digit-grouped number, for example 12,400. */
export function formatNumber(value: number): string {
  return NUMBER.format(value);
}

/** Calendar date in English, for example 19 Oct 2026. */
export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

/** File size in megabytes with one decimal, for example 12.4. */
export function formatMegabytes(bytes: number): string {
  return (bytes / BYTES_PER_MB).toFixed(1);
}

/** Share of rows that are finished (completed, failed or skipped), for example "75 %"; "-" with no rows. */
export function formatProgress(counts: Counts): string {
  if (counts.total === 0) return '-';
  const finished = counts.completed + counts.failed + counts.skipped;
  return `${Math.round((100 * finished) / counts.total)} %`;
}

/** Human ETA text: "ETA 1 min 30 s", or "ETA -" when unknown. */
export function formatEta(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds < 0) {
    return 'ETA -';
  }
  const total = Math.round(seconds);
  if (total < SECONDS_PER_MINUTE) return `ETA ${total} s`;
  if (total < SECONDS_PER_HOUR) {
    const rest = total % SECONDS_PER_MINUTE;
    return rest
      ? `ETA ${Math.floor(total / SECONDS_PER_MINUTE)} min ${rest} s`
      : `ETA ${total / SECONDS_PER_MINUTE} min`;
  }
  const hours = Math.floor(total / SECONDS_PER_HOUR);
  const minutes = Math.floor((total % SECONDS_PER_HOUR) / SECONDS_PER_MINUTE);
  return minutes ? `ETA ${hours} h ${minutes} min` : `ETA ${hours} h`;
}

/** Render time such as "12.5 s", or "-" when there is none. */
export function formatRenderTime(seconds: number | null): string {
  return seconds === null ? '-' : `${seconds.toFixed(1)} s`;
}

const DEVANAGARI = /[ऀ-ॿ]/;

/** True when the text contains Devanagari letters (so it gets lang="hi"). */
export function hasDevanagari(text: string): boolean {
  return DEVANAGARI.test(text);
}

const FINISHED = new Set(['COMPLETED', 'CANCELLED', 'FAILED']);

/** ETA line for a batch: "Done" once it has finished, otherwise the estimate. */
export function etaLabel(batchStatus: string, seconds: number | null | undefined): string {
  return FINISHED.has(batchStatus) ? 'Done' : formatEta(seconds);
}
