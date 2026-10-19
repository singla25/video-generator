import type { DailyStat } from '../api/types';
import { formatNumber } from '../format';

export type Period = 'day' | 'week';

export interface Bar {
  label: string;
  videos: number;
}

/** How many days of history each period asks the API for. */
export const PERIOD_DAYS: Record<Period, number> = { day: 14, week: 56 };

const DAYS_PER_WEEK = 7;

function shortDate(iso: string, options: Intl.DateTimeFormatOptions): string {
  return new Date(`${iso}T12:00:00Z`).toLocaleDateString('en-US', { timeZone: 'UTC', ...options });
}

/** Turn daily stats into chart bars: one per day, or one per 7-day block. */
export function toBars(days: DailyStat[], period: Period): Bar[] {
  if (period === 'day') {
    return days.map((d) => ({ label: shortDate(d.date, { weekday: 'short' }), videos: d.videos }));
  }
  const bars: Bar[] = [];
  for (let end = days.length; end > 0; end -= DAYS_PER_WEEK) {
    const block = days.slice(Math.max(0, end - DAYS_PER_WEEK), end);
    bars.unshift({
      label: shortDate(block[0]!.date, { month: 'short', day: 'numeric' }),
      videos: block.reduce((sum, d) => sum + d.videos, 0),
    });
  }
  return bars;
}

/** Text for the change pill: latest 7 days (or week) against the one before. */
export function deltaText(days: DailyStat[], period: Period): string {
  const values = days.map((d) => d.videos);
  const sum = (items: number[]) => items.reduce((a, b) => a + b, 0);
  const current = sum(values.slice(-DAYS_PER_WEEK));
  const previous = sum(values.slice(-2 * DAYS_PER_WEEK, -DAYS_PER_WEEK));
  const suffix = period === 'week' ? 'vs last week' : 'vs last 7 days';
  if (previous === 0) return `- ${suffix}`;
  const percent = Math.round(((current - previous) / previous) * 100);
  return `${percent >= 0 ? '+' : '-'}${formatNumber(Math.abs(percent))} % ${suffix}`;
}
