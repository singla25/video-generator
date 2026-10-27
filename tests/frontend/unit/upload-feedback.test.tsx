// FIX-UPLOAD-1 Uploads must never fail silently (plan UI-AC5 and UI-AC10: every screen shows
// error states). Case IDs: TT-UP-<P|N|E><n>.
//
// CONTRACT (frontend/src), the same for every upload in the dashboard:
//   progress   while the file is being sent: an element role="progressbar" with aria-valuemin=0,
//              aria-valuemax=100, aria-valuenow=<percent>, and the text "<percent>%".
//              fetch cannot report upload progress, so the upload uses XMLHttpRequest
//              (tests drive it with support/fake-xhr.ts). The bar is gone when the upload ends.
//   failure    role="alert" in plain words: the API message when the JSON body has one, else a
//              sentence that tells the operator to try again (HTTP 500/503/413, network
//              failure, timeout), plus a button named /retry/i that sends the same file again.
//              The form stays usable; no progress bar and no "success" state is left over.
//   cancel     leaving the page, or pressing Cancel on the template form, aborts the request.
//   401        sends the user to the login screen (existing behaviour).
// Surfaces: wizard sheet (inspect), wizard Validate sheet, new template, consent.
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { renderApp } from "../helpers";
import { IDS, batch, report, template } from "../mocks/data";
import { apiError } from "../mocks/handlers";
import { server } from "../mocks/server";
import { FakeXhr, installFakeXhr, uploads } from "../support/fake-xhr";

let lastUnmount: () => void = () => undefined;

function open(path: string) {
  const view = renderApp(path);
  lastUnmount = view.unmount;
  return view;
}

interface Surface {
  name: string;
  url: string; // fragment of the upload URL
  ok: { status: number; body: Record<string, unknown> }; // what a healthy server answers
  prepare: (file?: File) => Promise<() => Promise<void>>; // returns the submit action
  noStaleSuccess: () => void;
}

const CSV = () =>
  new File(["Voter Name,Voter ID,Spoken\nA,1,\n"], "sheet.csv", {
    type: "text/csv",
  });
const MP4 = () => new File(["video"], "intro.mp4", { type: "video/mp4" });
const PDF = () => new File(["x"], "consent.pdf", { type: "application/pdf" });

async function pickSheet(file: File) {
  await userEvent.upload(await screen.findByLabelText("Sheet file"), file, {
    applyAccept: false,
  });
  const select = await screen.findByRole("combobox", { name: "Template" });
  await within(select).findByRole("option", { name: /Rahul/ });
  await userEvent.selectOptions(select, IDS.template);
}

async function toMapping() {
  open("/batches/new");
  await pickSheet(CSV());
  await userEvent.click(screen.getByRole("button", { name: "Next" }));
  await userEvent.selectOptions(
    await screen.findByRole("combobox", { name: "Name column" }),
    "Voter Name",
  );
  await userEvent.selectOptions(
    screen.getByRole("combobox", { name: "ID column" }),
    "Voter ID",
  );
}

