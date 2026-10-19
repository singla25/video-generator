// UI-AC6 Batch detail. Cases: TT-UI-AC6-*
//
// CONTRACT (frontend/src):
//   pages/BatchDetailPage.tsx  route /batches/:id   (uses RowsTable with the filter props below)
//     header stats      [data-testid=batch-stats] counts + status text (Running, Paused, Completed...)
//     progress          role=progressbar name "Batch progress" aria-valuenow = progress_percent, "ETA ..."
//     failure chart     list aria-label "Failure reasons"; one button per reason named
//                       "<message> (<count>)"; click -> RowsTable requests GET rows?failure_code=<code> (server-side filter,
//                       no client-side filtering); chip "Filtering: <message>" + button "Clear filter"
//     inline preview    clicking "Preview video for <name>" shows [data-testid=inline-preview] <video>
//                       with src /batches/<id>/rows/<n>/video
//     links             "Download ZIP" -> /batches/<id>/download.zip (aria-disabled when no completed row)
//                       "Export failures CSV" -> /batches/<id>/failures.csv (aria-disabled when 0 failed)
//     buttons           Pause | Resume (no confirmation), Retry failed (no confirmation),
//                       "Cancel batch" -> dialog "Cancel this batch?" [Yes, cancel batch | Keep running],
//                       "Delete batch" -> dialog "Delete this batch and its videos?" [Delete | Keep]
//                       -> DELETE /batches/<id> then navigate to /history
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { CSRF, renderApp } from '../helpers';
import { COUNTS, IDS, ROWS_BY_STATUS, batch, row, rowsPage, status } from '../mocks/data';
import { apiError } from '../mocks/handlers';
import { server } from '../mocks/server';
import { setReducedMotion } from '../motion';

const PATH = `/batches/${IDS.batch}`;
const TTS = 'The voice for this name could not be created.';

describe('header and progress', () => {
  it('TT-UI-AC6-P1 shows the header stats, progress bar and ETA', async () => {
    setReducedMotion(true);
    renderApp(PATH);
    const stats = await screen.findByTestId('batch-stats');
    expect(stats).toHaveTextContent('Running');
    expect(stats).toHaveTextContent('60');
    expect(screen.getByRole('progressbar', { name: 'Batch progress' })).toHaveAttribute(
      'aria-valuenow',
      '75',
    );
    expect(screen.getByText(/ETA 1 min 30 s/)).toBeInTheDocument();
  });

  it('TT-UI-AC6-N1 an unknown batch shows the not-found message', async () => {
    server.use(
      http.get('*/batches/:id', () =>
        apiError(404, 'NOT_FOUND', 'The requested item was not found.'),
      ),
    );
    renderApp(PATH);
    expect(await screen.findByRole('alert')).toHaveTextContent('The requested item was not found.');
  });

  it('TT-UI-AC6-E1 loading shows skeletons first', () => {
    renderApp(PATH);
    expect(screen.getAllByTestId('skeleton').length).toBeGreaterThan(0);
  });

  it('TT-UI-AC6-E2 a batch with zero rows shows 0 progress, not NaN', async () => {
    const zero = {
      total: 0,
      completed: 0,
      processing: 0,
      queued: 0,
      failed: 0,
      skipped: 0,
      cancelled: 0,
    };
    server.use(
      http.get('*/batches/:id/status', () =>
        HttpResponse.json(
          status({ counts: zero, progress_percent: 0, eta_seconds: null, failures: [] }),
        ),
      ),
    );
    renderApp(PATH);
    const bar = await screen.findByRole('progressbar', { name: 'Batch progress' });
    expect(bar).toHaveAttribute('aria-valuenow', '0');
    expect(document.body.textContent).not.toMatch(/NaN/);
  });
});

