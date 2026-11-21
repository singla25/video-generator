// A-N2 / BL-6 AC5: "Closest matches" candidate buttons in the template slot editor.
// See docs/test-tree/better-name-detection-ui.md.
//
// CONTRACT (frontend/src):
//   The analyse response (POST /templates/<id>/analyse) gains `candidates` (0 to 3 items of
//   { text, start_s, end_s, closeness, confidence }, best first). The UI keeps it in memory only. When no
//   slot was found and candidates exist, the slot editor shows role="group" aria-label "Closest matches"
//   with one list item per candidate ("{start}-{end} s" to 1 decimal, "{round(closeness*100)}% close") and a
//   button "Use this word" that calls the existing PUT /templates/<id>/slot with the candidate's start/end.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { renderApp } from "../helpers";
import { template } from "../mocks/data";
import { apiError } from "../mocks/handlers";
import { server } from "../mocks/server";

type Json = Record<string, unknown>;
interface Candidate {
  text: string;
  start_s: number;
  end_s: number;
  closeness: number;
  confidence: number;
}

const cand = (
  text: string,
  start_s: number,
  closeness = 0.7,
  end_s = start_s + 0.5,
): Candidate => ({
  text,
  start_s,
  end_s,
  closeness,
  confidence: 0.5,
});
const THREE = [
  cand("Kishan", 1.234, 0.804, 1.678),
  cand("Krishna", 4, 0.66),
  cand("Kiran", 9.05, 0.61),
];
const NO_SLOT = template({
  slot: null,
  slot_source: null,
  slot_confirmed: false,
  needs_manual_slot: true,
  usable: false,
});

interface Options {
  putDelay?: Promise<void>;
  putError?: Response;
}

/** A stateful fake of upload + analyse + set-slot. `analyses` is consumed one per upload. */
function api(analyses: Json[], opts: Options = {}) {
  let templates: Json[] = [];
  const seen = { puts: [] as { id: string; body: Json }[], analyseCalls: 0 };
  let uploads = 0;
  server.use(
    http.get("*/templates", () => HttpResponse.json({ templates })),
    http.post("*/templates", () => {
      uploads += 1;
      const created = {
        ...NO_SLOT,
        id: `00000000-0000-4000-8000-00000000000${uploads}`,
      };
      templates = [...templates, created];
      return HttpResponse.json(created, { status: 201 });
    }),
    http.post("*/templates/:id/analyse", ({ params }) => {
      const body = analyses[seen.analyseCalls] ?? {};
      seen.analyseCalls += 1;
      if (body.slot) {
        templates = templates.map((t) =>
          t.id === params.id
            ? template({
                ...NO_SLOT,
                id: t.id,
                slot: body.slot,
                needs_manual_slot: false,
              })
            : t,
        );
      }
      return HttpResponse.json(body);
    }),
    http.put("*/templates/:id/slot", async ({ request, params }) => {
      const body = (await request.json()) as { start_s: number; end_s: number };
      seen.puts.push({ id: String(params.id), body });
      await opts.putDelay;
      if (opts.putError) return opts.putError;
      const next = template({
        ...NO_SLOT,
        id: String(params.id),
        slot: { start_s: body.start_s, end_s: body.end_s },
        slot_source: "MANUAL",
        needs_manual_slot: false,
      });
      templates = templates.map((t) => (t.id === params.id ? next : t));
      return HttpResponse.json(next);
    }),
  );
  return seen;
}

async function upload() {
  await userEvent.click(
    await screen.findByRole("button", { name: "New template" }),
  );
  const zone = screen.getByLabelText("Template video");
  const input =
    zone instanceof HTMLInputElement
      ? zone
      : (zone.querySelector('input[type="file"]') as HTMLInputElement);
  await userEvent.upload(
    input,
    new File(["v"], "intro.mp4", { type: "video/mp4" }),
    {
      applyAccept: false,
    },
  );
  await userEvent.type(screen.getByLabelText("Word to replace"), "Krishan");
  await userEvent.click(
    screen.getByRole("button", { name: "Upload template" }),
  );
}

const group = () => screen.findByRole("group", { name: "Closest matches" });
const noGroup = () => screen.queryByRole("group", { name: "Closest matches" });

async function analyseWith(candidates: unknown, extra: Json = {}) {
  const body = candidates === undefined ? extra : { ...extra, candidates };
  const seen = api([body]);
  renderApp("/templates");
  await upload();
  return seen;
}

