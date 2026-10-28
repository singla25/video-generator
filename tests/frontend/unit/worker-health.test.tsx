// FIX-WORKER-1 (DD-29) The dashboard must say when the background worker is not running.
// Case IDs: TT-WH-<P|N|E><n>.
//
// CONTRACT (frontend/src):
//   API        GET /system/status -> { worker_alive: boolean, queue_depth: number | null,
//              redis_ok: boolean }, polled every POLL_INTERVAL_MS (2 s) while the app is open
//              and the user is logged in (no call on /login).
//   Banner     inside the app shell (every logged-in page): role="alert" with the text
//              "The background worker is not running, so videos won't be made. Start it with
//              scripts/dev_up.sh" shown ONLY when worker_alive === false AND there is work
//              waiting (a batch in GET /batches with counts.queued > 0 or preview.status
//              PENDING). Hidden when the worker is alive, when there is nothing to do, and
//              while the status call is loading or failing (no false alarm).
//   Preview    in the wizard, a preview that stays PENDING for more than 30 s shows
//              "Preview is taking longer than expected" (plus "the background worker is not
//              running" when worker_alive is false) and a Retry button that POSTs
//              /batches/<id>/preview again.
//   401        from the status call sends the user to the login screen.
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, delay, http } from "msw";
import { describe, expect, it, vi } from "vitest";

import { renderApp } from "../helpers";
import { COUNTS, IDS, batch, report } from "../mocks/data";
import { apiError } from "../mocks/handlers";
import { setReducedMotion } from "../motion";
import { server } from "../mocks/server";

const BANNER = /The background worker is not running, so videos won't be made/;
const START_HINT = /scripts\/dev_up\.sh/;

function workerStatus(alive: boolean, redisOk = true) {
  return http.get("*/system/status", () =>
    HttpResponse.json({
      worker_alive: alive,
      queue_depth: alive ? 0 : 20,
      redis_ok: redisOk,
    }),
  );
}

function batchesList(over: Record<string, unknown>) {
  return http.get("*/batches", () =>
    HttpResponse.json({
      batches: [batch(over)],
      page: 1,
      page_size: 50,
      total: 1,
      total_pages: 1,
    }),
  );
}

const WAITING = {};
const NOTHING_TO_DO = {
  status: "COMPLETED",
  counts: { ...COUNTS, queued: 0, processing: 0 },
  preview: { status: "READY", approved: true },
};
const ONLY_PENDING_PREVIEW = {
  status: "DRAFT",
  counts: { ...COUNTS, queued: 0, processing: 0 },
  preview: { status: "PENDING", approved: false },
};

