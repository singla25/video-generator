import { useEffect, useRef, useState } from 'react';

import { COUNT_UP_DURATION_MS, COUNT_UP_STEP_MS } from '../config';
import { useReducedMotion } from '../hooks';

const FORMAT = new Intl.NumberFormat('en-US');

/** A number that counts up from 0, or appears at once when motion is reduced. */
export function CountUp({ value }: { value: number }) {
  const reduced = useReducedMotion();
  const [animated, setAnimated] = useState(0);
  const from = useRef(0);

  useEffect(() => {
    if (reduced) return;
    const start = from.current;
    const steps = Math.max(1, Math.round(COUNT_UP_DURATION_MS / COUNT_UP_STEP_MS));
    let step = 0;
    const timer = setInterval(() => {
      step += 1;
      const progress = 1 - (1 - step / steps) ** 3;
      const next = Math.round(start + (value - start) * progress);
      from.current = next;
      setAnimated(next);
      if (step >= steps) clearInterval(timer);
    }, COUNT_UP_STEP_MS);
    return () => clearInterval(timer);
  }, [value, reduced]);

  return <span>{FORMAT.format(reduced ? value : animated)}</span>;
}
