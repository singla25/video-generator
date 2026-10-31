// DD-37 B: wizard step 4 "Videos to generate" and the limit sent with the start. Cases: TT-DD37-B-*
//
// CONTRACT (frontend/src/pages/wizard/StepOutput.tsx):
//   radio group named "Videos to generate" with radios "All N rows" (N = valid rows of the batch,
//     default), "First 5", "First 10", "First 15", "Custom"
//   options larger than N are disabled (N = 8: "First 10" and "First 15" disabled)
//   "Custom" reveals a number input named "Number of videos" (min 1, max N)
//   summary under the group: "You will get X videos. The other Y rows are skipped." when X < N,
//     "You will get N videos." when all
//   "Review and start" -> dialog -> "Confirm and start" posts POST /batches/<id>/start with
//     JSON {folder_name, limit}; limit only when the choice is not All. For Custom only when the
//     typed number is an integer from 1 to N-1. 0, a negative, empty or above-N value disables
//     "Review and start" and shows "Enter a number from 1 to N" (N written out, e.g. 8).
//   The Idempotency-Key header stays.
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { renderApp } from '../helpers';
import { IDS, batch, report } from '../mocks/data';
import { server } from '../mocks/server';

const PREVIEW_APPROVED = { status: 'READY', approved: true };

/** Serve a draft batch whose sheet has `validRows` valid rows, so step 3 can be passed. */
function draftWithRows(validRows: number) {
  server.use(
    http.get('*/batches/:id', () =>
      HttpResponse.json(
        batch({
          status: 'DRAFT',
          preview: PREVIEW_APPROVED,
          report: report({ total_rows: validRows + 2, valid_rows: validRows, skipped_rows: 2 }),
        }),
      ),
    ),
  );
}

/** Open step 4 of the wizard for a draft with `validRows` valid rows. */
async function openStep4(validRows = 8) {
  draftWithRows(validRows);
  renderApp(`/batches/new?batch=${IDS.batch}`);
  await userEvent.click(await screen.findByRole('button', { name: 'Next' }));
  await screen.findByRole('textbox', { name: 'Output folder' });
}

function group(): HTMLElement {
  return screen.getByRole('radiogroup', { name: 'Videos to generate' });
}

function option(name: string): HTMLElement {
  return within(group()).getByRole('radio', { name });
}

/** Record the JSON body of every start request. */
function captureStarts(): unknown[] {
  const bodies: unknown[] = [];
  server.use(
    http.post('*/batches/:id/start', async ({ request }) => {
      bodies.push(await request.json());
      return HttpResponse.json(batch());
    }),
  );
  return bodies;
}

async function setFolder(name: string) {
  const folder = screen.getByRole('textbox', { name: 'Output folder' });
  await userEvent.clear(folder);
  await userEvent.type(folder, name);
}

/** Press Review and start, then Confirm and start in the dialog. */
async function startBatch() {
  await userEvent.click(screen.getByRole('button', { name: 'Review and start' }));
  const dialog = await screen.findByRole('dialog');
  await userEvent.click(within(dialog).getByRole('button', { name: 'Confirm and start' }));
}

async function typeCustom(value: string) {
  const box = screen.getByRole('spinbutton', { name: 'Number of videos' });
  await userEvent.clear(box);
  if (value !== '') await userEvent.type(box, value);
}

describe('options', () => {
  it('TT-DD37-B-P1 the group offers All N rows, First 5, First 10, First 15 and Custom, All selected', async () => {
    await openStep4(8);
    expect(group()).toBeInTheDocument();
    expect(within(group()).getAllByRole('radio')).toHaveLength(5);
    for (const name of ['All 8 rows', 'First 5', 'First 10', 'First 15', 'Custom']) {
      expect(option(name)).toBeInTheDocument();
    }
    expect(option('All 8 rows')).toBeChecked();
  });

  it('TT-DD37-B-P2 with 8 rows First 5 is enabled while First 10 and First 15 are disabled', async () => {
    await openStep4(8);
    expect(option('First 5')).toBeEnabled();
    expect(option('First 10')).toBeDisabled();
    expect(option('First 15')).toBeDisabled();
  });

  it('TT-DD37-B-P3 with 20 rows every fixed option is enabled and All reads All 20 rows', async () => {
    await openStep4(20);
    expect(option('All 20 rows')).toBeEnabled();
    expect(option('First 5')).toBeEnabled();
    expect(option('First 10')).toBeEnabled();
    expect(option('First 15')).toBeEnabled();
  });

  it('TT-DD37-B-P4 the summary names the videos and the skipped rows when fewer than all are chosen', async () => {
    await openStep4(8);
    await userEvent.click(option('First 5'));
    expect(
      await screen.findByText('You will get 5 videos. The other 3 rows are skipped.'),
    ).toBeInTheDocument();
    await userEvent.click(option('All 8 rows'));
    expect(await screen.findByText('You will get 8 videos.')).toBeInTheDocument();
  });

  it('TT-DD37-B-P5 Custom reveals the number field, and typing 3 summarises 3 of 8', async () => {
    await openStep4(8);
    expect(screen.queryByRole('spinbutton', { name: 'Number of videos' })).not.toBeInTheDocument();
    await userEvent.click(option('Custom'));
    const box = await screen.findByRole('spinbutton', { name: 'Number of videos' });
    await userEvent.type(box, '3');
    expect(
      await screen.findByText('You will get 3 videos. The other 5 rows are skipped.'),
    ).toBeInTheDocument();
  });

  it('TT-DD37-B-P6 the number field has min 1 and max equal to the valid rows', async () => {
    await openStep4(8);
    await userEvent.click(option('Custom'));
    const box = await screen.findByRole('spinbutton', { name: 'Number of videos' });
    expect(box).toHaveAttribute('min', '1');
    expect(box).toHaveAttribute('max', '8');
  });
});

