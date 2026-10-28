// L1b / L5 (M2-local, AC5 and AC9) The UI must say which AI is active and make the human confirm the spoken name.
// Case IDs: TT-AM-<P|N|E><n>. Contract is also written in docs/test-tree/m2-local-real-ai.md.
//
// CONTRACT (frontend/src):
//   API        GET /system/status -> { ..., ai_mode: "fake" | "local" }.
//              batch.preview gains (optional, local mode only):
//                suggested_spoken_name: string | null   the LLM pre-fill
//                spoken_name: string | null             the confirmed spelling (null until confirmed)
//                spoken_name_confirmed: boolean
//              POST /batches/<id>/preview/confirm-spelling  JSON {spoken_name}  -> batch with confirmed flag.
//   Banner     app shell, every logged-in page: [data-testid=ai-mode-badge] with
//              fake  -> "Fake AI: a beep stands in for the name until real AI is on"
//              local -> "Local AI"
//              Nothing is shown while the status call loads or fails.
//   Next hint  step 1: while no template is chosen, under the disabled Next button the text
//              "Choose a template to continue"; it disappears once a template is selected.
//   Template card (fake mode, template needing a manual slot): "Automatic detection needs real AI" and
//              "set the slot by hand"; not shown in local mode, nor for a template with a detected slot.
//   Preview    step 3, READY preview, local mode: textbox "Spoken name" pre-filled from
//              suggested_spoken_name (editable); button "Confirm spelling"; "Approve preview" stays
//              disabled until confirmed (and re-disabled after the text is edited again). Confirm POSTs
//              {spoken_name} with the edited text. Fake mode: no "Spoken name" field, Approve unchanged.
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { renderApp } from '../helpers';
import { DEVANAGARI_NAME, IDS, batch, report, template } from '../mocks/data';
import { server } from '../mocks/server';

const FAKE_TEXT = 'Fake AI: a beep stands in for the name until real AI is on';

function mode(aiMode: string) {
  server.use(
    http.get('*/system/status', () =>
      HttpResponse.json({ worker_alive: true, queue_depth: 0, redis_ok: true, ai_mode: aiMode }),
    ),
  );
}

function draft(preview: Record<string, unknown>) {
  server.use(
    http.get('*/batches/:id', () =>
      HttpResponse.json(batch({ status: 'DRAFT', preview, report: report({ valid_rows: 8 }) })),
    ),
  );
}

const READY_LOCAL = {
  status: 'READY',
  approved: false,
  suggested_spoken_name: DEVANAGARI_NAME,
  spoken_name: null,
  spoken_name_confirmed: false,
};

describe('mode badge', () => {
  it('TT-AM-P1 fake mode says a beep stands in', async () => {
    mode('fake');
    renderApp('/');
    expect(await screen.findByTestId('ai-mode-badge')).toHaveTextContent(FAKE_TEXT);
  });

  it('TT-AM-P2 local mode says Local AI', async () => {
    mode('local');
    renderApp('/');
    const badge = await screen.findByTestId('ai-mode-badge');
    expect(badge).toHaveTextContent('Local AI');
    expect(badge).not.toHaveTextContent('beep');
  });

  it('TT-AM-P3 the badge is in the shell, so other pages show it too', async () => {
    mode('local');
    renderApp('/templates');
    expect(await screen.findByTestId('ai-mode-badge')).toHaveTextContent('Local AI');
  });

  it('TT-AM-N1 no badge while the status call fails', async () => {
    server.use(http.get('*/system/status', () => HttpResponse.json({}, { status: 500 })));
    renderApp('/');
    await screen.findByRole('navigation');
    expect(screen.queryByTestId('ai-mode-badge')).not.toBeInTheDocument();
  });

  it('TT-AM-E1 an older server without ai_mode shows no badge instead of crashing', async () => {
    server.use(
      http.get('*/system/status', () =>
        HttpResponse.json({ worker_alive: true, queue_depth: 0, redis_ok: true }),
      ),
    );
    renderApp('/');
    await screen.findByRole('navigation');
    expect(screen.queryByTestId('ai-mode-badge')).not.toBeInTheDocument();
  });
});

