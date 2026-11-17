import { useId } from 'react';

import type { DataClass } from '../../api/types';

export const CONFIRM_DEMO_LABEL = 'I confirm this is demo or learning data only';

export interface DataClassState {
  dataClass: DataClass;
  confirmDemo: boolean;
}

interface Props {
  value: DataClassState;
  onChange: (next: DataClassState) => void;
}

/** True when the data class choice lets the user go on (demo needs its confirmation). */
export function dataClassReady({ dataClass, confirmDemo }: DataClassState): boolean {
  return dataClass === 'real' || confirmDemo;
}

/** Step 1 choice: real data (default) or demo data, which must be confirmed. */
export function DataClassChoice({ value, onChange }: Props) {
  const labelId = useId();
  const name = useId();
  const option = (dataClass: DataClass, label: string) => (
    <label className="flex items-center gap-2 text-sm">
      <input
        type="radio"
        name={name}
        checked={value.dataClass === dataClass}
        onChange={() => onChange({ dataClass, confirmDemo: false })}
      />
      {label}
    </label>
  );
  return (
    <div role="radiogroup" aria-labelledby={labelId} className="space-y-2">
      <p id={labelId} className="text-sm font-semibold">
        Data class
      </p>
      {option('real', 'Real data')}
      {option('demo', 'Demo or learning data')}
      {value.dataClass === 'demo' && (
        <label className="flex items-center gap-2 pl-6 text-sm">
          <input
            type="checkbox"
            checked={value.confirmDemo}
            onChange={(e) => onChange({ dataClass: 'demo', confirmDemo: e.target.checked })}
          />
          {CONFIRM_DEMO_LABEL}
        </label>
      )}
    </div>
  );
}
