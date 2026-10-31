// DD-38 D: resuming a batch from /batches/new?batch=<id>. Cases: TT-DD38-D-*
//
// CONTRACT (frontend/src/pages/WizardPage.tsx, frontend/src/pages/wizard/resume.ts; GET /batches/<id>):
//   The real GET never sends `report` (only the create and mapping responses do); it sends `counts`.
//   Valid rows of a resumed draft = report.valid_rows when a report is present, else
//   counts.total - counts.skipped.
//   Missing (404)                  the existing error alert (role=alert, the API message) and a link
//                                  "Back to Overview" (-> /)
//   Exists, not DRAFT              "This batch can't be continued." and a link "Back to Overview" (-> /)
//   DRAFT, valid rows below 1      "This draft has no sheet data yet. Delete it and upload the sheet
//                                  again." and a "Delete draft" button (dialog "Delete this draft?",
//                                  then DELETE /batches/<id>, then navigate to /)
//   DRAFT, valid rows 1 or more    step 3 "Slot & preview" (stepper aria-current), with or without an
//                                  approved preview; Next goes to step 4 "Output & start", which shows
//                                  "All N rows" with the same N
//   No batch parameter             unchanged: step 1 "Upload", no batch request
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { renderApp } from "../helpers";
import { COUNTS, IDS, batch, batchesPage, report } from "../mocks/data";
import { apiError } from "../mocks/handlers";
import { server } from "../mocks/server";

const CANNOT = "This batch can't be continued.";
const NO_SHEET =
  "This draft has no sheet data yet. Delete it and upload the sheet again.";
const RESUME = `/batches/new?batch=${IDS.batch}`;

type Json = ReturnType<typeof batch>;

/** Serve GET /batches/<id> with `body`, and record each requested batch id. */
function serveBatch(body: Json | null): string[] {
  const requested: string[] = [];
  server.use(
    http.get("*/batches/:id", ({ params }) => {
      requested.push(String(params.id));
      if (body === null) return apiError(404, "NOT_FOUND", "Batch not found.");
      return HttpResponse.json(body);
    }),
  );
  return requested;
}

/** Live counts as the real GET sends them: `total` rows, of which `skipped` are skipped. */
function countsOf(total: number, skipped: number): Record<string, number> {
  return { ...COUNTS, total, skipped };
}

/** A DRAFT as the real GET sends it: counts present, no report unless `over` adds one. */
function draftWith(
  preview: Record<string, unknown> = {},
  over: Record<string, unknown> = {},
): Json {
  return batch({
    status: "DRAFT",
    preview: { status: "NONE", approved: false, ...preview },
    ...over,
  });
}

/** A DRAFT with no valid rows: every row is skipped. */
function noSheetDraft(preview: Record<string, unknown> = {}): Json {
  return draftWith(preview, { counts: countsOf(10, 10) });
}

/** The stepper item marked as the current step. */
function currentStep(): Element | null {
  return screen
    .getByRole("list", { name: "Steps" })
    .querySelector('[aria-current="step"]');
}

