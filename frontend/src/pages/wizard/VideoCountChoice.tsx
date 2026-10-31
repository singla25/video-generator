import { useId } from 'react';

import {
  FIXED_COUNTS,
  countSummary,
  customProblem,
  videoCount,
  type VideoChoice,
} from './videoCount';

interface OptionProps {
  name: string;
  label: string;
  checked: boolean;
  disabled?: boolean;
  onSelect: () => void;
}

/** One radio drawn as a pill; the whole pill is the click target. */
function Option({ name, label, checked, disabled = false, onSelect }: OptionProps) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-2 rounded-full border px-4 py-1.5 text-sm font-semibold has-[:checked]:border-emerald has-[:checked]:bg-mint has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-50 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-emerald">
      <input
        type="radio"
        name={name}
        checked={checked}
        disabled={disabled}
        onChange={onSelect}
        className="size-4 accent-emerald"
      />
      {label}
    </label>
  );
}

interface Props {
  rows: number;
  choice: VideoChoice;
  custom: string;
  onChoice: (choice: VideoChoice) => void;
  onCustom: (text: string) => void;
}

/** Step 4 "Videos to generate": all rows, First 5/10/15, or a custom number, with a summary. */
export function VideoCountChoice({ rows, choice, custom, onChoice, onCustom }: Props) {
  const id = useId();
  const count = videoCount(choice, custom, rows);
  const problem = choice === 'custom' ? customProblem(custom, rows) : null;
  const radioName = `${id}-videos`;

  return (
    <div className="space-y-3">
      <p id={`${id}-group`} className="text-sm font-semibold">
        Videos to generate
      </p>
      <div role="radiogroup" aria-labelledby={`${id}-group`} className="flex flex-wrap gap-2">
        <Option
          name={radioName}
          label={`All ${rows} rows`}
          checked={choice === 'all'}
          onSelect={() => onChoice('all')}
        />
        {FIXED_COUNTS.map((n) => (
          <Option
            key={n}
            name={radioName}
            label={`First ${n}`}
            checked={choice === n}
            disabled={n > rows}
            onSelect={() => onChoice(n)}
          />
        ))}
        <Option
          name={radioName}
          label="Custom"
          checked={choice === 'custom'}
          onSelect={() => onChoice('custom')}
        />
      </div>
      {choice === 'custom' && (
        <div className="space-y-1">
          <label htmlFor={`${id}-custom`} className="block text-sm font-semibold">
            Number of videos
          </label>
          <input
            id={`${id}-custom`}
            type="number"
            min={1}
            max={rows}
            step={1}
            value={custom}
            aria-invalid={problem !== null}
            aria-describedby={problem ? `${id}-problem` : undefined}
            onChange={(e) => onCustom(e.target.value)}
            className="w-32 rounded-tile border px-3 py-2"
          />
          {problem && (
            <p id={`${id}-problem`} className="text-sm text-status-failed">
              {problem}
            </p>
          )}
        </div>
      )}
      {count !== null && <p className="text-sm text-muted">{countSummary(count, rows)}</p>}
    </div>
  );
}
