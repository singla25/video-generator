import { DatabaseZap } from 'lucide-react';
import { useEffect } from 'react';

import { setMigrationMessage, useMigrationMessage } from '../api/migrationState';
import { useSystemStatus } from '../api/queries';

const FOLLOW_UP = 'The dashboard will work again after the migration is applied.';

/** Full-width alert while the database needs a migration; says what the server said. */
export function SchemaBanner() {
  const schema = useSystemStatus().data?.schema;
  const callMessage = useMigrationMessage();
  const behind = schema?.state === 'behind' || schema?.state === 'empty';

  // A fresh app start never inherits an old failure (calls are still in flight here).
  useEffect(() => setMigrationMessage(null), []);

  // A healthy status answer means the migration was applied: forget the old call failure.
  useEffect(() => {
    if (schema && !behind) setMigrationMessage(null);
  }, [schema, behind]);

  const text = behind ? schema.message : callMessage;
  if (text === null) return null;
  return (
    <div
      data-testid="schema-banner"
      role="alert"
      className="mb-4 flex items-start gap-3 rounded-tile border border-status-failed bg-red-50 px-4 py-3 text-sm"
    >
      <DatabaseZap
        aria-hidden="true"
        strokeWidth={1.5}
        className="size-5 shrink-0 text-status-failed"
      />
      <div>
        <p className="font-semibold">{text}</p>
        <p>{FOLLOW_UP}</p>
      </div>
    </div>
  );
}
