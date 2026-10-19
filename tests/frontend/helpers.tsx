// Shared render helpers. Contract: <App /> needs a Router and a QueryClientProvider above it.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter } from 'react-router-dom';

import { App } from '../../frontend/src/App';

export const CSRF = 'csrf-cookie-value';

export function setCsrfCookie(value: string = CSRF): void {
  document.cookie = `vidgen_csrf=${value}; path=/`;
}

export function newClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

export function renderWithProviders(ui: ReactElement, path = '/') {
  return render(
    <QueryClientProvider client={newClient()}>
      <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Render the whole application at `path` as a logged-in operator (CSRF cookie present). */
export function renderApp(path = '/') {
  setCsrfCookie();
  return renderWithProviders(<App />, path);
}

/** Wrap fetch and remember every requested URL, for the privacy checks. */
export function spyOnFetch(): { urls: () => string[] } {
  const original = globalThis.fetch;
  const seen: string[] = [];
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
    seen.push(input instanceof Request ? input.url : String(input));
    return original(input, init);
  }) as typeof fetch;
  return { urls: () => seen };
}
