// RP-UI-CH Provider chooser at preview approval (AC4, AC5, AC8). docs/test-tree/render-providers.md.
//
// CONTRACT (frontend/src/pages/wizard/PreviewPanel.tsx; GET /batches/<id>/providers as in the tree):
//   Clicking "Approve preview" no longer approves at once: it opens a modal dialog named
//   "Choose where to render" (focus moves inside, Escape or "Cancel" closes it, nothing is sent).
//   The dialog loads GET /batches/<id>/providers and shows a radiogroup "Render provider" with one
//   radio per provider (accessible name starts with the provider name). Each option shows: kind
//   ("Local", "Remote function", "Remote worker"), estimated time of the batch ("5 min"), estimated
//   cost ("$0.30"), remaining credit ("$4.70 left" or "No cap") - or the text "not measured yet"
//   instead of time and cost when estimate is null.
//   Not ready (setup.state needs_setup) and refused (selectable false) options have a DISABLED radio,
//   data-selectable="false", and show their reason text (setup.reason or refusal.reason), linked to
//   the radio by aria-describedby. Providers refused by data_class are hidden (not listed).
//   Nothing is preselected. Button "Approve with this provider" is disabled until a selectable radio
//   is chosen; it POSTs /batches/<id>/preview/approve with JSON {provider_id}. On success the dialog
//   closes and the batch refreshes. On an API refusal the dialog STAYS OPEN and shows the API message
//   in role="alert" (409 PROVIDER_NOT_READY / PROVIDER_NOT_ALLOWED / PROVIDER_OVER_CREDIT, 422
//   UNKNOWN_PROVIDER); the list is reloaded. When any_selectable is false the API `message` is shown
//   and the confirm button stays disabled.
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { renderApp } from "../helpers";
import { IDS, batch, report } from "../mocks/data";
import { apiError } from "../mocks/handlers";
import { modal, provider, providersBody } from "../mocks/providers";
import { server } from "../mocks/server";

const READY = { status: "READY", approved: false };
const APPROVED = { status: "READY", approved: true };

function setup(
  providers: Record<string, unknown>[],
  over: Record<string, unknown> = {},
) {
  const calls: unknown[] = [];
  let approved = false;
  server.use(
    http.get("*/batches/:id", () =>
      HttpResponse.json(
        batch({
          status: "DRAFT",
          preview: approved ? APPROVED : READY,
          report: report({ valid_rows: 8 }),
        }),
      ),
    ),
    http.get("*/batches/:id/providers", () =>
      HttpResponse.json(
        providersBody(providers, { data_class: "demo", ...over }),
      ),
    ),
    http.post("*/batches/:id/preview/approve", async ({ request }) => {
      calls.push(await request.json());
      approved = true;
      return HttpResponse.json(batch({ status: "DRAFT", preview: APPROVED }));
    }),
  );
  return calls;
}

async function openChooser() {
  renderApp(`/batches/new?batch=${IDS.batch}`);
  await userEvent.click(
    await screen.findByRole("button", { name: "Approve preview" }),
  );
  return screen.findByRole("dialog", { name: "Choose where to render" });
}

