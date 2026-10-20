import { useMutation } from '@tanstack/react-query';
import { UploadCloud } from 'lucide-react';
import { useState, type DragEvent } from 'react';
import { Link } from 'react-router-dom';

import { ApiError, apiFetch } from '../../api/client';
import { useTemplates } from '../../api/queries';
import type { SheetInspection } from '../../api/types';
import { ErrorState, Skeleton } from '../../components/states';
import { hasDevanagari } from '../../format';
import { sheetProblem } from './rules';

interface Props {
  file: File | null;
  templateId: string;
  onChange: (file: File | null, templateId: string) => void;
  onInspected: (inspection: SheetInspection) => void;
}

const BUTTON = 'rounded-full bg-lime px-5 py-2 font-semibold disabled:opacity-50';

/** Step 1: choose a template and a sheet (click or drag and drop). */
export function StepUpload({ file, templateId, onChange, onInspected }: Props) {
  const templates = useTemplates();
  const [problem, setProblem] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const inspect = useMutation({
    mutationFn: (sheet: File) => {
      const form = new FormData();
      form.append('sheet', sheet);
      return apiFetch<SheetInspection>('/batches/inspect-sheet', { method: 'POST', body: form });
    },
    onSuccess: onInspected,
  });

  function choose(candidate: File | undefined) {
    if (!candidate) return;
    const issue = sheetProblem(candidate);
    setProblem(issue);
    onChange(issue ? null : candidate, templateId);
  }

  function drop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    choose(event.dataTransfer.files[0]);
  }

  if (templates.isError) {
    return <ErrorState title="Could not load templates" onRetry={() => void templates.refetch()} />;
  }

  return (
    <section className="space-y-5 rounded-card border bg-card p-6">
      <div>
        <div className="mb-1 flex items-center justify-between">
          <label htmlFor="template" className="text-sm font-semibold">
            Template
          </label>
          <Link to="/templates" className="text-sm font-semibold text-emerald underline">
            + New template
          </Link>
        </div>
        {templates.isPending ? (
          <Skeleton className="h-10" />
        ) : (
          <select
            id="template"
            value={templateId}
            onChange={(e) => onChange(file, e.target.value)}
            className="w-full rounded-tile border bg-card px-3 py-2"
          >
            <option value="">Choose a template</option>
            {templates.data.templates.map((t) => (
              <option key={t.id} value={t.id} disabled={!t.usable}>
                {t.usable ? t.original_name : `${t.original_name} (consent missing)`}
              </option>
            ))}
          </select>
        )}
      </div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={drop}
        className={`relative grid place-items-center gap-2 rounded-card border-2 border-dashed p-10 text-center focus-within:ring-2 focus-within:ring-emerald ${dragging ? 'bg-mint' : ''}`}
      >
        <UploadCloud aria-hidden="true" strokeWidth={1.5} className="size-8 text-emerald" />
        <p className="font-semibold">Drag a sheet here or choose a file</p>
        <p className="text-sm text-muted">CSV or Excel (.csv, .xlsx)</p>
        <input
          type="file"
          aria-label="Sheet file"
          accept=".csv,.xlsx"
          onChange={(e) => choose(e.target.files?.[0])}
          className="absolute inset-0 cursor-pointer opacity-0"
        />
        {file && (
          <p
            className="text-sm font-semibold text-emerald"
            lang={hasDevanagari(file.name) ? 'hi' : undefined}
          >
            {file.name}
          </p>
        )}
      </div>
      {problem && (
        <p role="alert" className="text-sm text-status-failed">
          {problem}
        </p>
      )}
      {inspect.isError && (
        <p role="alert" className="text-sm text-status-failed">
          {inspect.error instanceof ApiError ? inspect.error.message : 'Something went wrong.'}
        </p>
      )}
      <div className="flex justify-end">
        <button
          type="button"
          className={BUTTON}
          disabled={!file || !templateId || inspect.isPending}
          onClick={() => file && inspect.mutate(file)}
        >
          Next
        </button>
      </div>
    </section>
  );
}