describe("worker banner", () => {
  it("TT-WH-P1 shows an alert with the start hint when the worker is down and rows are queued", async () => {
    server.use(workerStatus(false), batchesList(WAITING));
    renderApp("/");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(BANNER);
    expect(alert).toHaveTextContent(START_HINT);
  });

  it("TT-WH-P2 the banner is in the shell, so other pages show it too", async () => {
    server.use(workerStatus(false), batchesList(WAITING));
    renderApp("/templates");
    expect(await screen.findByRole("alert")).toHaveTextContent(BANNER);
  });

  it("TT-WH-P3 a pending preview alone (no queued rows) is enough work to warn", async () => {
    server.use(workerStatus(false), batchesList(ONLY_PENDING_PREVIEW));
    renderApp("/");
    expect(await screen.findByRole("alert")).toHaveTextContent(BANNER);
  });

  it("TT-WH-N1 no banner when the worker is alive", async () => {
    server.use(workerStatus(true), batchesList(WAITING));
    renderApp("/");
    await screen.findByRole("navigation", { name: "Primary" });
    await new Promise((r) => setTimeout(r, 150));
    expect(screen.queryByText(BANNER)).not.toBeInTheDocument();
  });

  it("TT-WH-N2 no banner when the worker is down but there is nothing to do", async () => {
    server.use(workerStatus(false), batchesList(NOTHING_TO_DO));
    renderApp("/");
    await screen.findByRole("navigation", { name: "Primary" });
    await new Promise((r) => setTimeout(r, 150));
    expect(screen.queryByText(BANNER)).not.toBeInTheDocument();
  });

  it.each([
    ["a 500", () => apiError(500, "INTERNAL_ERROR", "Something went wrong.")],
    [
      "a 503",
      () =>
        apiError(503, "QUEUE_UNAVAILABLE", "The job queue is not reachable."),
    ],
    ["a network failure", () => HttpResponse.error()],
    [
      "a non-JSON answer",
      () => new HttpResponse("<html>bad gateway</html>", { status: 502 }),
    ],
  ])(
    "TT-WH-N3 %s from the status call is not a false alarm",
    async (_name, answer) => {
      server.use(
        http.get("*/system/status", () => answer()),
        batchesList(WAITING),
      );
      renderApp("/");
      await screen.findByRole("navigation", { name: "Primary" });
      await new Promise((r) => setTimeout(r, 150));
      expect(screen.queryByText(BANNER)).not.toBeInTheDocument();
    },
  );

  it("TT-WH-N4 while the status call is still loading there is no banner", async () => {
    server.use(
      http.get("*/system/status", async () => {
        await delay("infinite");
        return HttpResponse.json({});
      }),
      batchesList(WAITING),
    );
    renderApp("/");
    await screen.findByRole("navigation", { name: "Primary" });
    await new Promise((r) => setTimeout(r, 150));
    expect(screen.queryByText(BANNER)).not.toBeInTheDocument();
  });

  it("TT-WH-N5 if the batch list cannot be read the banner is not guessed", async () => {
    server.use(
      workerStatus(false),
      http.get("*/batches", () =>
        apiError(500, "INTERNAL_ERROR", "Something went wrong."),
      ),
    );
    renderApp("/");
    await screen.findByRole("navigation", { name: "Primary" });
    await new Promise((r) => setTimeout(r, 150));
    expect(screen.queryByText(BANNER)).not.toBeInTheDocument();
  });

  it("TT-WH-E1 a 401 from the status call sends the user to login", async () => {
    server.use(
      http.get("*/system/status", () =>
        apiError(401, "UNAUTHENTICATED", "Please log in to continue."),
      ),
    );
    renderApp("/");
    expect(
      await screen.findByRole("button", { name: "Log in" }),
    ).toBeInTheDocument();
  });

  it("TT-WH-E2 the login screen does not call the status endpoint", async () => {
    let calls = 0;
    server.use(
      http.get("*/system/status", () => {
        calls += 1;
        return HttpResponse.json({
          worker_alive: false,
          queue_depth: 0,
          redis_ok: true,
        });
      }),
    );
    renderApp("/login");
    await screen.findByRole("button", { name: "Log in" });
    await new Promise((r) => setTimeout(r, 150));
    expect(calls).toBe(0);
  });

  it("TT-WH-E3 the banner appears and disappears as the worker stops and starts (polling)", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let alive = true;
    server.use(
      http.get("*/system/status", () =>
        HttpResponse.json({
          worker_alive: alive,
          queue_depth: 5,
          redis_ok: true,
        }),
      ),
      batchesList(WAITING),
    );
    renderApp("/");
    await screen.findByRole("navigation", { name: "Primary" });
    expect(screen.queryByText(BANNER)).not.toBeInTheDocument();
    alive = false;
    await act(() => vi.advanceTimersByTimeAsync(6000));
    expect(await screen.findByText(BANNER)).toBeInTheDocument();
    alive = true;
    await act(() => vi.advanceTimersByTimeAsync(6000));
    await waitFor(() =>
      expect(screen.queryByText(BANNER)).not.toBeInTheDocument(),
    );
  });

  it("TT-WH-E4 Redis down (redis_ok false) with queued work still warns", async () => {
    server.use(workerStatus(false, false), batchesList(WAITING));
    renderApp("/");
    expect(await screen.findByRole("alert")).toHaveTextContent(BANNER);
  });

  it("TT-WH-E5 with reduced motion the banner is static (no animation classes)", async () => {
    setReducedMotion(true);
    server.use(workerStatus(false), batchesList(WAITING));
    renderApp("/");
    const alert = await screen.findByRole("alert");
    expect(alert.outerHTML).not.toMatch(/animate-|transition/);
  });

  it("TT-WH-E6 the banner shows no connection string or internal detail", async () => {
    server.use(workerStatus(false, false), batchesList(WAITING));
    renderApp("/");
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).not.toMatch(
      /redis:\/\/|password|Traceback|127\.0\.0\.1/i,
    );
  });
});