describe("chooser content", () => {
  it("RP-UI-CH-P1 lists providers side by side with kind, time, cost and remaining credit", async () => {
    setup([
      provider({
        estimate: {
          seconds_per_video: 30,
          batch_seconds: 300,
          batch_cost_usd: 0,
        },
      }),
      modal({
        estimate: {
          seconds_per_video: 5,
          batch_seconds: 40,
          batch_cost_usd: 0.3,
        },
      }),
    ]);
    const dialog = await openChooser();
    const group = await within(dialog).findByRole("radiogroup", {
      name: "Render provider",
    });
    const local = within(group).getByRole("radio", { name: /This Mac/ });
    const remote = within(group).getByRole("radio", { name: /Modal \(demo\)/ });
    const localText = local.closest("[data-provider]")?.textContent ?? "";
    const remoteText = remote.closest("[data-provider]")?.textContent ?? "";
    expect(localText).toMatch(/Local/);
    expect(localText).toMatch(/5 min/);
    expect(localText).toMatch(/\$0\.00/);
    expect(localText).toMatch(/No cap/);
    expect(remoteText).toMatch(/Remote function/);
    expect(remoteText).toMatch(/\$0\.30/);
    expect(remoteText).toMatch(/\$4\.70 left/);
    expect(local).toBeEnabled();
    expect(remote).toBeEnabled();
  });

  it('RP-UI-CH-P2 an unmeasured provider shows "not measured yet" and can still be picked', async () => {
    const calls = setup([modal()]);
    const dialog = await openChooser();
    const radio = await within(dialog).findByRole("radio", {
      name: /Modal \(demo\)/,
    });
    expect(radio.closest("[data-provider]")).toHaveTextContent(
      "not measured yet",
    );
    await userEvent.click(radio);
    await userEvent.click(
      within(dialog).getByRole("button", {
        name: "Approve with this provider",
      }),
    );
    await waitFor(() => expect(calls).toEqual([{ provider_id: "modal-demo" }]));
  });

  it("RP-UI-CH-P3 confirming sends the chosen provider id, closes the dialog and approves", async () => {
    const calls = setup([provider(), modal()]);
    const dialog = await openChooser();
    await userEvent.click(
      await within(dialog).findByRole("radio", { name: /This Mac/ }),
    );
    await userEvent.click(
      within(dialog).getByRole("button", {
        name: "Approve with this provider",
      }),
    );
    await waitFor(() => expect(calls).toEqual([{ provider_id: "local-mac" }]));
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Next" })).toBeEnabled(),
    );
  });

  it("RP-UI-CH-E1 a single provider still shows the chooser (nothing is chosen silently)", async () => {
    const calls = setup([provider()]);
    const dialog = await openChooser();
    const radio = await within(dialog).findByRole("radio", {
      name: /This Mac/,
    });
    expect(radio).not.toBeChecked();
    expect(
      within(dialog).getByRole("button", {
        name: "Approve with this provider",
      }),
    ).toBeDisabled();
    expect(calls).toEqual([]);
  });

  it("RP-UI-CH-E2 unicode provider names are shown and labelled correctly", async () => {
    setup([provider({ id: "mac", name: "मेरा Mac 🍎" })]);
    const dialog = await openChooser();
    expect(
      await within(dialog).findByRole("radio", { name: /मेरा Mac 🍎/ }),
    ).toBeEnabled();
  });
});

