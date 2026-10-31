// DD-38 A: confirming the spoken name regenerates the preview. Cases: TT-DD38-A-*
//
// CONTRACT (frontend/src/pages/wizard/PreviewPanel.tsx, spoken name block, local AI mode):
//   Confirm spelling   POST /batches/<id>/preview/confirm-spelling  JSON {spoken_name: <text>}
//                      and, only when that succeeds, POST /batches/<id>/preview right away, so the
//                      panel shows "Generating preview..." (role=status) while the new spelling renders.
//   Confirm fails      409 or any other error: no preview request is sent; the error shows in role=alert.
//   Hint               "Confirm to hear the preview with this spelling." under the field.
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { renderApp } from "../helpers";
import { DEVANAGARI_NAME, IDS, batch, report } from "../mocks/data";
import { apiError } from "../mocks/handlers";
import { server } from "../mocks/server";

const NEW_NAME = "सुनील";
const HINT = "Confirm to hear the preview with this spelling.";
const GENERATING = "Generating preview...";

interface Scene {
  /** The spelling the server has confirmed, or null before any confirm. */
  confirmed: string | null;
  /** True once a new preview has been requested and is still rendering. */
  generating: boolean;
}

function previewOf(scene: Scene): Record<string, unknown> {
  const base = {
    approved: false,
    suggested_spoken_name: DEVANAGARI_NAME,
    spoken_name: scene.confirmed,
    spoken_name_confirmed: scene.confirmed !== null,
  };
  return scene.generating
    ? { ...base, status: "PENDING", stage: null }
    : { ...base, status: "READY" };
}

/**
 * A draft in local AI mode with a READY preview. Confirm and Generate preview update the scene,
 * and the batch read reflects it, like the real API does.
 */
function serveScene(
  options: { confirmFails?: { httpStatus: number; message: string } } = {},
) {
  const scene: Scene = { confirmed: null, generating: false };
  const calls: string[] = [];
  let confirmBody: unknown = null;
  server.use(
    http.get("*/system/status", () =>
      HttpResponse.json({
        worker_alive: true,
        queue_depth: 0,
        redis_ok: true,
        ai_mode: "local",
      }),
    ),
    http.get("*/batches/:id", () =>
      HttpResponse.json(
        batch({
          status: "DRAFT",
          report: report({ valid_rows: 8 }),
          preview: previewOf(scene),
        }),
      ),
    ),
    http.post("*/batches/:id/preview/confirm-spelling", async ({ request }) => {
      calls.push("confirm");
      confirmBody = await request.json();
      if (options.confirmFails) {
        const { httpStatus, message } = options.confirmFails;
        return apiError(httpStatus, "INVALID_STATE", message);
      }
      scene.confirmed = (confirmBody as { spoken_name: string }).spoken_name;
      return HttpResponse.json(
        batch({ status: "DRAFT", preview: previewOf(scene) }),
      );
    }),
    http.post("*/batches/:id/preview", () => {
      calls.push("generate");
      scene.generating = true;
      return HttpResponse.json(
        batch({ status: "DRAFT", preview: previewOf(scene) }),
        {
          status: 202,
        },
      );
    }),
  );
  return { calls, body: () => confirmBody };
}

async function typeAndConfirm(text: string) {
  const field = await screen.findByRole("textbox", { name: "Spoken name" });
  await userEvent.clear(field);
  await userEvent.type(field, text);
  await userEvent.click(
    screen.getByRole("button", { name: "Confirm spelling" }),
  );
}

describe("positive", () => {
  it("TT-DD38-A-P1 confirm sends the typed spelling, then asks for a new preview", async () => {
    const { calls, body } = serveScene();
    renderApp(`/batches/new?batch=${IDS.batch}`);
    await typeAndConfirm(NEW_NAME);
    await waitFor(() => expect(calls).toEqual(["confirm", "generate"]));
    expect(body()).toEqual({ spoken_name: NEW_NAME });
  });

  it("TT-DD38-A-P2 after a successful confirm the panel shows Generating preview...", async () => {
    serveScene();
    renderApp(`/batches/new?batch=${IDS.batch}`);
    await typeAndConfirm(NEW_NAME);
    expect(await screen.findByText(GENERATING)).toBeInTheDocument();
  });

  it("TT-DD38-A-P3 the hint sits under the spoken name field", async () => {
    serveScene();
    renderApp(`/batches/new?batch=${IDS.batch}`);
    const field = await screen.findByRole("textbox", { name: "Spoken name" });
    expect(screen.getByText(HINT)).toBeInTheDocument();
    expect(field.compareDocumentPosition(screen.getByText(HINT))).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });
});

describe("negative", () => {
  it.each([
    [409, "This spelling can't be saved while the preview is being made."],
    [500, "Could not save the spelling."],
  ])(
    "TT-DD38-A-N1 a %i on confirm sends no preview request and shows the error",
    async (httpStatus, message) => {
      const { calls } = serveScene({ confirmFails: { httpStatus, message } });
      renderApp(`/batches/new?batch=${IDS.batch}`);
      await typeAndConfirm(NEW_NAME);
      expect(await screen.findByRole("alert")).toHaveTextContent(message);
      expect(calls).toEqual(["confirm"]);
      expect(screen.queryByText(GENERATING)).not.toBeInTheDocument();
    },
  );

  it("TT-DD38-A-N2 after a failed confirm Approve stays disabled", async () => {
    serveScene({ confirmFails: { httpStatus: 409, message: "Not now." } });
    renderApp(`/batches/new?batch=${IDS.batch}`);
    await typeAndConfirm(NEW_NAME);
    await screen.findByRole("alert");
    expect(
      screen.getByRole("button", { name: "Approve preview" }),
    ).toBeDisabled();
  });
});

describe("edge", () => {
  it("TT-DD38-A-E1 confirming the unchanged suggestion still asks for a new preview", async () => {
    const { calls, body } = serveScene();
    renderApp(`/batches/new?batch=${IDS.batch}`);
    await userEvent.click(
      await screen.findByRole("button", { name: "Confirm spelling" }),
    );
    await waitFor(() => expect(calls).toEqual(["confirm", "generate"]));
    expect(body()).toEqual({ spoken_name: DEVANAGARI_NAME });
  });

  it("TT-DD38-A-E2 a whitespace-only spelling disables Confirm and sends nothing", async () => {
    const { calls } = serveScene();
    renderApp(`/batches/new?batch=${IDS.batch}`);
    const field = await screen.findByRole("textbox", { name: "Spoken name" });
    await userEvent.clear(field);
    await userEvent.type(field, "   ");
    expect(
      screen.getByRole("button", { name: "Confirm spelling" }),
    ).toBeDisabled();
    expect(calls).toEqual([]);
  });

  it("TT-DD38-A-E3 a long spelling with a space is sent unchanged", async () => {
    const longName = `${DEVANAGARI_NAME} ${"राम ".repeat(20)}`.trim();
    const { calls, body } = serveScene();
    renderApp(`/batches/new?batch=${IDS.batch}`);
    await typeAndConfirm(longName);
    await waitFor(() => expect(calls).toEqual(["confirm", "generate"]));
    expect(body()).toEqual({ spoken_name: longName });
  });
});