const SURFACES: Surface[] = [
  {
    name: "wizard sheet",
    url: "/batches/inspect-sheet",
    ok: {
      status: 200,
      body: {
        sheet_name: "sheet.csv",
        headers: ["Voter Name", "Voter ID"],
        sample_rows: [],
        row_count: 1,
      },
    },
    prepare: async (file = CSV()) => {
      open("/batches/new");
      await pickSheet(file);
      return () =>
        userEvent.click(screen.getByRole("button", { name: "Next" }));
    },
    noStaleSuccess: () => {
      expect(
        screen.queryByRole("combobox", { name: "Name column" }),
      ).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();
    },
  },
  {
    name: "wizard Validate sheet",
    url: "/batches",
    ok: { status: 201, body: batch({ status: "DRAFT", report: report() }) },
    prepare: async () => {
      await toMapping();
      return () =>
        userEvent.click(screen.getByRole("button", { name: "Validate sheet" }));
    },
    noStaleSuccess: () => {
      expect(screen.queryByText(/rows are valid/)).not.toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Validate sheet" }),
      ).toBeEnabled();
    },
  },
  {
    name: "new template",
    url: "/templates",
    ok: { status: 201, body: template({ id: IDS.template }) },
    prepare: async (file = MP4()) => {
      open("/templates");
      await userEvent.click(
        await screen.findByRole("button", { name: "New template" }),
      );
      await userEvent.upload(screen.getByLabelText("Template video"), file, {
        applyAccept: false,
      });
      await userEvent.type(screen.getByLabelText("Word to replace"), "Rahul");
      return () =>
        userEvent.click(
          screen.getByRole("button", { name: "Upload template" }),
        );
    },
    noStaleSuccess: () => {
      // The form must not close as if the template had been created.
      expect(
        screen.getByRole("button", { name: "Upload template" }),
      ).toBeEnabled();
    },
  },
  {
    name: "consent",
    url: "/consent",
    ok: {
      status: 200,
      body: template({ id: IDS.templateNoConsent, original_name: "Priya" }),
    },
    prepare: async (file = PDF()) => {
      open("/templates");
      const cards = await screen.findAllByTestId("template-card");
      const priya = cards.find((c) => within(c).queryByText("Priya"))!;
      await userEvent.click(
        within(priya).getByRole("button", { name: "Upload consent" }),
      );
      await userEvent.upload(screen.getByLabelText("Consent file"), file, {
        applyAccept: false,
      });
      await userEvent.click(
        screen.getByRole("checkbox", {
          name: "I confirm I have consent to use this video",
        }),
      );
      return () =>
        userEvent.click(screen.getByRole("button", { name: "Submit consent" }));
    },
    noStaleSuccess: () => {
      expect(
        screen
          .getAllByTestId("consent-badge")
          .some((b) => /missing/i.test(b.textContent ?? "")),
      ).toBe(true);
      expect(
        screen.getByRole("button", { name: "Submit consent" }),
      ).toBeEnabled();
    },
  },
];

function noLeftovers() {
  expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  for (const status of screen.queryAllByRole("status")) {
    expect(status).not.toHaveTextContent(
      /uploaded|upload complete|success|done/i,
    );
  }
}

async function startFake(surface: Surface, file?: File) {
  const submit = await surface.prepare(file);
  installFakeXhr();
  await submit();
  await waitFor(() => expect(uploads(surface.url).length).toBeGreaterThan(0));
  return uploads(surface.url).at(-1) as FakeXhr;
}

