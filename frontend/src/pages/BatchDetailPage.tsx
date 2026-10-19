import { Download, FileText, X } from 'lucide-react';
import { useState } from 'react';
import { useParams } from 'react-router-dom';

import { ApiError, apiUrl } from '../api/client';
import { useBatch, useBatchStatus } from '../api/queries';
import type { FailureGroup } from '../api/types';
import { ProgressRing } from '../components/ProgressRing';
import { RowsTable } from '../components/RowsTable';
import { ErrorState, Skeleton } from '../components/states';
import { formatEta, formatNumber } from '../format';
import { BatchActions } from './batch/BatchActions';
import { FailureReasons } from './batch/FailureReasons';

const STATUS_LABELS: Record<string, string> = {
  DRAFT: 'Draft',
  READY: 'Ready',
  RUNNING: 'Running',
  PAUSED: 'Paused',
  COMPLETED: 'Completed',
  CANCELLED: 'Cancelled',
  FAILED: 'Failed',
};
const STAT_LABELS = ['completed', 'processing', 'queued', 'failed', 'skipped'] as const;
const LINK =
  'inline-flex items-center gap-1.5 rounded-full border px-4 py-1.5 text-sm font-semibold hover:bg-mint';

function ExportLink({
  href,
  enabled,
  icon,
  children,
}: {
  href: string;
  enabled: boolean;
  icon: 'zip' | 'csv';
  children: string;
}) {
  const Icon = icon === 'zip' ? Download : FileText;
  return (
    <a
      href={href}
      aria-disabled={!enabled}
      onClick={(event) => !enabled && event.preventDefault()}
      className={`${LINK} ${enabled ? '' : 'pointer-events-none opacity-50'}`}
    >
      <Icon aria-hidden="true" strokeWidth={1.5} className="size-4" />
      {children}
    </a>
  );
}

/** One batch: stats, progress, failure reasons, rows, previews, exports and controls. */
export function BatchDetailPage() {
  const { id = '' } = useParams();
  const batch = useBatch(id);
  const status = useBatchStatus(id);
  const [reason, setReason] = useState<FailureGroup | null>(null);
  const [preview, setPreview] = useState<{ url: string; name: string } | null>(null);

  if (batch.isError || status.isError) {
    const error = batch.error ?? status.error;
    const text = error instanceof ApiError ? error.message : 'Could not load this batch';
    return (
      <ErrorState
        title={text}
        onRetry={() => {
          void batch.refetch();
          void status.refetch();
        }}
      />
    );
  }
  if (!batch.data || !status.data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-28" />
        <Skeleton className="h-60" />
      </div>
    );
  }

  const { counts } = status.data;
  return (
    <div className="space-y-4">
      <section data-testid="batch-stats" className="rounded-card border bg-card p-5">
        <div className="flex flex-wrap items-center gap-6">
          <ProgressRing percent={status.data.progress_percent} />
          <div>
            <p className="text-sm text-muted">
              {batch.data.sheet_name ?? batch.data.folder_name ?? ''}
            </p>
            <p className="text-2xl font-bold">
              {STATUS_LABELS[batch.data.status] ?? batch.data.status}
            </p>
            <p className="text-sm font-semibold">{formatEta(status.data.eta_seconds)}</p>
          </div>
          <dl className="ml-auto grid grid-cols-3 gap-x-6 gap-y-2 text-sm sm:grid-cols-6">
            <div>
              <dt className="text-muted">Total</dt>
              <dd className="font-bold">{formatNumber(counts.total)}</dd>
            </div>
            {STAT_LABELS.map((key) => (
              <div key={key}>
                <dt className="text-muted">{key[0]!.toUpperCase() + key.slice(1)}</dt>
                <dd className="font-bold">{formatNumber(counts[key])}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <BatchActions batch={batch.data} />
        <div className="flex gap-2">
          <ExportLink
            href={apiUrl(`/batches/${id}/download.zip`)}
            enabled={counts.completed > 0}
            icon="zip"
          >
            Download ZIP
          </ExportLink>
          <ExportLink
            href={apiUrl(`/batches/${id}/failures.csv`)}
            enabled={counts.failed > 0}
            icon="csv"
          >
            Export failures CSV
          </ExportLink>
        </div>
      </div>
      <FailureReasons
        failures={status.data.failures}
        selected={reason?.code ?? null}
        onSelect={setReason}
      />
      {preview && (
        <section className="rounded-card border bg-card p-5">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="font-semibold">{`Preview: ${preview.name}`}</h2>
            <button type="button" aria-label="Close preview" onClick={() => setPreview(null)}>
              <X aria-hidden="true" strokeWidth={1.5} className="size-5" />
            </button>
          </div>
          <video
            data-testid="inline-preview"
            src={preview.url}
            controls
            autoPlay
            className="w-full max-w-xl rounded-tile bg-black"
          />
        </section>
      )}
      {reason && (
        <p className="flex items-center gap-3 text-sm">
          <span className="rounded-full bg-mint px-3 py-1 font-semibold text-emerald">{`Filtering: ${reason.message}`}</span>
          <button type="button" className="underline" onClick={() => setReason(null)}>
            Clear filter
          </button>
        </p>
      )}
      <RowsTable
        key={reason?.code ?? 'all'}
        batchId={id}
        failureCode={reason?.code}
        onPreview={(url, name) => setPreview({ url, name })}
      />
    </div>
  );
}
