// Default MSW handlers: a healthy API with one running batch. Tests override per case.
import { HttpResponse, http } from "msw";

import {
  ROWS_BY_STATUS,
  TEMPLATE_NO_CONSENT,
  batch,
  batchesPage,
  daily,
  report,
  rowsPage,
  status,
  template,
} from "./data";

/** An API error body exactly like backend/vidgen/api/errors.py: {code, message}. */
export function apiError(
  httpStatus: number,
  code: string,
  message: string,
  headers: Record<string, string> = {},
): Response {
  return HttpResponse.json({ code, message }, { status: httpStatus, headers });
}

type Json = Record<string, unknown>;

/** Bodies of every PUT /templates/<id>/slot the default handler received (cleared by the tests that use it). */
export const slotPuts: Json[] = [];

export const handlers = [
  http.post("*/auth/login", () =>
    HttpResponse.json({ csrf_token: "csrf-test-token" }),
  ),
  http.post("*/auth/logout", () => HttpResponse.json({ status: "logged_out" })),
  http.post("*/batches/inspect-sheet", () =>
    HttpResponse.json({
      sheet_name: "sheet.csv",
      headers: ["Voter Name", "Voter ID", "Spoken"],
      sample_rows: [["Test Person 1", "TST000001", ""]],
      row_count: 1,
    }),
  ),
  http.get("*/system/status", () =>
    HttpResponse.json({ worker_alive: true, queue_depth: 0, redis_ok: true }),
  ),
  http.get("*/stats/daily", () => HttpResponse.json(daily())),
  http.get("*/audit", () => HttpResponse.json({ entries: [] })),
  http.get("*/templates", () =>
    HttpResponse.json({ templates: [template(), TEMPLATE_NO_CONSENT] }),
  ),
  http.get("*/templates/:id", () => HttpResponse.json(template())),
  http.put("*/templates/:id/slot", async ({ request }) => {
    const body = (await request.json()) as Json;
    slotPuts.push(body);
    return HttpResponse.json(
      template({
        slot: { start_s: body.start_s, end_s: body.end_s },
        extra_slots: body.extra_slots,
        slot_confirmed: false,
      }),
    );
  }),
  http.delete("*/templates/:id", () => new HttpResponse(null, { status: 204 })),
  http.get("*/batches", ({ request }) => {
    // DD-38: the Not started list is empty unless a test serves drafts.
    if (new URL(request.url).searchParams.get("view") === "drafts") {
      return HttpResponse.json(batchesPage([]));
    }
    return HttpResponse.json({
      batches: [batch()],
      page: 1,
      page_size: 50,
      total: 1,
      total_pages: 1,
    });
  }),
  http.delete("*/batches/:id", () => new HttpResponse(null, { status: 204 })),
  http.post("*/batches/:id/preview", () =>
    HttpResponse.json(
      batch({ preview: { status: "PENDING", approved: false } }),
      {
        status: 202,
      },
    ),
  ),
  http.get("*/batches/:id/status", () => HttpResponse.json(status())),
  http.get("*/batches/:id/rows", () =>
    HttpResponse.json(rowsPage(ROWS_BY_STATUS)),
  ),
  http.get("*/batches/:id/report", () => HttpResponse.json(report())),
  http.post("*/batches/:id/start", () => HttpResponse.json(batch())),
  http.get("*/batches/:id", () => HttpResponse.json(batch())),
];
