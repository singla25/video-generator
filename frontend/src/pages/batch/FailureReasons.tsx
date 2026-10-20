import type { FailureGroup } from '../../api/types';
import { formatNumber } from '../../format';

interface Props {
  failures: FailureGroup[];
  selected: string | null;
  onSelect: (group: FailureGroup | null) => void;
}

/** Why rows failed, as bars; clicking one filters the rows table on the server. */
export function FailureReasons({ failures, selected, onSelect }: Props) {
  if (failures.length === 0) {
    return (
      <section className="rounded-card border bg-card p-5">
        <h2 className="font-semibold">Failure reasons</h2>
        <p className="mt-2 text-muted">No failures</p>
      </section>
    );
  }
  const max = Math.max(...failures.map((f) => f.count), 1);
  return (
    <section className="rounded-card border bg-card p-5">
      <h2 className="font-semibold">Failure reasons</h2>
      <ul aria-label="Failure reasons" className="mt-3 space-y-2">
        {failures.map((group) => (
          <li key={group.code}>
            <button
              type="button"
              aria-label={`${group.message} (${group.count})`}
              aria-pressed={selected === group.code}
              onClick={() => onSelect(group)}
              className={`w-full rounded-tile border p-3 text-left hover:bg-mint ${selected === group.code ? 'bg-mint' : ''}`}
            >
              <span className="flex justify-between gap-3 text-sm">
                <span>{group.message}</span>
                <span className="font-semibold">{formatNumber(group.count)}</span>
              </span>
              <span aria-hidden="true" className="mt-2 block h-2 rounded-full bg-page">
                <span
                  className="block h-2 rounded-full bg-status-failed"
                  style={{ width: `${(group.count / max) * 100}%` }}
                />
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
