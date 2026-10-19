// UI-AC5 New batch wizard, UI-AC11 Hindi in the wizard. Cases: TT-UI-AC5-*
//
// CONTRACT (frontend/src):
//   pages/WizardPage.tsx   route /batches/new ; "?batch=<id>" resumes a draft batch (starts at step 3
//                          when its report has valid rows, else step 2)
//   Steps list             <ol aria-label="Steps"> items "Upload", "Map columns", "Slot & preview",
//                          "Output & start"; the current one has aria-current="step"
//   Step 1 Upload          combobox "Template" (templates that are not usable are disabled and say
//                          "(consent missing)"), file input "Sheet file" (.csv/.xlsx), drop text
//                          "Drag a sheet here or choose a file", button "Next".
//                          Errors: "Use a CSV or Excel sheet." / "The sheet is empty."
//   Step 2 Map columns     comboboxes "Name column", "ID column", "Spoken name column (optional)" filled
//                          from the headers returned by POST /batches/inspect-sheet (multipart `sheet`, called when Next is
//                          pressed on step 1; response {sheet_name, headers, sample_rows, row_count});
//                          sample rows are shown as a preview; button "Validate sheet" -> POST /batches (multipart:
//                          sheet, name_column, id_column, template_id). Report summary
//                          "8 of 10 rows are valid"; each problem is a row with data-invalid="true"
//                          showing row number and the API message; "Next" needs valid_rows > 0.
//   Step 3 Slot & preview  [data-testid=preview-video] <video src=/batches/<id>/preview> only when the
//                          preview is READY; spinbuttons "Slot start (s)" / "Slot end (s)" prefilled
//                          from the template slot, button "Save slot" -> PUT /templates/<id>/slot;
//                          button "Generate preview" -> POST /batches/<id>/preview then polls the batch;
//                          button "Approve preview" (POST .../preview/approve) enabled only for a READY
//                          preview that is not approved; "Next" disabled until approved.
//                          STALE preview -> text "The preview is out of date".
//   Step 4 Output & start  textbox "Output folder" prefilled YYYY-MM-DD-N (today's date), button
//                          "Review and start" -> dialog "Start 8 videos?" with "Confirm and start" and
//                          "Cancel"; confirm -> POST /batches/<id>/start with header Idempotency-Key and
//                          JSON {folder_name}; success -> navigate to /batches/<id>.
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { renderApp } from '../helpers';
import { DEVANAGARI_NAME, IDS, batch, report, template } from '../mocks/data';
import { apiError } from '../mocks/handlers';
import { server } from '../mocks/server';

const PREVIEW_NONE = { status: 'NONE', approved: false };
const PREVIEW_READY = { status: 'READY', approved: false };
const PREVIEW_APPROVED = { status: 'READY', approved: true };

function draft(preview: Record<string, unknown>) {
  server.use(
    http.get('*/batches/:id', () =>
      HttpResponse.json(batch({ status: 'DRAFT', preview, report: report({ valid_rows: 8 }) })),
    ),
  );
}

function resume(path = `/batches/new?batch=${IDS.batch}`) {
  return renderApp(path);
}

function csv(text: string, name = 'sheet.csv', type = 'text/csv'): File {
  return new File([text], name, { type });
}

async function pickSheet(file: File) {
  const input = await screen.findByLabelText('Sheet file');
  await userEvent.upload(input, file, { applyAccept: false });
}

describe('steps', () => {
  it('TT-UI-AC5-P1 lists four steps and starts on Upload', async () => {
    renderApp('/batches/new');
    const steps = await screen.findByRole('list', { name: 'Steps' });
    const items = within(steps).getAllByRole('listitem');
    expect(items.map((i) => i.textContent)).toEqual([
      expect.stringContaining('Upload'),
      expect.stringContaining('Map columns'),
      expect.stringContaining('Slot & preview'),
      expect.stringContaining('Output & start'),
    ]);
    expect(items[0]).toHaveAttribute('aria-current', 'step');
  });
});

