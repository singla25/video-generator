// BL-8 Startup schema check: one clear banner when the database is behind the code.
// Case IDs: TT-SB-<P|N|E><n>.
//
// CONTRACT (frontend/src):
//   GET /system/status gains schema: { state: "ok"|"behind"|"ahead"|"empty", current, expected, message }.
//   state "behind" or "empty", OR any API call answering { code: "DB_NEEDS_MIGRATION", message }:
//     a full-width banner role="alert" with exactly the server's message and the line
//     "The dashboard will work again after the migration is applied."; the database-error
//     toasts of the batch/template screens are hidden.
//   state "ok" or "ahead": nothing shown. A failing status call raises no false alarm.
import { screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { renderApp } from "../helpers";
import { apiError } from "../mocks/handlers";
import { server } from "../mocks/server";

const BEHIND =
  "The database needs migration 0003 (it is at 0002). Ask the admin to run it.";
const EMPTY =
  "The database needs migration 0003 (it is at none). Ask the admin to run it.";
const AHEAD = "The database is newer than this version of the app.";
const WORKS_AGAIN = "The dashboard will work again after the migration is applied.";
const DB_DOWN = "The database is not reachable right now. Please try again in a moment.";

function schemaStatus(state: string, message: string, current: string | null = "0002") {
  return http.get("*/system/status", () =>
    HttpResponse.json({
      worker_alive: true,
      queue_depth: 0,
      redis_ok: true,
      ai_mode: "fake",
      schema: { state, current, expected: "0003", message },
    }),
  );
}

const needsMigration = () =>
  apiError(503, "DB_NEEDS_MIGRATION", BEHIND);

describe("schema banner", () => {
  it("TT-SB-P1 shows the server message and the follow-up line when the database is behind", async () => {
    server.use(schemaStatus("behind", BEHIND));
    renderApp("/");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(BEHIND);
    expect(alert).toHaveTextContent(WORKS_AGAIN);
  });

  it("TT-SB-P2 shows the banner for an empty database with 'none'", async () => {
    server.use(schemaStatus("empty", EMPTY, null));
    renderApp("/templates");
    expect(await screen.findByRole("alert")).toHaveTextContent(EMPTY);
  });

  it("TT-SB-P3 shows the banner when an API call answers DB_NEEDS_MIGRATION", async () => {
    server.use(http.get("*/batches", () => needsMigration()));
    renderApp("/");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(BEHIND);
    expect(alert).toHaveTextContent(WORKS_AGAIN);
  });

  it("TT-SB-P4 the banner is also shown on the templates screen (call-driven)", async () => {
    server.use(http.get("*/templates", () => needsMigration()));
    renderApp("/templates");
    expect(await screen.findByRole("alert")).toHaveTextContent(BEHIND);
  });

  it("TT-SB-N1 shows no banner when the state is ok", async () => {
    server.use(schemaStatus("ok", "", "0003"));
    renderApp("/");
    await screen.findByText(/batches|templates/i, undefined, { timeout: 3000 }).catch(() => undefined);
    expect(screen.queryByText(WORKS_AGAIN)).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("TT-SB-N2 shows no banner when the database is ahead", async () => {
    server.use(schemaStatus("ahead", AHEAD, "0004"));
    renderApp("/");
    await new Promise((r) => setTimeout(r, 300));
    expect(screen.queryByText(AHEAD)).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("TT-SB-N3 a failing status call raises no false alarm", async () => {
    server.use(http.get("*/system/status", () => apiError(500, "INTERNAL_ERROR", "x")));
    renderApp("/");
    await new Promise((r) => setTimeout(r, 300));
    expect(screen.queryByText(WORKS_AGAIN)).not.toBeInTheDocument();
  });

  it("TT-SB-N4 a status body without a schema block (old server) shows no banner", async () => {
    renderApp("/");
    await new Promise((r) => setTimeout(r, 300));
    expect(screen.queryByText(WORKS_AGAIN)).not.toBeInTheDocument();
  });

  it("TT-SB-E1 hides the database-error toast of the batch screen while migrating", async () => {
    server.use(
      schemaStatus("behind", BEHIND),
      http.get("*/batches", () => apiError(503, "DB_NEEDS_MIGRATION", BEHIND)),
    );
    renderApp("/");
    await screen.findByText(WORKS_AGAIN);
    expect(screen.queryByText(DB_DOWN)).not.toBeInTheDocument();
    expect(screen.getAllByRole("alert")).toHaveLength(1); // one clear message, not a pile
  });

  it("TT-SB-E2 the banner text is exactly the server's message, even an unusual one", async () => {
    const odd = "Run migration 0003 — डेटाबेस & <b>x</b>";
    server.use(schemaStatus("behind", odd));
    renderApp("/");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(odd);
    expect(alert.querySelector("b")).toBeNull(); // rendered as text, never as HTML
  });

  it("TT-SB-E3 the banner disappears after the migration is applied", async () => {
    let state = "behind";
    server.use(
      http.get("*/system/status", () =>
        HttpResponse.json({
          worker_alive: true,
          queue_depth: 0,
          redis_ok: true,
          ai_mode: "fake",
          schema:
            state === "ok"
              ? { state, current: "0003", expected: "0003", message: "" }
              : { state, current: "0002", expected: "0003", message: BEHIND },
        }),
      ),
    );
    renderApp("/");
    await screen.findByText(WORKS_AGAIN);
    state = "ok";
    await waitFor(() => expect(screen.queryByText(WORKS_AGAIN)).not.toBeInTheDocument(), {
      timeout: 8000,
    });
  }, 12000);
});
