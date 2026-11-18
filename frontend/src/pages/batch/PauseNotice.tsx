import { useProviders } from '../../api/queries';
import type { Batch } from '../../api/types';
import { formatUsd } from '../../format';

/** Says why the system paused a batch and, with a provider, how much of its cap is spent. */
export function PauseNotice({ batch }: { batch: Batch }) {
  const paused = batch.status === 'PAUSED';
  const providers = useProviders(batch.id, paused && Boolean(batch.provider_id));
  const provider = providers.data?.providers.find((p) => p.id === batch.provider_id);
  const cap = provider?.spend_cap_usd ?? null;
  if (!paused || !batch.pause_reason) return null;
  return (
    <div className="space-y-1 rounded-card border bg-card p-4 text-sm">
      <p data-testid="pause-reason" role="status" className="font-semibold text-status-skipped">
        {`Paused: ${batch.pause_reason}`}
      </p>
      {cap !== null && (
        <p data-testid="spend-summary">
          {`${formatUsd(batch.spent_usd ?? provider?.spent_usd ?? 0)} of ${formatUsd(cap)}`}
        </p>
      )}
    </div>
  );
}
