// DD-38 D: resuming a batch from /batches/new?batch=<id>. Cases: TT-DD38-D-*
//
// CONTRACT (frontend/src/pages/WizardPage.tsx; GET /batches/<id>):
//   Missing (404) or not DRAFT   "This batch can't be continued." and a link "Back to Overview" (-> /)
//   DRAFT, report null or missing "This draft has no sheet data yet. Delete it and upload the sheet
//                                 again." and a "Delete draft" button (dialog "Delete this draft?",
//                                 then DELETE /batches/<id>, then navigate to /)
//   DRAFT with report, preview.approved not true   step 3 "Slot & preview" (stepper aria-current)
//   DRAFT with report, preview.approved true       step 4 "Output & start" with validRows = report.valid_rows
//   No batch parameter                             unchanged: step 1 "Upload", no batch request
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { renderApp } from "../helpers";
import { IDS, batch, batchesPage, report } from "../mocks/data";
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

/** A DRAFT. `sheet` null means report: null; undefined means the report key is missing. */
function draftWith(
  sheet: Record<string, unknown> | null | undefined,
  preview = {},
): Json {
  const over: Record<string, unknown> = {
    status: "DRAFT",
    preview: { status: "NONE", approved: false, ...preview },
  };
  if (sheet !== undefined) over.report = sheet;
  return batch(over);
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
      serveBatch(draftWith(report({ valid_rows: 8 }), preview));
      renderApp(RESUME);
      expect(
        await screen.findByRole("spinbutton", { name: "Slot start (s)" }),
      ).toHaveValue(4.2);
      expect(currentStep()).toHaveTextContent("Slot & preview");
    },
  );

  it("TT-DD38-D-P4 an approved preview opens step 4 Output & start", async () => {
    serveBatch(
      draftWith(report({ valid_rows: 8 }), { status: "READY", approved: true }),
    );
    renderApp(RESUME);
    expect(
      await screen.findByRole("textbox", { name: "Output folder" }),
    ).toBeInTheDocument();
    expect(currentStep()).toHaveTextContent("Output & start");
  });

  it("TT-DD38-D-P5 step 4 of an approved draft counts the sheet valid rows", async () => {
    serveBatch(
      draftWith(report({ total_rows: 7, valid_rows: 5, skipped_rows: 2 }), {
        status: "READY",
        approved: true,
      }),
    );
    renderApp(RESUME);
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
    serveBatch(draftWith(null));
    renderApp(RESUME);
    expect(await screen.findByText(NO_SHEET)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Delete draft" }),
    ).toBeInTheDocument();
  });

  it("TT-DD38-D-P2 Delete draft confirms, sends DELETE, then opens the Overview", async () => {
    const deleted: string[] = [];
    serveBatch(draftWith(null));
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
});

describe("negative", () => {
  it("TT-DD38-D-N1 a missing batch (404) says it cannot be continued, with Back to Overview", async () => {
    serveBatch(null);
    renderApp(RESUME);
    expect(await screen.findByText(CANNOT)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Back to Overview" }),
    ).toHaveAttribute("href", "/");
  });

  it.each(["RUNNING", "COMPLETED", "CANCELLED"])(
    "TT-DD38-D-N2 a %s batch cannot be resumed in the wizard",
    async (state) => {
      serveBatch(batch({ status: state, report: report() }));
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
    ["report is null", null],
    ["report is missing", undefined],
  ])(
    "TT-DD38-D-N3 a draft whose %s shows the no-sheet message",
    async (_label, value) => {
      serveBatch(draftWith(value as Record<string, unknown> | null));
      renderApp(RESUME);
      expect(await screen.findByText(NO_SHEET)).toBeInTheDocument();
      expect(
        screen.queryByRole("spinbutton", { name: "Slot start (s)" }),
      ).not.toBeInTheDocument();
    },
  );

  it("TT-DD38-D-N6 a draft with zero valid rows and an unapproved preview shows the no-sheet message", async () => {
    serveBatch(
      draftWith(report({ total_rows: 2, valid_rows: 0, skipped_rows: 2 }), {
        status: "NONE",
        approved: false,
      }),
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

  it("TT-DD38-D-N7 a draft with zero valid rows and an approved preview shows the no-sheet message, not step 4", async () => {
    serveBatch(
      draftWith(report({ total_rows: 2, valid_rows: 0, skipped_rows: 2 }), {
        status: "READY",
        approved: true,
      }),
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
    serveBatch(draftWith(null));
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
    serveBatch(draftWith(null));
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
    serveBatch(draftWith(null));
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
