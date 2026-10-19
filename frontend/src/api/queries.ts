import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef } from 'react';

import { POLL_INTERVAL_MS } from '../config';
import { apiFetch } from './client';
import type { Batch, BatchList, BatchStatus, DailyStat, Template } from './types';

/** One batch; polled while its preview is being generated. */
export function useBatch(batchId: string | undefined) {
  return useQuery({
    queryKey: ['batches', 'detail', batchId],
    queryFn: () => apiFetch<Batch>(`/batches/${batchId}`),
    enabled: Boolean(batchId),
    refetchInterval: (query) =>
      query.state.data?.preview?.status === 'PENDING' ? POLL_INTERVAL_MS : false,
  });
}

/** All templates. */
export function useTemplates() {
  return useQuery({
    queryKey: ['templates', 'list'],
    queryFn: () => apiFetch<{ templates: Template[] }>('/templates'),
  });
}

/** One template (slot, duration, consent). */
export function useTemplate(templateId: string | undefined) {
  return useQuery({
    queryKey: ['templates', 'detail', templateId],
    queryFn: () => apiFetch<Template>(`/templates/${templateId}`),
    enabled: Boolean(templateId),
  });
}

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

export type BatchAction = 'pause' | 'resume' | 'retry-failed' | 'cancel';

/**
 * Pause, resume, retry-failed or cancel a batch; refreshes the dashboard data afterwards.
 * `run` ignores calls while a request is in flight, so a double click sends one request.
 */
export function useBatchAction(batchId: string) {
  const client = useQueryClient();
  const busy = useRef(false);
  const mutation = useMutation({
    mutationFn: (action: BatchAction) =>
      apiFetch(`/batches/${batchId}/${action}`, { method: 'POST' }),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ['batches'] }),
        client.invalidateQueries({ queryKey: ['batch-status'] }),
        client.invalidateQueries({ queryKey: ['rows'] }),
      ]);
    },
    onSettled: () => {
      busy.current = false;
    },
  });
  const run = (action: BatchAction) => {
    if (busy.current) return;
    busy.current = true;
    mutation.mutate(action);
  };
  return { run, isPending: mutation.isPending, isError: mutation.isError, error: mutation.error };
}
