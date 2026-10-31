import { Link } from 'react-router-dom';

import { useBatchList, useBatchStatus } from '../api/queries';
import type { Batch } from '../api/types';
import { CurrentBatchPanel } from '../components/CurrentBatchPanel';
import { KpiCards } from '../components/KpiCards';
import { RowsTable } from '../components/RowsTable';
import { VideosChart } from '../components/VideosChart';
import { EmptyState, ErrorState, Skeleton } from '../components/states';

const ACTIVE = new Set(['RUNNING', 'PAUSED']);

/** The batch to show: the first running or paused one, otherwise the newest. */
function pickCurrent(batches: Batch[]): Batch | undefined {
  return batches.find((b) => ACTIVE.has(b.status)) ?? batches[0];
}

function LoadingState() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4 xl:grid-cols-7">
        {Array.from({ length: 7 }, (_, i) => (
          <Skeleton key={i} className="h-28" />
        ))}
      </div>
      <Skeleton className="h-72" />
    </div>
  );
}

/** Dashboard home: KPIs, videos chart, current batch and its rows. */
export function OverviewPage() {
  const list = useBatchList();
  const current = list.data ? pickCurrent(list.data.batches) : undefined;
  const status = useBatchStatus(current?.id);

  if (list.isError || status.isError) {
    return (
      <ErrorState
        title="Could not load the dashboard"
        onRetry={() => {
          void list.refetch();
          void status.refetch();
        }}
      />
    );
  }
  if (list.isPending || (current && !status.data)) return <LoadingState />;
  if (!current || !status.data) {
    return (
      <EmptyState title="No batches yet">
        <Link to="/batches/new" className="rounded-full bg-lime px-4 py-2 font-semibold">
          Create your first batch
        </Link>
      </EmptyState>
    );
  }

  return (
    <div className="space-y-4">
      <KpiCards counts={status.data.counts} draft={current.status === 'DRAFT'} />
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <VideosChart />
        <CurrentBatchPanel batch={current} status={status.data} />
      </div>
      <RowsTable batchId={current.id} batchStatus={current.status} />
    </div>
  );
}
