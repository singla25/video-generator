import { useState } from 'react';

import { useBatchView, useTemplateNames } from '../api/queries';
import type { BatchView } from '../api/types';
import { BatchListTable } from '../components/BatchListTable';
import { Pager } from '../components/Pager';
import { EmptyState, ErrorState, Skeleton } from '../components/states';

const EMPTY_TITLE: Record<BatchView, string> = {
  running: 'No running batches',
  completed: 'No completed batches',
  failed: 'No failed batches',
};

/** One dashboard list of batches (running, completed or failed), newest first, with paging. */
export function BatchListPage({ view }: { view: BatchView }) {
  const [page, setPage] = useState(1);
  const names = useTemplateNames();
  const query = useBatchView(view, page);

  if (query.isPending) return <Skeleton className="h-72" />;
  if (query.isError)
    return (
      <ErrorState
        title="Could not load batches"
        retryLabel="Retry"
        onRetry={() => void query.refetch()}
      />
    );

  const { batches, page: current, total_pages: pages } = query.data;
  if (batches.length === 0)
    return (
      <EmptyState title={EMPTY_TITLE[view]}>
        {current > 1 && <Pager page={current} pages={pages} onPage={setPage} />}
      </EmptyState>
    );

  return (
    <section className="rounded-card border bg-card p-5">
      <BatchListTable batches={batches} templateNames={names} />
      <Pager page={current} pages={pages} onPage={setPage} />
    </section>
  );
}
