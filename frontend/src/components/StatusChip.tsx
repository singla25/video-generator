import { chipColors, type ChipTone } from './chipColors';

export type RowStatus = 'QUEUED' | 'PROCESSING' | 'COMPLETED' | 'FAILED' | 'SKIPPED' | 'CANCELLED';

const CHIPS: Record<RowStatus, { label: string; tone: ChipTone }> = {
  COMPLETED: { label: 'Completed', tone: 'green' },
  PROCESSING: { label: 'Processing', tone: 'blue' },
  QUEUED: { label: 'Queued', tone: 'grey' },
  FAILED: { label: 'Failed', tone: 'red' },
  SKIPPED: { label: 'Skipped', tone: 'amber' },
  CANCELLED: { label: 'Cancelled', tone: 'grey' },
};

/** Small pill with a coloured dot for a row or batch status. */
export function StatusChip({ status }: { status: RowStatus }) {
  const known = CHIPS[status] as { label: string; tone: ChipTone } | undefined;
  const { label, tone } = known ?? { label: String(status), tone: 'grey' as const };
  const { text, background } = chipColors[tone];
  return (
    <span
      data-testid="status-chip"
      data-tone={tone}
      style={{ color: text, backgroundColor: background }}
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold"
    >
      <span
        aria-hidden="true"
        style={{ backgroundColor: text }}
        className="size-1.5 rounded-full"
      />
      {label}
    </span>
  );
}
