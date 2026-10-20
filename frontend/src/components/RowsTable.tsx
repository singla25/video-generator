import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Download, Play, RotateCcw } from 'lucide-react';
import { useEffect, useState } from 'react';

import { ApiError, apiFetch, apiUrl } from '../api/client';
import type { BatchRow, RowsPage } from '../api/types';
import { formatRenderTime, hasDevanagari } from '../format';
import { StatusChip, type RowStatus } from './StatusChip';
import { EmptyState, ErrorState, Skeleton } from './states';

const PAGE_SIZE = 50;
const SEARCH_DEBOUNCE_MS = 300;
const MAX_SEARCH_CHARS = 200;
const FILTERS: { value: '' | RowStatus; label: string }[] = [
  { value: '', label: 'All' },
  { value: 'COMPLETED', label: 'Completed' },
  { value: 'PROCESSING', label: 'Processing' },
  { value: 'QUEUED', label: 'Queued' },
  { value: 'FAILED', label: 'Failed' },
  { value: 'SKIPPED', label: 'Skipped' },
];

interface Props {
  batchId: string;
  status?: RowStatus;
  failureCode?: string;
  onPreview?: (url: string, name: string) => void;
}

function rowsUrl(batchId: string, p: Record<string, string | number | undefined>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(p)) {
    if (value !== undefined && value !== '') params.set(key, String(value));
  }
  return `/batches/${batchId}/rows?${params.toString()}`;
}

function NameCell({ name }: { name: string }) {
  return <span lang={hasDevanagari(name) ? 'hi' : undefined}>{name}</span>;
}

function RowActions({
  batchId,
  row,
  onRetry,
  onPreview,
}: {
  batchId: string;
  row: BatchRow;
  onRetry: () => void;
  onPreview?: (url: string, name: string) => void;
}) {
  const video = apiUrl(`/batches/${batchId}/rows/${row.row_number}/video`);
  const icon = 'inline-grid size-8 place-items-center rounded-full border hover:bg-mint';
  return (
    <div className="flex gap-1.5">
      {row.status === 'COMPLETED' && row.has_video && (
        <>
          <a
            href={video}
            target="_blank"
            rel="noreferrer"
            aria-label={`Preview video for ${row.name}`}
            className={icon}
            onClick={(event) => {
              if (!onPreview) return;
              event.preventDefault();
              onPreview(video, row.name);
            }}
          >
            <Play aria-hidden="true" strokeWidth={1.5} className="size-4" />
          </a>
          <a href={video} download aria-label={`Download video for ${row.name}`} className={icon}>
            <Download aria-hidden="true" strokeWidth={1.5} className="size-4" />
          </a>
        </>
      )}
      {row.status === 'FAILED' && (
        <button
          type="button"
          aria-label={`Retry row ${row.row_number}`}
          onClick={onRetry}
          className={icon}
        >
          <RotateCcw aria-hidden="true" strokeWidth={1.5} className="size-4" />
        </button>
      )}
    </div>
  );
}

/** Paged table of a batch's rows with search, status filter and row actions. */
export function RowsTable({ batchId, status, failureCode, onPreview }: Props) {
  const client = useQueryClient();
  const [search, setSearch] = useState('');
  const [debounced, setDebounced] = useState('');
  const [filter, setFilter] = useState<'' | RowStatus>(status ?? '');
  const [page, setPage] = useState(1);

  useEffect(() => {
    const timer = setTimeout(
      () => setDebounced(search.slice(0, MAX_SEARCH_CHARS)),
      SEARCH_DEBOUNCE_MS,
    );
    return () => clearTimeout(timer);
  }, [search]);

  const query = useQuery({
    queryKey: ['rows', batchId, filter, failureCode, debounced, page],
    queryFn: () =>
      apiFetch<RowsPage>(
        rowsUrl(batchId, {
          page,
          page_size: PAGE_SIZE,
          status: filter,
          failure_code: failureCode,
          search: debounced,
        }),
      ),
    placeholderData: keepPreviousData,
  });

  const retry = useMutation({
    mutationFn: (rowNumber: number) =>
      apiFetch(`/batches/${batchId}/rows/${rowNumber}/retry`, { method: 'POST' }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['rows', batchId] }),
  });

  const data = query.data;
  return (
    <section className="rounded-card border bg-card p-5">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h2 className="mr-auto font-semibold">Rows</h2>
        <input
          type="text"
          aria-label="Search by name or ID"
          placeholder="Search by name or ID"
          maxLength={MAX_SEARCH_CHARS}
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          className="rounded-full border px-4 py-1.5 text-sm"
        />
        <select
          aria-label="Status"
          value={filter}
          onChange={(e) => {
            setFilter(e.target.value as '' | RowStatus);
            setPage(1);
          }}
          className="rounded-full border bg-card px-3 py-1.5 text-sm"
        >
          {FILTERS.map((f) => (
            <option key={f.label} value={f.value}>
              {f.label}
            </option>
          ))}
        </select>
      </div>
      {retry.isError && (
        <p role="alert" className="mb-3 text-sm text-status-failed">
          {retry.error instanceof ApiError ? retry.error.message : 'Something went wrong.'}
        </p>
      )}
      {query.isPending ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} className="h-10" />
          ))}
        </div>
      ) : query.isError ? (
        <ErrorState title="Could not load rows" onRetry={() => void query.refetch()} />
      ) : data && data.rows.length === 0 ? (
        <EmptyState title="No rows match" />
      ) : (
        data && (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-muted">
                  <tr>
                    {['Name', 'ID', 'Status', 'Reason', 'Render time', 'Actions'].map((h) => (
                      <th key={h} scope="col" className="px-3 py-2 font-semibold">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row) => (
                    <tr key={row.row_number} className="border-t">
                      <td className="px-3 py-2">
                        <NameCell name={row.name} />
                      </td>
                      <td className="px-3 py-2">{row.voter_id}</td>
                      <td className="px-3 py-2">
                        <StatusChip status={row.status} />
                      </td>
                      <td className="px-3 py-2">{row.message ?? '-'}</td>
                      <td className="px-3 py-2">{formatRenderTime(row.render_seconds)}</td>
                      <td className="px-3 py-2">
                        <RowActions
                          batchId={batchId}
                          row={row}
                          onRetry={() => retry.mutate(row.row_number)}
                          onPreview={onPreview}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-4 flex items-center justify-end gap-3 text-sm">
              <button
                type="button"
                className="rounded-full border px-3 py-1 disabled:opacity-50"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
              >
                Previous page
              </button>
              <span>{`Page ${data.page} of ${data.total_pages}`}</span>
              <button
                type="button"
                className="rounded-full border px-3 py-1 disabled:opacity-50"
                disabled={page >= data.total_pages}
                onClick={() => setPage(page + 1)}
              >
                Next page
              </button>
            </div>
          </>
        )
      )}
    </section>
  );
}
