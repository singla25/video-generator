import { ApiError } from '../../api/client';
import type { Batch, SheetReport } from '../../api/types';

/** What /batches/new?batch=<id> shows for a batch: the wizard at step 3, or a message. */
export type Resume =
  { kind: 'cannot' } | { kind: 'no-sheet' } | { kind: 'wizard'; report: SheetReport };

/**
 * A DRAFT with sheet data reopens the wizard at step 3 (slot and preview), also when the preview is
 * already approved: the user clicks Next to reach step 4. A batch that is not a draft cannot be
 * continued, and a draft without valid rows has nothing to continue (DD-38).
 */
export function resumeOf(batch: Batch): Resume {
  if (batch.status !== 'DRAFT') return { kind: 'cannot' };
  const report = batch.report ?? null;
  if (!report || report.valid_rows < 1) return { kind: 'no-sheet' };
  return { kind: 'wizard', report };
}

/** True for a 4xx API answer: the batch is missing or cannot be read, so a retry will not help. */
export function isClientError(error: unknown): error is ApiError {
  return error instanceof ApiError && error.status >= 400 && error.status < 500;
}
