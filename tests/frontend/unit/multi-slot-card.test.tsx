// DD-40 several name slots per template, Templates page card. Cases: TT-DD40-P15..P18, N12, E9
//
// CONTRACT (frontend/src, implemented by the frontend developer; see docs/test-tree/multi-slot-dashboard.md):
//   pages/templates/TemplateCard.tsx
//     one slot (template.slots has one entry):      "Slot 4.2 s - 5.1 s"  (exactly as today)
//     several slots (template.slots, sorted):        "Slots 2 s - 3 s, 10 s - 11 s"
//       numbers are printed as today (plain JS number text); comma and space between slots.
//     no primary slot (template.slot null):          "No slot yet"
//     a consented template whose slot is not confirmed shows the SlotEditor, prefilled with
//       template.extra_slots (see multi-slot-editor.test.tsx for the editor itself).
import { screen, within } from '@testing-library/react';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { renderApp } from '../helpers';
import { template } from '../mocks/data';
import { server } from '../mocks/server';

type Json = Record<string, unknown>;

/** Shows only the given template on the Templates page. */
function onlyTemplate(t: Json) {
  server.use(http.get('*/templates', () => HttpResponse.json({ templates: [t] })));
  renderApp('/templates');
  return screen.findByTestId('template-card');
}

describe('template card lists the name slots', () => {
  it('TT-DD40-P15 one slot reads exactly as today: "Slot 4.2 s - 5.1 s"', async () => {
    const card = await onlyTemplate(template());
    expect(within(card).getByText('Slot 4.2 s - 5.1 s')).toBeInTheDocument();
    expect(within(card).queryByText(/^Slots /)).not.toBeInTheDocument();
  });

  it('TT-DD40-P16 two slots read "Slots 2 s - 3 s, 10 s - 11 s"', async () => {
    const card = await onlyTemplate(
      template({
        slot: { start_s: 2, end_s: 3 },
        extra_slots: [[10, 11]],
        slots: [
          [2, 3],
          [10, 11],
        ],
      }),
    );
    expect(within(card).getByText('Slots 2 s - 3 s, 10 s - 11 s')).toBeInTheDocument();
  });

  it('TT-DD40-P17 three slots keep decimals as plain numbers: "Slots 1 s - 2.5 s, 3 s - 4 s, 10 s - 11.5 s"', async () => {
    const card = await onlyTemplate(
      template({
        slot: { start_s: 1, end_s: 2.5 },
        extra_slots: [
          [3, 4],
          [10, 11.5],
        ],
        slots: [
          [1, 2.5],
          [3, 4],
          [10, 11.5],
        ],
      }),
    );
    expect(
      within(card).getByText('Slots 1 s - 2.5 s, 3 s - 4 s, 10 s - 11.5 s'),
    ).toBeInTheDocument();
  });

  it('TT-DD40-P18 an unconfirmed card shows the slot editor prefilled with the extra slots', async () => {
    const card = await onlyTemplate(
      template({
        slot_confirmed: false,
        usable: false,
        extra_slots: [
          [2, 3],
          [10, 11],
        ],
        slots: [
          [2, 3],
          [10, 11],
        ],
      }),
    );
    expect(await within(card).findByRole('spinbutton', { name: 'Slot 2 start (s)' })).toHaveValue(
      2,
    );
    expect(within(card).getByRole('spinbutton', { name: 'Slot 3 end (s)' })).toHaveValue(11);
    expect(within(card).getByRole('button', { name: 'Add another name slot' })).toBeEnabled();
  });

  it('TT-DD40-N12 no primary slot reads "No slot yet", even with extra slots in the JSON', async () => {
    const card = await onlyTemplate(
      template({
        slot: null,
        extra_slots: [[10, 11]],
        slots: [],
        needs_manual_slot: true,
      }),
    );
    expect(within(card).getByText('No slot yet')).toBeInTheDocument();
    expect(within(card).queryByText(/^Slots? /)).not.toBeInTheDocument();
  });

  it('TT-DD40-E9 a single slot never uses the plural "Slots"', async () => {
    const card = await onlyTemplate(
      template({
        slot: { start_s: 2, end_s: 3 },
        extra_slots: [],
        slots: [[2, 3]],
      }),
    );
    expect(within(card).getByText('Slot 2 s - 3 s')).toBeInTheDocument();
    expect(card).not.toHaveTextContent('Slots');
  });
});
