import type { PreviewStage } from '../../api/types';

interface Step {
  stage: PreviewStage;
  label: string;
}

const STEPS: readonly Step[] = [
  { stage: 'preparing', label: 'Preparing' },
  { stage: 'voice', label: 'Speaking the name' },
  { stage: 'lipsync', label: 'Matching the lips' },
  { stage: 'finishing', label: 'Finishing' },
];

type StepState = 'done' | 'current' | 'todo';

/** Position of the active step; an unknown or missing stage counts as the first step. */
export function currentStepIndex(stage: string | null | undefined): number {
  return Math.max(
    STEPS.findIndex((step) => step.stage === stage),
    0,
  );
}

function stepState(index: number, current: number): StepState {
  if (index < current) return 'done';
  return index === current ? 'current' : 'todo';
}

/** Four-step list of a pending preview; exactly one step is current at a time. */
export function PreviewProgress({ stage }: { stage: string | null | undefined }) {
  const current = currentStepIndex(stage);
  return (
    <ol role="list" aria-label="Preview progress" className="grid gap-2 text-sm sm:grid-cols-4">
      {STEPS.map((step, index) => {
        const state = stepState(index, current);
        return (
          <li
            key={step.stage}
            data-state={state}
            aria-current={state === 'current' ? 'step' : undefined}
            className="rounded-tile border px-3 py-2 text-muted data-[state=current]:bg-mint data-[state=current]:font-semibold data-[state=current]:text-emerald data-[state=done]:text-ink"
          >
            {step.label}
          </li>
        );
      })}
    </ol>
  );
}
