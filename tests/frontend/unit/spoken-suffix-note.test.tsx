// BL-12 Spoken suffix note in the preview step. Case IDs: BL12-<P|N|E><n>.
// Contract is also written in docs/test-tree/spoken-suffix-note.md.
//
// CONTRACT (frontend/src, PreviewPanel in pages/wizard):
//   API   GET /system/status -> spoken_suffix?: string ("" = off; absent on older servers).
//   UI    once the status is loaded, inside the Preview panel: role="note"
//         data-testid="spoken-suffix-note" with the exact text
//           non-empty: "After the name the voice also says: {suffix}. This is a global setting
//                       (VIDGEN_SPOKEN_SUFFIX) that applies to every template."
//           empty:     "No spoken suffix is set. This is a global setting (VIDGEN_SPOKEN_SUFFIX)."
//         Any preview state, fake and local mode. Nothing while loading, on a failed status
//         call, or when the key is missing. The suffix is plain text, never markup.
import { screen, waitFor, within } from "@testing-library/react";
import { HttpResponse, delay, http } from "msw";
import { describe, expect, it } from "vitest";

import { renderApp } from "../helpers";
import { IDS, batch, report } from "../mocks/data";
import { server } from "../mocks/server";

const TESTID = "spoken-suffix-note";
const GLOBAL = "(VIDGEN_SPOKEN_SUFFIX)";
const WIZARD_PATH = `/batches/new?batch=${IDS.batch}`;
const HINDI = "जी";

const withSuffix = (s: string) =>
  `After the name the voice also says: ${s}. This is a global setting ${GLOBAL} that applies to every template.`;
const OFF_TEXT = `No spoken suffix is set. This is a global setting ${GLOBAL}.`;

type Json = Record<string, unknown>;

function draft(preview: Json | null) {
  server.use(
    http.get("*/batches/:id", () =>
      HttpResponse.json(
        batch({ status: "DRAFT", preview, report: report({ valid_rows: 8 }) }),
      ),
    ),
  );
}

function setup(
  statusExtra: Json | null,
  preview: Json | null = { status: "READY", approved: false },
) {
  server.use(
    http.get("*/system/status", () =>
      statusExtra === null
        ? HttpResponse.json({ detail: "boom" }, { status: 500 })
        : HttpResponse.json({
            worker_alive: true,
            queue_depth: 0,
            redis_ok: true,
            ...statusExtra,
          }),
    ),
  );
  draft(preview);
}

async function panel() {
  renderApp(WIZARD_PATH);
  return (await screen.findByRole("heading", { name: "Preview" }))
    .parentElement as HTMLElement;
}

