import clsx from 'clsx';

export type RowStatus = 'QUEUED' | 'PROCESSING' | 'COMPLETED' | 'FAILED' | 'SKIPPED' | 'CANCELLED';
type Tone = 'green' | 'blue' | 'grey' | 'red' | 'amber';

const CHIPS: Record<RowStatus, { label: string; tone: Tone }> = {
  COMPLETED: { label: 'Completed', tone: 'green' },
  PROCESSING: { label: 'Processing', tone: 'blue' },
  QUEUED: { label: 'Queued', tone: 'grey' },
  FAILED: { label: 'Failed', tone: 'red' },
  SKIPPED: { label: 'Skipped', tone: 'amber' },
  CANCELLED: { label: 'Cancelled', tone: 'grey' },
};

const TONE_CLASSES: Record<Tone, { chip: string; dot: string }> = {
  green: { chip: 'bg-mint text-status-completed', dot: 'bg-status-completed' },
  blue: { chip: 'bg-blue-50 text-status-processing', dot: 'bg-status-processing' },
  grey: { chip: 'bg-slate-100 text-status-queued', dot: 'bg-status-queued' },
  red: { chip: 'bg-red-50 text-status-failed', dot: 'bg-status-failed' },
  amber: { chip: 'bg-amber-50 text-status-skipped', dot: 'bg-status-skipped' },
};

/** Small pill with a coloured dot for a row or batch status. */
export function StatusChip({ status }: { status: RowStatus }) {
  const known = CHIPS[status] as { label: string; tone: Tone } | undefined;
  const { label, tone } = known ?? { label: String(status), tone: 'grey' as const };
  return (
    <span
      data-testid="status-chip"
      data-tone={tone}
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold',
        TONE_CLASSES[tone].chip,
      )}
    >
      <span aria-hidden="true" className={clsx('size-1.5 rounded-full', TONE_CLASSES[tone].dot)} />
      {label}
    </span>
  );
}