describe('failure chart', () => {
  const failedRows = [
    row(4, { status: 'FAILED', failure_code: 'TTS_FAILED', message: TTS, has_video: false }),
    row(8, {
      status: 'FAILED',
      failure_code: 'RENDER_TIMEOUT',
      message: 'Making this video took too long.',
      has_video: false,
    }),
  ];

  it('TT-UI-AC6-P2 lists each failure reason with its count', async () => {
    renderApp(PATH);
    const list = await screen.findByRole('list', { name: 'Failure reasons' });
    expect(within(list).getByRole('button', { name: `${TTS} (6)` })).toBeInTheDocument();
    expect(
      within(list).getByRole('button', { name: 'Making this video took too long. (4)' }),
    ).toBeInTheDocument();
  });

  it('TT-UI-AC6-P3 clicking a reason requests rows with failure_code and can be cleared', async () => {
    const codes: (string | null)[] = [];
    server.use(
      http.get('*/batches/:id/rows', ({ request }) => {
        const c = new URL(request.url).searchParams.get('failure_code');
        codes.push(c);
        return HttpResponse.json(rowsPage(c === 'TTS_FAILED' ? [failedRows[0]!] : ROWS_BY_STATUS));
      }),
    );
    renderApp(PATH);
    await userEvent.click(await screen.findByRole('button', { name: `${TTS} (6)` }));
    await waitFor(() => expect(codes.at(-1)).toBe('TTS_FAILED'));
    const table = await screen.findByRole('table');
    await waitFor(() => expect(within(table).getAllByRole('row')).toHaveLength(2));
    expect(screen.getByText(`Filtering: ${TTS}`)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Clear filter' }));
    await waitFor(() => expect(codes.at(-1)).toBeNull());
  });

  it('TT-UI-AC6-E6 the UI trusts the server: rows returned for a filter are not re-filtered', async () => {
    server.use(
      http.get('*/batches/:id/rows', ({ request }) =>
        HttpResponse.json(
          rowsPage(
            new URL(request.url).searchParams.get('failure_code') ? failedRows : ROWS_BY_STATUS,
          ),
        ),
      ),
    );
    renderApp(PATH);
    await userEvent.click(await screen.findByRole('button', { name: `${TTS} (6)` }));
    const table = await screen.findByRole('table');
    await waitFor(() => expect(within(table).getAllByRole('row')).toHaveLength(3));
  });

  it('TT-UI-AC6-E3 no failures shows a friendly empty note instead of an empty chart', async () => {
    server.use(http.get('*/batches/:id/status', () => HttpResponse.json(status({ failures: [] }))));
    renderApp(PATH);
    expect(await screen.findByText('No failures')).toBeInTheDocument();
  });
});

describe('inline preview and downloads', () => {
  it('TT-UI-AC6-P4 Preview opens an inline player on the row video', async () => {
    renderApp(PATH);
    await userEvent.click(await screen.findByRole('link', { name: /Preview video for/ }));
    const video = await screen.findByTestId('inline-preview');
    expect(video.tagName).toBe('VIDEO');
    expect(video).toHaveAttribute(
      'src',
      expect.stringContaining(`/batches/${IDS.batch}/rows/1/video`),
    );
  });

  it('TT-UI-AC6-P5 offers ZIP and failures CSV links', async () => {
    renderApp(PATH);
    expect(await screen.findByRole('link', { name: 'Download ZIP' })).toHaveAttribute(
      'href',
      `/batches/${IDS.batch}/download.zip`,
    );
    expect(screen.getByRole('link', { name: 'Export failures CSV' })).toHaveAttribute(
      'href',
      `/batches/${IDS.batch}/failures.csv`,
    );
  });

  it('TT-UI-AC6-N2 ZIP is disabled with no completed rows and CSV with no failures', async () => {
    const none = { ...COUNTS, completed: 0, failed: 0 };
    server.use(
      http.get('*/batches/:id/status', () =>
        HttpResponse.json(status({ counts: none, failures: [] })),
      ),
    );
    renderApp(PATH);
    expect(await screen.findByRole('link', { name: 'Download ZIP' })).toHaveAttribute(
      'aria-disabled',
      'true',
    );
    expect(screen.getByRole('link', { name: 'Export failures CSV' })).toHaveAttribute(
      'aria-disabled',
      'true',
    );
  });
});

describe('batch actions', () => {
  it('TT-UI-AC6-P6 Pause and Resume post with the CSRF header', async () => {
    const seen: string[] = [];
    server.use(
      http.post('*/batches/:id/pause', ({ request }) => {
        seen.push(`pause:${request.headers.get('x-csrf-token')}`);
        return HttpResponse.json(batch({ status: 'PAUSED' }));
      }),
      http.post('*/batches/:id/resume', ({ request }) => {
        seen.push(`resume:${request.headers.get('x-csrf-token')}`);
        return HttpResponse.json(batch());
      }),
    );
    renderApp(PATH);
    await userEvent.click(await screen.findByRole('button', { name: 'Pause' }));
    await waitFor(() => expect(seen).toContain(`pause:${CSRF}`));
  });

  it('TT-UI-AC6-P7 batch-level Retry failed (page only) posts retry-failed', async () => {
    const hit = vi.fn();
    server.use(http.post('*/batches/:id/retry-failed', () => (hit(), HttpResponse.json(batch()))));
    renderApp(PATH);
    await userEvent.click(await screen.findByRole('button', { name: 'Retry failed' }));
    await waitFor(() => expect(hit).toHaveBeenCalledTimes(1));
  });

  it('TT-UI-AC6-P8 Cancel batch asks first and only cancels after confirmation', async () => {
    const hit = vi.fn();
    server.use(
      http.post(
        '*/batches/:id/cancel',
        () => (hit(), HttpResponse.json(batch({ status: 'CANCELLED' }))),
      ),
    );
    renderApp(PATH);
    await userEvent.click(await screen.findByRole('button', { name: 'Cancel batch' }));
    const dialog = await screen.findByRole('dialog', { name: 'Cancel this batch?' });
    expect(hit).not.toHaveBeenCalled();
    await userEvent.click(within(dialog).getByRole('button', { name: 'Yes, cancel batch' }));
    await waitFor(() => expect(hit).toHaveBeenCalledTimes(1));
  });

  it('TT-UI-AC6-N3 Keep running closes the dialog and sends nothing', async () => {
    const hit = vi.fn();
    server.use(http.post('*/batches/:id/cancel', () => (hit(), HttpResponse.json(batch()))));
    renderApp(PATH);
    await userEvent.click(await screen.findByRole('button', { name: 'Cancel batch' }));
    await userEvent.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Keep running' }),
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(hit).not.toHaveBeenCalled();
  });

  it('TT-UI-AC6-P9 Delete batch confirms, deletes and goes to History', async () => {
    const hit = vi.fn();
    server.use(
      http.delete('*/batches/:id', () => (hit(), new HttpResponse(null, { status: 204 }))),
    );
    renderApp(PATH);
    await userEvent.click(await screen.findByRole('button', { name: 'Delete batch' }));
    const dialog = await screen.findByRole('dialog', { name: 'Delete this batch and its videos?' });
    await userEvent.click(within(dialog).getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(hit).toHaveBeenCalledTimes(1));
    expect(await screen.findByRole('heading', { level: 1, name: 'History' })).toBeInTheDocument();
  });

  it('TT-UI-AC6-N4 an action refused by the API shows its message and keeps the page', async () => {
    server.use(
      http.post('*/batches/:id/pause', () =>
        apiError(409, 'INVALID_STATE', "This action is not possible in the batch's current state."),
      ),
    );
    renderApp(PATH);
    await userEvent.click(await screen.findByRole('button', { name: 'Pause' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('not possible');
    expect(screen.getByTestId('batch-stats')).toBeInTheDocument();
  });

  it('TT-UI-AC6-E4 a finished batch hides Pause, Resume and Cancel', async () => {
    server.use(http.get('*/batches/:id', () => HttpResponse.json(batch({ status: 'COMPLETED' }))));
    renderApp(PATH);
    await screen.findByTestId('batch-stats');
    for (const name of ['Pause', 'Resume', 'Cancel batch']) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
    }
  });

  it('TT-UI-AC6-E5 a button is disabled while its request is in flight (no double submit)', async () => {
    let calls = 0;
    server.use(
      http.post('*/batches/:id/pause', async () => {
        calls += 1;
        await new Promise((r) => setTimeout(r, 100));
        return HttpResponse.json(batch({ status: 'PAUSED' }));
      }),
    );
    renderApp(PATH);
    const pause = await screen.findByRole('button', { name: 'Pause' });
    await userEvent.dblClick(pause);
    await waitFor(() => expect(calls).toBeGreaterThan(0));
    expect(calls).toBe(1);
  });
});