describe('Next hint', () => {
  it('TT-AM-P4 explains why Next is disabled until a template is chosen', async () => {
    renderApp('/batches/new');
    expect(await screen.findByText('Choose a template to continue')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
  });

  it('TT-AM-P5 the hint goes away once a template is selected', async () => {
    renderApp('/batches/new');
    const select = await screen.findByRole('combobox', { name: 'Template' });
    await within(select).findByRole('option', { name: /Rahul/ });
    await userEvent.selectOptions(select, IDS.template);
    expect(screen.queryByText('Choose a template to continue')).not.toBeInTheDocument();
  });
});

describe('template card note', () => {
  const NEEDS_MANUAL = template({ slot: null, needs_manual_slot: true, slot_confirmed: false });
  const note = /Automatic detection needs real AI/i;

  it('TT-AM-P6 fake mode explains why the slot must be set by hand', async () => {
    mode('fake');
    server.use(http.get('*/templates', () => HttpResponse.json({ templates: [NEEDS_MANUAL] })));
    renderApp('/templates');
    const card = await screen.findByTestId('template-card');
    expect(card).toHaveTextContent(note);
    expect(card).toHaveTextContent(/set the slot by hand/i);
  });

  it('TT-AM-N2 local mode does not show the note', async () => {
    mode('local');
    server.use(http.get('*/templates', () => HttpResponse.json({ templates: [NEEDS_MANUAL] })));
    renderApp('/templates');
    await screen.findByTestId('template-card');
    expect(screen.queryByText(note)).not.toBeInTheDocument();
  });

  it('TT-AM-N3 a template with a detected slot has no note even in fake mode', async () => {
    mode('fake');
    server.use(http.get('*/templates', () => HttpResponse.json({ templates: [template()] })));
    renderApp('/templates');
    await screen.findByTestId('template-card');
    expect(screen.queryByText(note)).not.toBeInTheDocument();
  });
});

describe('spoken name confirmation in the preview step', () => {
  it('TT-AM-P7 local mode pre-fills the suggestion and keeps Approve disabled until confirmed', async () => {
    mode('local');
    draft(READY_LOCAL);
    renderApp(`/batches/new?batch=${IDS.batch}`);
    const field = await screen.findByRole('textbox', { name: 'Spoken name' });
    expect(field).toHaveValue(DEVANAGARI_NAME);
    expect(screen.getByRole('button', { name: 'Confirm spelling' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Approve preview' })).toBeDisabled();
  });

  it('TT-AM-P8 confirming posts the (edited) spelling and unlocks Approve', async () => {
    mode('local');
    let confirmed = false;
    let sent: unknown = null;
    server.use(
      http.get('*/batches/:id', () =>
        HttpResponse.json(
          batch({
            status: 'DRAFT',
            report: report({ valid_rows: 8 }),
            preview: confirmed
              ? { ...READY_LOCAL, spoken_name: 'सुनील', spoken_name_confirmed: true }
              : READY_LOCAL,
          }),
        ),
      ),
      http.post('*/batches/:id/preview/confirm-spelling', async ({ request }) => {
        sent = await request.json();
        confirmed = true;
        return HttpResponse.json(batch());
      }),
    );
    renderApp(`/batches/new?batch=${IDS.batch}`);
    const field = await screen.findByRole('textbox', { name: 'Spoken name' });
    await userEvent.clear(field);
    await userEvent.type(field, 'सुनील');
    await userEvent.click(screen.getByRole('button', { name: 'Confirm spelling' }));
    await waitFor(() => expect(sent).toEqual({ spoken_name: 'सुनील' }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Approve preview' })).toBeEnabled(),
    );
  });

  it('TT-AM-N4 a preview is never auto-approved: confirmed text alone does not approve it', async () => {
    mode('local');
    draft({ ...READY_LOCAL, spoken_name: DEVANAGARI_NAME, spoken_name_confirmed: true });
    renderApp(`/batches/new?batch=${IDS.batch}`);
    await screen.findByRole('textbox', { name: 'Spoken name' });
    expect(screen.queryByText('Preview approved')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve preview' })).toBeEnabled();
  });

  it('TT-AM-N5 fake mode has no Spoken name field and Approve works as before', async () => {
    mode('fake');
    draft({ status: 'READY', approved: false });
    renderApp(`/batches/new?batch=${IDS.batch}`);
    await screen.findByRole('button', { name: 'Approve preview' });
    expect(screen.queryByRole('textbox', { name: 'Spoken name' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve preview' })).toBeEnabled();
  });

  it('TT-AM-E2 editing the confirmed text locks Approve again until re-confirmed', async () => {
    mode('local');
    draft({ ...READY_LOCAL, spoken_name: DEVANAGARI_NAME, spoken_name_confirmed: true });
    renderApp(`/batches/new?batch=${IDS.batch}`);
    const field = await screen.findByRole('textbox', { name: 'Spoken name' });
    await userEvent.type(field, 'x');
    expect(screen.getByRole('button', { name: 'Approve preview' })).toBeDisabled();
  });

  it('TT-AM-E3 an empty suggestion leaves the field empty and Confirm disabled', async () => {
    mode('local');
    draft({ ...READY_LOCAL, suggested_spoken_name: null });
    renderApp(`/batches/new?batch=${IDS.batch}`);
    expect(await screen.findByRole('textbox', { name: 'Spoken name' })).toHaveValue('');
    expect(screen.getByRole('button', { name: 'Confirm spelling' })).toBeDisabled();
  });

  it('TT-AM-E4 a failed confirm shows an alert and keeps Approve disabled', async () => {
    mode('local');
    draft(READY_LOCAL);
    server.use(
      http.post('*/batches/:id/preview/confirm-spelling', () =>
        HttpResponse.json({ code: 'INTERNAL_ERROR', message: 'Could not save.' }, { status: 500 }),
      ),
    );
    renderApp(`/batches/new?batch=${IDS.batch}`);
    await userEvent.click(await screen.findByRole('button', { name: 'Confirm spelling' }));
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve preview' })).toBeDisabled();
  });
});
