import clsx from 'clsx';

export const STEP_LABELS = ['Upload', 'Map columns', 'Slot & preview', 'Output & start'] as const;

/** The four wizard steps; the current one carries aria-current="step". */
export function Stepper({ current }: { current: number }) {
  return (
    <ol aria-label="Steps" className="mb-6 flex flex-wrap gap-3">
      {STEP_LABELS.map((label, i) => {
        const number = i + 1;
        const active = number === current;
        return (
          <li
            key={label}
            aria-current={active ? 'step' : undefined}
            className={clsx(
              'flex items-center gap-2 rounded-full border px-4 py-1.5 text-sm font-semibold',
              active ? 'bg-mint text-emerald' : 'bg-card text-muted',
              number < current && 'text-emerald',
            )}
          >
            <span aria-hidden="true">{number}</span>
            {label}
          </li>
        );
      })}
    </ol>
  );
}
