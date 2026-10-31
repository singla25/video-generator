// UI-AC3 Overview and UI-AC10 states/motion. Cases: TT-UI-AC3-*, TT-UI-AC10-*
//
// CONTRACT (frontend/src):
//   config.ts                  export POLL_INTERVAL_MS = 2000
//   components/CountUp.tsx     export CountUp({ value: number })  text = formatted number;
//                              counts up from 0 over <= 1 s, or shows `value` at once when the user
//                              prefers reduced motion (window.matchMedia('(prefers-reduced-motion: reduce)'))
//   pages/OverviewPage.tsx     route "/"
//     [data-testid=kpi-total|completed|processing|queued|failed|skipped]  each has data-value="<n>"
//        and the visible number; labels "Total", "Completed", "Processing", "Queued", "Failed", "Skipped"
//     [data-testid=new-batch-card]   link to /batches/new
//     [data-testid=chart-total]      sum of /stats/daily videos; [data-testid=chart-delta] "+X % vs last"
//     buttons "Day" / "Week"         period toggle (aria-pressed)
//     [data-testid=current-batch]    role=progressbar (aria-valuenow = progress_percent), ETA text
//                                    "ETA 1 min 30 s", counts, buttons Pause | Resume, Retry failed
//     current batch = first batch in GET /batches with status RUNNING or PAUSED, else the newest
//     skeleton placeholders      [data-testid=skeleton] while loading
//     error state                role=alert "Could not load the dashboard" + button "Try again"
//     empty state                "No batches yet" + link "Create your first batch" -> /batches/new
//   Live data: GET /batches/{id}/status every POLL_INTERVAL_MS; a failed poll replaces numbers
//   with the error state (never stale numbers).
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { CountUp } from '../../../frontend/src/components/CountUp';
import { POLL_INTERVAL_MS } from '../../../frontend/src/config';
import { CSRF, renderApp } from '../helpers';
import { COUNTS, IDS, batch, status } from '../mocks/data';
import { apiError } from '../mocks/handlers';
import { server } from '../mocks/server';
import { setReducedMotion } from '../motion';

const KEYS = ['completed', 'processing', 'queued', 'failed', 'skipped'] as const;

function valueOf(key: string): number {
  return Number(screen.getByTestId(`kpi-${key}`).dataset.value);
}

describe('current batch panel (W-4a)', () => {
  it('counts completed against renderable rows and shows skipped separately', async () => {
    setReducedMotion(true);
    renderApp('/');
    const panel = await screen.findByTestId('current-batch');
    expect(panel).toHaveTextContent('60 completed / 95'); // 100 rows minus 5 skipped
    expect(panel).toHaveTextContent('5 skipped');
  });
});