describe("positive", () => {
  it.each([
    ["no preview yet", { status: "NONE", approved: false }],
    ["a READY preview not approved", { status: "READY", approved: false }],
    ["a STALE preview", { status: "STALE", approved: false }],
  ])(
    "TT-DD38-D-P3 a draft with sheet data and %s opens step 3 Slot & preview",
    async (_label, preview) => {
      serveBatch(draftWith(preview, { counts: countsOf(10, 2) }));
      renderApp(RESUME);
      expect(
        await screen.findByRole("spinbutton", { name: "Slot start (s)" }),
      ).toHaveValue(4.2);
      expect(currentStep()).toHaveTextContent("Slot & preview");
    },
  );

  it("TT-DD38-D-P4 an approved preview still opens step 3 with it shown; Next goes to step 4 with All 8 rows", async () => {
    serveBatch(
      draftWith(
        { status: "READY", approved: true },
        { counts: countsOf(10, 2) },
      ),
    );
    renderApp(RESUME);
    expect(
      await screen.findByRole("spinbutton", { name: "Slot start (s)" }),
    ).toBeInTheDocument();
    expect(currentStep()).toHaveTextContent("Slot & preview");
    expect(screen.getByText("Preview approved")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(
      await screen.findByRole("textbox", { name: "Output folder" }),
    ).toBeInTheDocument();
    expect(currentStep()).toHaveTextContent("Output & start");
    expect(screen.getByText("All 8 rows")).toBeInTheDocument();
  });

  it("TT-DD38-D-P5 step 4 of an approved draft counts the valid rows", async () => {
    serveBatch(
      draftWith(
        { status: "READY", approved: true },
        { counts: countsOf(7, 2) },
      ),
    );
    renderApp(RESUME);
    await userEvent.click(await screen.findByRole("button", { name: "Next" }));
    await userEvent.click(
      await screen.findByRole("button", { name: "Review and start" }),
    );
    expect(
      await screen.findByRole("dialog", { name: "Start 5 videos?" }),
    ).toBeInTheDocument();
  });

  it("TT-DD38-D-P6 without a batch parameter the wizard starts at step 1 and fetches no batch", async () => {
    const requested = serveBatch(null);
    renderApp("/batches/new");
    expect(await screen.findByLabelText("Sheet file")).toBeInTheDocument();
    expect(currentStep()).toHaveTextContent("Upload");
    expect(requested).toEqual([]);
  });

  it("TT-DD38-D-P1 a draft with no sheet data says so and offers Delete draft", async () => {
    serveBatch(noSheetDraft());
    renderApp(RESUME);
    expect(await screen.findByText(NO_SHEET)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Delete draft" }),
    ).toBeInTheDocument();
  });

  it("TT-DD38-D-P2 Delete draft confirms, sends DELETE, then opens the Overview", async () => {
    const deleted: string[] = [];
    serveBatch(noSheetDraft());
    server.use(
      http.delete("*/batches/:id", ({ params }) => {
        deleted.push(String(params.id));
        return new HttpResponse(null, { status: 204 });
      }),
      http.get("*/batches", () => HttpResponse.json(batchesPage([]))),
    );
    renderApp(RESUME);
    await userEvent.click(
      await screen.findByRole("button", { name: "Delete draft" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Delete this draft?",
    });
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Delete" }),
    );
    expect(await screen.findByText("No batches yet")).toBeInTheDocument();
    expect(deleted).toEqual([IDS.batch]);
  });

  it("TT-DD38-D-P7 the real API shape (counts, no report) with 10 valid rows opens step 3", async () => {
    serveBatch(draftWith({}, { counts: countsOf(10, 0) }));
    renderApp(RESUME);
    expect(
      await screen.findByRole("spinbutton", { name: "Slot start (s)" }),
    ).toBeInTheDocument();
    expect(currentStep()).toHaveTextContent("Slot & preview");
    expect(screen.queryByText(NO_SHEET)).not.toBeInTheDocument();
  });

  it("TT-DD38-D-P8 when a report is present its valid_rows win over the counts", async () => {
    serveBatch(
      draftWith(
        { status: "READY", approved: true },
        {
          counts: countsOf(10, 0),
          report: report({ total_rows: 10, valid_rows: 7, skipped_rows: 3 }),
        },
      ),
    );
    renderApp(RESUME);
    await userEvent.click(await screen.findByRole("button", { name: "Next" }));
    expect(await screen.findByText("All 7 rows")).toBeInTheDocument();
    expect(screen.queryByText("All 10 rows")).not.toBeInTheDocument();
  });
});

describe("negative", () => {
  it("TT-DD38-D-N1 a missing batch (404) shows the API error alert, with Back to Overview", async () => {
    serveBatch(null);
    renderApp(RESUME);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Batch not found.",
    );
    expect(
      screen.getByRole("link", { name: "Back to Overview" }),
    ).toHaveAttribute("href", "/");
  });

  it.each(["RUNNING", "COMPLETED", "CANCELLED"])(
    "TT-DD38-D-N2 a %s batch cannot be resumed in the wizard",
    async (state) => {
      serveBatch(batch({ status: state }));
      renderApp(RESUME);
      expect(await screen.findByText(CANNOT)).toBeInTheDocument();
      expect(
        screen.getByRole("link", { name: "Back to Overview" }),
      ).toHaveAttribute("href", "/");
      expect(
        screen.queryByRole("spinbutton", { name: "Slot start (s)" }),
      ).not.toBeInTheDocument();
    },
  );

  it.each([
    ["every row is skipped", countsOf(10, 10), undefined],
    ["the sheet has no rows", countsOf(0, 0), undefined],
    ["report is null and every row is skipped", countsOf(10, 10), null],
  ])(
    "TT-DD38-D-N3 a draft where %s shows the no-sheet message",
    async (_label, counts, sheet) => {
      serveBatch(
        draftWith(
          {},
          sheet === undefined ? { counts } : { counts, report: sheet },
        ),
      );
      renderApp(RESUME);
      expect(await screen.findByText(NO_SHEET)).toBeInTheDocument();
      expect(
        screen.queryByRole("spinbutton", { name: "Slot start (s)" }),
      ).not.toBeInTheDocument();
    },
  );

  it("TT-DD38-D-N6 a report with zero valid rows and an unapproved preview shows the no-sheet message", async () => {
    serveBatch(
      draftWith(
        { status: "NONE", approved: false },
        {
          report: report({ total_rows: 2, valid_rows: 0, skipped_rows: 2 }),
        },
      ),
    );
    renderApp(RESUME);
    expect(await screen.findByText(NO_SHEET)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Delete draft" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("spinbutton", { name: "Slot start (s)" }),
    ).not.toBeInTheDocument();
  });

  it("TT-DD38-D-N7 a report with zero valid rows and an approved preview shows the no-sheet message, not step 4", async () => {
    serveBatch(
      draftWith(
        { status: "READY", approved: true },
        {
          report: report({ total_rows: 2, valid_rows: 0, skipped_rows: 2 }),
        },
      ),
    );
    renderApp(RESUME);
    expect(await screen.findByText(NO_SHEET)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Delete draft" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("textbox", { name: "Output folder" }),
    ).not.toBeInTheDocument();
  });

  it("TT-DD38-D-N4 Keep in the delete dialog sends nothing and stays on the page", async () => {
    const deleted: string[] = [];
    serveBatch(noSheetDraft());
    server.use(
      http.delete("*/batches/:id", ({ params }) => {
        deleted.push(String(params.id));
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderApp(RESUME);
    await userEvent.click(
      await screen.findByRole("button", { name: "Delete draft" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Delete this draft?",
    });
    await userEvent.click(within(dialog).getByRole("button", { name: "Keep" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByText(NO_SHEET)).toBeInTheDocument();
    expect(deleted).toEqual([]);
  });

  it("TT-DD38-D-N5 a failed DELETE shows its message and keeps the page", async () => {
    serveBatch(noSheetDraft());
    server.use(
      http.delete("*/batches/:id", () =>
        apiError(500, "INTERNAL_ERROR", "The draft could not be deleted."),
      ),
    );
    renderApp(RESUME);
    await userEvent.click(
      await screen.findByRole("button", { name: "Delete draft" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Delete this draft?",
    });
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Delete" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The draft could not be deleted.",
    );
    expect(screen.getByText(NO_SHEET)).toBeInTheDocument();
  });
});

describe("edge", () => {
  it("TT-DD38-D-E1 Back to Overview opens the Overview", async () => {
    serveBatch(null);
    server.use(http.get("*/batches", () => HttpResponse.json(batchesPage([]))));
    renderApp(RESUME);
    await userEvent.click(
      await screen.findByRole("link", { name: "Back to Overview" }),
    );
    expect(await screen.findByText("No batches yet")).toBeInTheDocument();
  });

  it("TT-DD38-D-E2 a double click on Delete confirm sends one DELETE", async () => {
    const deleted: string[] = [];
    serveBatch(noSheetDraft());
    server.use(
      http.delete("*/batches/:id", async ({ params }) => {
        deleted.push(String(params.id));
        await new Promise((r) => setTimeout(r, 50));
        return new HttpResponse(null, { status: 204 });
      }),
      http.get("*/batches", () => HttpResponse.json(batchesPage([]))),
    );
    renderApp(RESUME);
    await userEvent.click(
      await screen.findByRole("button", { name: "Delete draft" }),
    );
    const confirm = within(await screen.findByRole("dialog")).getByRole(
      "button",
      {
        name: "Delete",
      },
    );
    await userEvent.dblClick(confirm);
    await waitFor(() => expect(deleted.length).toBeGreaterThan(0));
    await new Promise((r) => setTimeout(r, 150));
    expect(deleted).toEqual([IDS.batch]);
  });
});
