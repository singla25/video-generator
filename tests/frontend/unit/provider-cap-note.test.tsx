// BL-5 Spend-cap overshoot note in the chooser. docs/test-tree/provider-cap-note.md.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, delay, http } from "msw";
import { describe, expect, it } from "vitest";

import { renderApp } from "../helpers";
import { IDS, batch, report } from "../mocks/data";
import { modal, provider, providersBody } from "../mocks/providers";
import { server } from "../mocks/server";

const NOTE =
  "With several rows rendering at once, the spend cap can be passed by up to N-1 rows' cost (N = rows rendering at once). The provider's own workspace limit is the hard stop.";

function setup(
  providers: Record<string, unknown>[],
  over: Record<string, unknown> = {},
  providersHandler?: Parameters<typeof http.get>[1],
) {
  server.use(
    http.get("*/batches/:id", () =>
      HttpResponse.json(
        batch({
          status: "DRAFT",
          preview: { status: "READY", approved: false },
          report: report({ valid_rows: 8 }),
        }),
      ),
    ),
    http.get(
      "*/batches/:id/providers",
      providersHandler ??
        (() =>
          HttpResponse.json(
            providersBody(providers, { data_class: "demo", ...over }),
          )),
    ),
  );
}

async function openChooser() {
  renderApp(`/batches/new?batch=${IDS.batch}`);
  await userEvent.click(
    await screen.findByRole("button", { name: "Approve preview" }),
  );
  return screen.findByRole("dialog", { name: "Choose where to render" });
}

const REFUSED = {
  selectable: false,
  refusal: { code: "data_class", reason: "demo only" },
};

describe("spend-cap overshoot note", () => {
  it("BL5-P1 shows the exact note inside the dialog for local plus cloud with a cap", async () => {
    setup([provider(), modal()]);
    const dialog = await openChooser();
    const note = await within(dialog).findByRole("note");
    expect(note.textContent?.trim()).toBe(NOTE);
  });

  it("BL5-P2 shows the note when only a cloud provider with a cap is offered", async () => {
    setup([modal()]);
    const dialog = await openChooser();
    expect(await within(dialog).findByRole("note")).toHaveTextContent(NOTE);
  });

  it("BL5-P3 the note is reachable by a screen reader (not aria-hidden)", async () => {
    setup([modal()]);
    const dialog = await openChooser();
    const note = await within(dialog).findByRole("note");
    expect(note.closest("[aria-hidden='true']")).toBeNull();
    expect(note).toBeVisible();
  });

  it("BL5-N1 does not show the note when only a local provider is offered", async () => {
    setup([provider()]);
    const dialog = await openChooser();
    await within(dialog).findByRole("radio");
    expect(within(dialog).queryByRole("note")).toBeNull();
  });

  it("BL5-N2 does not show the note when the cloud provider is refused by data class", async () => {
    setup([provider(), modal(REFUSED)], { data_class: "real" });
    const dialog = await openChooser();
    await within(dialog).findByRole("radio");
    expect(within(dialog).queryByRole("note")).toBeNull();
  });

  it("BL5-N3 does not show the note when the only cloud provider is refused by data class", async () => {
    setup([modal(REFUSED)], { data_class: "real" });
    const dialog = await openChooser();
    await within(dialog).findByRole("radiogroup");
    expect(within(dialog).queryByRole("radio")).toBeNull();
    expect(within(dialog).queryByRole("note")).toBeNull();
  });

  it("BL5-N4 does not show the note while loading", async () => {
    setup([], {}, async () => {
      await delay("infinite");
      return HttpResponse.json(providersBody([modal()]));
    });
    const dialog = await openChooser();
    expect(within(dialog).queryByRole("note")).toBeNull();
  });

  it("BL5-N5 does not show the note on a load error", async () => {
    setup([], {}, () => HttpResponse.json({ detail: "boom" }, { status: 500 }));
    const dialog = await openChooser();
    await within(dialog).findByText("Could not load providers");
    expect(within(dialog).queryByRole("note")).toBeNull();
  });

  it("BL5-E1 cloud provider without a cap (null) shows no note", async () => {
    setup([provider(), modal({ spend_cap_usd: null, remaining_usd: null })]);
    const dialog = await openChooser();
    await within(dialog).findAllByRole("radio");
    expect(within(dialog).queryByRole("note")).toBeNull();
  });

  it("BL5-E2 a cap of 0 is still a cap and shows the note", async () => {
    setup([modal({ spend_cap_usd: 0, remaining_usd: 0, selectable: false })]);
    const dialog = await openChooser();
    expect(await within(dialog).findByRole("note")).toHaveTextContent(NOTE);
  });

  it("BL5-E3 the note appears once, also after the list is refetched", async () => {
    let calls = 0;
    setup([], {}, () => {
      calls += 1;
      return HttpResponse.json(
        providersBody([provider(), modal()], { data_class: "demo" }),
      );
    });
    const dialog = await openChooser();
    await within(dialog).findByRole("note");
    window.dispatchEvent(new Event("focus"));
    document.dispatchEvent(new Event("visibilitychange"));
    await waitFor(() => expect(calls).toBeGreaterThanOrEqual(1));
    expect(within(dialog).getAllByRole("note")).toHaveLength(1);
    expect(screen.getAllByRole("note")).toHaveLength(1);
  });
});