describe('KPI cards', () => {
  it('TT-UI-AC3-P1 shows six KPI cards with labels and numbers', async () => {
    setReducedMotion(true);
    renderApp('/');
    for (const key of ['total', ...KEYS]) {
      expect(await screen.findByTestId(`kpi-${key}`)).toBeInTheDocument();
    }
    const completed = screen.getByTestId('kpi-completed');
    expect(within(completed).getByText('Completed')).toBeInTheDocument();
    expect(completed).toHaveTextContent('60');
    expect(screen.getByTestId('kpi-failed')).toHaveTextContent('10');
  });

  it('TT-UI-AC3-P2 the counts always add up to the total', async () => {
    setReducedMotion(true);
    renderApp('/');
    await screen.findByTestId('kpi-total');
    const sum = KEYS.reduce((acc, k) => acc + valueOf(k), 0) + COUNTS.cancelled;
    expect(sum).toBe(valueOf('total'));
  });

  it('TT-UI-AC3-P3 each non-total card carries a status chip with its tone', async () => {
    setReducedMotion(true);
    renderApp('/');
    await screen.findByTestId('kpi-total');
    const tones: Record<string, string> = {
      completed: 'green',
      processing: 'blue',
      queued: 'grey',
      failed: 'red',
      skipped: 'amber',
    };
    for (const [key, tone] of Object.entries(tones)) {
      const chip = within(screen.getByTestId(`kpi-${key}`)).getByTestId('status-chip');
      expect(chip).toHaveAttribute('data-tone', tone);
    }
  });

  it('TT-UI-AC3-P4 a dashed New batch card links to the wizard', async () => {
    renderApp('/');
    expect(await screen.findByTestId('new-batch-card')).toHaveAttribute('href', '/batches/new');
  });

  it('TT-UI-AC3-E1 zero counts render as 0, not blank', async () => {
    setReducedMotion(true);
    const zero = {
      total: 0,
      completed: 0,
      processing: 0,
      queued: 0,
      failed: 0,
      skipped: 0,
      cancelled: 0,
    };
    server.use(http.get('*/batches/:id/status', () => HttpResponse.json(status({ counts: zero }))));
    renderApp('/');
    expect(await screen.findByTestId('kpi-failed')).toHaveTextContent('0');
    expect(screen.getByTestId('kpi-failed').dataset.value).toBe('0');
  });

  it('TT-UI-AC3-E2 large numbers use digit grouping', async () => {
    setReducedMotion(true);
    const big = {
      ...COUNTS,
      total: 12400,
      completed: 12400,
      processing: 0,
      queued: 0,
      failed: 0,
      skipped: 0,
    };
    server.use(http.get('*/batches/:id/status', () => HttpResponse.json(status({ counts: big }))));
    renderApp('/');
    expect(await screen.findByTestId('kpi-total')).toHaveTextContent(/12,400/);
  });
});

describe('chart', () => {
  it('TT-UI-AC3-P5 Videos generated shows the total and a vs-last pill', async () => {
    renderApp('/');
    expect(await screen.findByRole('heading', { name: 'Videos generated' })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('chart-total')).toHaveTextContent('870'));
    expect(screen.getByTestId('chart-delta')).toHaveTextContent(/vs last/);
  });

  it('TT-UI-AC3-P6 the Day and Week toggle switches the period', async () => {
    const days: string[] = [];
    server.use(
      http.get('*/stats/daily', ({ request }) => {
        days.push(new URL(request.url).searchParams.get('days') ?? '');
        return HttpResponse.json({ days: [] });
      }),
    );
    renderApp('/');
    await screen.findByRole('heading', { name: 'Videos generated' });
    await userEvent.click(screen.getByRole('button', { name: 'Day' }));
    expect(screen.getByRole('button', { name: 'Day' })).toHaveAttribute('aria-pressed', 'true');
    await userEvent.click(screen.getByRole('button', { name: 'Week' }));
    expect(screen.getByRole('button', { name: 'Week' })).toHaveAttribute('aria-pressed', 'true');
    await waitFor(() => expect(new Set(days).size).toBeGreaterThan(1));
  });

  it('TT-UI-AC3-E3 an empty series shows 0 and a no-data note, not a broken chart', async () => {
    server.use(http.get('*/stats/daily', () => HttpResponse.json({ days: [] })));
    renderApp('/');
    await waitFor(() => expect(screen.getByTestId('chart-total')).toHaveTextContent('0'));
    expect(screen.getByText('No videos generated in this period')).toBeInTheDocument();
  });

  it('TT-UI-AC3-E4 a failing stats call degrades only the chart card', async () => {
    setReducedMotion(true);
    server.use(
      http.get('*/stats/daily', () => apiError(500, 'INTERNAL_ERROR', 'Something went wrong.')),
    );
    renderApp('/');
    expect(await screen.findByTestId('kpi-total')).toBeInTheDocument();
    expect(await screen.findByText('Chart unavailable')).toBeInTheDocument();
  });
});