describe("chooser refusals", () => {
  it("RP-UI-CH-N1 a provider that needs setup is greyed with its reason and cannot be picked", async () => {
    const calls = setup([
      provider(),
      modal({
        setup: { state: "needs_setup", reason: "MODAL_TOKEN_ID missing" },
        selectable: false,
        refusal: { code: "not_ready", reason: "MODAL_TOKEN_ID missing" },
      }),
    ]);
    const dialog = await openChooser();
    const radio = await within(dialog).findByRole("radio", {
      name: /Modal \(demo\)/,
    });
    expect(radio).toBeDisabled();
    expect(radio.closest("[data-provider]")).toHaveAttribute(
      "data-selectable",
      "false",
    );
    expect(radio).toHaveAccessibleDescription(/MODAL_TOKEN_ID missing/);
    await userEvent.click(radio);
    expect(
      within(dialog).getByRole("button", {
        name: "Approve with this provider",
      }),
    ).toBeDisabled();
    expect(calls).toEqual([]);
  });

  it("RP-UI-CH-N2 an estimate above the remaining credit is greyed with the refusal reason", async () => {
    setup([
      modal({
        estimate: {
          seconds_per_video: 100,
          batch_seconds: 300,
          batch_cost_usd: 0.3,
        },
        remaining_usd: 0.2,
        selectable: false,
        refusal: {
          code: "over_credit",
          reason: "The estimate is above the remaining credit.",
        },
      }),
    ]);
    const dialog = await openChooser();
    const radio = await within(dialog).findByRole("radio", {
      name: /Modal \(demo\)/,
    });
    expect(radio).toBeDisabled();
    expect(radio).toHaveAccessibleDescription(/above the remaining credit/);
  });

  it("RP-UI-CH-N3 a provider refused only by the data class is not listed", async () => {
    setup([
      provider(),
      modal({
        selectable: false,
        refusal: { code: "data_class", reason: "Demo data only." },
      }),
    ]);
    const dialog = await openChooser();
    await within(dialog).findByRole("radio", { name: /This Mac/ });
    expect(
      within(dialog).queryByRole("radio", { name: /Modal/ }),
    ).not.toBeInTheDocument();
  });

  it.each([
    [
      409,
      "PROVIDER_NOT_READY",
      "This provider is not ready. Start its worker and try again.",
    ],
    [409, "PROVIDER_NOT_ALLOWED", "This provider cannot take real data."],
    [
      409,
      "PROVIDER_OVER_CREDIT",
      "The estimate is above the remaining credit.",
    ],
    [422, "UNKNOWN_PROVIDER", "This provider does not exist any more."],
  ])(
    "RP-UI-CH-N4 a %i %s refusal shows its message and keeps the chooser open",
    async (status, code, text) => {
      setup([provider()]);
      server.use(
        http.post("*/batches/:id/preview/approve", () =>
          apiError(status, code, text),
        ),
      );
      const dialog = await openChooser();
      await userEvent.click(
        await within(dialog).findByRole("radio", { name: /This Mac/ }),
      );
      await userEvent.click(
        within(dialog).getByRole("button", {
          name: "Approve with this provider",
        }),
      );
      expect(await within(dialog).findByRole("alert")).toHaveTextContent(text);
      expect(
        screen.getByRole("dialog", { name: "Choose where to render" }),
      ).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    },
  );

  it("RP-UI-CH-E3 with no selectable provider the API message is shown and approval is blocked", async () => {
    setup(
      [
        provider({
          selectable: false,
          setup: { state: "needs_setup", reason: "worker not running" },
          refusal: { code: "not_ready", reason: "worker not running" },
        }),
      ],
      {
        any_selectable: false,
        message: "No render provider is ready. Start a worker first.",
      },
    );
    const dialog = await openChooser();
    expect(
      await within(dialog).findByText(/No render provider is ready/),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", {
        name: "Approve with this provider",
      }),
    ).toBeDisabled();
  });
});

describe("chooser accessibility", () => {
  it("RP-UI-CH-E4 focus moves into the dialog; Escape and Cancel close it without sending anything", async () => {
    const calls = setup([provider()]);
    const dialog = await openChooser();
    expect(dialog.contains(document.activeElement)).toBe(true);
    await userEvent.keyboard("{Escape}");
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Approve preview" }),
    );
    const again = await screen.findByRole("dialog", {
      name: "Choose where to render",
    });
    await userEvent.click(
      within(again).getByRole("button", { name: "Cancel" }),
    );
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    expect(calls).toEqual([]);
  });

  it("RP-UI-CH-E5 the whole choice can be made with the keyboard", async () => {
    const calls = setup([provider()]);
    const dialog = await openChooser();
    const radio = await within(dialog).findByRole("radio", {
      name: /This Mac/,
    });
    radio.focus();
    await userEvent.keyboard(" ");
    expect(radio).toBeChecked();
    const confirm = within(dialog).getByRole("button", {
      name: "Approve with this provider",
    });
    await waitFor(() => expect(confirm).toBeEnabled());
    confirm.focus();
    await userEvent.keyboard("{Enter}");
    await waitFor(() => expect(calls).toEqual([{ provider_id: "local-mac" }]));
  });
});
