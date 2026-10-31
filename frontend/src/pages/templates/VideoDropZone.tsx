import { useRef, useState, type DragEvent } from 'react';

import { formatMegabytes } from '../../format';

const DROP_HINT = 'Drop the video here or choose a file';
const FORMATS = 'MP4, MOV, MKV or WebM';

/** Upload arrow drawn inline, so no icon package is needed. Decorative: the label says it all. */
function UploadIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      className="size-10 text-emerald"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M12 15V4" />
      <path d="m7 9 5-5 5 5" />
      <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
    </svg>
  );
}

interface Props {
  file: File | null;
  onChoose: (file: File) => void;
  onRemove: () => void;
}

/** Template video box: click to choose a file, or drag one onto it. Shows the chosen file. */
export function VideoDropZone({ file, onChoose, onRemove }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function drop(e: DragEvent<HTMLLabelElement>) {
    e.preventDefault();
    setDragging(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) onChoose(dropped);
  }

  function remove() {
    // Clear the input too, so choosing the same file again fires a change.
    if (input.current) input.current.value = '';
    onRemove();
  }

  const highlight = dragging ? 'border-emerald bg-mint' : 'bg-page';

  return (
    <div className="space-y-2">
      <label
        aria-label="Template video"
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={drop}
        className={`flex cursor-pointer flex-col items-center gap-2 rounded-card border-2 border-dashed p-6 text-center focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-emerald ${highlight}`}
      >
        <input
          ref={input}
          type="file"
          accept="video/*"
          className="sr-only"
          onChange={(e) => {
            const chosen = e.target.files?.[0];
            if (chosen) onChoose(chosen);
          }}
        />
        {file ? (
          <>
            <span className="font-semibold break-all">
              {`${file.name} · ${formatMegabytes(file.size)} MB`}
            </span>
            <span className="text-sm text-muted">Choose another video to replace it</span>
          </>
        ) : (
          <>
            <UploadIcon />
            <span className="font-semibold">{DROP_HINT}</span>
            <span className="text-sm text-muted">{FORMATS}</span>
          </>
        )}
      </label>
      {file && (
        <div className="flex justify-end">
          <button
            type="button"
            onClick={remove}
            className="rounded-full border px-4 py-1.5 text-sm font-semibold hover:bg-mint focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald"
          >
            Remove file
          </button>
        </div>
      )}
    </div>
  );
}
