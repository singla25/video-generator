// DD-38 C: Overview when the current batch is a draft. Cases: TT-DD38-C-*
//
// CONTRACT (frontend/src/components/CurrentBatchPanel.tsx, KpiCards.tsx):
//   DRAFT current batch   primary button is the link "Continue setup" -> /batches/new?batch=<id>
//                         (not "Start batch"); "Delete draft" stays; the KPI tile that said "Queued"
//                         (data-testid kpi-queued) reads "Not started" and keeps its number.
//   RUNNING / PAUSED / COMPLETED   unchanged: tile "Queued", "View batch" or the existing buttons.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { renderApp } from "../helpers";
import { COUNTS, IDS, batch, row, rowsPage, status } from "../mocks/data";
import { server } from "../mocks/server";
import { setReducedMotion } from "../motion";

const QUEUED_ROWS = [1, 2, 3].map((n) =>
  row(n, { status: "QUEUED", has_video: false, render_seconds: null }),
);

/** Serve one current batch in the given state, with its live counts. */
function serve(state: string, counts = { ...COUNTS }) {
  server.use(
    http.get("*/batches", () =>
      HttpResponse.json({
        batches: [
          batch({
            status: state,
            preview: { status: "READY", approved: state !== "DRAFT" },
          }),
        ],
        page: 1,
        page_size: 50,
        total: 1,
        total_pages: 1,
      }),
    ),
    http.get("*/batches/:id/status", () =>
      HttpResponse.json(status({ counts })),
    ),
    http.get("*/batches/:id/rows", () =>
      HttpResponse.json(rowsPage(QUEUED_ROWS)),
    ),
  );
}

async function panel() {
  setReducedMotion(true);
  renderApp("/");
  return within(await screen.findByTestId("current-batch"));
}

function tile(key: string): HTMLElement {
  return screen.getByTestId(`kpi-${key}`);
}

describe("positive", () => {
  it("TT-DD38-C-P1 a draft offers Continue setup linking to the wizard resume page", async () => {
    serve("DRAFT");
    const p = await panel();
    expect(p.getByRole("link", { name: "Continue setup" })).toHaveAttribute(
      "href",
      `/batches/new?batch=${IDS.batch}`,
    );
  });

  it("TT-DD38-C-P2 a draft keeps the Delete draft button", async () => {
    serve("DRAFT");
    const p = await panel();
    expect(p.getByRole("button", { name: "Delete draft" })).toBeInTheDocument();
  });

  it("TT-DD38-C-P3 the Queued tile of a draft reads Not started and keeps its number", async () => {
    serve("DRAFT");
    await panel();
    const queued = tile("queued");
    expect(within(queued).getByText("Not started")).toBeInTheDocument();
    expect(queued).not.toHaveTextContent("Queued");
    expect(queued.dataset.value).toBe(String(COUNTS.queued));
    expect(queued).toHaveTextContent(String(COUNTS.queued));
  });

  it("TT-DD38-C-P4 the other KPI labels of a draft do not change", async () => {
    serve("DRAFT");
    await panel();
    expect(
      within(tile("completed")).getByText("Completed"),
    ).toBeInTheDocument();
    expect(
      within(tile("processing")).getByText("Processing"),
    ).toBeInTheDocument();
    expect(within(tile("failed")).getByText("Failed")).toBeInTheDocument();
    expect(within(tile("skipped")).getByText("Skipped")).toBeInTheDocument();
  });
});

describe("negative", () => {
  it("TT-DD38-C-N1 a draft has no Start batch link any more", async () => {
    serve("DRAFT");
    const p = await panel();
    expect(
      p.queryByRole("link", { name: "Start batch" }),
    ).not.toBeInTheDocument();
  });

  it("TT-DD38-C-N2 a draft has no Pause, Resume or Cancel batch button", async () => {
    serve("DRAFT");
    const p = await panel();
    for (const name of ["Pause", "Resume", "Cancel batch"]) {
      expect(p.queryByRole("button", { name })).not.toBeInTheDocument();
    }
  });

  it("TT-DD38-C-N3 a running batch keeps the Queued tile and View batch, with no Continue setup", async () => {
    serve("RUNNING");
    const p = await panel();
    expect(within(tile("queued")).getByText("Queued")).toBeInTheDocument();
    expect(p.getByRole("link", { name: "View batch" })).toHaveAttribute(
      "href",
      `/batches/${IDS.batch}`,
    );
    expect(p.getByRole("button", { name: "Pause" })).toBeInTheDocument();
    expect(
      p.queryByRole("link", { name: "Continue setup" }),
    ).not.toBeInTheDocument();
  });

  it("TT-DD38-C-N4 a paused batch keeps the Queued tile and Resume, with no Continue setup", async () => {
    serve("PAUSED");
    const p = await panel();
    expect(within(tile("queued")).getByText("Queued")).toBeInTheDocument();
    expect(p.getByRole("button", { name: "Resume" })).toBeInTheDocument();
    expect(
      p.queryByRole("link", { name: "Continue setup" }),
    ).not.toBeInTheDocument();
  });

  it("TT-DD38-C-N5 a completed batch keeps the Queued tile and View batch, with no Delete draft", async () => {
    serve("COMPLETED");
    const p = await panel();
    expect(within(tile("queued")).getByText("Queued")).toBeInTheDocument();
    expect(p.getByRole("link", { name: "View batch" })).toBeInTheDocument();
    expect(
      p.queryByRole("button", { name: "Delete draft" }),
    ).not.toBeInTheDocument();
    expect(
      p.queryByRole("link", { name: "Continue setup" }),
    ).not.toBeInTheDocument();
  });
});

describe("edge", () => {
  it("TT-DD38-C-E1 a draft with no queued rows still reads Not started, with 0", async () => {
    serve("DRAFT", { ...COUNTS, queued: 0 });
    await panel();
    expect(within(tile("queued")).getByText("Not started")).toBeInTheDocument();
    expect(tile("queued").dataset.value).toBe("0");
  });

  it("TT-DD38-C-E2 clicking Continue setup leaves the Overview for the wizard", async () => {
    serve("DRAFT");
    const p = await panel();
    await userEvent.click(p.getByRole("link", { name: "Continue setup" }));
    await waitFor(() =>
      expect(screen.queryByTestId("current-batch")).not.toBeInTheDocument(),
    );
  });
});
