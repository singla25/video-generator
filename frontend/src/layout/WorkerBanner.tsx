import { ServerOff } from 'lucide-react';

import { useBatchList, useSystemStatus } from '../api/queries';
import type { Batch } from '../api/types';

function hasWaitingWork(batches: Batch[]): boolean {
  return batches.some((b) => b.counts.queued > 0 || b.preview?.status === 'PENDING');
}

/** Alert on every page when the worker is down while videos or previews are waiting. */
export function WorkerBanner() {
  const status = useSystemStatus().data;
  const workerDown = status?.worker_alive === false;
  // Poll the list only while the worker is down, so recovery clears the banner promptly.
  const batches = useBatchList({ poll: workerDown }).data?.batches;
  // Loading or failing calls must never raise a false alarm.
  if (!workerDown || !batches || !hasWaitingWork(batches)) return null;
  return (
    <div
      data-testid="worker-banner"
      role="alert"
      className="mb-4 flex items-center gap-3 rounded-tile border border-status-failed bg-red-50 px-4 py-3 text-sm"
    >
      <ServerOff aria-hidden="true" strokeWidth={1.5} className="size-5 text-status-failed" />
      <span className="font-semibold">
        The background worker is not running, so videos won&apos;t be made. Start it with
        scripts/dev_up.sh
      </span>
    </div>
  );
}
