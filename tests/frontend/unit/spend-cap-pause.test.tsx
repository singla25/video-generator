// RP-UI-CAP A batch paused at its spend cap says so (AC7). docs/test-tree/render-providers.md.
//
// CONTRACT (frontend/src/pages/BatchPage and children, route /batches/<id>):
//   Batch JSON carries pause_reason ("spend cap reached" | "provider not allowed for this data class" |
//   null), provider_id and spent_usd. While status is PAUSED and pause_reason is set, an element
//   [data-testid=pause-reason] shows the reason text. When provider_id is set the page reads
//   GET /batches/<id>/providers and shows [data-testid=spend-summary] with the spent amount and the
//   provider's spend_cap_usd, e.g. "$4.95 of $5.00". No pause_reason -> no pause-reason element.
import { screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { renderApp } from "../helpers";
import { IDS, batch } from "../mocks/data";
import { modal, providersBody } from "../mocks/providers";
import { server } from "../mocks/server";

const PATH = `/batches/${IDS.batch}`;

function paused(over: Record<string, unknown>) {
  server.use(
    http.get("*/batches/:id", () =>
      HttpResponse.json(
        batch({ status: "PAUSED", provider_id: "modal-demo", ...over }),
      ),
    ),
    http.get("*/batches/:id/providers", () =>
      HttpResponse.json(
        providersBody([modal({ spend_cap_usd: 5, spent_usd: 4.95 })]),
      ),
    ),
  );
}

describe("spend cap pause", () => {
  it("RP-UI-CAP-P1 shows the reason and spent / cap for a batch paused at the cap", async () => {
    paused({
      pause_reason: "spend cap reached",
      spent_usd: 4.95,
      data_class: "demo",
    });
    renderApp(PATH);
    expect(await screen.findByTestId("pause-reason")).toHaveTextContent(
      "spend cap reached",
    );
    const summary = await screen.findByTestId("spend-summary");
    expect(summary).toHaveTextContent("$4.95 of $5.00");
  });

  it("RP-UI-CAP-P2 names a data-class pause the same way", async () => {
    paused({
      pause_reason: "provider not allowed for this data class",
      data_class: "real",
    });
    renderApp(PATH);
    expect(await screen.findByTestId("pause-reason")).toHaveTextContent(
      "provider not allowed for this data class",
    );
  });

  it("RP-UI-CAP-N1 a paused batch without a reason (paused by hand) shows no reason box", async () => {
    paused({ pause_reason: null, spent_usd: 0.3 });
    renderApp(PATH);
    await screen.findByTestId("batch-stats");
    expect(screen.queryByTestId("pause-reason")).not.toBeInTheDocument();
  });

  it("RP-UI-CAP-N2 a running batch never shows the pause reason", async () => {
    server.use(
      http.get("*/batches/:id", () =>
        HttpResponse.json(
          batch({ status: "RUNNING", pause_reason: null, provider_id: null }),
        ),
      ),
    );
    renderApp(PATH);
    await screen.findByTestId("batch-stats");
    expect(screen.queryByTestId("pause-reason")).not.toBeInTheDocument();
    expect(screen.queryByTestId("spend-summary")).not.toBeInTheDocument();
  });

  it("RP-UI-CAP-E1 the reason is announced to screen readers (role status)", async () => {
    paused({ pause_reason: "spend cap reached", spent_usd: 4.95 });
    renderApp(PATH);
    const reason = await screen.findByTestId("pause-reason");
    expect(reason).toHaveAttribute("role", "status");
  });
});
