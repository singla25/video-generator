import { API_PREFIX, CSRF_COOKIE, UPLOAD_TIMEOUT_MS } from '../config';

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

/** Same-origin API path for a call or a download link; never prefixes twice. */
export function apiUrl(path: string): string {
  return path === API_PREFIX || path.startsWith(`${API_PREFIX}/`) ? path : `${API_PREFIX}${path}`;
}

const SAFE_METHODS = new Set(['GET', 'HEAD']);
const LOGIN_API_PATH = '/auth/login';
const NETWORK_MESSAGE = 'Could not reach the server. Check the connection and try again.';
const TIMEOUT_MESSAGE = 'The upload took too long and was stopped. Please try again.';
const UNAVAILABLE_MESSAGE = 'The server is unavailable right now. Please try again in a moment.';
const FALLBACK_MESSAGE = 'Something went wrong. Please try again.';
/** Plain words for failures whose body is not the API envelope (for example a proxy page). */
const STATUS_MESSAGES: Record<number, string> = {
  413: 'This file is too large. Choose a smaller one.',
  500: 'Something went wrong on the server. Please try again.',
  502: UNAVAILABLE_MESSAGE,
  503: UNAVAILABLE_MESSAGE,
  504: UNAVAILABLE_MESSAGE,
};
const DIGITS = /^[0-9]+$/;

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

function addCsrf(method: string, headers: Headers): void {
  if (SAFE_METHODS.has(method)) return;
  const token = readCookie(CSRF_COOKIE);
  if (token) headers.set('X-CSRF-Token', token);
}

/** Build an ApiError from a status and the raw body text (the API envelope, else plain words). */
function errorFromBody(status: number, text: string, retryHeader: string | null): ApiError {
  const retry = retryHeader !== null && DIGITS.test(retryHeader) ? Number(retryHeader) : undefined;
  try {
    const body: unknown = JSON.parse(text);
    if (body && typeof body === 'object') {
      const { code, message } = body as { code?: unknown; message?: unknown };
      if (typeof code === 'string' && typeof message === 'string') {
        return new ApiError(status, code, message, retry);
      }
    }
  } catch {
    // Not JSON (for example a proxy error page): fall through to the generic error.
  }
  return new ApiError(status, 'UNKNOWN_ERROR', STATUS_MESSAGES[status] ?? FALLBACK_MESSAGE, retry);
}

async function toApiError(response: Response): Promise<ApiError> {
  const text = await response.text().catch(() => '');
  return errorFromBody(response.status, text, response.headers.get('Retry-After'));
}

/** Call the API on the same origin; resolves the parsed JSON (undefined for 204). */
export async function apiFetch<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase();
  const headers = new Headers(init.headers);
  addCsrf(method, headers);
  if (typeof init.body === 'string' && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  let response: Response;
  try {
    response = await fetch(`${window.location.origin}${apiUrl(path)}`, {
      ...init,
      method,
      headers,
      credentials: 'same-origin',
    });
  } catch {
    throw new ApiError(0, 'NETWORK_ERROR', NETWORK_MESSAGE);
  }

  if (!response.ok) {
    const error = await toApiError(response);
    if (error.status === 401 && path !== LOGIN_API_PATH) onUnauthorized?.();
    throw error;
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** Raised when an upload is cancelled on purpose; callers ignore it. */
export class UploadAbortedError extends Error {
  constructor() {
    super('Upload cancelled');
    this.name = 'UploadAbortedError';
  }
}

export interface UploadOptions {
  /** Called with 0-100 while the file is being sent. */
  onProgress?: (percent: number) => void;
  signal?: AbortSignal;
  timeoutMs?: number;
}

function parseSuccess<T>(xhr: XMLHttpRequest): T {
  if (xhr.status === 204 || !xhr.responseText) return undefined as T;
  return JSON.parse(xhr.responseText) as T;
}

/**
 * POST a form to the API with upload progress (fetch cannot report it). Same CSRF header, 401
 * handling and error envelope as apiFetch. Rejects with ApiError, or UploadAbortedError.
 */
export function apiUpload<T = unknown>(
  path: string,
  form: FormData,
  { onProgress, signal, timeoutMs = UPLOAD_TIMEOUT_MS }: UploadOptions = {},
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new UploadAbortedError());
      return;
    }
    const xhr = new XMLHttpRequest();
    let settled = false;
    // Only the first outcome counts: a late answer after abort must change nothing.
    const settle = (action: () => void) => {
      if (settled) return;
      settled = true;
      signal?.removeEventListener('abort', onAbort);
      action();
    };
    function onAbort() {
      settle(() => reject(new UploadAbortedError()));
      xhr.abort();
    }

    xhr.open('POST', `${window.location.origin}${apiUrl(path)}`);
    xhr.withCredentials = true;
    xhr.timeout = timeoutMs;
    const headers = new Headers();
    addCsrf('POST', headers);
    headers.forEach((value, name) => xhr.setRequestHeader(name, value));

    xhr.upload.onprogress = (event) => {
      if (settled || !event.lengthComputable || event.total === 0) return;
      onProgress?.(Math.min(100, Math.round((event.loaded / event.total) * 100)));
    };
    xhr.onload = () =>
      settle(() => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            resolve(parseSuccess<T>(xhr));
          } catch {
            reject(new ApiError(xhr.status, 'UNKNOWN_ERROR', FALLBACK_MESSAGE));
          }
          return;
        }
        const retry = xhr.getResponseHeader('Retry-After');
        const error = errorFromBody(xhr.status, xhr.responseText, retry);
        if (error.status === 401) onUnauthorized?.();
        reject(error);
      });
    xhr.onerror = () => settle(() => reject(new ApiError(0, 'NETWORK_ERROR', NETWORK_MESSAGE)));
    xhr.ontimeout = () => settle(() => reject(new ApiError(0, 'TIMEOUT', TIMEOUT_MESSAGE)));
    signal?.addEventListener('abort', onAbort);
    xhr.send(form);
  });
}
