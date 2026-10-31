// DD-37 A: batch list pages Running, Completed and Failed. Cases: TT-DD37-A-*
//
// CONTRACT (frontend/src/pages/BatchListPage.tsx, routes in frontend/src/App.tsx):
//   BatchListPage({ view }) with view running | completed | failed; routes /batches/running,
//     /batches/completed, /batches/failed render it (no "is coming soon" placeholder any more).
//   GET /api/batches?page=<n>&page_size=50&view=<view>
//   table headers, exactly: Batch, Template, Progress, Rows, Created
//   Batch     sheet name, else folder name, else "Batch"; link to /batches/<id>
//   Template  name from the templates list, "-" when unknown
//   Progress  round(100 * (completed + failed + skipped) / total) + " %", "-" when total is 0
//   Rows      "<total> rows", plus " · <failed> failed" only when failed is not 0
//   Created   date like History (en-GB, for example 19 Oct 2026)
//   empty     "No running batches" | "No completed batches" | "No failed batches"
//   error     role=alert "Could not load batches" with a "Retry" button
//   paging    "Previous page", "Next page", "Page X of Y" (as History)
//   polling   every 5 s for view running only
import { act, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { renderApp } from '../helpers';
import { COUNTS, IDS, batch, batchesPage } from '../mocks/data';
import { apiError } from '../mocks/handlers';
import { server } from '../mocks/server';

type View = 'running' | 'completed' | 'failed';
const VIEWS: View[] = ['running', 'completed', 'failed'];
const EMPTY_TEXT: Record<View, string> = {
  running: 'No running batches',
  completed: 'No completed batches',
  failed: 'No failed batches',
};
const HEADERS = ['Batch', 'Template', 'Progress', 'Rows', 'Created'];
const UNKNOWN_TEMPLATE = '55555555-5555-4555-8555-555555555555';
/** Noon UTC keeps the calendar date the same in every time zone. */
const CREATED = '2026-10-19T12:00:00+00:00';
const POLL_MS = 5000;

interface Hit {
  page: string | null;
  page_size: string | null;
  view: string | null;
}

/**
 * Serve GET /batches for the list pages and record each call that carries a view parameter.
 * The sidebar's worker banner polls the unfiltered list, so it is not recorded.
 */
type BatchRow = ReturnType<typeof batch>;

function serveBatches(batches: BatchRow[] | ((page: number) => BatchRow[]), totalPages = 1) {
  const hits: Hit[] = [];
  server.use(
    http.get('*/batches', ({ request }) => {
      const query = new URL(request.url).searchParams;
      if (!query.has('view')) return HttpResponse.json(batchesPage([batch()]));
      hits.push({
        page: query.get('page'),
        page_size: query.get('page_size'),
        view: query.get('view'),
      });
      const page = Number(query.get('page') ?? 1);
      const list = typeof batches === 'function' ? batches(page) : batches;
      return HttpResponse.json(batchesPage(list, page, totalPages));
    }),
  );
  return hits;
}

/** Text of each cell in a row, so the check does not depend on td or th roles. */
function cellTexts(row: HTMLElement): string[] {
  return Array.from(row.querySelectorAll('td, th')).map((cell) => cell.textContent ?? '');
}

async function bodyRows(): Promise<HTMLElement[]> {
  const table = await screen.findByRole('table');
  return within(table).getAllByRole('row').slice(1);
}

function createdText(iso: string): string {
  return new Date(iso).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

describe('routes', () => {
  it.each(VIEWS)(
    'TT-DD37-A-P1 /batches/%s renders the batch table, not the placeholder',
    async (view) => {
      serveBatches([batch()]);
      renderApp(`/batches/${view}`);
      expect(await screen.findByRole('table')).toBeInTheDocument();
      expect(screen.queryByText(/is coming soon/i)).not.toBeInTheDocument();
    },
  );
});

describe('positive', () => {
  it.each(VIEWS)(
    'TT-DD37-A-P2 the %s view asks the API for page 1, 50 rows and its own view',
    async (view) => {
      const hits = serveBatches([batch()]);
      renderApp(`/batches/${view}`);
      await screen.findByRole('table');
      expect(hits[0]).toEqual({ page: '1', page_size: '50', view });
    },
  );

  it('TT-DD37-A-P3 shows the five column headers with their exact texts', async () => {
    serveBatches([batch()]);
    renderApp('/batches/running');
    const table = await screen.findByRole('table');
    const headers = within(table)
      .getAllByRole('columnheader')
      .map((h) => h.textContent);
    expect(headers).toEqual(HEADERS);
  });

  it('TT-DD37-A-P4 a row shows name, template, progress, rows and created date', async () => {
    serveBatches([batch()]);
    renderApp('/batches/running');
    const [row] = await bodyRows();
    expect(cellTexts(row!)).toEqual([
      'sheet-a.csv',
      'Rahul',
      '75 %',
      `${COUNTS.total} rows · ${COUNTS.failed} failed`,
      createdText(batch().created_at as string),
    ]);
  });

  it('TT-DD37-A-P5 the batch name links to the batch detail page', async () => {
    serveBatches([batch()]);
    renderApp('/batches/completed');
    const [row] = await bodyRows();
    expect(within(row!).getByRole('link', { name: 'sheet-a.csv' })).toHaveAttribute(
      'href',
      `/batches/${IDS.batch}`,
    );
  });

  it.each([
    [
      'sheet name when there is one',
      { sheet_name: 'voters.csv', folder_name: '2026-10-19-1' },
      'voters.csv',
    ],
    [
      'folder name when there is no sheet name',
      { sheet_name: null, folder_name: '2026-10-19-1' },
      '2026-10-19-1',
    ],
    ['Batch when there is neither', { sheet_name: null, folder_name: null }, 'Batch'],
  ])('TT-DD37-A-P6 the batch name is the %s', async (_label, names, expected) => {
    serveBatches([batch(names)]);
    renderApp('/batches/running');
    const [row] = await bodyRows();
    expect(cellTexts(row!)[0]).toBe(expected);
  });

  it.each([
    [
      '3 rows, 1 completed',
      { total: 3, completed: 1, processing: 0, queued: 2, failed: 0, skipped: 0, cancelled: 0 },
      '33 %',
    ],
    [
      '3 rows, 2 completed',
      { total: 3, completed: 2, processing: 0, queued: 1, failed: 0, skipped: 0, cancelled: 0 },
      '67 %',
    ],
    [
      '4 rows, processing not counted',
      { total: 4, completed: 1, processing: 1, queued: 0, failed: 1, skipped: 1, cancelled: 0 },
      '75 %',
    ],
  ])(
    'TT-DD37-A-P7 progress counts completed, failed and skipped only (%s)',
    async (_label, counts, expected) => {
      serveBatches([batch({ counts })]);
      renderApp('/batches/running');
      const [row] = await bodyRows();
      expect(cellTexts(row!)[2]).toBe(expected);
    },
  );

  it('TT-DD37-A-P8 the template column shows the name of the template', async () => {
    serveBatches([batch({ template_id: IDS.template })]);
    renderApp('/batches/running');
    const [row] = await bodyRows();
    expect(cellTexts(row!)[1]).toBe('Rahul');
  });

  it('TT-DD37-A-P9 the created column shows the date the way History does', async () => {
    serveBatches([batch({ created_at: CREATED })]);
    renderApp('/batches/running');
    const [row] = await bodyRows();
    expect(cellTexts(row!)[4]).toBe(createdText(CREATED));
  });

  it('TT-DD37-A-P10 paging moves to the next and previous page', async () => {
    const hits = serveBatches((page) => [batch({ sheet_name: `page-${page}.csv` })], 3);
    renderApp('/batches/running');
    expect(await screen.findByRole('link', { name: 'page-1.csv' })).toBeInTheDocument();
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Next page' }));
    expect(await screen.findByRole('link', { name: 'page-2.csv' })).toBeInTheDocument();
    expect(screen.getByText('Page 2 of 3')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeEnabled();
    expect(hits.map((h) => h.page)).toEqual(['1', '2']);
    await userEvent.click(screen.getByRole('button', { name: 'Previous page' }));
    expect(await screen.findByRole('link', { name: 'page-1.csv' })).toBeInTheDocument();
  });

  it('TT-DD37-A-P11 the running view refetches every 5 seconds', async () => {
    const hits = serveBatches([batch({ status: 'RUNNING' })]);
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderApp('/batches/running');
    await screen.findByRole('table');
    const first = hits.length;
    await act(() => vi.advanceTimersByTimeAsync(POLL_MS - 1000));
    expect(hits).toHaveLength(first);
    await act(() => vi.advanceTimersByTimeAsync(2000));
    expect(hits).toHaveLength(first + 1);
  });

  it.each(['completed', 'failed'] as const)(
    'TT-DD37-A-P12 the %s view does not poll',
    async (view) => {
      const hits = serveBatches([batch({ status: 'COMPLETED' })]);
      vi.useFakeTimers({ shouldAdvanceTime: true });
      renderApp(`/batches/${view}`);
      await screen.findByRole('table');
      const first = hits.length;
      await act(() => vi.advanceTimersByTimeAsync(POLL_MS * 4));
      expect(hits).toHaveLength(first);
    },
  );
});

describe('negative', () => {
  it.each(VIEWS)('TT-DD37-A-N1 an empty %s list shows its empty state', async (view) => {
    serveBatches([]);
    renderApp(`/batches/${view}`);
    expect(await screen.findByText(EMPTY_TEXT[view])).toBeInTheDocument();
  });

  it('TT-DD37-A-N2 an API failure shows Could not load batches with a Retry button', async () => {
    server.use(
      http.get('*/batches', () => apiError(500, 'INTERNAL_ERROR', 'Something went wrong.')),
    );
    renderApp('/batches/failed');
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Could not load batches');
    expect(within(alert).getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('TT-DD37-A-N3 Retry asks the API again and then shows the list', async () => {
    let failures = 1;
    server.use(
      http.get('*/batches', ({ request }) => {
        if (!new URL(request.url).searchParams.has('view'))
          return HttpResponse.json(batchesPage([batch()]));
        if (failures > 0) {
          failures -= 1;
          return apiError(500, 'INTERNAL_ERROR', 'Something went wrong.');
        }
        return HttpResponse.json(batchesPage([batch({ sheet_name: 'after-retry.csv' })]));
      }),
    );
    renderApp('/batches/running');
    await userEvent.click(await screen.findByRole('button', { name: 'Retry' }));
    expect(await screen.findByRole('link', { name: 'after-retry.csv' })).toBeInTheDocument();
  });

  it('TT-DD37-A-N4 a template id missing from the templates list shows a dash', async () => {
    serveBatches([batch({ template_id: UNKNOWN_TEMPLATE })]);
    renderApp('/batches/running');
    const [row] = await bodyRows();
    expect(cellTexts(row!)[1]).toBe('-');
  });
});

describe('edge', () => {
  it('TT-DD37-A-E1 a batch with no rows shows a dash for progress and 0 rows', async () => {
    const none = {
      total: 0,
      completed: 0,
      processing: 0,
      queued: 0,
      failed: 0,
      skipped: 0,
      cancelled: 0,
    };
    serveBatches([batch({ counts: none })]);
    renderApp('/batches/running');
    const [row] = await bodyRows();
    const cells = cellTexts(row!);
    expect(cells[2]).toBe('-');
    expect(cells[3]).toBe('0 rows');
  });

  it('TT-DD37-A-E2 zero failures show the row count without the failed part', async () => {
    serveBatches([batch({ counts: { ...COUNTS, failed: 0 } })]);
    renderApp('/batches/completed');
    const [row] = await bodyRows();
    expect(cellTexts(row!)[3]).toBe(`${COUNTS.total} rows`);
  });

  it('TT-DD37-A-E3 a single page shows Page 1 of 1 with both paging buttons disabled', async () => {
    serveBatches([batch()], 1);
    renderApp('/batches/running');
    await screen.findByRole('table');
    expect(screen.getByText('Page 1 of 1')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled();
  });

  it('TT-DD37-A-E4 the running view stops polling once the page is left', async () => {
    const hits = serveBatches([batch({ status: 'RUNNING' })]);
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { unmount } = renderApp('/batches/running');
    await screen.findByRole('table');
    unmount();
    const before = hits.length;
    await act(() => vi.advanceTimersByTimeAsync(POLL_MS * 3));
    expect(hits).toHaveLength(before);
  });
});