describe('current batch panel', () => {
  it('TT-UI-AC3-P7 shows the progress ring, ETA and Pause for a running batch', async () => {
    renderApp('/');
    const panel = await screen.findByTestId('current-batch');
    expect(within(panel).getByRole('progressbar')).toHaveAttribute('aria-valuenow', '75');
    expect(panel).toHaveTextContent('ETA 1 min 30 s');
    expect(within(panel).getByRole('button', { name: 'Pause' })).toBeInTheDocument();
    expect(within(panel).getByRole('button', { name: 'Retry failed' })).toBeInTheDocument();
  });

  it('TT-UI-AC3-P8 a paused batch offers Resume instead of Pause', async () => {
    server.use(
      http.get('*/batches', () =>
        HttpResponse.json({
          batches: [batch({ status: 'PAUSED' })],
          page: 1,
          page_size: 50,
          total: 1,
          total_pages: 1,
        }),
      ),
    );
    renderApp('/');
    const panel = await screen.findByTestId('current-batch');
    expect(within(panel).getByRole('button', { name: 'Resume' })).toBeInTheDocument();
    expect(within(panel).queryByRole('button', { name: 'Pause' })).not.toBeInTheDocument();
  });

  it('TT-UI-AC3-P9 Pause posts to the API with the CSRF header', async () => {
    let csrf: string | null = null;
    let hit = false;
    server.use(
      http.post('*/batches/:id/pause', ({ request }) => {
        hit = true;
        csrf = request.headers.get('x-csrf-token');
        return HttpResponse.json(batch({ status: 'PAUSED' }));
      }),
    );
    renderApp('/');
    const panel = await screen.findByTestId('current-batch');
    await userEvent.click(within(panel).getByRole('button', { name: 'Pause' }));
    await waitFor(() => expect(hit).toBe(true));
    expect(csrf).toBe(CSRF);
  });

  it('TT-UI-AC3-P10 a draft batch shows the lime Continue setup action to the wizard (DD-38)', async () => {
    server.use(
      http.get('*/batches', () =>
        HttpResponse.json({
          batches: [batch({ status: 'DRAFT' })],
          page: 1,
          page_size: 50,
          total: 1,
          total_pages: 1,
        }),
      ),
    );
    renderApp('/');
    const panel = await screen.findByTestId('current-batch');
    expect(within(panel).getByRole('link', { name: 'Continue setup' })).toHaveAttribute(
      'href',
      `/batches/new?batch=${IDS.batch}`,
    );
  });

  it('TT-UI-AC3-E5 prefers the RUNNING batch over a newer finished one', async () => {
    const seen: string[] = [];
    server.use(
      http.get('*/batches', () =>
        HttpResponse.json({
          batches: [batch({ id: IDS.oldBatch, status: 'COMPLETED' }), batch({ id: IDS.batch })],
          page: 1,
          page_size: 50,
          total: 2,
          total_pages: 1,
        }),
      ),
      http.get('*/batches/:id/status', ({ params }) => {
        seen.push(String(params.id));
        return HttpResponse.json(status());
      }),
    );
    renderApp('/');
    await screen.findByTestId('current-batch');
    expect(seen[0]).toBe(IDS.batch);
  });

  it('TT-UI-AC3-E6 no ETA yet (null) shows a dash instead of NaN', async () => {
    server.use(
      http.get('*/batches/:id/status', () => HttpResponse.json(status({ eta_seconds: null }))),
    );
    renderApp('/');
    const panel = await screen.findByTestId('current-batch');
    expect(panel).toHaveTextContent('ETA -');
    expect(panel.textContent).not.toMatch(/NaN|undefined/);
  });
});

