import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { ApiError } from '../../api/client';
import { useDeleteDraft } from '../../api/queries';
import { DeleteDraftDialog } from '../../components/DeleteDraftDialog';
import { EmptyState } from '../../components/states';

const MESSAGE = 'This draft has no sheet data yet. Delete it and upload the sheet again.';
const BUTTON =
  'rounded-full border px-4 py-1.5 text-sm font-semibold text-status-failed hover:bg-mint disabled:opacity-50';

/** A draft whose sheet has no valid rows: the wizard cannot continue, so the user may delete it. */
export function NoSheetDraft({ batchId }: { batchId: string }) {
  const navigate = useNavigate();
  const remove = useDeleteDraft(batchId);
  const [asking, setAsking] = useState(false);
  const failure = remove.error instanceof ApiError ? remove.error.message : 'Something went wrong.';

  return (
    <EmptyState title={MESSAGE}>
      <button
        type="button"
        className={BUTTON}
        disabled={remove.isPending}
        onClick={() => setAsking(true)}
      >
        Delete draft
      </button>
      {remove.isError && (
        <p role="alert" className="mt-3 text-sm text-status-failed">
          {failure}
        </p>
      )}
      {asking && (
        <DeleteDraftDialog
          onConfirm={() => {
            setAsking(false);
            remove.run(() => navigate('/'));
          }}
          onCancel={() => setAsking(false)}
        />
      )}
    </EmptyState>
  );
}
