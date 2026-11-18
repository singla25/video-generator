// RP-UI-DC Data class at upload (C5). Test tree: docs/test-tree/render-providers.md (UI section).
//
// CONTRACT (frontend/src/pages/wizard/StepUpload.tsx and StepMap.tsx):
//   Step 1 shows radiogroup "Data class" with radios "Real data" (checked by default) and
//   "Demo or learning data". Choosing demo reveals the checkbox "I confirm this is demo or learning
//   data only" (unchecked). With demo chosen and the box unchecked, "Next" is disabled and a hint
//   says why. Going back to "Real data" hides the box and forgets the confirmation.
//   POST /batches (step 2, "Validate sheet") adds form fields data_class = "real" | "demo" and, only
//   for demo, confirm_demo = "true".
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { renderApp } from "../helpers";
import { DEVANAGARI_NAME, IDS, batch, report } from "../mocks/data";
import { server } from "../mocks/server";

const CONFIRM = "I confirm this is demo or learning data only";

async function fillStep1() {
  const input = await screen.findByLabelText("Sheet file");
  const sheet = new File(
    [`Voter Name,Voter ID\n${DEVANAGARI_NAME},TST000001\n`],
    "sheet.csv",
    {
      type: "text/csv",
    },
  );
  await userEvent.upload(input, sheet, { applyAccept: false });
  const select = await screen.findByRole("combobox", { name: "Template" });
  await within(select).findByRole("option", { name: /Rahul/ });
  await userEvent.selectOptions(select, IDS.template);
}

function captureCreate() {
  const sent: Record<string, unknown> = {};
  server.use(
    http.post("*/batches", async ({ request }) => {
      const form = await request.formData();
      sent.data_class = form.get("data_class");
      sent.confirm_demo = form.get("confirm_demo");
      return HttpResponse.json(batch({ status: "DRAFT", report: report() }), {
        status: 201,
      });
    }),
  );
  return sent;
}

async function validate() {
  await userEvent.click(screen.getByRole("button", { name: "Next" }));
  await userEvent.selectOptions(
    await screen.findByRole("combobox", { name: "Name column" }),
    "Voter Name",
  );
  await userEvent.selectOptions(
    screen.getByRole("combobox", { name: "ID column" }),
    "Voter ID",
  );
  await userEvent.click(screen.getByRole("button", { name: "Validate sheet" }));
  await screen.findByText(/rows are valid/);
}

describe("data class choice", () => {
  it("RP-UI-DC-P1 offers Real data (default) and Demo or learning data as a labelled group", async () => {
    renderApp("/batches/new");
    const group = await screen.findByRole("radiogroup", { name: "Data class" });
    expect(
      within(group).getByRole("radio", { name: "Real data" }),
    ).toBeChecked();
    expect(
      within(group).getByRole("radio", { name: "Demo or learning data" }),
    ).not.toBeChecked();
    expect(
      screen.queryByRole("checkbox", { name: CONFIRM }),
    ).not.toBeInTheDocument();
  });

  it("RP-UI-DC-P2 a real batch sends data_class=real and no demo confirmation", async () => {
    const sent = captureCreate();
    renderApp("/batches/new");
    await fillStep1();
    await validate();
    expect(sent).toEqual({ data_class: "real", confirm_demo: null });
  });

  it("RP-UI-DC-P3 a confirmed demo batch sends data_class=demo and confirm_demo=true", async () => {
    const sent = captureCreate();
    renderApp("/batches/new");
    await fillStep1();
    await userEvent.click(
      screen.getByRole("radio", { name: "Demo or learning data" }),
    );
    await userEvent.click(screen.getByRole("checkbox", { name: CONFIRM }));
    await validate();
    expect(sent).toEqual({ data_class: "demo", confirm_demo: "true" });
  });

  it("RP-UI-DC-N1 demo without the confirmation blocks Next and says why", async () => {
    renderApp("/batches/new");
    await fillStep1();
    await userEvent.click(
      screen.getByRole("radio", { name: "Demo or learning data" }),
    );
    const next = screen.getByRole("button", { name: "Next" });
    expect(next).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: CONFIRM })).not.toBeChecked();
    expect(next).toHaveAccessibleDescription(/confirm/i);
    await userEvent.click(screen.getByRole("checkbox", { name: CONFIRM }));
    expect(next).toBeEnabled();
  });

  it("RP-UI-DC-E1 switching back to Real data hides the box and forgets the confirmation", async () => {
    const sent = captureCreate();
    renderApp("/batches/new");
    await fillStep1();
    await userEvent.click(
      screen.getByRole("radio", { name: "Demo or learning data" }),
    );
    await userEvent.click(screen.getByRole("checkbox", { name: CONFIRM }));
    await userEvent.click(screen.getByRole("radio", { name: "Real data" }));
    expect(
      screen.queryByRole("checkbox", { name: CONFIRM }),
    ).not.toBeInTheDocument();
    await validate();
    expect(sent).toEqual({ data_class: "real", confirm_demo: null });
  });

  it("RP-UI-DC-E2 the choice works from the keyboard (arrow keys move between the radios)", async () => {
    renderApp("/batches/new");
    await screen.findByRole("radiogroup", { name: "Data class" });
    screen.getByRole("radio", { name: "Real data" }).focus();
    await userEvent.keyboard("{ArrowDown}");
    await waitFor(() =>
      expect(
        screen.getByRole("radio", { name: "Demo or learning data" }),
      ).toBeChecked(),
    );
    expect(screen.getByRole("checkbox", { name: CONFIRM })).toBeInTheDocument();
  });
});
