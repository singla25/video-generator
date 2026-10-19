/** Local input rules for the wizard. The backend validates again. */

const SHEET_EXTENSIONS = ['.csv', '.xlsx'];
/** Generous upper bound; the API enforces its own limit. */
export const MAX_SHEET_BYTES = 25 * 1024 * 1024;
const FORBIDDEN_FOLDER = /[\\/:*?"<>|\u0000-\u001f]/;

/** Returns a plain-language problem with the chosen sheet, or null when it is acceptable. */
export function sheetProblem(file: File): string | null {
  const name = file.name.toLowerCase();
  if (!SHEET_EXTENSIONS.some((ext) => name.endsWith(ext))) return 'Use a CSV or Excel sheet.';
  if (file.size === 0) return 'The sheet is empty.';
  if (file.size > MAX_SHEET_BYTES) return 'The sheet is too large.';
  return null;
}

/** Returns a plain-language problem with the output folder name, or null. */
export function folderProblem(name: string): string | null {
  const value = name.trim();
  if (!value) return 'Enter a folder name.';
  if (FORBIDDEN_FOLDER.test(value) || value.includes('..') || value.startsWith('.')) {
    return 'Folder name can’t contain \\ / : * ? " < > | or "..".';
  }
  return null;
}

/** Default output folder: today's local date plus a running number, e.g. 2026-10-19-1. */
export function defaultFolder(existing: (string | null)[], now: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  const day = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  const used = existing.filter((f) => f?.startsWith(`${day}-`)).length;
  return `${day}-${used + 1}`;
}

/** A fresh key so a double submit cannot start the batch twice. */
export function newIdempotencyKey(): string {
  return (
    globalThis.crypto?.randomUUID?.() ?? `key-${Date.now()}-${Math.random().toString(36).slice(2)}`
  );
}