describe.each(SURFACES)("upload feedback: $name", (surface) => {
  // ---- progress (AC1) ------------------------------------------------------------------
  it("TT-UP-P1 shows a progress bar with the percentage while the file is sent", async () => {
    const xhr = await startFake(surface);
    act(() => xhr.progress(0, 100));
    act(() => xhr.progress(40, 100));
    const bar = await screen.findByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuemin", "0");
    expect(bar).toHaveAttribute("aria-valuemax", "100");
    expect(bar).toHaveAttribute("aria-valuenow", "40");
    expect(bar).toHaveAccessibleName();
    expect(screen.getByText("40%")).toBeInTheDocument();
    act(() => xhr.progress(100, 100));
    expect(screen.getByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "100",
    );
  });

  it("TT-UP-P2 the progress bar goes away once the upload succeeds", async () => {
    const xhr = await startFake(surface);
    act(() => xhr.progress(50, 100));
    await screen.findByRole("progressbar");
    act(() => xhr.respond(surface.ok.status, surface.ok.body));
    await waitFor(() =>
      expect(screen.queryByRole("progressbar")).not.toBeInTheDocument(),
    );
  });

  // ---- failures (AC2, AC3) -------------------------------------------------------------
  it("TT-UP-N1 an HTTP 500 with the API error body shows its message and a Retry button", async () => {
    server.use(
      http.post(`*${surface.url}`, () =>
        apiError(
          500,
          "INTERNAL_ERROR",
          "Something went wrong on our side. Please try again.",
        ),
      ),
    );
    const submit = await surface.prepare();
    await submit();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(
      "Something went wrong on our side. Please try again.",
    );
    expect(screen.getByRole("button", { name: /retry/i })).toBeEnabled();
    noLeftovers();
    surface.noStaleSuccess();
  });

  it("TT-UP-N2 an HTTP 503 DB_UNAVAILABLE shows the API message, not a generic one", async () => {
    server.use(
      http.post(`*${surface.url}`, () =>
        apiError(
          503,
          "DB_UNAVAILABLE",
          "The database is not reachable. Please try again shortly.",
        ),
      ),
    );
    const submit = await surface.prepare();
    await submit();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "database is not reachable",
    );
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    noLeftovers();
    surface.noStaleSuccess();
  });

  it("TT-UP-N3 a 503 from a proxy with an HTML body still gives a plain-words alert and Retry", async () => {
    server.use(
      http.post(
        `*${surface.url}`,
        () =>
          new HttpResponse("<html><body>Bad gateway nginx</body></html>", {
            status: 503,
            headers: { "Content-Type": "text/html" },
          }),
      ),
    );
    const submit = await surface.prepare();
    await submit();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/server|unavailable|try again/i);
    expect(alert.textContent).not.toMatch(/<html|nginx|undefined|\[object/);
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    noLeftovers();
  });

  it("TT-UP-N4 a network failure says the server could not be reached and offers Retry", async () => {
    server.use(http.post(`*${surface.url}`, () => HttpResponse.error()));
    const submit = await surface.prepare();
    await submit();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /could not reach the server/i,
    );
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    noLeftovers();
    surface.noStaleSuccess();
  });

  it("TT-UP-N5 a connection dropped mid-upload (after progress) shows the alert and clears the bar", async () => {
    const xhr = await startFake(surface);
    act(() => xhr.progress(30, 100));
    await screen.findByRole("progressbar");
    act(() => xhr.networkError());
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /could not reach the server|try again/i,
    );
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    noLeftovers();
  });

  it("TT-UP-N6 a timeout shows a visible alert in plain words and Retry", async () => {
    const xhr = await startFake(surface);
    act(() => xhr.progress(10, 100));
    act(() => xhr.timedOut());
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/took too long|timed out|too long/i);
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    noLeftovers();
    surface.noStaleSuccess();
  });

  it("TT-UP-N7 Retry sends the same file again; success clears the alert", async () => {
    let calls = 0;
    const files: string[] = [];
    server.use(
      http.post(`*${surface.url}`, async ({ request }) => {
        calls += 1;
        const form = await request.formData();
        for (const value of form.values())
          if (value instanceof File) files.push(value.name);
        return calls === 1
          ? apiError(
              503,
              "DB_UNAVAILABLE",
              "The database is not reachable. Please try again shortly.",
            )
          : HttpResponse.json(surface.ok.body, { status: surface.ok.status });
      }),
    );
    const submit = await surface.prepare();
    await submit();
    await userEvent.click(
      await screen.findByRole("button", { name: /retry/i }),
    );
    await waitFor(() => expect(calls).toBe(2));
    expect(files).toHaveLength(2);
    expect(files[0]).toBe(files[1]);
    await waitFor(() =>
      expect(screen.queryByRole("alert")).not.toBeInTheDocument(),
    );
  });

  it("TT-UP-N8 the form stays usable after a failure: a new file can be chosen and sent", async () => {
    server.use(
      http.post(`*${surface.url}`, () =>
        apiError(
          500,
          "INTERNAL_ERROR",
          "Something went wrong. Please try again.",
        ),
      ),
    );
    const submit = await surface.prepare();
    await submit();
    await screen.findByRole("alert");
    for (const input of document.querySelectorAll('input[type="file"]'))
      expect(input).toBeEnabled();
    surface.noStaleSuccess();
  });

  it("TT-UP-N9 a second failure replaces the first alert (one alert, no pile-up)", async () => {
    server.use(
      http.post(`*${surface.url}`, () =>
        apiError(
          500,
          "INTERNAL_ERROR",
          "Something went wrong. Please try again.",
        ),
      ),
    );
    const submit = await surface.prepare();
    await submit();
    await userEvent.click(
      await screen.findByRole("button", { name: /retry/i }),
    );
    await waitFor(() => expect(screen.getAllByRole("alert")).toHaveLength(1));
  });

  // ---- edges (AC5) ---------------------------------------------------------------------
  it("TT-UP-E1 a 413 too-large answer says the file is too big, with or without an API body", async () => {
    server.use(
      http.post(
        `*${surface.url}`,
        () => new HttpResponse("Request Entity Too Large", { status: 413 }),
      ),
    );
    const submit = await surface.prepare();
    await submit();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /too (large|big)/i,
    );
    noLeftovers();
  });

  it("TT-UP-E2 a 413 with the API body shows the API message", async () => {
    server.use(
      http.post(`*${surface.url}`, () =>
        apiError(
          413,
          "FILE_TOO_LARGE",
          "This file is too large. The limit is 500 MB.",
        ),
      ),
    );
    const submit = await surface.prepare();
    await submit();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The limit is 500 MB.",
    );
  });

  it("TT-UP-E3 a 401 during the upload sends the user to the login screen", async () => {
    server.use(
      http.post(`*${surface.url}`, () =>
        apiError(401, "UNAUTHENTICATED", "Please log in to continue."),
      ),
    );
    const submit = await surface.prepare();
    await submit();
    expect(
      await screen.findByRole("button", { name: "Log in" }),
    ).toBeInTheDocument();
  });

  it("TT-UP-E4 leaving the page mid-upload aborts the request and shows nothing afterwards", async () => {
    const xhr = await startFake(surface);
    act(() => xhr.progress(20, 100));
    lastUnmount();
    expect(xhr.aborted).toBe(true);
  });

  it("TT-UP-E5 a double click on submit sends one request (no duplicate upload)", async () => {
    const submit = await surface.prepare();
    installFakeXhr();
    await submit();
    await waitFor(() => expect(uploads(surface.url).length).toBeGreaterThan(0));
    await submit().catch(() => undefined); // button is disabled while sending
    expect(uploads(surface.url)).toHaveLength(1);
  });
});

