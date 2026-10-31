// DD-38 B: drafts on the Running page. Cases: TT-DD38-B-*
//
// CONTRACT (frontend/src/pages/BatchListPage.tsx with view "running"):
//   GET /api/batches?page=1&page_size=50&view=drafts   only from the running view
//   Section    heading "Not started" below the running list, only when the drafts list has at least
//              one batch; a table with headers exactly Batch, Template, Rows, Created, Actions
//   Row        link "Continue setup" -> /batches/new?batch=<id>; button "Delete draft" opens the
//              existing dialog "Delete this draft?" [Delete | Keep]; Delete sends DELETE /batches/<id>,
//              then the lists refetch (the drafts section disappears when none is left)
//   Empty      "No running batches" still shows when the running list is empty
//   completed and failed views never ask for drafts
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, delay, http } from "msw";
import { describe, expect, it } from "vitest";

import { renderApp } from "../helpers";
import { COUNTS, IDS, batch, batchesPage, template } from "../mocks/data";
import { apiError } from "../mocks/handlers";
import { server } from "../mocks/server";

const HEADERS = ["Batch", "Template", "Rows", "Created", "Actions"];
const HEADING = "Not started";
const CREATED = "2026-10-19T12:00:00+00:00";
const DRAFT_SHEET = "draft-sheet.csv";

interface Hit {
  view: string | null;
  page: string | null;
  page_size: string | null;
}

type Json = ReturnType<typeof batch>;

/** A draft batch: never started, so its status is DRAFT and it has a template and a sheet. */
function draft(over: Record<string, unknown> = {}): Json {
  return batch({
    id: IDS.oldBatch,
    status: "DRAFT",
    sheet_name: DRAFT_SHEET,
    started_at: null,
    created_at: CREATED,
    preview: { status: "NONE", approved: false },
    ...over,
  });
}

/**
 * Serve GET /batches by view. `running` and `drafts` are read on every call, so a test can change
 * them (for example after a delete). Every call that carries a view is recorded.
 */
function serveLists(running: () => Json[], drafts: () => Json[]) {
  const hits: Hit[] = [];
  const deletes: string[] = [];
  server.use(
    http.get("*/batches", ({ request }) => {
      const query = new URL(request.url).searchParams;
      const view = query.get("view");
      if (!view) return HttpResponse.json(batchesPage([]));
      hits.push({
        view,
        page: query.get("page"),
        page_size: query.get("page_size"),
      });
      if (view === "drafts") return HttpResponse.json(batchesPage(drafts()));
      if (view === "running") return HttpResponse.json(batchesPage(running()));
      return HttpResponse.json(batchesPage([]));
    }),
    http.delete("*/batches/:id", ({ params }) => {
      deletes.push(String(params.id));
      return new HttpResponse(null, { status: 204 });
    }),
    http.get("*/templates", () =>
      HttpResponse.json({ templates: [template()] }),
    ),
  );
  return { hits, deletes };
}

const RUNNING = [batch({ status: "RUNNING" })];

/** The table whose headers are the drafts headers, not the running table. */
async function draftTable(): Promise<HTMLElement> {
  return waitFor(() => {
    const table = screen.getAllByRole("table").find(
      (t) =>
        within(t)
          .queryAllByRole("columnheader")
          .map((h) => h.textContent)
          .join("|") === HEADERS.join("|"),
    );
    if (!table) throw new Error("no drafts table yet");
    return table;
  });
}

function bodyRowsOf(table: HTMLElement): HTMLElement[] {
  return within(table).getAllByRole("row").slice(1);
}

