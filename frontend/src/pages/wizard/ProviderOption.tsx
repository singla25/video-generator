import { useId } from 'react';

import type { RenderProvider } from '../../api/types';
import { formatDuration, formatUsd } from '../../format';

const KIND_LABELS: Record<string, string> = {
  local: 'Local',
  remote_function: 'Remote function',
  remote_worker: 'Remote worker',
};

interface Props {
  provider: RenderProvider;
  name: string;
  selected: boolean;
  onSelect: () => void;
}

/** Why a provider cannot be picked, or null when it can. */
function unavailableReason(provider: RenderProvider): string | null {
  if (provider.setup.state !== 'ready') return provider.setup.reason ?? 'Not ready.';
  if (!provider.selectable) return provider.refusal?.reason ?? 'Not available.';
  return null;
}

/** One radio option: provider name, kind, estimated time and cost, remaining credit. */
export function ProviderOption({ provider, name, selected, onSelect }: Props) {
  const nameId = useId();
  const reasonId = useId();
  const reason = unavailableReason(provider);
  const usable = reason === null && provider.selectable;
  const { estimate } = provider;
  return (
    <div
      data-provider={provider.id}
      data-selectable={usable ? 'true' : 'false'}
      className={`flex items-start gap-3 rounded-tile border p-3 ${usable ? '' : 'bg-page text-muted opacity-70'}`}
    >
      <input
        type="radio"
        name={name}
        value={provider.id}
        checked={selected}
        disabled={!usable}
        aria-labelledby={nameId}
        aria-describedby={reason ? reasonId : undefined}
        onChange={onSelect}
        className="mt-1"
      />
      <div className="space-y-1 text-sm">
        <p id={nameId} className="font-semibold">
          {provider.name}
        </p>
        <p>{KIND_LABELS[provider.kind] ?? provider.kind}</p>
        {estimate ? (
          <p>{`${formatDuration(estimate.batch_seconds)} - ${formatUsd(estimate.batch_cost_usd)}`}</p>
        ) : (
          <p>{provider.estimate_label ?? 'not measured yet'}</p>
        )}
        <p>
          {provider.remaining_usd === null ? 'No cap' : `${formatUsd(provider.remaining_usd)} left`}
        </p>
        {reason && (
          <p id={reasonId} className="font-semibold text-status-skipped">
            {reason}
          </p>
        )}
      </div>
    </div>
  );
}