describe("upload feedback: zero-byte files and cancel", () => {
  it("TT-UP-E6 a 0-byte template video is refused on the client, no request is sent", async () => {
    const template = SURFACES[2]!;
    installFakeXhr();
    await template.prepare(new File([], "empty.mp4", { type: "video/mp4" }));
    expect(screen.getByText("The video is empty.")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Upload template" }),
    ).toBeDisabled();
    expect(FakeXhr.instances).toHaveLength(0);
  });

  it("TT-UP-E7 a 0-byte consent file is refused with a message, no request is sent", async () => {
    const consent = SURFACES[3]!;
    installFakeXhr();
    await consent.prepare(
      new File([], "empty.pdf", { type: "application/pdf" }),
    );
    expect(screen.getByText(/empty/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Submit consent" }),
    ).toBeDisabled();
    expect(FakeXhr.instances).toHaveLength(0);
  });

  it("TT-UP-E8 Cancel on the template form during an upload aborts it", async () => {
    const xhr = await startFake(SURFACES[2]!);
    act(() => xhr.progress(25, 100));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(xhr.aborted).toBe(true);
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("TT-UP-E9 an aborted upload that still gets a late answer shows no error", async () => {
    const xhr = await startFake(SURFACES[2]!);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    act(() =>
      xhr.respond(500, { code: "INTERNAL_ERROR", message: "Late failure." }),
    );
    expect(screen.queryByText("Late failure.")).not.toBeInTheDocument();
  });
});

describe.each(SURFACES)("upload feedback extras: $name", (surface) => {
  it("TT-UP-E10 the request has a positive timeout so a hung upload ends", async () => {
    const xhr = await startFake(surface);
    expect(xhr.timeout).toBeGreaterThan(0);
  });

  it("TT-UP-E11 progress never shows NaN or more than 100 percent", async () => {
    const xhr = await startFake(surface);
    act(() => xhr.progress(150, 100));
    const bar = await screen.findByRole("progressbar");
    expect(Number(bar.getAttribute("aria-valuenow"))).toBeLessThanOrEqual(100);
    expect(document.body.textContent).not.toMatch(/NaN/);
  });

  it("TT-UP-N10 a 504 gateway page gives an alert with Retry", async () => {
    const xhr = await startFake(surface);
    act(() => xhr.respond(504, "<html>Gateway Time-out</html>"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    noLeftovers();
  });
});