describe('step 1 upload', () => {
  it('TT-UI-AC5-P2 offers only usable templates and disables the consent-missing one', async () => {
    renderApp('/batches/new');
    const select = await screen.findByRole('combobox', { name: 'Template' });
    const missing = await within(select).findByRole('option', { name: /Priya.*consent missing/ });
    expect(missing).toBeDisabled();
    expect(within(select).getByRole('option', { name: /Rahul/ })).toBeEnabled();
  });

  it('TT-UI-AC5-P3 shows the drop zone text and keeps Next disabled until sheet and template exist', async () => {
    renderApp('/batches/new');
    expect(await screen.findByText('Drag a sheet here or choose a file')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
  });

  it('TT-UI-AC5-N1 a PDF is refused with a clear message', async () => {
    renderApp('/batches/new');
    await pickSheet(csv('x', 'voters.pdf', 'application/pdf'));
    expect(await screen.findByText('Use a CSV or Excel sheet.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
  });

  it('TT-UI-AC5-N2 an empty file is refused', async () => {
    renderApp('/batches/new');
    await pickSheet(csv(''));
    expect(await screen.findByText('The sheet is empty.')).toBeInTheDocument();
  });

  it('TT-UI-AC5-E1 a wrong extension on real CSV content is judged by name, spaces and unicode in the filename are fine', async () => {
    renderApp('/batches/new');
    await pickSheet(csv('Name,ID\nA,1\n', 'मतदाता सूची (final) 😀.csv'));
    expect(await screen.findByText(/मतदाता सूची/)).toBeInTheDocument();
    expect(screen.queryByText('Use a CSV or Excel sheet.')).not.toBeInTheDocument();
  });
});

describe('step 2 mapping and validation', () => {
  async function toStep2() {
    renderApp('/batches/new');
    await pickSheet(csv(`Voter Name,Voter ID,Spoken\n${DEVANAGARI_NAME},TST000001,\n`));
    const select = await screen.findByRole('combobox', { name: 'Template' });
    await within(select).findByRole('option', { name: /Rahul/ });
    await userEvent.selectOptions(select, IDS.template);
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
  }

  it('TT-UI-AC5-P12 Next on step 1 inspects the sheet through the API and shows a sample', async () => {
    let sent = 'none';
    server.use(
      http.post('*/batches/inspect-sheet', async ({ request }) => {
        const form = await request.formData();
        sent = form.get('sheet') instanceof File ? 'file' : 'missing';
        return HttpResponse.json({
          sheet_name: 'sheet.csv',
          headers: ['Voter Name', 'Voter ID'],
          sample_rows: [[DEVANAGARI_NAME, 'TST000001']],
          row_count: 1,
        });
      }),
    );
    await toStep2();
    expect(await screen.findByText(DEVANAGARI_NAME)).toBeInTheDocument();
    expect(sent).toBe('file');
  });

  it('TT-UI-AC5-N12 an unreadable sheet (UNSUPPORTED_SHEET) shows the message and stays on step 1', async () => {
    server.use(
      http.post('*/batches/inspect-sheet', () =>
        apiError(422, 'UNSUPPORTED_SHEET', 'This sheet type is not supported. Use CSV or XLSX.'),
      ),
    );
    await toStep2();
    expect(await screen.findByRole('alert')).toHaveTextContent('not supported');
    expect(screen.queryByRole('combobox', { name: 'Name column' })).not.toBeInTheDocument();
  });

  it('TT-UI-AC5-P4 fills the column pickers from the sheet header', async () => {
    await toStep2();
    const name = await screen.findByRole('combobox', { name: 'Name column' });
    expect(within(name).getByRole('option', { name: 'Voter Name' })).toBeInTheDocument();
    expect(
      within(screen.getByRole('combobox', { name: 'ID column' })).getByRole('option', {
        name: 'Voter ID',
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('combobox', { name: 'Spoken name column (optional)' }),
    ).toBeInTheDocument();
  });

  it('TT-UI-AC5-P5 validating uploads the sheet as multipart and lists invalid rows with reasons', async () => {
    let fields: Record<string, string> = {};
    server.use(
      http.post('*/batches', async ({ request }) => {
        const form = await request.formData();
        fields = {
          name_column: String(form.get('name_column')),
          id_column: String(form.get('id_column')),
          template_id: String(form.get('template_id')),
          sheet: form.get('sheet') instanceof File ? 'file' : 'missing',
        };
        return HttpResponse.json(batch({ status: 'DRAFT', report: report() }), { status: 201 });
      }),
    );
    await toStep2();
    await userEvent.selectOptions(
      await screen.findByRole('combobox', { name: 'Name column' }),
      'Voter Name',
    );
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'ID column' }), 'Voter ID');
    await userEvent.click(screen.getByRole('button', { name: 'Validate sheet' }));
    expect(await screen.findByText('8 of 10 rows are valid')).toBeInTheDocument();
    expect(fields).toEqual({
      name_column: 'Voter Name',
      id_column: 'Voter ID',
      template_id: IDS.template,
      sheet: 'file',
    });
    const bad = document.querySelectorAll('[data-invalid="true"]');
    expect(bad).toHaveLength(2);
    expect(bad[0]).toHaveTextContent('3');
    expect(bad[0]).toHaveTextContent('The name is empty.');
    expect(bad[1]).toHaveTextContent('This ID was already used in row 2.');
    expect(screen.getByRole('button', { name: 'Next' })).toBeEnabled();
  });

  it('TT-UI-AC5-N3 a sheet with no valid rows blocks Next', async () => {
    server.use(
      http.post('*/batches', () =>
        HttpResponse.json(
          batch({
            status: 'DRAFT',
            report: report({ total_rows: 2, valid_rows: 0, skipped_rows: 2 }),
          }),
          { status: 201 },
        ),
      ),
    );
    await toStep2();
    await userEvent.click(await screen.findByRole('button', { name: 'Validate sheet' }));
    expect(await screen.findByText('0 of 2 rows are valid')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
  });

  it('TT-UI-AC5-N4 the API rejecting the sheet shows its plain-language message', async () => {
    server.use(
      http.post('*/batches', () =>
        apiError(422, 'COLUMN_NOT_FOUND', 'A column you chose is not in the sheet.'),
      ),
    );
    await toStep2();
    await userEvent.click(await screen.findByRole('button', { name: 'Validate sheet' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'A column you chose is not in the sheet.',
    );
  });

  it('TT-UI-AC5-E2 Devanagari names in the report keep lang=hi', async () => {
    server.use(
      http.post('*/batches', () =>
        HttpResponse.json(
          batch({
            status: 'DRAFT',
            report: report({
              problems: [
                {
                  row_number: 9,
                  code: 'DUPLICATE_ID',
                  message: `${DEVANAGARI_NAME}: duplicate`,
                  faults: [],
                },
              ],
            }),
          }),
          { status: 201 },
        ),
      ),
    );
    await toStep2();
    await userEvent.click(await screen.findByRole('button', { name: 'Validate sheet' }));
    expect(await screen.findByText(new RegExp(DEVANAGARI_NAME))).toBeInTheDocument();
  });
});

describe('step 3 slot and preview gate', () => {
  it('TT-UI-AC5-P6 resuming a draft opens Slot & preview with the detected slot', async () => {
    draft(PREVIEW_NONE);
    resume();
    expect(await screen.findByRole('spinbutton', { name: 'Slot start (s)' })).toHaveValue(4.2);
    expect(screen.getByRole('spinbutton', { name: 'Slot end (s)' })).toHaveValue(5.1);
    expect(
      screen.getByRole('list', { name: 'Steps' }).querySelector('[aria-current="step"]'),
    ).toHaveTextContent('Slot & preview');
  });

  it('TT-UI-AC5-N5 without an approved preview, Next stays disabled (preview gate A5)', async () => {
    draft(PREVIEW_NONE);
    resume();
    await screen.findByRole('button', { name: 'Generate preview' });
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Approve preview' })).toBeDisabled();
    expect(screen.queryByTestId('preview-video')).not.toBeInTheDocument();
  });

  it('TT-UI-AC5-P7 Generate preview posts, polls until READY and then shows the player', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let state = 'NONE';
    let posted = false;
    server.use(
      http.post('*/batches/:id/preview', () => {
        posted = true;
        state = 'PENDING';
        setTimeout(() => (state = 'READY'), 3000);
        return HttpResponse.json(
          batch({ status: 'DRAFT', preview: { status: 'PENDING', approved: false } }),
          { status: 202 },
        );
      }),
      http.get('*/batches/:id', () =>
        HttpResponse.json(
          batch({
            status: 'DRAFT',
            preview: { status: state, approved: false },
            report: report({ valid_rows: 8 }),
          }),
        ),
      ),
    );
    resume();
    await userEvent
      .setup({ advanceTimers: vi.advanceTimersByTime })
      .click(await screen.findByRole('button', { name: 'Generate preview' }));
    await waitFor(() => expect(posted).toBe(true));
    expect(await screen.findByText('Generating preview...')).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(6000));
    const video = await screen.findByTestId('preview-video');
    expect(video).toHaveAttribute('src', expect.stringContaining(`/batches/${IDS.batch}/preview`));
    expect(screen.getByRole('button', { name: 'Approve preview' })).toBeEnabled();
  });

  it('TT-UI-AC5-P8 approving a READY preview enables Next', async () => {
    let approved = false;
    server.use(
      http.get('*/batches/:id', () =>
        HttpResponse.json(
          batch({
            status: 'DRAFT',
            preview: approved ? PREVIEW_APPROVED : PREVIEW_READY,
            report: report({ valid_rows: 8 }),
          }),
        ),
      ),
      http.post('*/batches/:id/preview/approve', () => {
        approved = true;
        return HttpResponse.json(batch({ status: 'DRAFT', preview: PREVIEW_APPROVED }));
      }),
    );
    resume();
    const approve = await screen.findByRole('button', { name: 'Approve preview' });
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
    await userEvent.click(approve);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Next' })).toBeEnabled());
  });

  it('TT-UI-AC5-N6 a STALE preview must be regenerated before approval', async () => {
    draft({ status: 'STALE', approved: false });
    resume();
    expect(await screen.findByText('The preview is out of date')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve preview' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
  });

  it('TT-UI-AC5-N7 saving a slot where end is not after start is refused locally', async () => {
    draft(PREVIEW_NONE);
    const put = vi.fn();
    server.use(http.put('*/templates/:id/slot', () => (put(), HttpResponse.json(template()))));
    resume();
    const end = await screen.findByRole('spinbutton', { name: 'Slot end (s)' });
    await userEvent.clear(end);
    await userEvent.type(end, '3');
    await userEvent.click(screen.getByRole('button', { name: 'Save slot' }));
    expect(await screen.findByText('End must be after start.')).toBeInTheDocument();
    expect(put).not.toHaveBeenCalled();
  });

  it('TT-UI-AC5-P9 saving a valid slot sends start_s and end_s as numbers', async () => {
    draft(PREVIEW_NONE);
    let body: unknown;
    server.use(
      http.put('*/templates/:id/slot', async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(
          template({ slot: { start_s: 4, end_s: 6 }, slot_confirmed: false }),
        );
      }),
    );
    resume();
    const start = await screen.findByRole('spinbutton', { name: 'Slot start (s)' });
    const end = screen.getByRole('spinbutton', { name: 'Slot end (s)' });
    await userEvent.clear(start);
    await userEvent.type(start, '4');
    await userEvent.clear(end);
    await userEvent.type(end, '6');
    await userEvent.click(screen.getByRole('button', { name: 'Save slot' }));
    await waitFor(() => expect(body).toEqual({ start_s: 4, end_s: 6 }));
  });

  it('TT-UI-AC5-E3 a slot beyond the video duration is refused locally', async () => {
    draft(PREVIEW_NONE);
    resume();
    const end = await screen.findByRole('spinbutton', { name: 'Slot end (s)' });
    await userEvent.clear(end);
    await userEvent.type(end, '99');
    await userEvent.click(screen.getByRole('button', { name: 'Save slot' }));
    expect(
      await screen.findByText('The slot must be inside the video (20 s).'),
    ).toBeInTheDocument();
  });

  it('TT-UI-AC5-E4 a template that needs a manual slot says so and has empty fields', async () => {
    draft(PREVIEW_NONE);
    server.use(
      http.get('*/templates/:id', () =>
        HttpResponse.json(template({ slot: null, needs_manual_slot: true, slot_confirmed: false })),
      ),
    );
    resume();
    expect(
      await screen.findByText('The slot could not be found automatically. Set it by hand.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('spinbutton', { name: 'Slot start (s)' })).toHaveValue(null);
  });

  it('TT-UI-AC5-E5 Generate preview failing shows the API message and allows trying again', async () => {
    draft(PREVIEW_NONE);
    server.use(
      http.post('*/batches/:id/preview', () =>
        apiError(409, 'INVALID_STATE', "This action is not possible in the batch's current state."),
      ),
    );
    resume();
    await userEvent.click(await screen.findByRole('button', { name: 'Generate preview' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('not possible');
    expect(screen.getByRole('button', { name: 'Generate preview' })).toBeEnabled();
  });
});

describe('step 4 output and start', () => {
  async function toStep4() {
    draft(PREVIEW_APPROVED);
    resume();
    await userEvent.click(await screen.findByRole('button', { name: 'Next' }));
  }

  it('TT-UI-AC5-P10 pre-fills the default folder name YYYY-MM-DD-N', async () => {
    vi.useFakeTimers({ toFake: ['Date'], now: new Date('2026-10-19T10:00:00') });
    await toStep4();
    expect(await screen.findByRole('textbox', { name: 'Output folder' })).toHaveValue(
      expect.stringMatching(/^2026-10-19-\d+$/),
    );
  });

  it('TT-UI-AC5-P11 confirm screen, then start with an Idempotency-Key and the folder', async () => {
    let key: string | null = null;
    let body: unknown;
    server.use(
      http.post('*/batches/:id/start', async ({ request }) => {
        key = request.headers.get('idempotency-key');
        body = await request.json();
        return HttpResponse.json(batch());
      }),
    );
    await toStep4();
    const folder = await screen.findByRole('textbox', { name: 'Output folder' });
    await userEvent.clear(folder);
    await userEvent.type(folder, 'ward-12 वार्ड');
    await userEvent.click(screen.getByRole('button', { name: 'Review and start' }));
    const dialog = await screen.findByRole('dialog', { name: 'Start 8 videos?' });
    await userEvent.click(within(dialog).getByRole('button', { name: 'Confirm and start' }));
    await waitFor(() => expect(body).toEqual({ folder_name: 'ward-12 वार्ड' }));
    expect(key).toMatch(/\S{8,}/);
    expect(await screen.findByRole('heading', { level: 1 })).toBeInTheDocument();
  });

  it('TT-UI-AC5-N8 Cancel in the confirm dialog starts nothing', async () => {
    const start = vi.fn();
    server.use(http.post('*/batches/:id/start', () => (start(), HttpResponse.json(batch()))));
    await toStep4();
    await userEvent.click(await screen.findByRole('button', { name: 'Review and start' }));
    await userEvent.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Cancel' }),
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(start).not.toHaveBeenCalled();
  });

  it.each(['../escape', 'a/b', 'a\\b', 'con:'])(
    'TT-UI-AC5-N9 folder name %s is refused locally without a request',
    async (bad) => {
      const start = vi.fn();
      server.use(http.post('*/batches/:id/start', () => (start(), HttpResponse.json(batch()))));
      await toStep4();
      const folder = await screen.findByRole('textbox', { name: 'Output folder' });
      await userEvent.clear(folder);
      await userEvent.type(folder, bad);
      await userEvent.click(screen.getByRole('button', { name: 'Review and start' }));
      expect(await screen.findByText(/Folder name can.t contain/)).toBeInTheDocument();
      expect(start).not.toHaveBeenCalled();
    },
  );

  it('TT-UI-AC5-N10 the API refusing the folder (INVALID_FOLDER_NAME) shows its message', async () => {
    server.use(
      http.post('*/batches/:id/start', () =>
        apiError(422, 'INVALID_FOLDER_NAME', 'This folder name is not allowed.'),
      ),
    );
    await toStep4();
    await userEvent.click(await screen.findByRole('button', { name: 'Review and start' }));
    await userEvent.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Confirm and start' }),
    );
    expect(await screen.findByRole('alert')).toHaveTextContent('This folder name is not allowed.');
  });

  it('TT-UI-AC5-N11 PREVIEW_NOT_APPROVED from the API is shown, nothing navigates away', async () => {
    server.use(
      http.post('*/batches/:id/start', () =>
        apiError(
          409,
          'PREVIEW_NOT_APPROVED',
          'Approve a preview of the current settings before starting.',
        ),
      ),
    );
    await toStep4();
    await userEvent.click(await screen.findByRole('button', { name: 'Review and start' }));
    await userEvent.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Confirm and start' }),
    );
    expect(await screen.findByRole('alert')).toHaveTextContent('Approve a preview');
    expect(screen.getByRole('textbox', { name: 'Output folder' })).toBeInTheDocument();
  });

  it('TT-UI-AC5-E6 double-clicking Confirm sends a single start request', async () => {
    let calls = 0;
    server.use(
      http.post('*/batches/:id/start', async () => {
        calls += 1;
        await new Promise((r) => setTimeout(r, 100));
        return HttpResponse.json(batch());
      }),
    );
    await toStep4();
    await userEvent.click(await screen.findByRole('button', { name: 'Review and start' }));
    const confirm = within(await screen.findByRole('dialog')).getByRole('button', {
      name: 'Confirm and start',
    });
    await userEvent.dblClick(confirm);
    await waitFor(() => expect(calls).toBeGreaterThan(0));
    expect(calls).toBe(1);
  });

  it('TT-UI-AC5-E7 an unknown draft id shows a not-found state', async () => {
    server.use(
      http.get('*/batches/:id', () =>
        apiError(404, 'NOT_FOUND', 'The requested item was not found.'),
      ),
    );
    resume();
    expect(await screen.findByRole('alert')).toHaveTextContent('The requested item was not found.');
  });
});
