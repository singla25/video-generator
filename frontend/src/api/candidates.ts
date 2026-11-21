import { type QueryClient, useQuery } from '@tanstack/react-query';

import type { NameCandidate } from './types';

const ROOT = 'name-candidates';
const NONE: NameCandidate[] = [];

/** Keep the closest-match words of one template in the query cache (memory only, never saved). */
export function setCandidates(client: QueryClient, id: string, list: NameCandidate[]): void {
  client.setQueryData([ROOT, id], list);
}

/** Forget the candidates of one template. */
export function clearCandidates(client: QueryClient, id: string): void {
  client.removeQueries({ queryKey: [ROOT, id] });
}

/** Forget every template's candidates, for when the user leaves the templates page. */
export function clearAllCandidates(client: QueryClient): void {
  client.removeQueries({ queryKey: [ROOT] });
}

/** The kept candidates of a template; empty when there are none. Never fetches. */
export function useCandidates(id: string): NameCandidate[] {
  const query = useQuery<NameCandidate[]>({
    queryKey: [ROOT, id],
    queryFn: () => NONE,
    enabled: false,
  });
  return query.data ?? NONE;
}
