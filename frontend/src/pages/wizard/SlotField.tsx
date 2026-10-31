const FIELD = 'w-full rounded-tile border px-3 py-2';

interface Props {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  /** Focus the field when it appears, used for a slot the user has just added. */
  autoFocus?: boolean;
}

/** A labelled number field for a slot time, in seconds. */
export function SlotField({ id, label, value, onChange, autoFocus = false }: Props) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-semibold">
        {label}
      </label>
      <input
        id={id}
        type="number"
        step="0.1"
        min="0"
        value={value}
        autoFocus={autoFocus}
        onChange={(e) => onChange(e.target.value)}
        className={FIELD}
      />
    </div>
  );
}
