import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';

import { ApiError, apiFetch } from '../../api/client';
import type { Batch, SheetInspection, SheetReport } from '../../api/types';
import { hasDevanagari } from '../../format';

const MAX_LISTED_PROBLEMS = 100;
const BUTTON = 'rounded-full bg-lime px-5 py-2 font-semibold disabled:opacity-50';
const GHOST = 'rounded-full border px-5 py-2 font-semibold hover:bg-mint';
const SELECT = 'w-full rounded-tile border bg-card px-3 py-2';

interface Props {
  inspection: SheetInspection | null;
  file: File | null;
  templateId: string;
  batchId: string | null;
  report: SheetReport | null;
  onValidated: (batch: Batch) => void;
  onBack: () => void;
  onNext: () => void;
}

function guess(headers: string[], pattern: RegExp, fallback: number): string {
  return headers.find((h) => pattern.test(h)) ?? headers[fallback] ?? '';
}

function Text({ value }: { value: string }) {
  return <span lang={hasDevanagari(value) ? 'hi' : undefined}>{value}</span>;
}

function ReportView({ report }: { report: SheetReport }) {
  const listed = report.problems.slice(0, MAX_LISTED_PROBLEMS);
  return (
    <div className="space-y-3">
      <p className="font-semibold">{`${report.valid_rows} of ${report.total_rows} rows are valid`}</p>
      {listed.length > 0 && (
        <ul className="divide-y rounded-tile border">
          {listed.map((p) => (
            <li
              key={`${p.row_number}-${p.code}`}
              data-invalid="true"
              className="flex gap-3 bg-red-50 px-3 py-2 text-sm"
            >
              <span className="font-semibold">{p.row_number}</span>
              <Text value={p.message} />
            </li>
          ))}
        </ul>
      )}
      {report.problems.length > listed.length && (
        <p className="text-sm text-muted">{`and ${report.problems.length - listed.length} more`}</p>
      )}
    </div>
  );
}

/** Step 2: pick the columns, validate the sheet and read the report. */
export function StepMap({
  inspection,
  file,
  templateId,
  batchId,
  report,
  onValidated,
  onBack,
  onNext,
}: Props) {
  const headers = inspection?.headers ?? [];
  const [nameColumn, setName] = useState(() => guess(headers, /name|नाम/i, 0));
  const [idColumn, setId] = useState(() => guess(headers, /\bid\b|number|क्रम/i, 1));
  const [spoken, setSpoken] = useState(() => headers.find((h) => /spoken/i.test(h)) ?? '');

  const validate = useMutation({
    mutationFn: async () => {
      if (batchId) {
        const body = JSON.stringify({
          name_column: nameColumn,
          id_column: idColumn,
          spoken_name_column: spoken || null,
        });
        return apiFetch<Batch>(`/batches/${batchId}/mapping`, { method: 'PUT', body });
      }
      const form = new FormData();
      form.append('sheet', file as File);
      form.append('name_column', nameColumn);
      form.append('id_column', idColumn);
      form.append('template_id', templateId);
      if (spoken) form.append('spoken_name_column', spoken);
      return apiFetch<Batch>('/batches', { method: 'POST', body: form });
    },
    onSuccess: onValidated,
  });

  if (!inspection) {
    return (
      <section className="space-y-4 rounded-card border bg-card p-6">
        {report && <ReportView report={report} />}
        <p className="text-sm text-muted">To change the columns, upload the sheet again.</p>
        <div className="flex justify-between">
          <button type="button" className={GHOST} onClick={onBack}>
            Back
          </button>
          <button
            type="button"
            className={BUTTON}
            disabled={!report || report.valid_rows === 0}
            onClick={onNext}
          >
            Next
          </button>
        </div>
      </section>
    );
  }

  const picker = (label: string, value: string, set: (v: string) => void, optional = false) => {
    const id = `col-${label.split(' ')[0]!.toLowerCase()}`;
    return (
      <div>
        <label htmlFor={id} className="mb-1 block text-sm font-semibold">
          {label}
        </label>
        <select id={id} value={value} onChange={(e) => set(e.target.value)} className={SELECT}>
          {optional && <option value="">None</option>}
          {headers.map((h) => (
            <option key={h} value={h}>
              {h}
            </option>
          ))}
        </select>
      </div>
    );
  };

  return (
    <section className="space-y-5 rounded-card border bg-card p-6">
      <div className="grid gap-4 md:grid-cols-3">
        {picker('Name column', nameColumn, setName)}
        {picker('ID column', idColumn, setId)}
        {picker('Spoken name column (optional)', spoken, setSpoken, true)}
      </div>
      <div className="overflow-x-auto rounded-tile border">
        <table className="w-full text-left text-sm">
          <thead className="bg-page text-muted">
            <tr>
              {headers.map((h) => (
                <th key={h} scope="col" className="px-3 py-2 font-semibold">
                  <Text value={h} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {inspection.sample_rows.map((cells, r) => (
              <tr key={r} className="border-t">
                {cells.map((cell, c) => (
                  <td key={c} className="px-3 py-2">
                    <Text value={cell} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {validate.isError && (
        <p role="alert" className="text-sm text-status-failed">
          {validate.error instanceof ApiError ? validate.error.message : 'Something went wrong.'}
        </p>
      )}
      {report && <ReportView report={report} />}
      <div className="flex justify-between">
        <button type="button" className={GHOST} onClick={onBack}>
          Back
        </button>
        <div className="flex gap-3">
          <button
            type="button"
            className={GHOST}
            disabled={validate.isPending}
            onClick={() => validate.mutate()}
          >
            Validate sheet
          </button>
          <button
            type="button"
            className={BUTTON}
            disabled={!report || report.valid_rows === 0}
            onClick={onNext}
          >
            Next
          </button>
        </div>
      </div>
    </section>
  );
}
