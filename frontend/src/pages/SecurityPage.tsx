import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { apiFetch } from '../api/client';
import { EmptyState, ErrorState, Skeleton } from '../components/states';

interface AuditEntry {
  at: string;
  actor: string;
  action: string;
}

/** "LOGIN_FAILED" becomes "Login failed". */
function eventLabel(action: string): string {
  const words = action.toLowerCase().replaceAll('_', ' ');
  return words[0]!.toUpperCase() + words.slice(1);
}

/** Audit log with an event filter. */
export function SecurityPage() {
  const [action, setAction] = useState('');
  const [known, setKnown] = useState<string[]>([]);
  const query = useQuery({
    queryKey: ['audit', action],
    queryFn: async () => {
      const result = await apiFetch<{ entries: AuditEntry[] }>(
        action ? `/audit?action=${encodeURIComponent(action)}` : '/audit',
      );
      // Keep every event type seen so far, so the filter list does not shrink when filtering.
      setKnown((previous) =>
        [...new Set([...previous, ...result.entries.map((e) => e.action)])].sort(),
      );
      return result;
    },
  });

  // First load: no filter yet, because its choices come from the first answer.
  if (query.isPending && action === '') return <Skeleton className="h-48" />;

  return (
    <section className="rounded-card border bg-card p-5">
      <div className="mb-4 flex items-center gap-3">
        <label htmlFor="event" className="text-sm font-semibold">
          Event
        </label>
        <select
          id="event"
          value={action}
          onChange={(e) => setAction(e.target.value)}
          className="rounded-full border bg-card px-3 py-1.5 text-sm"
        >
          <option value="">All</option>
          {known.map((code) => (
            <option key={code} value={code}>
              {code}
            </option>
          ))}
        </select>
      </div>
      {query.isPending ? (
        <Skeleton className="h-48" />
      ) : query.isError ? (
        <ErrorState title="Could not load the security log" onRetry={() => void query.refetch()} />
      ) : query.data.entries.length === 0 ? (
        <EmptyState title="No security events" />
      ) : (
        <table className="w-full text-left text-sm">
          <thead className="text-muted">
            <tr>
              {['Time', 'Actor', 'Event'].map((h) => (
                <th key={h} scope="col" className="px-3 py-2 font-semibold">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {query.data.entries.map((entry, i) => (
              <tr key={`${entry.at}-${i}`} data-action={entry.action} className="border-t">
                <td className="px-3 py-2">{new Date(entry.at).toLocaleString('en-GB')}</td>
                <td className="px-3 py-2">{entry.actor}</td>
                <td className="px-3 py-2" title={eventLabel(entry.action)}>
                  {entry.action}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
