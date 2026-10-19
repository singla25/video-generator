import { useEffect, useState } from 'react';
import { Bar, BarChart, CartesianGrid, Cell, LabelList, XAxis } from 'recharts';

import { useDailyStats } from '../api/queries';
import { formatNumber } from '../format';
import { useReducedMotion } from '../hooks';
import { PERIOD_DAYS, deltaText, toBars, type Period } from './chartData';
import { Skeleton } from './states';

const EMERALD = '#1e7a5a';
const MINT = '#e6f6ee';
const CHART_HEIGHT = 240;
const INITIAL_WIDTH = 640;
const PERIODS: { id: Period; label: string }[] = [
  { id: 'day', label: 'Day' },
  { id: 'week', label: 'Week' },
];

function Toggle({ period, onChange }: { period: Period; onChange: (p: Period) => void }) {
  return (
    <div className="flex gap-1 rounded-full border p-1">
      {PERIODS.map(({ id, label }) => (
        <button
          key={id}
          type="button"
          aria-pressed={period === id}
          onClick={() => onChange(id)}
          className={`rounded-full px-3 py-1 text-sm font-semibold ${period === id ? 'bg-mint text-emerald' : 'text-muted'}`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

/** "Videos generated": big total, change pill and stepped hatched bars. */
export function VideosChart() {
  const [period, setPeriod] = useState<Period>('week');
  const reduced = useReducedMotion();
  const query = useDailyStats(PERIOD_DAYS[period]);
  const [box, setBox] = useState<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(INITIAL_WIDTH);

  // Follow the card width; where nothing can be measured (tests) keep the default.
  useEffect(() => {
    if (!box || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(([entry]) => {
      const next = Math.floor(entry?.contentRect.width ?? 0);
      if (next > 0) setWidth(next);
    });
    observer.observe(box);
    return () => observer.disconnect();
  }, [box]);
  const days = query.data?.days ?? [];
  const bars = toBars(days, period);
  const total = days.reduce((sum, d) => sum + d.videos, 0);
  const peak = bars.reduce((best, b, i) => (b.videos > (bars[best]?.videos ?? -1) ? i : best), 0);

  return (
    <section className="min-w-0 rounded-card border bg-card p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-semibold">Videos generated</h2>
        <Toggle period={period} onChange={setPeriod} />
      </div>
      {query.isError ? (
        <p className="py-10 text-center text-muted">Chart unavailable</p>
      ) : query.isPending ? (
        <Skeleton className="mt-4 h-60" />
      ) : (
        <>
          <div className="mt-3 flex items-center gap-3">
            <p data-testid="chart-total" className="text-3xl font-bold">
              {formatNumber(total)}
            </p>
            <span
              data-testid="chart-delta"
              className="rounded-full bg-mint px-2.5 py-0.5 text-xs font-semibold text-emerald"
            >
              {deltaText(days, period)}
            </span>
          </div>
          {total === 0 ? (
            <p className="py-10 text-center text-muted">No videos generated in this period</p>
          ) : (
            <div className="mt-4" aria-label="Videos generated per period" role="img">
              <div
                ref={setBox}
                className="relative w-full overflow-hidden"
                style={{ height: CHART_HEIGHT }}
              >
                <BarChart data={bars} width={width} height={CHART_HEIGHT} margin={{ top: 24 }}>
                  <defs>
                    <pattern
                      id="hatch"
                      width="5"
                      height="5"
                      patternUnits="userSpaceOnUse"
                      patternTransform="rotate(45)"
                    >
                      <rect width="5" height="5" fill={MINT} />
                      <line x1="0" y1="0" x2="0" y2="5" stroke={EMERALD} strokeWidth="2" />
                    </pattern>
                  </defs>
                  <CartesianGrid
                    vertical
                    strokeDasharray="4 4"
                    horizontal={false}
                    stroke="#e4e7ec"
                  />
                  <XAxis dataKey="label" axisLine={false} tickLine={false} />
                  <Bar dataKey="videos" radius={6} isAnimationActive={!reduced}>
                    {bars.map((bar, i) => (
                      <Cell key={bar.label + i} fill={i === peak ? EMERALD : 'url(#hatch)'} />
                    ))}
                    <LabelList
                      dataKey="videos"
                      position="top"
                      formatter={(v) => formatNumber(Number(v))}
                    />
                  </Bar>
                </BarChart>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
