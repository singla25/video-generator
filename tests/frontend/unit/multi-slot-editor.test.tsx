// DD-40 several name slots per template, dashboard slot editor. Cases: TT-DD40-*
//
// CONTRACT (frontend/src, implemented by the frontend developer; see docs/test-tree/multi-slot-dashboard.md):
//   pages/wizard/SlotEditor.tsx (used by StepSlot in the wizard and by the Templates card)
//     below "Slot start (s)" / "Slot end (s)": button "Add another name slot" appends a pair of
//       spinbuttons "Slot 2 start (s)" / "Slot 2 end (s)" (then "Slot 3 ...", up to "Slot 5 ...");
//       each extra pair has a button "Remove slot 2" ("Remove slot 3" ...).
//       The add button is disabled when 5 slots are shown (primary plus 4).
//       Extra inputs start empty; template.extra_slots ([[start, end], ...]) prefills one pair each.
//     Save slot -> PUT /templates/<id>/slot with {start_s, end_s, extra_slots: [[s, e], ...]} as numbers;
//       extra_slots is always sent ([] when there are none).
//     Client checks run while the user types; while one fails "Save slot" is disabled and a
//       role=alert shows the exact text:
//       "Slots must not overlap or touch."  (sorted by start, gap < 0.2 s or overlap)
//       "Each slot must end after it starts."
//       "Fill in every slot or remove it."
//       "Slot N ends after the video."  (end above template.duration_s)
//     After a save the slot must be confirmed again: "Slot confirmed" disappears and "Confirm slot" shows.
import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { beforeEach, describe, expect, it } from 'vitest';

import type { Template } from '../../../frontend/src/api/types';
import { SlotEditor } from '../../../frontend/src/pages/wizard/SlotEditor';
import { renderApp, renderWithProviders, setCsrfCookie } from '../helpers';
import { IDS, batch, report, template } from '../mocks/data';
import { slotPuts } from '../mocks/handlers';
import { server } from '../mocks/server';

type Json = Record<string, unknown>;
type Pair = [number, number];

const OVERLAP = 'Slots must not overlap or touch.';
const ORDER = 'Each slot must end after it starts.';
const FILL = 'Fill in every slot or remove it.';

/** The primary slot is 4.2-5.1 s and the video is 20 s long in the default fixture. */
function editor(over: Json = {}) {
  const t = template(over) as unknown as Template;
  return renderWithProviders(<SlotEditor template={t} showVideo={false} />);
}

function field(name: string): HTMLInputElement {
  return screen.getByRole('spinbutton', { name }) as HTMLInputElement;
}

/** Sets a number field the way a user's final value lands (exact decimals, no typing artefacts). */
function setValue(name: string, value: string): void {
  fireEvent.change(field(name), { target: { value } });
}

function addButton() {
  return screen.getByRole('button', { name: 'Add another name slot' });
}

function saveButton() {
  return screen.getByRole('button', { name: 'Save slot' });
}

/** Adds one extra pair per entry (Slot 2, Slot 3, ...) and fills it from the given text pair. */
async function addExtras(values: [string, string][]): Promise<void> {
  for (const [i, [start, end]] of values.entries()) {
    await userEvent.click(addButton());
    const n = i + 2;
    setValue(`Slot ${n} start (s)`, start);
    setValue(`Slot ${n} end (s)`, end);
  }
}

/** Every alert text on screen must include the expected message (several may be shown at once). */
async function expectAlert(message: string): Promise<void> {
  const alerts = await screen.findAllByRole('alert');
  expect(alerts.map((a) => a.textContent?.trim())).toContain(message);
}

function draft(tpl: Json = template()) {
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
    http.get('*/templates/:id', () => HttpResponse.json(tpl)),
  );
}

/** A stateful fake of the template slot endpoints: a save resets the confirmation, as the API does. */
function statefulSlots(initial: Json) {
  let current = initial;
  const seen = { puts: [] as unknown[], confirms: 0 };
  server.use(
    http.get('*/templates/:id', () => HttpResponse.json(current)),
    http.put('*/templates/:id/slot', async ({ request }) => {
      const body = (await request.json()) as {
        start_s: number;
        end_s: number;
        extra_slots: Pair[];
      };
      seen.puts.push(body);
      current = template({
        ...current,
        slot: { start_s: body.start_s, end_s: body.end_s },
        extra_slots: body.extra_slots,
        slot_confirmed: false,
        slots: undefined,
      });
      return HttpResponse.json(current);
    }),
    http.post('*/templates/:id/slot/confirm', () => {
      seen.confirms += 1;
      current = { ...current, slot_confirmed: true };
      return HttpResponse.json(current);
    }),
  );
  return seen;
}

