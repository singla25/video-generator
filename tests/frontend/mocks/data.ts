// Synthetic fixtures shaped exactly like the M1 API (backend/vidgen/api/schemas*.py).
// Every name and ID is invented; no real samples.
export type RowStatus = 'QUEUED' | 'PROCESSING' | 'COMPLETED' | 'FAILED' | 'SKIPPED' | 'CANCELLED';

export const IDS = {
  batch: '11111111-1111-4111-8111-111111111111',
  oldBatch: '22222222-2222-4222-8222-222222222222',
  template: '33333333-3333-4333-8333-333333333333',
  templateNoConsent: '44444444-4444-4444-8444-444444444444',
} as const;

export const DEVANAGARI_NAME = 'अनुराधा शर्मा';

export interface Counts {
  total: number;
  completed: number;
  processing: number;
  queued: number;
  failed: number;
  skipped: number;
  cancelled: number;
}

export const COUNTS: Counts = {
  total: 100,
  completed: 60,
  processing: 5,
  queued: 20,
  failed: 10,
  skipped: 5,
  cancelled: 0,
};

type Json = Record<string, unknown>;

export function batch(over: Json = {}): Json {
  return {
    id: IDS.batch,
    template_id: IDS.template,
    status: 'RUNNING',
    created_at: '2026-10-19T08:00:00+00:00',
    started_at: '2026-10-19T08:05:00+00:00',
    finished_at: null,
    folder_name: '2026-10-19-1',
    sheet_name: 'sheet-a.csv',
    preview: { status: 'READY', approved: true },
    counts: { ...COUNTS },
    success_rate: 0.8,
    ...over,
  };
}

export function status(over: Json = {}): Json {
  return {
    counts: { ...COUNTS },
    progress_percent: 75,
    eta_seconds: 90,
    failures: [
      { code: 'TTS_FAILED', count: 6, message: 'The voice for this name could not be created.' },
      { code: 'RENDER_TIMEOUT', count: 4, message: 'Making this video took too long.' },
    ],
    ...over,
  };
}

export function row(n: number, over: Json = {}): Json {
  return {
    row_number: n,
    name: `Test Person ${n}`,
    voter_id: `TST${String(n).padStart(6, '0')}`,
    spoken_name: null,
    status: 'COMPLETED',
    failure_code: null,
    message: null,
    render_seconds: 12.5,
    has_video: true,
    ...over,
  };
}

export const ROWS_BY_STATUS: Json[] = [
  row(1, { name: DEVANAGARI_NAME, voter_id: 'TST000001' }),
  row(2, { status: 'PROCESSING', render_seconds: null, has_video: false }),
  row(3, { status: 'QUEUED', render_seconds: null, has_video: false }),
  row(4, {
    status: 'FAILED',
    failure_code: 'TTS_FAILED',
    message: 'The voice for this name could not be created.',
    has_video: false,
  }),
  row(5, {
    status: 'SKIPPED',
    failure_code: 'INVALID_ROW_EMPTY_ID',
    message: 'The ID is empty.',
    has_video: false,
  }),
];

export function rowsPage(rows: Json[], page = 1, pageSize = 50, total = rows.length): Json {
  return {
    rows,
    page,
    page_size: pageSize,
    total,
    total_pages: Math.max(1, Math.ceil(total / pageSize)),
  };
}

/** One page of GET /batches. `total` mirrors the batches given; pages are the caller's choice. */
export function batchesPage(batches: Json[], page = 1, totalPages = 1): Json {
  return { batches, page, page_size: 50, total: batches.length, total_pages: totalPages };
}

export function template(over: Json = {}): Json {
  return {
    id: IDS.template,
    original_name: 'Rahul',
    duration_s: 20,
    width: 1280,
    height: 720,
    slot: { start_s: 4.2, end_s: 5.1 },
    slot_source: 'STT',
    slot_confidence: 0.93,
    slot_confirmed: true,
    slot_error: null,
    needs_manual_slot: false,
    consent_confirmed: true,
    usable: true,
    created_at: '2026-10-18T10:00:00+00:00',
    ...over,
  };
}

export const TEMPLATE_NO_CONSENT: Json = template({
  id: IDS.templateNoConsent,
  original_name: 'Priya',
  consent_confirmed: false,
  usable: false,
});

export function daily(): Json {
  return {
    days: [
      { date: '2026-10-13', videos: 120, avg_render_seconds: 11.2 },
      { date: '2026-10-14', videos: 340, avg_render_seconds: 10.8 },
      { date: '2026-10-15', videos: 0, avg_render_seconds: 0 },
      { date: '2026-10-16', videos: 410, avg_render_seconds: 12.1 },
    ],
  };
}

export function auditEntry(action: string, at = '2026-10-19T09:00:00+00:00'): Json {
  return { at, actor: 'system', action, details: {} };
}

export function report(over: Json = {}): Json {
  return {
    total_rows: 10,
    valid_rows: 8,
    skipped_rows: 2,
    problems: [
      { row_number: 3, code: 'INVALID_ROW_EMPTY_NAME', message: 'The name is empty.', faults: [] },
      {
        row_number: 7,
        code: 'DUPLICATE_ID',
        message: 'This ID was already used in row 2.',
        faults: [],
      },
    ],
    ...over,
  };
}
