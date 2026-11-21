import { useSyncExternalStore } from 'react';

/** The API error code that means the database is behind the code. */
export const DB_NEEDS_MIGRATION = 'DB_NEEDS_MIGRATION';

let message: string | null = null;
const listeners = new Set<() => void>();

/** Remember the server's migration message (null clears it). */
export function setMigrationMessage(next: string | null): void {
  if (next === message) return;
  message = next;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** The message of the last call that failed with DB_NEEDS_MIGRATION, or null. */
export function useMigrationMessage(): string | null {
  return useSyncExternalStore(subscribe, () => message);
}
