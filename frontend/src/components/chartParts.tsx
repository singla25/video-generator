import { formatNumber } from '../format';

export const HATCH_ID = 'hatch';
const EMERALD = '#1e7a5a';
const MINT = '#e6f6ee';
const TOP_MARGIN = 24;
const BAR_RADIUS = 6;
const BACKDROP_PAD = 8;

export interface BarShapeProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  index?: number;
}

/** The fine diagonal emerald hatch used for every bar. */
export function HatchPattern() {
  return (
    <pattern
      id={HATCH_ID}
      width="5"
      height="5"
      patternUnits="userSpaceOnUse"
      patternTransform="rotate(45)"
    >
      <rect width="5" height="5" fill={MINT} />
      <line x1="0" y1="0" x2="0" y2="5" stroke={EMERALD} strokeWidth="2" />
    </pattern>
  );
}

/** A hatched column; the highlighted one also sits on a pale mint backdrop. */
export function HatchedBar({
  x = 0,
  y = 0,
  width = 0,
  height = 0,
  highlighted,
}: BarShapeProps & { highlighted: boolean }) {
  return (
    <g>
      {highlighted && (
        <rect
          x={x - BACKDROP_PAD}
          y={TOP_MARGIN}
          width={width + 2 * BACKDROP_PAD}
          height={Math.max(0, y + height - TOP_MARGIN)}
          rx={BAR_RADIUS}
          fill={MINT}
        />
      )}
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        rx={BAR_RADIUS}
        fill={`url(#${HATCH_ID})`}
        stroke={EMERALD}
        strokeWidth={1}
      />
    </g>
  );
}

interface ValueProps {
  x?: number | string;
  y?: number | string;
  width?: number | string;
  value?: number | string;
  highlighted: boolean;
}

/** Value label above a column; the highlighted one is bolder and darker. */
export function BarValue({ x = 0, y = 0, width = 0, value = 0, highlighted }: ValueProps) {
  return (
    <text
      x={Number(x) + Number(width) / 2}
      y={Number(y) - 6}
      textAnchor="middle"
      fontSize={highlighted ? 14 : 12}
      fontWeight={highlighted ? 700 : 500}
      fill={highlighted ? EMERALD : '#6b7480'}
    >
      {formatNumber(Number(value))}
    </text>
  );
}
