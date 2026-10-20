export type ChipTone = 'green' | 'blue' | 'grey' | 'red' | 'amber';

/**
 * Status chip colours. The hues follow the design notes (green, blue, grey, red, amber);
 * every text/background pair has a contrast of at least 4.5:1 (WCAG AA for small text).
 */
export const chipColors: Record<ChipTone, { text: string; background: string }> = {
  green: { text: '#17694b', background: '#e6f6ee' },
  blue: { text: '#1f55b8', background: '#e7effd' },
  grey: { text: '#4b5563', background: '#eef0f3' },
  red: { text: '#b42323', background: '#fdecec' },
  amber: { text: '#8a5300', background: '#fff3dc' },
};
