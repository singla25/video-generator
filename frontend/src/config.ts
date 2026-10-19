/** Live-data polling interval for running batches (milliseconds). */
export const POLL_INTERVAL_MS = 2000;

/** Duration of the KPI count-up animation (milliseconds). */
export const COUNT_UP_DURATION_MS = 800;

/** Step length of the count-up animation (milliseconds). */
export const COUNT_UP_STEP_MS = 40;

/** Where a 401 sends the user. */
export const LOGIN_PATH = '/login';

/** Name of the readable (non-HttpOnly) CSRF cookie set by the API. */
export const CSRF_COOKIE = 'vidgen_csrf';
