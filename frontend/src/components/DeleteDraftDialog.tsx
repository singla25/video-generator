import { ConfirmDialog } from './ConfirmDialog';

interface Props {
  onConfirm: () => void;
  onCancel: () => void;
}

/** Asks before a never-started draft is deleted. The same wording on every screen that offers it. */
export function DeleteDraftDialog({ onConfirm, onCancel }: Props) {
  return (
    <ConfirmDialog
      title="Delete this draft?"
      body="The uploaded rows will be removed. This cannot be undone."
      confirmLabel="Delete"
      cancelLabel="Keep"
      onConfirm={onConfirm}
      onCancel={onCancel}
    />
  );
}