describe('live polling', () => {
  it('TT-UI-AC3-P11 polls status every POLL_INTERVAL_MS and shows new numbers', async () => {
    expect(POLL_INTERVAL_MS).toBe(2000);
    setReducedMotion(true);
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let calls = 0;
    server.use(
      http.get('*/batches/:id/status', () => {
        calls += 1;
        const c = { ...COUNTS, completed: 60 + calls - 1, queued: 20 - (calls - 1) };
        return HttpResponse.json(status({ counts: c }));
      }),
    );
    renderApp('/');
    await waitFor(() => expect(valueOf('completed')).toBe(60));
    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS + 100));
    await waitFor(() => expect(valueOf('completed')).toBe(61));
    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS));
    await waitFor(() => expect(calls).toBeGreaterThanOrEqual(3));
    expect(valueOf('completed') + valueOf('queued')).toBe(80);
  });

  it('TT-UI-AC3-E7 polling stops after the page is left', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let calls = 0;
    server.use(
      http.get('*/batches/:id/status', () => {
        calls += 1;
        return HttpResponse.json(status());
      }),
    );
    const { unmount } = renderApp('/');
    await screen.findByTestId('current-batch');
    unmount();
    const before = calls;
    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 5));
    expect(calls).toBe(before);
  });

  it('TT-UI-AC10-N3 a failed poll replaces the numbers with the error state', async () => {
    setReducedMotion(true);
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let fail = false;
    server.use(
      http.get('*/batches/:id/status', () =>
        fail
          ? apiError(500, 'INTERNAL_ERROR', 'Something went wrong.')
          : HttpResponse.json(status()),
      ),
    );
    renderApp('/');
    await screen.findByTestId('kpi-total');
    fail = true;
    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS + 100));
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load the dashboard');
    expect(screen.queryByTestId('kpi-total')).not.toBeInTheDocument();
  });
});

describe('states and motion', () => {
  it('TT-UI-AC10-P1 shows skeletons while loading', () => {
    renderApp('/');
    expect(screen.getAllByTestId('skeleton').length).toBeGreaterThan(0);
  });

  it('TT-UI-AC10-N1 API down shows an error state with Try again, no numbers', async () => {
    server.use(http.get('*/batches', () => HttpResponse.error()));
    renderApp('/');
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Could not load the dashboard');
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
    expect(screen.queryByTestId('kpi-total')).not.toBeInTheDocument();
  });

  it('TT-UI-AC10-N2 Try again fetches again and recovers', async () => {
    setReducedMotion(true);
    let down = true;
    server.use(
      http.get('*/batches', () =>
        down
          ? HttpResponse.error()
          : HttpResponse.json({
              batches: [batch()],
              page: 1,
              page_size: 50,
              total: 1,
              total_pages: 1,
            }),
      ),
    );
    renderApp('/');
    await screen.findByRole('alert');
    down = false;
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByTestId('kpi-total')).toBeInTheDocument();
  });

  it('TT-UI-AC10-E2 no batches yet shows the empty state with a first-batch call to action', async () => {
    server.use(
      http.get('*/batches', () =>
        HttpResponse.json({ batches: [], page: 1, page_size: 50, total: 0, total_pages: 1 }),
      ),
    );
    renderApp('/');
    expect(await screen.findByText('No batches yet')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Create your first batch' })).toHaveAttribute(
      'href',
      '/batches/new',
    );
    expect(screen.queryByTestId('kpi-total')).not.toBeInTheDocument();
  });

  it('TT-UI-AC10-P2 reduced motion shows the final KPI number immediately', async () => {
    setReducedMotion(true);
    renderApp('/');
    const card = await screen.findByTestId('kpi-completed');
    expect(card).toHaveTextContent('60');
  });

  it('TT-UI-AC10-P3 CountUp animates from 0 to the value when motion is allowed', async () => {
    vi.useFakeTimers();
    render(<CountUp value={50} />);
    expect(screen.getByText('0')).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(1500));
    expect(screen.getByText('50')).toBeInTheDocument();
  });

  it('TT-UI-AC10-P4 CountUp renders the value at once under reduced motion', () => {
    setReducedMotion(true);
    render(<CountUp value={50} />);
    expect(screen.getByText('50')).toBeInTheDocument();
  });

  it('TT-UI-AC10-E3 CountUp handles value 0 and negative-free large values', () => {
    setReducedMotion(true);
    const { rerender } = render(<CountUp value={0} />);
    expect(screen.getByText('0')).toBeInTheDocument();
    rerender(<CountUp value={1000000} />);
    expect(screen.getByText('1,000,000')).toBeInTheDocument();
  });
});
