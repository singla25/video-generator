// Global test setup: jest-dom, MSW lifecycle, matchMedia stub, clean storage.
import './support/node-fetch-types';
import './support/xhr-formdata';
import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, beforeEach, vi } from 'vitest';

import { server } from './mocks/server';
import { installMatchMedia, resetMotion } from './motion';

installMatchMedia();

beforeAll(() => server.listen({ onUnhandledFrame: 'error' }));
beforeEach(() => {
  resetMotion();
  window.localStorage.clear();
  window.sessionStorage.clear();
  document.cookie = 'vidgen_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
});
afterEach(() => {
  cleanup();
  server.resetHandlers();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
afterAll(() => server.close());
