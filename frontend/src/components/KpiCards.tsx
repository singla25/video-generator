import { Plus } from 'lucide-react';
import { Link } from 'react-router-dom';

import type { Counts } from '../api/types';
import { formatNumber } from '../format';
import { CountUp } from './CountUp';
import { StatusChip, type RowStatus } from './StatusChip';

const STATUS_CARDS: { key: keyof Counts; status: RowStatus }[] = [
  { key: 'completed', status: 'COMPLETED' },
  { key: 'processing', status: 'PROCESSING' },
  { key: 'queued', status: 'QUEUED' },
  { key: 'failed', status: 'FAILED' },
  { key: 'skipped', status: 'SKIPPED' },
];

/** Tile labels for a DRAFT batch: nothing has started, so its rows are not queued (DD-38). */
const DRAFT_LABELS: Partial<Record<keyof Counts, string>> = { queued: 'Not started' };

const CARD = 'rounded-card border bg-card p-4';

function Big({ value, of }: { value: number; of?: number }) {
  return (
    <p className="mt-3 text-3xl font-bold">
      <CountUp value={value} />
      {of !== undefined && (
        <span className="ml-1 text-base font-medium text-muted"> / {formatNumber(of)}</span>
      )}
    </p>
  );
}

/** Six KPI cards (total + one per status) and the dashed New batch card. */
export function KpiCards({ counts, draft = false }: { counts: Counts; draft?: boolean }) {
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4 xl:grid-cols-7">
      <div data-testid="kpi-total" data-value={counts.total} className={CARD}>
        <p className="text-sm font-semibold text-muted">Total</p>
        <Big value={counts.total} />
      </div>
      {STATUS_CARDS.map(({ key, status }) => (
        <div key={key} data-testid={`kpi-${key}`} data-value={counts[key]} className={CARD}>
          <StatusChip status={status} label={draft ? DRAFT_LABELS[key] : undefined} />
          <Big value={counts[key]} of={counts.total} />
        </div>
      ))}
      <Link
        to="/batches/new"
        data-testid="new-batch-card"
        className="flex flex-col items-center justify-center gap-1 rounded-card border-2 border-dashed p-4 text-sm font-semibold text-emerald hover:bg-mint"
      >
        <Plus aria-hidden="true" strokeWidth={1.5} className="size-6" />
        New batch
      </Link>
    </div>
  );
}
