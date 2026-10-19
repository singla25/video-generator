// Default MSW handlers: a healthy API with one running batch. Tests override per case.
import { HttpResponse, http } from 'msw';

import {
  ROWS_BY_STATUS,
  TEMPLATE_NO_CONSENT,
  batch,
  daily,
  report,
  rowsPage,
  status,
  template,
} from './data';

/** An API error body exactly like backend/vidgen/api/errors.py: {code, message}. */
export function apiError(
  httpStatus: number,
  code: string,
  message: string,
  headers: Record<string, string> = {},
): Response {
  return HttpResponse.json({ code, message }, { status: httpStatus, headers });
}

export const handlers = [
  http.post('*/auth/login', () => HttpResponse.json({ csrf_token: 'csrf-test-token' })),
  http.post('*/auth/logout', () => HttpResponse.json({ status: 'logged_out' })),
  http.get('*/stats/daily', () => HttpResponse.json(daily())),
  http.get('*/audit', () => HttpResponse.json({ entries: [] })),
  http.get('*/templates', () =>
    HttpResponse.json({ templates: [template(), TEMPLATE_NO_CONSENT] }),
  ),
  http.get('*/templates/:id', () => HttpResponse.json(template())),
  http.get('*/batches', () =>
    HttpResponse.json({ batches: [batch()], page: 1, page_size: 50, total: 1, total_pages: 1 }),
  ),
  http.get('*/batches/:id/status', () => HttpResponse.json(status())),
  http.get('*/batches/:id/rows', () => HttpResponse.json(rowsPage(ROWS_BY_STATUS))),
  http.get('*/batches/:id/report', () => HttpResponse.json(report())),
  http.get('*/batches/:id', () => HttpResponse.json(batch())),
];