function createdText(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
/** Long enough for a request that should not happen to have happened. */
const SETTLE_MS = 100;

describe("positive", () => {
  it("TT-DD38-B-P1 a Not started section appears when a draft exists", async () => {
    serveLists(
      () => RUNNING,
      () => [draft()],
    );
    renderApp("/batches/running");
    expect(
      await screen.findByRole("heading", { name: HEADING }),
    ).toBeInTheDocument();
  });

  it("TT-DD38-B-P2 the section sits below the running list and has the five headers", async () => {
    serveLists(
      () => RUNNING,
      () => [draft()],
    );
    renderApp("/batches/running");
    const drafts = await draftTable();
    const running = screen
      .getAllByRole("table")
      .find((t) => t !== drafts) as HTMLElement;
    expect(
      running.compareDocumentPosition(drafts) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    const headers = within(drafts)
      .getAllByRole("columnheader")
      .map((h) => h.textContent);
    expect(headers).toEqual(HEADERS);
  });

  it("TT-DD38-B-P3 each draft row links to Continue setup and has a Delete draft button", async () => {
    serveLists(
      () => RUNNING,
      () => [draft()],
    );
    renderApp("/batches/running");
    const [row] = bodyRowsOf(await draftTable());
    expect(
      within(row!).getByRole("link", { name: "Continue setup" }),
    ).toHaveAttribute("href", `/batches/new?batch=${IDS.oldBatch}`);
    expect(
      within(row!).getByRole("button", { name: "Delete draft" }),
    ).toBeInTheDocument();
  });

  it("TT-DD38-B-P4 a row shows the sheet name, template name, rows and created date", async () => {
    serveLists(
      () => RUNNING,
      () => [draft()],
    );
    renderApp("/batches/running");
    const [row] = bodyRowsOf(await draftTable());
    const cells = Array.from(row!.querySelectorAll("td")).map(
      (c) => c.textContent ?? "",
    );
    expect(cells[0]).toBe(DRAFT_SHEET);
    expect(cells[1]).toBe("Rahul");
    expect(cells[2]).toContain(String(COUNTS.total));
    expect(cells[3]).toBe(createdText(CREATED));
  });

  it("TT-DD38-B-P5 Delete draft confirms, sends DELETE, then refetches and hides the section", async () => {
    let drafts: Json[] = [draft()];
    const { hits } = serveLists(
      () => RUNNING,
      () => drafts,
    );
    const deleted: string[] = [];
    server.use(
      http.delete("*/batches/:id", ({ params }) => {
        deleted.push(String(params.id));
        drafts = [];
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderApp("/batches/running");
    const [row] = bodyRowsOf(await draftTable());
    await userEvent.click(
      within(row!).getByRole("button", { name: "Delete draft" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Delete this draft?",
    });
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Delete" }),
    );
    await waitFor(() =>
      expect(
        screen.queryByRole("heading", { name: HEADING }),
      ).not.toBeInTheDocument(),
    );
    expect(deleted).toEqual([IDS.oldBatch]);
    expect(
      hits.filter((h) => h.view === "drafts").length,
    ).toBeGreaterThanOrEqual(2);
    expect(
      hits.filter((h) => h.view === "running").length,
    ).toBeGreaterThanOrEqual(2);
  });

  it("TT-DD38-B-P6 the drafts list asks for page 1, 50 rows and view=drafts", async () => {
    const { hits } = serveLists(
      () => RUNNING,
      () => [draft()],
    );
    renderApp("/batches/running");
    await draftTable();
    expect(hits).toContainEqual({ view: "drafts", page: "1", page_size: "50" });
  });

  it("TT-DD38-B-P7 several drafts give one row each with its own links and buttons", async () => {
    const drafts = [
      draft({ id: IDS.oldBatch, sheet_name: "one.csv" }),
      draft({ id: IDS.batch, sheet_name: "two.csv" }),
      draft({
        id: "66666666-6666-4666-8666-666666666666",
        sheet_name: "three.csv",
      }),
    ];
    serveLists(
      () => RUNNING,
      () => drafts,
    );
    renderApp("/batches/running");
    const rows = bodyRowsOf(await draftTable());
    expect(rows).toHaveLength(3);
    expect(
      screen.getAllByRole("link", { name: "Continue setup" }),
    ).toHaveLength(3);
    expect(
      screen.getAllByRole("button", { name: "Delete draft" }),
    ).toHaveLength(3);
  });
});

describe("negative", () => {
  it("TT-DD38-B-N1 with no drafts there is no section, no Continue setup link", async () => {
    serveLists(
      () => RUNNING,
      () => [],
    );
    renderApp("/batches/running");
    await screen.findByRole("table");
    await act(() => sleep(SETTLE_MS));
    expect(
      screen.queryByRole("heading", { name: HEADING }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Continue setup" }),
    ).not.toBeInTheDocument();
    expect(screen.getAllByRole("table")).toHaveLength(1);
  });

  it("TT-DD38-B-N2 an empty running list with drafts shows No running batches and the section", async () => {
    serveLists(
      () => [],
      () => [draft()],
    );
    renderApp("/batches/running");
    expect(await screen.findByText("No running batches")).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: HEADING }),
    ).toBeInTheDocument();
  });

  it("TT-DD38-B-N3 an empty running list without drafts shows only No running batches", async () => {
    serveLists(
      () => [],
      () => [],
    );
    renderApp("/batches/running");
    expect(await screen.findByText("No running batches")).toBeInTheDocument();
    await act(() => sleep(SETTLE_MS));
    expect(
      screen.queryByRole("heading", { name: HEADING }),
    ).not.toBeInTheDocument();
  });

  it("TT-DD38-B-N4 Keep closes the dialog and sends no DELETE", async () => {
    const { deletes } = serveLists(
      () => RUNNING,
      () => [draft()],
    );
    renderApp("/batches/running");
    const [row] = bodyRowsOf(await draftTable());
    await userEvent.click(
      within(row!).getByRole("button", { name: "Delete draft" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Delete this draft?",
    });
    await userEvent.click(within(dialog).getByRole("button", { name: "Keep" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await act(() => sleep(50));
    expect(deletes).toEqual([]);
    expect(
      within(row!).getByRole("button", { name: "Delete draft" }),
    ).toBeInTheDocument();
  });

  it("TT-DD38-B-N5 a failed DELETE shows its message and keeps the draft row", async () => {
    serveLists(
      () => RUNNING,
      () => [draft()],
    );
    server.use(
      http.delete("*/batches/:id", () =>
        apiError(500, "INTERNAL_ERROR", "The draft could not be deleted."),
      ),
    );
    renderApp("/batches/running");
    const [row] = bodyRowsOf(await draftTable());
    await userEvent.click(
      within(row!).getByRole("button", { name: "Delete draft" }),
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
    expect(
      screen.getByRole("link", { name: "Continue setup" }),
    ).toBeInTheDocument();
  });
});

describe("edge", () => {
  it("TT-DD38-B-E1 a double click on Delete confirm sends one DELETE", async () => {
    const calls: string[] = [];
    serveLists(
      () => RUNNING,
      () => [draft()],
    );
    server.use(
      http.delete("*/batches/:id", async () => {
        calls.push("DELETE");
        await delay(50);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderApp("/batches/running");
    const [row] = bodyRowsOf(await draftTable());
    await userEvent.click(
      within(row!).getByRole("button", { name: "Delete draft" }),
    );
    const confirm = within(await screen.findByRole("dialog")).getByRole(
      "button",
      {
        name: "Delete",
      },
    );
    await userEvent.dblClick(confirm);
    await waitFor(() => expect(calls.length).toBeGreaterThan(0));
    await act(() => sleep(150));
    expect(calls).toEqual(["DELETE"]);
  });

  it.each(["completed", "failed"] as const)(
    "TT-DD38-B-E2 the %s view never asks for drafts",
    async (view) => {
      const { hits } = serveLists(
        () => RUNNING,
        () => [draft()],
      );
      renderApp(`/batches/${view}`);
      expect(
        await screen.findByText(new RegExp(`No ${view} batches`)),
      ).toBeInTheDocument();
      await act(() => sleep(50));
      expect(hits.some((h) => h.view === "drafts")).toBe(false);
      expect(
        screen.queryByRole("heading", { name: HEADING }),
      ).not.toBeInTheDocument();
    },
  );

  it("TT-DD38-B-E3 the running view asks for drafts with the same paging as its own list", async () => {
    const { hits } = serveLists(
      () => RUNNING,
      () => [],
    );
    renderApp("/batches/running");
    await screen.findByRole("table");
    await waitFor(() =>
      expect(hits.some((h) => h.view === "drafts")).toBe(true),
    );
    const running = hits.find((h) => h.view === "running");
    const drafts = hits.find((h) => h.view === "drafts");
    expect(drafts).toEqual({
      view: "drafts",
      page: running?.page,
      page_size: running?.page_size,
    });
  });
});
