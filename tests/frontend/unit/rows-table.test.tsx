// UI-AC4 Rows table, UI-AC11 Hindi. Cases: TT-UI-AC4-*, TT-UI-AC11-*
//
// CONTRACT (frontend/src):
//   components/StatusChip.tsx  export StatusChip({ status })  status: QUEUED|PROCESSING|COMPLETED|
//        FAILED|SKIPPED|CANCELLED; [data-testid=status-chip] with the label (Completed, Processing,
//        Queued, Failed, Skipped, Cancelled) and data-tone = green|blue|grey|red|amber|grey
//   components/RowsTable.tsx   export RowsTable({ batchId: string; status?: RowStatus; failureCode?: string })  (failureCode -> query failure_code)
//        table (role=table) with column headers Name, ID, Status, Reason, Render time, Actions
//        textbox "Search by name or ID" (debounced <= 400 ms; query params search=, page=1)
//        combobox "Status" (All, Completed, Processing, Queued, Failed, Skipped) -> status=FAILED...
//        paging: "Page 1 of 3", buttons "Previous page" / "Next page", page_size 50
//        per row: link "Preview video for <name>" (completed only), link "Download video for <name>"
//          href /batches/<id>/rows/<n>/video, button "Retry row <n>" (failed only) -> POST
//          /batches/<id>/rows/<n>/retry (per row, DD-18; never retry-failed), then refetch rows
//        a cell containing Devanagari gets lang="hi"; names are rendered as text, never HTML
//        empty result "No rows match", error role=alert "Could not load rows"
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { RowsTable } from '../../../frontend/src/components/RowsTable';
import { StatusChip } from '../../../frontend/src/components/StatusChip';
import { CSRF, renderWithProviders, setCsrfCookie } from '../helpers';
import { DEVANAGARI_NAME, IDS, ROWS_BY_STATUS, row, rowsPage } from '../mocks/data';
import { server } from '../mocks/server';

const CHIPS = [
  ['COMPLETED', 'Completed', 'green'],
  ['PROCESSING', 'Processing', 'blue'],
  ['QUEUED', 'Queued', 'grey'],
  ['FAILED', 'Failed', 'red'],
  ['SKIPPED', 'Skipped', 'amber'],
  ['CANCELLED', 'Cancelled', 'grey'],
] as const;

function table() {
  setCsrfCookie();
  return renderWithProviders(<RowsTable batchId={IDS.batch} />);
}

describe('StatusChip', () => {
  it.each(CHIPS)('TT-UI-AC4-P1 %s shows "%s" in %s', (status, label, tone) => {
    renderWithProviders(<StatusChip status={status} />);
    const chip = screen.getByTestId('status-chip');
    expect(chip).toHaveTextContent(label);
    expect(chip).toHaveAttribute('data-tone', tone);
  });

  it('TT-UI-AC4-E1 an unknown status renders a neutral chip, not a crash', () => {
    renderWithProviders(<StatusChip status={'WEIRD' as never} />);
    expect(screen.getByTestId('status-chip')).toHaveAttribute('data-tone', 'grey');
  });
});

describe('rows rendering', () => {
  it('TT-UI-AC4-P2 shows the columns and one chip per row status', async () => {
    table();
    const t = await screen.findByRole('table');
    for (const h of ['Name', 'ID', 'Status', 'Reason', 'Render time', 'Actions']) {
      expect(within(t).getByRole('columnheader', { name: h })).toBeInTheDocument();
    }
    const tones = within(t)
      .getAllByTestId('status-chip')
      .map((c) => c.getAttribute('data-tone'));
    expect(tones).toEqual(['green', 'blue', 'grey', 'red', 'amber']);
  });

  it('TT-UI-AC4-P3 a failed row explains the failure in plain words', async () => {
    table();
    expect(
      await screen.findByText('The voice for this name could not be created.'),
    ).toBeInTheDocument();
    expect(screen.getByText('The ID is empty.')).toBeInTheDocument();
    expect(screen.queryByText('TTS_FAILED')).not.toBeInTheDocument();
  });

  it('TT-UI-AC4-P4 shows render time in seconds and a dash when there is none', async () => {
    table();
    const rows = await screen.findAllByRole('row');
    expect(within(rows[1]!).getByText('12.5 s')).toBeInTheDocument();
    expect(within(rows[2]!).getAllByText('-').length).toBeGreaterThan(0);
  });

  it('TT-UI-AC11-P1 renders a Devanagari name intact and marks it lang=hi', async () => {
    table();
    const cell = await screen.findByText(DEVANAGARI_NAME);
    expect(cell.textContent).toBe(DEVANAGARI_NAME);
    expect(cell.closest('[lang]')).toHaveAttribute('lang', 'hi');
  });

  it('TT-UI-AC11-E1 mixed Hindi and English names keep every character', async () => {
    const mixed = 'Ravi रवि Kumar';
    server.use(
      http.get('*/batches/:id/rows', () => HttpResponse.json(rowsPage([row(1, { name: mixed })]))),
    );
    table();
    expect(await screen.findByText(mixed)).toBeInTheDocument();
  });

  it('TT-UI-AC4-E2 markup in a name is shown as text, never executed', async () => {
    const evil = '<img src=x onerror=alert(1)>';
    server.use(
      http.get('*/batches/:id/rows', () => HttpResponse.json(rowsPage([row(1, { name: evil })]))),
    );
    table();
    expect(await screen.findByText(evil)).toBeInTheDocument();
    expect(document.querySelector('img[onerror]')).toBeNull();
  });
});

