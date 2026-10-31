import { useState } from 'react';

import { useBatchView, useDraftBatches, useTemplateNames } from '../api/queries';
import type { BatchView } from '../api/types';
import { BatchListTable } from '../components/BatchListTable';
import { DraftsSection } from '../components/DraftsSection';
import { Pager } from '../components/Pager';
import { EmptyState, ErrorState, Skeleton } from '../components/states';

const EMPTY_TITLE: Record<BatchView, string> = {
  running: 'No running batches',
  completed: 'No completed batches',
  failed: 'No failed batches',
};

type DraftsQuery = ReturnType<typeof useDraftBatches>;

/** The Not started section (DD-38): shown only when there is at least one draft. */
function NotStarted({ query, names }: { query: DraftsQuery; names: Map<string, string> }) {
  if (query.isError)
    return (
      <ErrorState
        title="Could not load drafts"
        retryLabel="Retry"
        onRetry={() => void query.refetch()}
      />
    );
  const batches = query.data?.batches ?? [];
  if (batches.length === 0) return null;
  return <DraftsSection drafts={batches} templateNames={names} />;
}

/** One dashboard list of batches (running, completed or failed), newest first, with paging. */
export function BatchListPage({ view }: { view: BatchView }) {
  const [page, setPage] = useState(1);
  const names = useTemplateNames();
  const query = useBatchView(view, page);
  // Drafts are asked for on the running page only; the other lists never see them.
  const drafts = useDraftBatches(view === 'running');

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
  return (
    <div className="space-y-4">
      {batches.length === 0 ? (
        <EmptyState title={EMPTY_TITLE[view]}>
          {current > 1 && <Pager page={current} pages={pages} onPage={setPage} />}
        </EmptyState>
      ) : (
        <section className="rounded-card border bg-card p-5">
          <BatchListTable batches={batches} templateNames={names} />
          <Pager page={current} pages={pages} onPage={setPage} />
        </section>
      )}
      {view === 'running' && <NotStarted query={drafts} names={names} />}
    </div>
  );
}