describe("name candidate buttons", () => {
  it.each([1, 2, 3])(
    'NC-P1 shows %i candidate(s) with a "Use this word" button each',
    async (n) => {
      await analyseWith(THREE.slice(0, n));
      const g = await group();
      expect(within(g).getAllByRole("listitem")).toHaveLength(n);
      expect(
        within(g).getAllByRole("button", { name: "Use this word" }),
      ).toHaveLength(n);
    },
  );

  it("NC-P2 lists candidates best first with word, time and rounded percentage", async () => {
    await analyseWith(THREE);
    const items = within(await group()).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Kishan");
    expect(items[0]).toHaveTextContent("1.2-1.7 s");
    expect(items[0]).toHaveTextContent("80% close"); // 0.804 rounds to 80
    expect(items[1]).toHaveTextContent("Krishna");
    expect(items[1]).toHaveTextContent("4.0-4.5 s");
    expect(items[1]).toHaveTextContent("66% close");
    expect(items[2]).toHaveTextContent("Kiran");
    expect(items[2]).toHaveTextContent("61% close");
  });

  it('NC-P3 "Use this word" sets the slot, the group goes, confirmation is still needed', async () => {
    const seen = await analyseWith(THREE);
    const second = within(await group()).getAllByRole("listitem")[1];
    await userEvent.click(
      within(second).getByRole("button", { name: "Use this word" }),
    );
    await waitFor(() => expect(seen.puts).toHaveLength(1));
    expect(seen.puts[0].body).toMatchObject({ start_s: 4, end_s: 4.5 });
    await waitFor(() => expect(noGroup()).not.toBeInTheDocument());
    expect(
      await screen.findByRole("spinbutton", { name: "Slot start (s)" }),
    ).toHaveValue(4);
    expect(
      screen.getByRole("button", { name: "Confirm slot" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Slot confirmed")).not.toBeInTheDocument();
  });

  it("NC-N1 an empty candidate list keeps today's message and shows no group", async () => {
    await analyseWith([]);
    expect(
      await screen.findByText(/could not be found automatically/i),
    ).toBeInTheDocument();
    expect(noGroup()).not.toBeInTheDocument();
  });

  it("NC-N2 a found slot shows no group even if candidates came with it", async () => {
    await analyseWith(THREE, { slot: { start_s: 2, end_s: 3 } });
    expect(
      await screen.findByRole("spinbutton", { name: "Slot start (s)" }),
    ).toHaveValue(2);
    expect(noGroup()).not.toBeInTheDocument();
  });

  it("NC-N3 an old response without `candidates` is treated as empty", async () => {
    await analyseWith(undefined);
    expect(
      await screen.findByText(/could not be found automatically/i),
    ).toBeInTheDocument();
    expect(noGroup()).not.toBeInTheDocument();
  });

  it.each([
    [409, "SLOT_LOCKED", "The slot cannot change now."],
    [500, "INTERNAL", "Something broke on the server."],
  ])(
    "NC-N4 API error %i shows its message and keeps the group",
    async (status, code, message) => {
      const seen = api([{ candidates: THREE }], {
        putError: apiError(status, code, message),
      });
      renderApp("/templates");
      await upload();
      const g = await group();
      await userEvent.click(
        within(g).getAllByRole("button", { name: "Use this word" })[0],
      );
      await waitFor(() => expect(seen.puts).toHaveLength(1));
      expect(await screen.findByRole("alert")).toHaveTextContent(message);
      expect(noGroup()).toBeInTheDocument();
    },
  );

  it("NC-E1 a very long word and Devanagari text are shown whole", async () => {
    const long = "क".repeat(80);
    await analyseWith([
      cand("कृष्ण", 1),
      cand(long, 2),
      cand("Ab".repeat(60), 3),
    ]);
    const items = within(await group()).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("कृष्ण");
    expect(items[1]).toHaveTextContent(long);
    expect(items[2]).toHaveTextContent("Ab".repeat(60));
  });

  it("NC-E2 a double click sends one request, and buttons are disabled while pending", async () => {
    let release: () => void = () => undefined;
    const putDelay = new Promise<void>((resolve) => {
      release = resolve;
    });
    const seen = api([{ candidates: THREE }], { putDelay });
    renderApp("/templates");
    await upload();
    const buttons = within(await group()).getAllByRole("button", {
      name: "Use this word",
    });
    await userEvent.dblClick(buttons[0]);
    await waitFor(() => expect(seen.puts).toHaveLength(1));
    for (const b of within(await group()).getAllByRole("button", {
      name: "Use this word",
    })) {
      expect(b).toBeDisabled();
    }
    release();
    await waitFor(() => expect(noGroup()).not.toBeInTheDocument());
    expect(seen.puts).toHaveLength(1);
  });

  it("NC-E3 a new analyse clears the earlier candidates", async () => {
    api([{ candidates: THREE }, { candidates: [] }]);
    renderApp("/templates");
    await upload();
    await group();
    await upload();
    await waitFor(() => expect(noGroup()).not.toBeInTheDocument());
  });

  it("NC-E4 candidates are not kept after leaving and returning to the Templates page", async () => {
    api([{ candidates: THREE }]);
    renderApp("/templates");
    await upload();
    await group();
    await userEvent.click(
      screen.getByRole("link", { name: /overview|home|dashboard/i }),
    );
    await userEvent.click(
      await screen.findByRole("link", { name: /templates/i }),
    );
    await screen.findByTestId("template-card");
    expect(noGroup()).not.toBeInTheDocument();
  });
});
