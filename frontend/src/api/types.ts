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

export type PreviewState = 'NONE' | 'PENDING' | 'READY' | 'STALE' | 'FAILED' | string;

export interface Problem {
  row_number: number;
  code: string;
  message: string;
}

export interface SheetReport {
  total_rows: number;
  valid_rows: number;
  skipped_rows: number;
  problems: Problem[];
}

export interface Template {
  id: string;
  original_name: string;
  duration_s: number;
  slot: { start_s: number; end_s: number } | null;
  needs_manual_slot: boolean;
  slot_confirmed: boolean;
  consent_confirmed: boolean;
  usable: boolean;
}

export interface SheetInspection {
  sheet_name: string;
  headers: string[];
  sample_rows: string[][];
  row_count: number;
}

export interface Batch {
  id: string;
  template_id: string;
  status: BatchState;
  created_at: string;
  sheet_name: string | null;
  folder_name: string | null;
  counts: Counts;
  success_rate: number | null;
  preview?: { status: PreviewState; approved: boolean };
  report?: SheetReport | null;
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
