import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { apiFetch } from '../api/client';
import { useTemplateNames } from '../api/queries';
import type { BatchList } from '../api/types';
import { Pager } from '../components/Pager';
import { EmptyState, ErrorState, Skeleton } from '../components/states';
import { formatDate, formatNumber } from '../format';

const PAGE_SIZE = 50;
const HEADERS = ['Date', 'Batch', 'Template', 'Total', 'Success rate'];

function formatRate(rate: number | null): string {
  return rate === null || !Number.isFinite(rate) ? '-' : `${Math.round(rate * 100)} %`;
}

/** Past batches, newest first, each linking to its detail page. */
export function HistoryPage() {
  const [page, setPage] = useState(1);
  const names = useTemplateNames();
  const query = useQuery({
    queryKey: ['batches', 'history', page],
    queryFn: () => apiFetch<BatchList>(`/batches?page=${page}&page_size=${PAGE_SIZE}`),
    placeholderData: keepPreviousData,
  });

  if (query.isPending) return <Skeleton className="h-72" />;
  if (query.isError)
    return <ErrorState title="Could not load history" onRetry={() => void query.refetch()} />;
  const { batches, total_pages: pages } = query.data;
  if (batches.length === 0) return <EmptyState title="No past batches yet" />;

  return (
    <section className="rounded-card border bg-card p-5">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-muted">
            <tr>
              {HEADERS.map((h) => (
                <th key={h} scope="col" className="px-3 py-2 font-semibold">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {batches.map((b) => (
              <tr key={b.id} className="border-t">
                <td className="px-3 py-2">{formatDate(b.created_at)}</td>
                <td className="px-3 py-2">
                  <Link to={`/batches/${b.id}`} className="font-semibold text-emerald underline">
                    {b.sheet_name ?? b.folder_name ?? 'Batch'}
                  </Link>
                </td>
                <td className="px-3 py-2">{names.get(b.template_id) ?? '-'}</td>
                <td className="px-3 py-2">{formatNumber(b.counts.total)}</td>
                <td className="px-3 py-2">{formatRate(b.success_rate)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pager page={query.data.page} pages={pages} onPage={setPage} />
    </section>
  );
}