describe("spoken suffix note", () => {
  it("BL12-P1 shows the default Devanagari suffix text", async () => {
    setup({ ai_mode: "fake", spoken_suffix: HINDI });
    renderApp(WIZARD_PATH);
    const note = await screen.findByTestId(TESTID);
    expect(note.textContent?.trim()).toBe(withSuffix(HINDI));
  });

  it("BL12-P2 shows a Latin suffix", async () => {
    setup({ ai_mode: "fake", spoken_suffix: "ji" });
    renderApp(WIZARD_PATH);
    expect((await screen.findByTestId(TESTID)).textContent?.trim()).toBe(
      withSuffix("ji"),
    );
  });

  it("BL12-P3 shows the off text for an empty suffix", async () => {
    setup({ ai_mode: "fake", spoken_suffix: "" });
    renderApp(WIZARD_PATH);
    expect((await screen.findByTestId(TESTID)).textContent?.trim()).toBe(
      OFF_TEXT,
    );
  });

  it.each([
    ["PENDING", { status: "PENDING", approved: false }],
    ["READY", { status: "READY", approved: false }],
    ["FAILED", { status: "FAILED", approved: false }],
    ["STALE", { status: "STALE", approved: false }],
    ["NONE", null],
  ])("BL12-P4 is shown while the preview is %s", async (_name, preview) => {
    setup({ ai_mode: "fake", spoken_suffix: HINDI }, preview);
    renderApp(WIZARD_PATH);
    expect(await screen.findByTestId(TESTID)).toHaveTextContent(
      withSuffix(HINDI),
    );
  });

  it.each(["fake", "local"])("BL12-P5 is shown in %s mode", async (mode) => {
    setup({ ai_mode: mode, spoken_suffix: HINDI });
    renderApp(WIZARD_PATH);
    expect(await screen.findByTestId(TESTID)).toHaveTextContent(
      withSuffix(HINDI),
    );
  });

  it("BL12-P6 sits inside the preview panel next to the Generate preview button", async () => {
    setup({ ai_mode: "local", spoken_suffix: HINDI });
    const p = await panel();
    const note = await within(p).findByTestId(TESTID);
    expect(
      within(p).getByRole("button", { name: "Generate preview" }),
    ).toBeInTheDocument();
    expect(p.contains(note)).toBe(true);
  });

  it("BL12-P7 is a role=note reachable by a screen reader", async () => {
    setup({ ai_mode: "fake", spoken_suffix: HINDI });
    renderApp(WIZARD_PATH);
    const note = await screen.findByTestId(TESTID);
    expect(note).toHaveAttribute("role", "note");
    expect(note.closest("[aria-hidden='true']")).toBeNull();
    expect(note).toBeVisible();
  });

  it("BL12-N1 shows nothing while the status is loading", async () => {
    draft({ status: "READY", approved: false });
    server.use(
      http.get("*/system/status", async () => {
        await delay("infinite");
        return HttpResponse.json({});
      }),
    );
    const p = await panel();
    await within(p).findByRole("button", { name: "Generate preview" });
    expect(screen.queryByTestId(TESTID)).toBeNull();
  });

  it("BL12-N2 shows nothing when the status call fails (no false alarm)", async () => {
    setup(null);
    const p = await panel();
    await within(p).findByRole("button", { name: "Generate preview" });
    await new Promise((r) => setTimeout(r, 100));
    expect(screen.queryByTestId(TESTID)).toBeNull();
  });

  it("BL12-N3 shows nothing when an older server sends no spoken_suffix key", async () => {
    setup({ ai_mode: "fake" });
    renderApp(WIZARD_PATH);
    // The fake-AI note proves the status was loaded.
    await screen.findByText(/Fake AI is on/);
    expect(screen.queryByTestId(TESTID)).toBeNull();
    expect(screen.queryByText(/spoken suffix/i)).toBeNull();
  });

  it("BL12-E1 renders a markup-like value as plain text", async () => {
    setup({ ai_mode: "fake", spoken_suffix: "<b>x</b>" });
    renderApp(WIZARD_PATH);
    const note = await screen.findByTestId(TESTID);
    expect(note.textContent?.trim()).toBe(withSuffix("<b>x</b>"));
    expect(note.querySelector("b")).toBeNull();
  });

  it("BL12-E2 shows a 20 character suffix in full", async () => {
    const long = HINDI.repeat(10);
    expect(long).toHaveLength(20);
    setup({ ai_mode: "fake", spoken_suffix: long });
    renderApp(WIZARD_PATH);
    expect(await screen.findByTestId(TESTID)).toHaveTextContent(
      withSuffix(long),
    );
  });

  it("BL12-E3 surrounding spaces from the server do not break the sentence", async () => {
    setup({ ai_mode: "fake", spoken_suffix: ` ${HINDI} ` });
    renderApp(WIZARD_PATH);
    expect(await screen.findByTestId(TESTID)).toHaveTextContent(
      withSuffix(HINDI),
    );
  });

  it("BL12-E4 appears once, also after the status is refetched", async () => {
    let calls = 0;
    server.use(
      http.get("*/system/status", () => {
        calls += 1;
        return HttpResponse.json({
          worker_alive: true,
          queue_depth: 0,
          redis_ok: true,
          ai_mode: "fake",
          spoken_suffix: HINDI,
        });
      }),
    );
    draft({ status: "READY", approved: false });
    renderApp(WIZARD_PATH);
    await screen.findByTestId(TESTID);
    window.dispatchEvent(new Event("focus"));
    document.dispatchEvent(new Event("visibilitychange"));
    await waitFor(() => expect(calls).toBeGreaterThanOrEqual(1));
    expect(screen.getAllByTestId(TESTID)).toHaveLength(1);
  });

  it("BL12-E5 the local spoken-name box and the note both show", async () => {
    setup({ ai_mode: "local", spoken_suffix: HINDI });
    renderApp(WIZARD_PATH);
    expect(await screen.findByLabelText("Spoken name")).toBeInTheDocument();
    expect(await screen.findByTestId(TESTID)).toHaveTextContent(
      withSuffix(HINDI),
    );
  });
});
