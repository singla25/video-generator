import type { StartBody } from '../../api/types';

/** Fixed choices of "Videos to generate"; each is offered only when the batch has that many rows. */
export const FIXED_COUNTS = [5, 10, 15] as const;

export type FixedCount = (typeof FIXED_COUNTS)[number];

/** All rows, a fixed count, or a number the user types. */
export type VideoChoice = 'all' | 'custom' | FixedCount;

/** The typed number when it is a whole number from 1 to `rows`; otherwise null. */
export function parseCustomCount(text: string, rows: number): number | null {
  const value = text.trim();
  if (!/^\d+$/.test(value)) return null;
  const count = Number(value);
  return count >= 1 && count <= rows ? count : null;
}

/** How many videos the choice asks for, or null while a typed number is not usable. */
export function videoCount(choice: VideoChoice, custom: string, rows: number): number | null {
  if (choice === 'all') return rows;
  if (choice === 'custom') return parseCustomCount(custom, rows);
  return choice;
}

/** Plain-language problem with the typed number, or null when it is usable. */
export function customProblem(text: string, rows: number): string | null {
  return parseCustomCount(text, rows) === null ? `Enter a number from 1 to ${rows}` : null;
}

/** The sentence under the choices: what will be generated and what is skipped. */
export function countSummary(count: number, rows: number): string {
  return count >= rows
    ? `You will get ${rows} videos.`
    : `You will get ${count} videos. The other ${rows - count} rows are skipped.`;
}

/** Start request body. `limit` is left out when every row is wanted, so the API renders them all. */
export function startBody(folderName: string, count: number, rows: number): StartBody {
  return count < rows ? { folder_name: folderName, limit: count } : { folder_name: folderName };
}
