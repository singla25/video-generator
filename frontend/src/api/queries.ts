import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { POLL_INTERVAL_MS } from '../config';
import { apiFetch } from './client';
import type { BatchList, BatchStatus, DailyStat } from './types';

const LIST_PAGE_SIZE = 50;

/** Newest batches, for picking the current one. */
export function useBatchList() {
  return useQuery({
    queryKey: ['batches', 'list'],
    queryFn: () => apiFetch<BatchList>(`/batches?page=1&page_size=${LIST_PAGE_SIZE}`),
  });
}

/** Live counts, progress and ETA of one batch; polled every POLL_INTERVAL_MS. */
export function useBatchStatus(batchId: string | undefined) {
  return useQuery({
    queryKey: ['batch-status', batchId],
    queryFn: () => apiFetch<BatchStatus>(`/batches/${batchId}/status`),
    enabled: Boolean(batchId),
    refetchInterval: POLL_INTERVAL_MS,
  });
}

/** Videos generated per day for the last `days` days. */
export function useDailyStats(days: number) {
  return useQuery({
    queryKey: ['stats', 'daily', days],
    queryFn: () => apiFetch<{ days: DailyStat[] }>(`/stats/daily?days=${days}`),
  });
}

export type BatchAction = 'pause' | 'resume' | 'retry-failed';

/** Pause, resume or retry-failed on a batch; refreshes the dashboard data afterwards. */
export function useBatchAction(batchId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (action: BatchAction) =>
      apiFetch(`/batches/${batchId}/${action}`, { method: 'POST' }),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ['batches'] }),
        client.invalidateQueries({ queryKey: ['batch-status'] }),
        client.invalidateQueries({ queryKey: ['rows'] }),
      ]);
    },
  });
}
