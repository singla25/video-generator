const NUMBER = new Intl.NumberFormat('en-US');
const SECONDS_PER_MINUTE = 60;
const SECONDS_PER_HOUR = 3600;

/** Digit-grouped number, for example 12,400. */
export function formatNumber(value: number): string {
  return NUMBER.format(value);
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
