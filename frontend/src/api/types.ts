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
  /** The primary name slot, or null when none was found or set. */
  slot: { start_s: number; end_s: number } | null;
  /** Extra name slots (DD-40), as [start, end] pairs in the order the user set them. */
  extra_slots: [number, number][];
  /** Every slot, primary and extra, sorted by start. Empty without a primary slot (DD-40). */
  slots: [number, number][];
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

/** Step of a pending preview; null or missing while it is still queued. */
export type PreviewStage = 'preparing' | 'voice' | 'lipsync' | 'finishing';

/** Preview state; the spoken-name fields exist in local AI mode only. */
export interface Preview {
  status: PreviewState;
  approved: boolean;
  stage?: PreviewStage | null;
  suggested_spoken_name?: string | null;
  spoken_name?: string | null;
  spoken_name_confirmed?: boolean;
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
  preview?: Preview;
  report?: SheetReport | null;
}

export interface BatchList {
  batches: Batch[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

/** The dashboard batch lists: running, completed and failed (DD-37). */
export type BatchView = 'running' | 'completed' | 'failed';

/** Body of POST /batches/<id>/start. `limit` is sent only when fewer videos than rows are wanted. */
export interface StartBody {
  folder_name: string;
  limit?: number;
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
  /** Whole-batch counts from the same snapshot as `rows` (W-4b); absent from older servers. */
  counts?: Counts;
  progress_percent?: number;
}

/** Counts and progress taken from one server snapshot. */
export interface Snapshot {
  counts: Counts;
  progress_percent: number;
}

export interface DailyStat {
  date: string;
  videos: number;
  avg_render_seconds: number;
}

export interface SystemStatus {
  worker_alive: boolean;
  queue_depth: number | null;
  redis_ok: boolean;
  /** Absent from older servers. */
  ai_mode?: 'fake' | 'local';
}
