import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useId, useState } from 'react';

import { ApiError, apiFetch } from '../../api/client';
import { useProviders } from '../../api/queries';
import { ErrorState, Skeleton } from '../../components/states';
import { ProviderOption } from './ProviderOption';

interface Props {
  batchId: string;
  onClose: () => void;
}

const BUTTON = 'rounded-full border px-5 py-2 font-semibold hover:bg-mint';

/** Modal that asks where to render and approves the preview with the chosen provider. */
export function ProviderChooser({ batchId, onClose }: Props) {
  const client = useQueryClient();
  const titleId = useId();
  const groupName = useId();
  const providers = useProviders(batchId);
  const [chosen, setChosen] = useState<string | null>(null);

  const approve = useMutation({
    mutationFn: (providerId: string) =>
      apiFetch(`/batches/${batchId}/preview/approve`, {
        method: 'POST',
        body: JSON.stringify({ provider_id: providerId }),
      }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ['batches'] });
      onClose();
    },
    // The list may have changed (credit used, worker stopped), so read it again.
    onError: () => void client.invalidateQueries({ queryKey: ['batches', 'providers', batchId] }),
  });

  const data = providers.data;
  // Providers refused only by the data class are not offered at all.
  const listed = (data?.providers ?? []).filter((p) => p.refusal?.code !== 'data_class');
  const picked = listed.find((p) => p.id === chosen);
  const canApprove = Boolean(picked?.selectable) && !approve.isPending;

  return (
    <div className="fixed inset-0 z-20 grid place-items-center bg-black/30 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={(e) => e.key === 'Escape' && onClose()}
        className="w-full max-w-lg space-y-4 rounded-card bg-card p-6"
      >
        <h2 id={titleId} className="text-lg font-bold">
          Choose where to render
        </h2>
        {providers.isPending && <Skeleton className="h-24" />}
        {providers.isError && (
          <ErrorState title="Could not load providers" onRetry={() => void providers.refetch()} />
        )}
        {data && (
          <div role="radiogroup" aria-label="Render provider" className="space-y-2">
            {listed.map((p) => (
              <ProviderOption
                key={p.id}
                provider={p}
                name={groupName}
                selected={chosen === p.id}
                onSelect={() => setChosen(p.id)}
              />
            ))}
          </div>
        )}
        {data && !data.any_selectable && data.message && (
          <p className="text-sm font-semibold text-status-skipped">{data.message}</p>
        )}
        {approve.error && (
          <p role="alert" className="text-sm font-semibold text-status-failed">
            {approve.error instanceof ApiError ? approve.error.message : 'Something went wrong.'}
          </p>
        )}
        <div className="flex justify-end gap-3">
          <button type="button" autoFocus onClick={onClose} className={BUTTON}>
            Cancel
          </button>
          <button
            type="button"
            disabled={!canApprove}
            onClick={() => picked && approve.mutate(picked.id)}
            className="rounded-full bg-lime px-5 py-2 font-semibold disabled:opacity-50"
          >
            Approve with this provider
          </button>
        </div>
      </div>
    </div>
  );
}
