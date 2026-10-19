import { CSRF_COOKIE } from '../config';

/** An error returned by the API (or a network failure) in a uniform shape. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryAfterSeconds?: number;

  constructor(status: number, code: string, message: string, retryAfterSeconds?: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

const SAFE_METHODS = new Set(['GET', 'HEAD']);
const LOGIN_API_PATH = '/auth/login';

type UnauthorizedHandler = () => void;
let onUnauthorized: UnauthorizedHandler | null = null;

/** Register what happens on any 401 (the app sends the user to the login screen). */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  onUnauthorized = handler;
}

function readCookie(name: string): string | null {
  for (const part of document.cookie.split(';')) {
    const [key, ...rest] = part.trim().split('=');
    if (key === name) return decodeURIComponent(rest.join('='));
  }
  return null;
}

async function toApiError(response: Response): Promise<ApiError> {
  const retryHeader = response.headers.get('Retry-After');
  const retry = retryHeader !== null && /^\d+$/.test(retryHeader) ? Number(retryHeader) : undefined;
  try {
    const body: unknown = await response.json();
    if (body && typeof body === 'object') {
      const { code, message } = body as { code?: unknown; message?: unknown };
      if (typeof code === 'string' && typeof message === 'string') {
        return new ApiError(response.status, code, message, retry);
      }
    }
  } catch {
    // Not JSON (for example a proxy error page): fall through to the generic error.
  }
  return new ApiError(response.status, 'UNKNOWN_ERROR', 'Something went wrong.', retry);
}

/** Call the API on the same origin; resolves the parsed JSON (undefined for 204). */
export async function apiFetch<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase();
  const headers = new Headers(init.headers);
  if (!SAFE_METHODS.has(method)) {
    const token = readCookie(CSRF_COOKIE);
    if (token) headers.set('X-CSRF-Token', token);
  }
  if (typeof init.body === 'string' && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  let response: Response;
  try {
    response = await fetch(`${window.location.origin}${path}`, {
      ...init,
      method,
      headers,
      credentials: 'same-origin',
    });
  } catch {
    throw new ApiError(0, 'NETWORK_ERROR', 'Could not reach the server. Check the connection.');
  }

  if (!response.ok) {
    const error = await toApiError(response);
    if (error.status === 401 && path !== LOGIN_API_PATH) onUnauthorized?.();
    throw error;
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
