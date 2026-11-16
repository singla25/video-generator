// D-F6-1: a new template can become usable from the UI. Cases: TT-UI-AC7-P4.., TT-UI-AC5-P16..
//
// CONTRACT (frontend/src):
//   pages/wizard/SlotEditor.tsx  after a slot exists and template.slot_confirmed is false it shows a
//     button "Confirm slot" -> POST /templates/<id>/slot/confirm, then refetches templates; a
//     confirmed slot shows the text "Slot confirmed" and no Confirm button. Saving a slot makes the
//     confirm step necessary (the API resets slot_confirmed on every PUT).
//   pages/templates/TemplateCard.tsx  a template with consent but without a confirmed slot shows the
//     SlotEditor inside its card (fields "Slot start (s)", "Slot end (s)", "Save slot",
//     "Confirm slot"), so it can be made usable on the Templates page; the card text changes to
//     "Ready to use" after the confirm.
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { CSRF, renderApp } from '../helpers';
import { IDS, batch, report, template } from '../mocks/data';
import { apiError } from '../mocks/handlers';
import { server } from '../mocks/server';

type Json = Record<string, unknown>;

/** A stateful fake of the template slot endpoints, as the real API behaves. */
function slotApi(initial: Json) {
  let current: Json = { ...initial };
  const seen = { put: null as unknown, confirmCsrf: null as string | null, confirms: 0 };
  server.use(
    http.get('*/templates', () => HttpResponse.json({ templates: [current] })),
    http.get('*/templates/:id', () => HttpResponse.json(current)),
    http.put('*/templates/:id/slot', async ({ request }) => {
      const body = (await request.json()) as { start_s: number; end_s: number };
      seen.put = body;
      current = {
        ...current,
        slot: body,
        slot_source: 'MANUAL',
        slot_confirmed: false,
        needs_manual_slot: false,
        usable: false,
      };
      return HttpResponse.json(current);
    }),
    http.post('*/templates/:id/slot/confirm', ({ request }) => {
      seen.confirms += 1;
      seen.confirmCsrf = request.headers.get('x-csrf-token');
      current = { ...current, slot_confirmed: true, usable: true };
      return HttpResponse.json(current);
    }),
  );
  return seen;
}

const FRESH = template({
  slot: null,
  slot_source: null,
  slot_confirmed: false,
  needs_manual_slot: true,
  usable: false,
});

function card() {
  return screen.findByTestId('template-card');
}

