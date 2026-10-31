import { useId, useState } from 'react';
import { Link } from 'react-router-dom';

import { ApiError } from '../api/client';
import { useDeleteDraft } from '../api/queries';
import type { Batch } from '../api/types';
import { formatDate, formatNumber } from '../format';
import { DeleteDraftDialog } from './DeleteDraftDialog';

const HEADERS = ['Batch', 'Template', 'Rows', 'Created', 'Actions'];
const LINK = 'rounded-full bg-lime px-4 py-1.5 text-sm font-semibold';
const BUTTON =
  'rounded-full border px-4 py-1.5 text-sm font-semibold text-status-failed hover:bg-mint disabled:opacity-50';

interface RowProps {
  draft: Batch;
  templateName: string;
}

/** One draft: its sheet, template, rows and creation date, with Continue setup and Delete draft. */
function DraftRow({ draft, templateName }: RowProps) {
  const remove = useDeleteDraft(draft.id);
  const [asking, setAsking] = useState(false);
  const failure = remove.error instanceof ApiError ? remove.error.message : 'Something went wrong.';

  return (
    <tr className="border-t">
      <td className="px-3 py-2">{draft.sheet_name || draft.folder_name || 'Batch'}</td>
      <td className="px-3 py-2">{templateName}</td>
      <td className="px-3 py-2">{formatNumber(draft.counts.total)} rows</td>
      <td className="px-3 py-2">{formatDate(draft.created_at)}</td>
      <td className="px-3 py-2">
        <div className="flex flex-wrap items-center gap-2">
          <Link to={`/batches/new?batch=${draft.id}`} className={LINK}>
            Continue setup
          </Link>
          <button
            type="button"
            className={BUTTON}
            disabled={remove.isPending}
            onClick={() => setAsking(true)}
          >
            Delete draft
          </button>
        </div>
        {remove.isError && (
          <p role="alert" className="mt-2 text-sm text-status-failed">
            {failure}
          </p>
        )}
        {asking && (
          <DeleteDraftDialog
            onConfirm={() => {
              setAsking(false);
              remove.run();
            }}
            onCancel={() => setAsking(false)}
          />
        )}
      </td>
    </tr>
  );
}

interface Props {
  drafts: Batch[];
  templateNames: Map<string, string>;
}

/**
 * Batches created but never started, listed under the running batches (DD-38). Each row can be
 * continued in the wizard or deleted.
 */
export function DraftsSection({ drafts, templateNames }: Props) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="rounded-card border bg-card p-5">
      <h2 id={headingId} className="mb-2 font-semibold">
        Not started
      </h2>
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
            {drafts.map((draft) => (
              <DraftRow
                key={draft.id}
                draft={draft}
                templateName={templateNames.get(draft.template_id) ?? '-'}
              />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
