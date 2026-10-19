// D-F6-3 chip contrast and UI-AC1 hatched chart. Cases: TT-UI-AC13-P1.., TT-UI-AC1-P1..
//
// CONTRACT (frontend/src):
//   components/chipColors.ts  export chipColors: Record<'green'|'blue'|'grey'|'red'|'amber',
//                             { text: '#rrggbb'; background: '#rrggbb' }>
//   components/StatusChip.tsx applies those two colours as inline style (color, background-color)
//   components/VideosChart.tsx  one <pattern id="..."> (hatch) in the chart; non-peak bars have
//                             fill="url(#<that id>)"; the peak bar is solid
import { render, screen, waitFor } from '@testing-library/react';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { chipColors } from '../../../frontend/src/components/chipColors';
import { StatusChip } from '../../../frontend/src/components/StatusChip';
import { renderApp } from '../helpers';
import { server } from '../mocks/server';
import { setReducedMotion } from '../motion';

const AA_NORMAL_TEXT = 4.5;

function channel(hex: string, start: number): number {
  const value = parseInt(hex.slice(start, start + 2), 16) / 255;
  return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  return 0.2126 * channel(hex, 1) + 0.7152 * channel(hex, 3) + 0.0722 * channel(hex, 5);
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
}

function rgb(hex: string): string {
  const n = (s: number) => parseInt(hex.slice(s, s + 2), 16);
  return `rgb(${n(1)}, ${n(3)}, ${n(5)})`;
}

const TONES = ['green', 'blue', 'grey', 'red', 'amber'] as const;
const STATUS_FOR_TONE = {
  green: 'COMPLETED',
  blue: 'PROCESSING',
  grey: 'QUEUED',
  red: 'FAILED',
  amber: 'SKIPPED',
} as const;

describe('status chip colours (WCAG AA)', () => {
  it('TT-UI-AC13-P1 the map has exactly the five tones with hex colours', () => {
    expect(Object.keys(chipColors).sort()).toEqual([...TONES].sort());
    for (const tone of TONES) {
      expect(chipColors[tone].text).toMatch(/^#[0-9a-fA-F]{6}$/);
      expect(chipColors[tone].background).toMatch(/^#[0-9a-fA-F]{6}$/);
    }
  });

  it.each(TONES)(
    'TT-UI-AC13-P2 %s chip text has at least 4.5:1 contrast on its background',
    (tone) => {
      const { text, background } = chipColors[tone];
      expect(contrast(text, background)).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
    },
  );

  it.each(TONES)('TT-UI-AC13-P3 the %s chip renders the colours from the map', (tone) => {
    render(<StatusChip status={STATUS_FOR_TONE[tone]} />);
    const chip = screen.getByTestId('status-chip');
    expect(chip).toHaveStyle({
      color: rgb(chipColors[tone].text),
      backgroundColor: rgb(chipColors[tone].background),
    });
  });

  it('TT-UI-AC13-E1 contrast helper sanity: black on white is 21, equal colours are 1', () => {
    expect(contrast('#000000', '#ffffff')).toBeCloseTo(21, 0);
    expect(contrast('#777777', '#777777')).toBeCloseTo(1, 5);
  });
});

describe('hatched chart', () => {
  function stats() {
    // Seven points eight days apart: always seven separate weekly buckets.
    const dates = [
      '2026-08-30',
      '2026-09-07',
      '2026-09-15',
      '2026-09-23',
      '2026-10-01',
      '2026-10-09',
      '2026-10-17',
    ];
    const videos = [40, 90, 60, 300, 120, 80, 150];
    server.use(
      http.get('*/stats/daily', () =>
        HttpResponse.json({
          days: dates.map((date, i) => ({ date, videos: videos[i], avg_render_seconds: 10 })),
        }),
      ),
    );
  }

  it('TT-UI-AC1-P1 a hatch pattern is defined and the non-peak bars are filled with it', async () => {
    setReducedMotion(true);
    stats();
    renderApp('/');
    await waitFor(() => expect(document.querySelector('pattern')).not.toBeNull());
    const pattern = document.querySelector('pattern')!;
    const id = pattern.getAttribute('id');
    expect(id).toBeTruthy();
    await waitFor(() =>
      expect(document.querySelectorAll(`[fill="url(#${id})"]`).length).toBeGreaterThanOrEqual(2),
    );
  });

  it('TT-UI-AC1-P2 the pattern draws diagonal lines (rotated) over a mint base', async () => {
    setReducedMotion(true);
    stats();
    renderApp('/');
    await waitFor(() => expect(document.querySelector('pattern')).not.toBeNull());
    const pattern = document.querySelector('pattern')!;
    expect(pattern.getAttribute('patternTransform')).toMatch(/rotate\(/);
    expect(pattern.querySelector('line')).not.toBeNull();
    expect(pattern.querySelector('rect')).not.toBeNull();
  });

  it('TT-UI-AC1-E1 the highest bar stays solid, not hatched', async () => {
    setReducedMotion(true);
    stats();
    renderApp('/');
    await waitFor(() => expect(document.querySelector('pattern')).not.toBeNull());
    const id = document.querySelector('pattern')!.getAttribute('id');
    await waitFor(() => {
      const hatched = document.querySelectorAll(`[fill="url(#${id})"]`).length;
      const solid = document.querySelectorAll(
        '.recharts-bar-rectangle [fill]:not([fill^="url"])',
      ).length;
      expect(hatched).toBeGreaterThanOrEqual(2);
      expect(solid).toBeGreaterThanOrEqual(1);
    });
  });
});