describe('slot confirmation on the Templates page', () => {
  it('TT-UI-AC7-P4 a consented template without a slot can be set, confirmed and becomes usable', async () => {
    const seen = slotApi(FRESH);
    renderApp('/templates');
    const c = await card();
    expect(c).toHaveTextContent('Not usable');
    expect(within(c).queryByRole('button', { name: 'Confirm slot' })).not.toBeInTheDocument();
    await userEvent.type(within(c).getByRole('spinbutton', { name: 'Slot start (s)' }), '1');
    await userEvent.type(within(c).getByRole('spinbutton', { name: 'Slot end (s)' }), '2');
    await userEvent.click(within(c).getByRole('button', { name: 'Save slot' }));
    await waitFor(() => expect(seen.put).toEqual({ start_s: 1, end_s: 2, extra_slots: [] }));
    await userEvent.click(await within(c).findByRole('button', { name: 'Confirm slot' }));
    await waitFor(() => expect(seen.confirms).toBe(1));
    expect(seen.confirmCsrf).toBe(CSRF);
    await waitFor(() => expect(c).toHaveTextContent('Ready to use'));
    expect(within(c).queryByRole('button', { name: 'Confirm slot' })).not.toBeInTheDocument();
  });

  it('TT-UI-AC7-P5 the wizard then offers the template as selectable', async () => {
    slotApi(FRESH);
    renderApp('/templates');
    const c = await card();
    await userEvent.type(within(c).getByRole('spinbutton', { name: 'Slot start (s)' }), '1');
    await userEvent.type(within(c).getByRole('spinbutton', { name: 'Slot end (s)' }), '2');
    await userEvent.click(within(c).getByRole('button', { name: 'Save slot' }));
    await userEvent.click(await within(c).findByRole('button', { name: 'Confirm slot' }));
    await waitFor(() => expect(c).toHaveTextContent('Ready to use'));
    await userEvent.click(screen.getByRole('link', { name: /new batch/i }));
    const select = await screen.findByRole('combobox', { name: 'Template' });
    expect(await within(select).findByRole('option', { name: /Rahul/ })).toBeEnabled();
  });

  it('TT-UI-AC7-N5 a confirm refused by the API shows its message and keeps the template unusable', async () => {
    slotApi({ ...FRESH, slot: { start_s: 1, end_s: 2 }, needs_manual_slot: false });
    server.use(
      http.post('*/templates/:id/slot/confirm', () =>
        apiError(409, 'INVALID_STATE', "This action is not possible in the batch's current state."),
      ),
    );
    renderApp('/templates');
    const c = await card();
    await userEvent.click(await within(c).findByRole('button', { name: 'Confirm slot' }));
    expect(await within(c).findByRole('alert')).toHaveTextContent('not possible');
    expect(c).toHaveTextContent('Not usable');
  });

  it('TT-UI-AC7-E6 a template whose slot is already confirmed shows no slot editor or Confirm button', async () => {
    slotApi(template());
    renderApp('/templates');
    const c = await card();
    expect(c).toHaveTextContent('Ready to use');
    expect(within(c).queryByRole('button', { name: 'Confirm slot' })).not.toBeInTheDocument();
    expect(within(c).queryByRole('spinbutton', { name: 'Slot start (s)' })).not.toBeInTheDocument();
  });

  it('TT-UI-AC7-E8 a template without consent gets no slot editor (consent comes first)', async () => {
    slotApi({ ...FRESH, consent_confirmed: false });
    renderApp('/templates');
    const c = await card();
    expect(within(c).queryByRole('spinbutton', { name: 'Slot start (s)' })).not.toBeInTheDocument();
    expect(within(c).getByRole('button', { name: 'Upload consent' })).toBeInTheDocument();
  });
});

describe('slot confirmation in the wizard (step 3)', () => {
  function draft() {
    server.use(
      http.get('*/batches/:id', () =>
        HttpResponse.json(
          batch({
            status: 'DRAFT',
            preview: { status: 'NONE', approved: false },
            report: report({ valid_rows: 8 }),
          }),
        ),
      ),
    );
  }

  it('TT-UI-AC5-P16 an unconfirmed slot shows Confirm slot; confirming shows "Slot confirmed"', async () => {
    draft();
    const seen = slotApi({ ...template(), slot_confirmed: false, usable: false });
    renderApp(`/batches/new?batch=${IDS.batch}`);
    await userEvent.click(await screen.findByRole('button', { name: 'Confirm slot' }));
    await waitFor(() => expect(seen.confirms).toBe(1));
    expect(await screen.findByText('Slot confirmed')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Confirm slot' })).not.toBeInTheDocument();
  });

  it('TT-UI-AC5-E9 a confirmed slot shows "Slot confirmed" at once and no button', async () => {
    draft();
    slotApi(template());
    renderApp(`/batches/new?batch=${IDS.batch}`);
    expect(await screen.findByText('Slot confirmed')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Confirm slot' })).not.toBeInTheDocument();
  });

  it('TT-UI-AC5-E10 Save slot then Confirm slot in the wizard sends PUT before POST', async () => {
    draft();
    const order: string[] = [];
    slotApi({ ...template(), slot_confirmed: false, usable: false });
    server.use(
      http.put('*/templates/:id/slot', async () => {
        order.push('put');
        return HttpResponse.json(template({ slot_confirmed: false, usable: false }));
      }),
      http.post('*/templates/:id/slot/confirm', () => {
        order.push('confirm');
        return HttpResponse.json(template());
      }),
    );
    renderApp(`/batches/new?batch=${IDS.batch}`);
    await userEvent.click(await screen.findByRole('button', { name: 'Save slot' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Confirm slot' }));
    await waitFor(() => expect(order).toEqual(['put', 'confirm']));
  });
});
