import type { RowStatus } from '../components/StatusChip';

/** Row counts of a batch, as returned by the API. */
export interface Counts {
  total: number;
  completed: number;
  processing: number;
  queued: number;
  failed: number;
  skipped: number;
  cancelled: number;
}

export type BatchState =
  'DRAFT' | 'READY' | 'RUNNING' | 'PAUSED' | 'COMPLETED' | 'CANCELLED' | 'FAILED' | string;

export interface Batch {
  id: string;
  template_id: string;
  status: BatchState;
  created_at: string;
  sheet_name: string | null;
  folder_name: string | null;
  counts: Counts;
  success_rate: number | null;
}

export interface BatchList {
  batches: Batch[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface FailureGroup {
  code: string;
  count: number;
  message: string;
}

export interface BatchStatus {
  counts: Counts;
  progress_percent: number;
  eta_seconds: number | null;
  failures: FailureGroup[];
}

export interface BatchRow {
  row_number: number;
  name: string;
  voter_id: string;
  status: RowStatus;
  failure_code: string | null;
  message: string | null;
  render_seconds: number | null;
  has_video: boolean;
}

export interface RowsPage {
  rows: BatchRow[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface DailyStat {
  date: string;
  videos: number;
  avg_render_seconds: number;
}
