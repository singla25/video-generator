// T-UI-controls: batch controls on the Overview current-batch panel. Cases: TT-UI-CTL-*
//
// CONTRACT (frontend/src/components/CurrentBatchPanel.tsx, RowsTable):
//   DRAFT batch   row chips read "Not started" (never "Queued"); panel offers the "Continue setup" link
//                 (DD-38, replaces "Start batch") and a "Delete draft" button -> dialog
//                 "Delete this draft?" [Delete | Keep];
//                 Delete sends DELETE /batches/{id} (204), then the lists refetch.
//   RUNNING       "Pause" and "Cancel batch"; Cancel asks first: dialog "Cancel this batch?"
//                 [Yes, cancel batch | Keep running], then POST /batches/{id}/cancel.
//   PAUSED        "Resume" and "Cancel batch".
//   COMPLETED / CANCELLED   none of: Pause, Resume, Cancel batch, Delete draft, Start batch.
//   A failed action shows its API message in role=alert; buttons are disabled while pending.
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, delay, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { renderApp } from '../helpers';
import { ROWS_BY_STATUS, batch, row, rowsPage } from '../mocks/data';
import { apiError } from '../mocks/handlers';
import { server } from '../mocks/server';
import { setReducedMotion } from '../motion';

const QUEUED_ROWS = [1, 2, 3].map((n) =>
  row(n, { status: 'QUEUED', has_video: false, render_seconds: null }),
);

function listOf(batches: unknown[]) {
  return HttpResponse.json({
    batches,
    page: 1,
    page_size: 50,
    total: batches.length,
    total_pages: 1,
  });
}

function serve(state: string, rows = ROWS_BY_STATUS) {
  server.use(
    http.get('*/batches', () => listOf([batch({ status: state })])),
    http.get('*/batches/:id/rows', () => HttpResponse.json(rowsPage(rows))),
  );
}

/** Record every action POST and DELETE sent to the batch endpoints. */
function record(): string[] {
  const calls: string[] = [];
  server.use(
    http.post('*/batches/:id/:action', ({ params }) => {
      calls.push(`POST ${String(params.action)}`);
      return HttpResponse.json({});
    }),
    http.delete('*/batches/:id', () => {
      calls.push('DELETE');
      return new HttpResponse(null, { status: 204 });
    }),
  );
  return calls;
}