describe("slow preview", () => {
  function pendingPreview(alive: boolean) {
    const posts: string[] = [];
    server.use(
      workerStatus(alive),
      http.get("*/batches/:id", () =>
        HttpResponse.json(
          batch({
            status: "DRAFT",
            preview: { status: "PENDING", approved: false },
            report: report({ valid_rows: 8 }),
            counts: { ...COUNTS, queued: 0, processing: 0 },
          }),
        ),
      ),
      http.post("*/batches/:id/preview", ({ params }) => {
        posts.push(String(params.id));
        return HttpResponse.json(
          batch({
            status: "DRAFT",
            preview: { status: "PENDING", approved: false },
          }),
          { status: 202 },
        );
      }),
    );
    return posts;
  }

  async function waitThrough(seconds: number) {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderApp(`/batches/new?batch=${IDS.batch}`);
    await screen.findByText("Generating preview...");
    await act(() => vi.advanceTimersByTimeAsync(seconds * 1000));
  }

  it("TT-WH-P4 after 30 s pending it says the preview is taking longer and offers Retry", async () => {
    pendingPreview(true);
    await waitThrough(31);
    expect(
      await screen.findByText(/Preview is taking longer than expected/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeEnabled();
  });

  it("TT-WH-P5 with the worker down the message also names the worker", async () => {
    pendingPreview(false);
    await waitThrough(31);
    const message = await screen.findByText(
      /Preview is taking longer than expected/,
    );
    expect(message.textContent).toMatch(
      /the background worker is not running/i,
    );
  });

  it("TT-WH-P6 Retry posts the preview request again", async () => {
    const posts = pendingPreview(true);
    await waitThrough(31);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.click(await screen.findByRole("button", { name: /retry/i }));
    await waitFor(() => expect(posts).toEqual([IDS.batch]));
  });

  it("TT-WH-N6 with a live worker the message does not blame the worker", async () => {
    pendingPreview(true);
    await waitThrough(31);
    const message = await screen.findByText(
      /Preview is taking longer than expected/,
    );
    expect(message.textContent).not.toMatch(/not running/i);
  });

  it("TT-WH-N7 nothing is shown before 30 s have passed", async () => {
    pendingPreview(true);
    await waitThrough(29);
    expect(
      screen.queryByText(/taking longer than expected/),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /retry/i }),
    ).not.toBeInTheDocument();
  });

  it("TT-WH-E7 a failing status call does not add a worker accusation to the wait message", async () => {
    pendingPreview(true);
    server.use(http.get("*/system/status", () => HttpResponse.error()));
    await waitThrough(31);
    const message = await screen.findByText(
      /Preview is taking longer than expected/,
    );
    expect(message.textContent).not.toMatch(/not running/i);
  });

  it("TT-WH-E8 a preview that finishes before 30 s never shows the slow message", async () => {
    let state = "PENDING";
    server.use(
      workerStatus(true),
      http.get("*/batches/:id", () =>
        HttpResponse.json(
          batch({
            status: "DRAFT",
            preview: { status: state, approved: false },
            report: report({ valid_rows: 8 }),
          }),
        ),
      ),
    );
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderApp(`/batches/new?batch=${IDS.batch}`);
    await screen.findByText("Generating preview...");
    await act(() => vi.advanceTimersByTimeAsync(10_000));
    state = "READY";
    await act(() => vi.advanceTimersByTimeAsync(10_000));
    await act(() => vi.advanceTimersByTimeAsync(30_000));
    expect(
      screen.queryByText(/taking longer than expected/),
    ).not.toBeInTheDocument();
  });
});
