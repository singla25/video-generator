import { useId } from 'react';

import { SlotField } from './SlotField';

interface Props {
  /** Position among the extra slots (0 for Slot 2). The label follows the position. */
  index: number;
  start: string;
  end: string;
  autoFocus: boolean;
  onChange: (field: 'start' | 'end', value: string) => void;
  onRemove: () => void;
}

/** One extra name slot: its start and end fields and a button that removes it. */
export function ExtraSlotRow({ index, start, end, autoFocus, onChange, onRemove }: Props) {
  const ids = useId();
  const n = index + 2;
  return (
    <div className="space-y-2 rounded-tile border p-3">
      <div className="grid grid-cols-2 gap-3">
        <SlotField
          id={`${ids}-start`}
          label={`Slot ${n} start (s)`}
          value={start}
          autoFocus={autoFocus}
          onChange={(value) => onChange('start', value)}
        />
        <SlotField
          id={`${ids}-end`}
          label={`Slot ${n} end (s)`}
          value={end}
          onChange={(value) => onChange('end', value)}
        />
      </div>
      <button
        type="button"
        onClick={onRemove}
        className="rounded-full border px-4 py-1.5 text-sm font-semibold text-status-failed hover:bg-mint"
      >
        {`Remove slot ${n}`}
      </button>
    </div>
  );
}