describe('row actions', () => {
  it('TT-UI-AC4-P5 completed rows offer preview and download links to the video', async () => {
    table();
    const name = DEVANAGARI_NAME;
    const download = await screen.findByRole('link', { name: `Download video for ${name}` });
    expect(download).toHaveAttribute('href', `/batches/${IDS.batch}/rows/1/video`);
    expect(screen.getByRole('link', { name: `Preview video for ${name}` })).toBeInTheDocument();
  });

  it('TT-UI-AC4-N1 queued, processing and skipped rows have no video actions', async () => {
    table();
    await screen.findByRole('table');
    expect(screen.getAllByRole('link', { name: /Download video for/ })).toHaveLength(1);
  });

  it('TT-UI-AC4-P6 Retry on a failed row posts the per-row endpoint with the CSRF header', async () => {
    let csrf: string | null = null;
    let batchWide = 0;
    server.use(
      http.post('*/batches/:id/rows/:n/retry', ({ request, params }) => {
        csrf = request.headers.get('x-csrf-token');
        expect(params.n).toBe('4');
        return HttpResponse.json({});
      }),
      http.post('*/batches/:id/retry-failed', () => {
        batchWide += 1;
        return HttpResponse.json({});
      }),
    );
    table();
    await userEvent.click(await screen.findByRole('button', { name: 'Retry row 4' }));
    await waitFor(() => expect(csrf).toBe(CSRF));
    expect(batchWide).toBe(0);
    expect(screen.queryByRole('button', { name: 'Retry row 1' })).not.toBeInTheDocument();
  });

  it('TT-UI-AC4-P11 after a row retry the row is refreshed from the server', async () => {
    let retried = false;
    server.use(
      http.get('*/batches/:id/rows', () =>
        HttpResponse.json(
          rowsPage([
            retried
              ? row(4, { status: 'QUEUED', failure_code: null, message: null, has_video: false })
              : row(4, {
                  status: 'FAILED',
                  failure_code: 'TTS_FAILED',
                  message: 'The voice for this name could not be created.',
                  has_video: false,
                }),
          ]),
        ),
      ),
      http.post('*/batches/:id/rows/:n/retry', () => {
        retried = true;
        return HttpResponse.json({});
      }),
    );
    table();
    await userEvent.click(await screen.findByRole('button', { name: 'Retry row 4' }));
    expect(await screen.findByText('Queued')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Retry row 4' })).not.toBeInTheDocument();
    expect(
      screen.queryByText('The voice for this name could not be created.'),
    ).not.toBeInTheDocument();
  });

  it('TT-UI-AC4-E6 only FAILED rows ever show a Retry button', async () => {
    table();
    await screen.findByRole('table');
    expect(screen.getAllByRole('button', { name: /^Retry row/ })).toHaveLength(1);
  });

  it('TT-UI-AC4-N2 a failing retry shows the API message and keeps the table', async () => {
    server.use(
      http.post('*/batches/:id/rows/:n/retry', () =>
        HttpResponse.json(
          {
            code: 'INVALID_STATE',
            message: "This action is not possible in the batch's current state.",
          },
          { status: 409 },
        ),
      ),
    );
    table();
    await userEvent.click(await screen.findByRole('button', { name: 'Retry row 4' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('not possible');
    expect(screen.getByRole('table')).toBeInTheDocument();
  });
});

describe('search, filter, paging', () => {
  it('TT-UI-AC4-P7 searching sends the text (Devanagari too) and resets to page 1', async () => {
    const queries: URLSearchParams[] = [];
    server.use(
      http.get('*/batches/:id/rows', ({ request }) => {
        queries.push(new URL(request.url).searchParams);
        return HttpResponse.json(rowsPage(ROWS_BY_STATUS));
      }),
    );
    table();
    await screen.findByRole('table');
    await userEvent.type(screen.getByRole('textbox', { name: 'Search by name or ID' }), 'अनु');
    await waitFor(() => expect(queries.at(-1)?.get('search')).toBe('अनु'));
    expect(queries.at(-1)?.get('page')).toBe('1');
  });

  it('TT-UI-AC4-E3 search text is capped at the API limit of 200 characters', async () => {
    const queries: URLSearchParams[] = [];
    server.use(
      http.get('*/batches/:id/rows', ({ request }) => {
        queries.push(new URL(request.url).searchParams);
        return HttpResponse.json(rowsPage([]));
      }),
    );
    table();
    await screen.findByText('No rows match');
    await userEvent.click(screen.getByRole('textbox', { name: 'Search by name or ID' }));
    await userEvent.paste('a'.repeat(250));
    await waitFor(() => expect(queries.at(-1)?.get('search')?.length).toBeLessThanOrEqual(200));
  });

  it('TT-UI-AC4-P8 the status filter sends the matching status value', async () => {
    const queries: URLSearchParams[] = [];
    server.use(
      http.get('*/batches/:id/rows', ({ request }) => {
        queries.push(new URL(request.url).searchParams);
        return HttpResponse.json(rowsPage(ROWS_BY_STATUS));
      }),
    );
    table();
    await screen.findByRole('table');
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Status' }), 'Failed');
    await waitFor(() => expect(queries.at(-1)?.get('status')).toBe('FAILED'));
  });

  it('TT-UI-AC4-P9 the status prop pre-applies a filter (failure-chart click-through)', async () => {
    const queries: URLSearchParams[] = [];
    server.use(
      http.get('*/batches/:id/rows', ({ request }) => {
        queries.push(new URL(request.url).searchParams);
        return HttpResponse.json(rowsPage([]));
      }),
    );
    setCsrfCookie();
    renderWithProviders(<RowsTable batchId={IDS.batch} status="FAILED" />);
    await waitFor(() => expect(queries[0]?.get('status')).toBe('FAILED'));
  });

  it('TT-UI-AC4-P10 pages forward and back with Page X of Y', async () => {
    const pages: string[] = [];
    server.use(
      http.get('*/batches/:id/rows', ({ request }) => {
        const page = Number(new URL(request.url).searchParams.get('page') ?? '1');
        pages.push(String(page));
        return HttpResponse.json(rowsPage([row(page * 100)], page, 50, 120));
      }),
    );
    table();
    expect(await screen.findByText('Page 1 of 3')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Next page' }));
    expect(await screen.findByText('Page 2 of 3')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Next page' }));
    expect(await screen.findByText('Page 3 of 3')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled();
    expect(pages).toEqual(['1', '2', '3']);
  });

  it('TT-UI-AC4-N3 no matching rows shows "No rows match"', async () => {
    server.use(http.get('*/batches/:id/rows', () => HttpResponse.json(rowsPage([]))));
    table();
    expect(await screen.findByText('No rows match')).toBeInTheDocument();
  });

  it('TT-UI-AC4-N4 a server error shows an alert, not an empty table', async () => {
    server.use(
      http.get('*/batches/:id/rows', () =>
        HttpResponse.json(
          { code: 'INTERNAL_ERROR', message: 'Something went wrong.' },
          { status: 500 },
        ),
      ),
    );
    table();
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load rows');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('TT-UI-AC4-E4 a 1,000-row batch renders one page only (smooth), not 1,000 DOM rows', async () => {
    const page = Array.from({ length: 50 }, (_, i) => row(i + 1));
    server.use(
      http.get('*/batches/:id/rows', () => HttpResponse.json(rowsPage(page, 1, 50, 1000))),
    );
    table();
    expect(await screen.findByText('Page 1 of 20')).toBeInTheDocument();
    expect(screen.getAllByRole('row').length).toBeLessThanOrEqual(51 + 1);
  });

  it('TT-UI-AC4-E5 shows skeleton rows while loading', () => {
    table();
    expect(screen.getAllByTestId('skeleton').length).toBeGreaterThan(0);
  });
});
