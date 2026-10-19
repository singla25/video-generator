import { useQuery } from '@tanstack/react-query';
import { ShieldAlert } from 'lucide-react';
import { Link } from 'react-router-dom';

import { apiFetch } from '../api/client';

const THROTTLE_PATH = '/audit?action=SECURITY_LOGIN_THROTTLED';

/** Alert shown on every page when the audit log holds a throttled-login event. */
export function SecurityBanner() {
  const { data } = useQuery({
    queryKey: ['audit', 'throttled'],
    queryFn: () => apiFetch<{ entries: unknown[] }>(THROTTLE_PATH),
  });
  // A failed audit call must never break the page: show nothing.
  if (!data || data.entries.length === 0) return null;
  return (
    <div
      data-testid="security-banner"
      role="alert"
      className="mb-4 flex items-center gap-3 rounded-tile border border-status-failed bg-red-50 px-4 py-3 text-sm"
    >
      <ShieldAlert aria-hidden="true" strokeWidth={1.5} className="size-5 text-status-failed" />
      <span className="font-semibold">Repeated failed logins were blocked</span>
      <Link to="/security" className="ml-auto font-semibold underline">
        Review in Security
      </Link>
    </div>
  );
}