describe('start request body', () => {
  it('TT-DD37-B-P7 First 5 posts folder_name and limit 5', async () => {
    const bodies = captureStarts();
    await openStep4(8);
    await userEvent.click(option('First 5'));
    await setFolder('ward-12');
    await startBatch();
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toEqual({ folder_name: 'ward-12', limit: 5 });
  });

  it('TT-DD37-B-P8 All sends no limit at all', async () => {
    const bodies = captureStarts();
    await openStep4(8);
    await setFolder('ward-12');
    await startBatch();
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toEqual({ folder_name: 'ward-12' });
    expect(bodies[0]).not.toHaveProperty('limit');
  });

  it('TT-DD37-B-P9 Custom with 3 posts limit 3', async () => {
    const bodies = captureStarts();
    await openStep4(8);
    await userEvent.click(option('Custom'));
    await typeCustom('3');
    await setFolder('ward-12');
    await startBatch();
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toEqual({ folder_name: 'ward-12', limit: 3 });
  });

  it('TT-DD37-B-P10 the Idempotency-Key header is still sent with the limit', async () => {
    let key: string | null = null;
    server.use(
      http.post('*/batches/:id/start', ({ request }) => {
        key = request.headers.get('idempotency-key');
        return HttpResponse.json(batch());
      }),
    );
    await openStep4(8);
    await userEvent.click(option('First 5'));
    await setFolder('ward-12');
    await startBatch();
    await waitFor(() => expect(key).toMatch(/\S{8,}/));
  });

  it('TT-DD37-B-N1 switching back to All drops the limit again', async () => {
    const bodies = captureStarts();
    await openStep4(8);
    await userEvent.click(option('First 5'));
    await userEvent.click(option('All 8 rows'));
    await setFolder('ward-12');
    await startBatch();
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).not.toHaveProperty('limit');
  });
});

describe('custom number refused', () => {
  it.each([
    ['0', '0'],
    ['a negative number', '-2'],
    ['an empty value', ''],
    ['a number above the valid rows', '9'],
  ])(
    'TT-DD37-B-N2 Custom with %s disables Review and start and says the range',
    async (_label, value) => {
      await openStep4(8);
      await userEvent.click(option('Custom'));
      await typeCustom(value);
      expect(screen.getByRole('button', { name: 'Review and start' })).toBeDisabled();
      expect(await screen.findByText('Enter a number from 1 to 8')).toBeInTheDocument();
    },
  );

  it('TT-DD37-B-N3 an invalid custom number sends no start request and opens no dialog', async () => {
    const bodies = captureStarts();
    await openStep4(8);
    await userEvent.click(option('Custom'));
    await typeCustom('0');
    await userEvent.click(screen.getByRole('button', { name: 'Review and start' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(bodies).toHaveLength(0);
  });
});

describe('edge', () => {
  it.each([1, 7])(
    'TT-DD37-B-E1 Custom %i (the bounds 1 and N-1 of 8) is sent as the limit',
    async (n) => {
      const bodies = captureStarts();
      await openStep4(8);
      await userEvent.click(option('Custom'));
      await typeCustom(String(n));
      await setFolder('ward-12');
      await startBatch();
      await waitFor(() => expect(bodies).toHaveLength(1));
      expect(bodies[0]).toEqual({ folder_name: 'ward-12', limit: n });
    },
  );

  it('TT-DD37-B-E2 Custom equal to N is accepted and sends no limit', async () => {
    const bodies = captureStarts();
    await openStep4(8);
    await userEvent.click(option('Custom'));
    await typeCustom('8');
    expect(screen.getByRole('button', { name: 'Review and start' })).toBeEnabled();
    await setFolder('ward-12');
    await startBatch();
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).not.toHaveProperty('limit');
  });

  it('TT-DD37-B-E3 with 20 rows First 15 is allowed and sends limit 15', async () => {
    const bodies = captureStarts();
    await openStep4(20);
    await userEvent.click(option('First 15'));
    await setFolder('ward-12');
    await startBatch();
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toEqual({ folder_name: 'ward-12', limit: 15 });
  });

  it('TT-DD37-B-E4 with a single valid row every fixed option is disabled', async () => {
    await openStep4(1);
    expect(option('First 5')).toBeDisabled();
    expect(option('First 10')).toBeDisabled();
    expect(option('First 15')).toBeDisabled();
  });
});