beforeEach(() => {
  slotPuts.length = 0;
  setCsrfCookie();
});

describe('add and remove name slots', () => {
  it('TT-DD40-P1 "Add another name slot" shows empty "Slot 2 start (s)" and "Slot 2 end (s)" fields', async () => {
    editor();
    await userEvent.click(addButton());
    expect(field('Slot 2 start (s)')).toHaveValue(null);
    expect(field('Slot 2 end (s)')).toHaveValue(null);
  });

  it('TT-DD40-P2 each further click adds the next pair: Slot 3, then Slot 4', async () => {
    editor();
    await userEvent.click(addButton());
    await userEvent.click(addButton());
    expect(field('Slot 3 start (s)')).toHaveValue(null);
    expect(field('Slot 3 end (s)')).toHaveValue(null);
    await userEvent.click(addButton());
    expect(field('Slot 4 start (s)')).toHaveValue(null);
    expect(field('Slot 4 end (s)')).toHaveValue(null);
  });

  it('TT-DD40-P3 "Remove slot 2" removes its pair, and adding again gives an empty Slot 2', async () => {
    editor();
    await userEvent.click(addButton());
    setValue('Slot 2 start (s)', '10');
    await userEvent.click(screen.getByRole('button', { name: 'Remove slot 2' }));
    expect(screen.queryByRole('spinbutton', { name: 'Slot 2 start (s)' })).not.toBeInTheDocument();
    expect(addButton()).toBeEnabled();
    await userEvent.click(addButton());
    expect(field('Slot 2 start (s)')).toHaveValue(null);
  });

  it('TT-DD40-P4 every extra pair has its own remove button', async () => {
    editor();
    await addExtras([
      ['10', '11'],
      ['15', '16'],
    ]);
    expect(screen.getByRole('button', { name: 'Remove slot 2' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Remove slot 3' })).toBeInTheDocument();
  });

  it('TT-DD40-N1 removing an extra slot leaves the primary start and end untouched', async () => {
    editor();
    await userEvent.click(addButton());
    await userEvent.click(screen.getByRole('button', { name: 'Remove slot 2' }));
    expect(field('Slot start (s)')).toHaveValue(4.2);
    expect(field('Slot end (s)')).toHaveValue(5.1);
  });

  it('TT-DD40-E1 by default there is no extra pair, only the add button', () => {
    editor();
    expect(addButton()).toBeEnabled();
    expect(screen.queryByRole('spinbutton', { name: 'Slot 2 start (s)' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Remove slot 2' })).not.toBeInTheDocument();
  });

  it('TT-DD40-E2 with 5 slots shown (primary plus 4) the add button is disabled and no Slot 6 appears', async () => {
    editor();
    for (let i = 0; i < 4; i += 1) await userEvent.click(addButton());
    expect(field('Slot 5 start (s)')).toBeInTheDocument();
    expect(addButton()).toBeDisabled();
    expect(screen.queryByRole('spinbutton', { name: 'Slot 6 start (s)' })).not.toBeInTheDocument();
  });

  it('TT-DD40-E3 a template that already has 4 extra slots opens with the add button disabled', () => {
    editor({
      extra_slots: [
        [2, 3],
        [6, 7],
        [10, 11],
        [14, 15],
      ],
    });
    expect(field('Slot 5 start (s)')).toHaveValue(14);
    expect(addButton()).toBeDisabled();
  });
});

describe('prefill from the template extra slots', () => {
  it('TT-DD40-P5 extra_slots [[2,3],[10,11]] fill Slot 2 and Slot 3; the primary slot is unchanged', () => {
    editor({
      extra_slots: [
        [2, 3],
        [10, 11],
      ],
    });
    expect(field('Slot 2 start (s)')).toHaveValue(2);
    expect(field('Slot 2 end (s)')).toHaveValue(3);
    expect(field('Slot 3 start (s)')).toHaveValue(10);
    expect(field('Slot 3 end (s)')).toHaveValue(11);
    expect(field('Slot start (s)')).toHaveValue(4.2);
    expect(field('Slot end (s)')).toHaveValue(5.1);
  });

  it('TT-DD40-P6 a template without extra slots has no extra pair', () => {
    editor({ extra_slots: [] });
    expect(screen.queryByRole('spinbutton', { name: 'Slot 2 start (s)' })).not.toBeInTheDocument();
  });

  it('TT-DD40-P7 wizard step 3 shows the same extra pairs for a draft', async () => {
    draft(
      template({
        extra_slots: [
          [2, 3],
          [10, 11],
        ],
      }),
    );
    renderApp(`/batches/new?batch=${IDS.batch}`);
    expect(await screen.findByRole('spinbutton', { name: 'Slot 2 start (s)' })).toHaveValue(2);
    expect(screen.getByRole('spinbutton', { name: 'Slot 3 end (s)' })).toHaveValue(11);
    expect(addButton()).toBeEnabled();
  });
});

describe('save sends the slots', () => {
  it('TT-DD40-P8 zero extra slots: the body has extra_slots as an empty list', async () => {
    editor();
    await userEvent.click(saveButton());
    await waitFor(() => expect(slotPuts).toHaveLength(1));
    expect(slotPuts[0]).toEqual({ start_s: 4.2, end_s: 5.1, extra_slots: [] });
  });

  it('TT-DD40-P9 one extra slot: extra_slots is [[10, 11]]', async () => {
    editor();
    await addExtras([['10', '11']]);
    await userEvent.click(saveButton());
    await waitFor(() => expect(slotPuts).toHaveLength(1));
    expect(slotPuts[0]).toEqual({
      start_s: 4.2,
      end_s: 5.1,
      extra_slots: [[10, 11]],
    });
  });

  it('TT-DD40-P10 two extra slots: extra_slots is [[10, 11], [15, 16]]', async () => {
    editor();
    await addExtras([
      ['10', '11'],
      ['15', '16'],
    ]);
    await userEvent.click(saveButton());
    await waitFor(() => expect(slotPuts).toHaveLength(1));
    expect(slotPuts[0]).toEqual({
      start_s: 4.2,
      end_s: 5.1,
      extra_slots: [
        [10, 11],
        [15, 16],
      ],
    });
  });

  it('TT-DD40-P11 prefilled extra slots are sent unchanged when nothing is edited', async () => {
    editor({
      extra_slots: [
        [2, 3],
        [10, 11],
      ],
    });
    await userEvent.click(saveButton());
    await waitFor(() => expect(slotPuts).toHaveLength(1));
    expect(slotPuts[0]).toEqual({
      start_s: 4.2,
      end_s: 5.1,
      extra_slots: [
        [2, 3],
        [10, 11],
      ],
    });
  });

  it('TT-DD40-P12 start_s, end_s and every extra value are numbers, not strings', async () => {
    editor();
    await addExtras([
      ['10', '11'],
      ['15', '16'],
    ]);
    await userEvent.click(saveButton());
    await waitFor(() => expect(slotPuts).toHaveLength(1));
    const body = slotPuts[0] as {
      start_s: unknown;
      end_s: unknown;
      extra_slots: unknown[][];
    };
    expect(typeof body.start_s).toBe('number');
    expect(typeof body.end_s).toBe('number');
    for (const pair of body.extra_slots) {
      expect(pair).toHaveLength(2);
      expect(pair.every((v) => typeof v === 'number')).toBe(true);
    }
  });

  it('TT-DD40-N2 a removed extra slot is not sent', async () => {
    editor();
    await addExtras([['10', '11']]);
    await userEvent.click(screen.getByRole('button', { name: 'Remove slot 2' }));
    await userEvent.click(saveButton());
    await waitFor(() => expect(slotPuts).toHaveLength(1));
    expect(slotPuts[0]).toEqual({ start_s: 4.2, end_s: 5.1, extra_slots: [] });
  });

  it('TT-DD40-E4 "10.0" is sent as the number 10', async () => {
    editor();
    await addExtras([['10.0', '11']]);
    await userEvent.click(saveButton());
    await waitFor(() => expect(slotPuts).toHaveLength(1));
    expect(slotPuts[0]).toEqual({
      start_s: 4.2,
      end_s: 5.1,
      extra_slots: [[10, 11]],
    });
  });
});

describe('client checks disable Save and say why', () => {
  // [test id, what is wrong, extra pairs typed as text, exact alert text]
  const BAD: [string, string, [string, string][], string][] = [
    ['TT-DD40-N3', 'overlaps the primary slot', [['5', '6']], OVERLAP],
    ['TT-DD40-N4', 'touches the primary slot', [['5.1', '6']], OVERLAP],
    ['TT-DD40-N5', 'is 0.1 s after the primary slot', [['5.2', '6']], OVERLAP],
    ['TT-DD40-N6', 'sorts before the primary slot and overlaps it', [['1', '4.5']], OVERLAP],
    [
      'TT-DD40-N7',
      'overlaps another extra slot',
      [
        ['10', '12'],
        ['11', '13'],
      ],
      OVERLAP,
    ],
    ['TT-DD40-N8', 'ends at its start', [['12', '12']], ORDER],
    ['TT-DD40-N8', 'ends before its start', [['12', '10']], ORDER],
    ['TT-DD40-N9', 'has an empty start', [['', '11']], FILL],
    ['TT-DD40-N9', 'has an empty end', [['10', '']], FILL],
    [
      'TT-DD40-N10',
      'ends after the video (21 s of 20 s)',
      [['15', '21']],
      'Slot 2 ends after the video.',
    ],
    [
      'TT-DD40-N11',
      'is the third slot and ends after the video',
      [
        ['10', '11'],
        ['15', '21'],
      ],
      'Slot 3 ends after the video.',
    ],
  ];

  it.each(BAD)(
    '%s a slot that %s: the alert shows and Save slot is disabled',
    async (_id, _what, extras, message) => {
      editor();
      await addExtras(extras);
      await expectAlert(message);
      expect(saveButton()).toBeDisabled();
    },
  );

  it('TT-DD40-E5 a gap of exactly 0.2 s is allowed (extra starts at 5.3, primary ends at 5.1)', async () => {
    editor();
    await addExtras([['5.3', '6']]);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(saveButton()).toBeEnabled();
  });

  it('TT-DD40-E6 an extra slot ending exactly at the video duration (20 s) is allowed', async () => {
    editor();
    await addExtras([['15', '20']]);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(saveButton()).toBeEnabled();
  });

  it('TT-DD40-E7 fixing the value removes the alert and enables Save again', async () => {
    editor();
    await addExtras([['15', '21']]);
    await expectAlert('Slot 2 ends after the video.');
    expect(saveButton()).toBeDisabled();
    setValue('Slot 2 end (s)', '16');
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(saveButton()).toBeEnabled();
  });

  it('TT-DD40-E8 valid slots typed out of order (sorted by start, gap >= 0.2 s) are accepted', async () => {
    editor();
    await addExtras([
      ['15', '16'],
      ['10', '11'],
    ]);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(saveButton()).toBeEnabled();
  });
});

describe('after a save the slot must be confirmed again (wizard step 3)', () => {
  /** Opens the draft with a confirmed slot, adds Slot 2 = 10-11 s and saves it. */
  async function saveExtraSlotInWizard() {
    // server.use prepends: the stateful template handlers must be registered after draft()'s.
    draft(template({ slot_confirmed: true }));
    const api = statefulSlots(template({ slot_confirmed: true }));
    renderApp(`/batches/new?batch=${IDS.batch}`);
    expect(await screen.findByText('Slot confirmed')).toBeInTheDocument();
    await addExtras([['10', '11']]);
    await userEvent.click(saveButton());
    await waitFor(() => expect(api.puts).toHaveLength(1));
    return api;
  }

  it('TT-DD40-P13 a save with an extra slot removes "Slot confirmed" and shows Confirm slot again', async () => {
    const api = await saveExtraSlotInWizard();
    expect(api.puts[0]).toEqual({
      start_s: 4.2,
      end_s: 5.1,
      extra_slots: [[10, 11]],
    });
    await waitFor(() => expect(screen.queryByText('Slot confirmed')).not.toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Confirm slot' })).toBeInTheDocument();
  });

  it('TT-DD40-P14 Confirm slot after the save posts once and shows "Slot confirmed" again', async () => {
    const api = await saveExtraSlotInWizard();
    await userEvent.click(await screen.findByRole('button', { name: 'Confirm slot' }));
    await waitFor(() => expect(api.confirms).toBe(1));
    expect(await screen.findByText('Slot confirmed')).toBeInTheDocument();
  });
});