async function panel() {
  setReducedMotion(true);
  renderApp('/');
  return within(await screen.findByTestId('current-batch'));
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

describe('draft batch', () => {
  it('TT-UI-CTL-P1 rows read "Not started" instead of "Queued"', async () => {
    serve('DRAFT', QUEUED_ROWS);
    await panel();
    await screen.findByText('Test Person 3');
    const rows = screen.getAllByRole('row').filter((r) => r.textContent?.includes('Test Person'));
    expect(rows).toHaveLength(3);
    for (const chip of within(rows[0]!.parentElement!).getAllByTestId('status-chip')) {
      expect(chip).toHaveTextContent('Not started');
      expect(chip).not.toHaveTextContent('Queued');
    }
  });

  it('TT-UI-CTL-P2 panel offers Continue setup and Delete draft', async () => {
    serve('DRAFT', QUEUED_ROWS);
    const p = await panel();
    expect(p.getByRole('link', { name: 'Continue setup' })).toBeInTheDocument();
    expect(p.getByRole('button', { name: 'Delete draft' })).toBeInTheDocument();
    expect(p.queryByRole('button', { name: 'Pause' })).not.toBeInTheDocument();
  });

  it('TT-UI-CTL-P3 confirming Delete calls DELETE and the batch disappears', async () => {
    let deleted = false;
    const calls: string[] = [];
    server.use(
      http.get('*/batches', () => listOf(deleted ? [] : [batch({ status: 'DRAFT' })])),
      http.get('*/batches/:id/rows', () => HttpResponse.json(rowsPage(QUEUED_ROWS))),
      http.delete('*/batches/:id', () => {
        deleted = true;
        calls.push('DELETE');
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const p = await panel();
    await userEvent.click(p.getByRole('button', { name: 'Delete draft' }));
    const dialog = await screen.findByRole('dialog', { name: 'Delete this draft?' });
    await userEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));
    expect(await screen.findByText('No batches yet')).toBeInTheDocument();
    expect(screen.queryByTestId('current-batch')).not.toBeInTheDocument();
    expect(calls).toEqual(['DELETE']);
  });

  it('TT-UI-CTL-N1 Keep closes the dialog and calls nothing', async () => {
    serve('DRAFT', QUEUED_ROWS);
    const calls = record();
    const p = await panel();
    await userEvent.click(p.getByRole('button', { name: 'Delete draft' }));
    const dialog = await screen.findByRole('dialog', { name: 'Delete this draft?' });
    await userEvent.click(within(dialog).getByRole('button', { name: 'Keep' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(calls).toEqual([]);
    expect(screen.getByTestId('current-batch')).toBeInTheDocument();
  });

  it('TT-UI-CTL-N2 a failed DELETE shows the message and keeps the batch', async () => {
    serve('DRAFT', QUEUED_ROWS);
    server.use(
      http.delete('*/batches/:id', () =>
        apiError(500, 'INTERNAL_ERROR', 'The draft could not be deleted.'),
      ),
    );
    const p = await panel();
    await userEvent.click(p.getByRole('button', { name: 'Delete draft' }));
    const dialog = await screen.findByRole('dialog', { name: 'Delete this draft?' });
    await userEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('The draft could not be deleted.');
    expect(screen.getByTestId('current-batch')).toBeInTheDocument();
  });

  it('TT-UI-CTL-E1 double click on Delete sends one request', async () => {
    serve('DRAFT', QUEUED_ROWS);
    const calls: string[] = [];
    server.use(
      http.delete('*/batches/:id', async () => {
        calls.push('DELETE');
        await delay(50);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const p = await panel();
    await userEvent.click(p.getByRole('button', { name: 'Delete draft' }));
    const confirm = within(await screen.findByRole('dialog')).getByRole('button', {
      name: 'Delete',
    });
    await userEvent.dblClick(confirm);
    await waitFor(() => expect(calls.length).toBeGreaterThan(0));
    await sleep(150);
    expect(calls).toEqual(['DELETE']);
  });

  it('TT-UI-CTL-E2 a running batch keeps "Queued" chips and has no Delete draft', async () => {
    serve('RUNNING');
    const p = await panel();
    expect(p.queryByRole('button', { name: 'Delete draft' })).not.toBeInTheDocument();
    const chips = await screen.findAllByTestId('status-chip');
    expect(chips.some((c) => c.textContent === 'Queued')).toBe(true);
    expect(chips.some((c) => c.textContent === 'Not started')).toBe(false);
  });
});

describe('running and paused batches', () => {
  it('TT-UI-CTL-P4 running: Pause calls pause and Cancel batch is offered', async () => {
    serve('RUNNING');
    const calls = record();
    const p = await panel();
    expect(p.getByRole('button', { name: 'Cancel batch' })).toBeInTheDocument();
    await userEvent.click(p.getByRole('button', { name: 'Pause' }));
    await waitFor(() => expect(calls).toEqual(['POST pause']));
  });

  it('TT-UI-CTL-P5 Cancel batch asks first, then calls cancel', async () => {
    serve('RUNNING');
    const calls = record();
    const p = await panel();
    await userEvent.click(p.getByRole('button', { name: 'Cancel batch' }));
    expect(calls).toEqual([]);
    const dialog = await screen.findByRole('dialog', { name: 'Cancel this batch?' });
    await userEvent.click(within(dialog).getByRole('button', { name: 'Yes, cancel batch' }));
    await waitFor(() => expect(calls).toEqual(['POST cancel']));
  });

  it('TT-UI-CTL-P6 paused: Resume calls resume and Cancel batch is offered', async () => {
    serve('PAUSED');
    const calls = record();
    const p = await panel();
    expect(p.getByRole('button', { name: 'Cancel batch' })).toBeInTheDocument();
    expect(p.queryByRole('button', { name: 'Pause' })).not.toBeInTheDocument();
    await userEvent.click(p.getByRole('button', { name: 'Resume' }));
    await waitFor(() => expect(calls).toEqual(['POST resume']));
  });

  it('TT-UI-CTL-N3 Keep running closes the dialog and sends nothing', async () => {
    serve('RUNNING');
    const calls = record();
    const p = await panel();
    await userEvent.click(p.getByRole('button', { name: 'Cancel batch' }));
    await userEvent.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Keep running' }),
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(calls).toEqual([]);
  });

  it('TT-UI-CTL-N4 a 409 from Pause shows its message', async () => {
    serve('RUNNING');
    server.use(
      http.post('*/batches/:id/pause', () =>
        apiError(409, 'INVALID_STATE', 'The batch already finished.'),
      ),
    );
    const p = await panel();
    await userEvent.click(p.getByRole('button', { name: 'Pause' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('The batch already finished.');
  });

  it('TT-UI-CTL-N5 a 409 on cancel shows its message and closes the dialog', async () => {
    serve('RUNNING');
    server.use(
      http.post('*/batches/:id/cancel', () =>
        apiError(409, 'INVALID_STATE', 'Already cancelled.'),
      ),
    );
    const p = await panel();
    await userEvent.click(p.getByRole('button', { name: 'Cancel batch' }));
    await userEvent.click(
      within(await screen.findByRole('dialog')).getByRole('button', {
        name: 'Yes, cancel batch',
      }),
    );
    expect(await screen.findByRole('alert')).toHaveTextContent('Already cancelled.');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('TT-UI-CTL-E3 double click on Pause sends one request; buttons disable while pending', async () => {
    serve('RUNNING');
    const calls: string[] = [];
    server.use(
      http.post('*/batches/:id/pause', async () => {
        calls.push('pause');
        await delay(100);
        return HttpResponse.json({});
      }),
    );
    const p = await panel();
    await userEvent.dblClick(p.getByRole('button', { name: 'Pause' }));
    await waitFor(() => expect(p.getByRole('button', { name: 'Cancel batch' })).toBeDisabled());
    expect(p.getByRole('button', { name: 'Pause' })).toBeDisabled();
    await sleep(200);
    expect(calls).toEqual(['pause']);
  });

  it('TT-UI-CTL-E4 Cancel batch is disabled while Resume is pending', async () => {
    serve('PAUSED');
    server.use(
      http.post('*/batches/:id/resume', async () => {
        await delay(100);
        return HttpResponse.json({});
      }),
    );
    const p = await panel();
    await userEvent.click(p.getByRole('button', { name: 'Resume' }));
    await waitFor(() => expect(p.getByRole('button', { name: 'Cancel batch' })).toBeDisabled());
  });
});

describe('finished batches', () => {
  it.each(['COMPLETED', 'CANCELLED'])('TT-UI-CTL-P7 %s batch shows no controls', async (state) => {
    serve(state);
    const p = await panel();
    for (const name of ['Pause', 'Resume', 'Cancel batch', 'Delete draft']) {
      expect(p.queryByRole('button', { name })).not.toBeInTheDocument();
    }
    expect(p.queryByRole('link', { name: 'Start batch' })).not.toBeInTheDocument();
  });
});
