import { ApiError } from '../../api/client';
import type { Batch, SheetReport } from '../../api/types';

/** What /batches/new?batch=<id> shows for a batch: the wizard at step 3, or a message. */
export type Resume =
  { kind: 'cannot' } | { kind: 'no-sheet' } | { kind: 'wizard'; report: SheetReport };

/**
 * Valid rows of a draft. Only the create and mapping responses carry a report; the plain GET sends
 * the row counts, so without a report the valid rows are the rows that are not skipped (DD-38).
 */
export function validRowsOf(batch: Batch): number {
  if (batch.report) return batch.report.valid_rows;
  return batch.counts.total - batch.counts.skipped;
}

/**
 * The report the wizard gets when the API sent none: built from the row counts, with no problems
 * listed (the step 4 count then matches the same valid rows).
 */
function reportFromCounts(batch: Batch, validRows: number): SheetReport {
  return {
    total_rows: batch.counts.total,
    valid_rows: validRows,
    skipped_rows: batch.counts.skipped,
    problems: [],
  };
}

/**
 * A DRAFT with valid rows reopens the wizard at step 3 (slot and preview), also when the preview is
 * already approved: the user clicks Next to reach step 4. A batch that is not a draft cannot be
 * continued, and a draft with fewer than one valid row has nothing to continue (DD-38).
 */
export function resumeOf(batch: Batch): Resume {
  if (batch.status !== 'DRAFT') return { kind: 'cannot' };
  const valid = validRowsOf(batch);
  if (valid < 1) return { kind: 'no-sheet' };
  return { kind: 'wizard', report: batch.report ?? reportFromCounts(batch, valid) };
}

/** True for a 4xx API answer: the batch is missing or cannot be read, so a retry will not help. */
export function isClientError(error: unknown): error is ApiError {
  return error instanceof ApiError && error.status >= 400 && error.status < 500;
}
