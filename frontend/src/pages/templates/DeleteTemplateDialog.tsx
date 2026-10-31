import { ApiError } from '../../api/client';
import { useDeleteTemplate } from '../../api/queries';
import { ConfirmDialog } from '../../components/ConfirmDialog';

const FALLBACK = 'Something went wrong. Please try again.';

/** The words to show for a failed delete: the API's own message when it gave one. */
function messageFor(error: unknown): string {
  return error instanceof ApiError ? error.message : FALLBACK;
}

interface Props {
  templateId: string;
  onClose: () => void;
}

/** Confirmation before a template is deleted. A refusal keeps the dialog open with the reason. */
export function DeleteTemplateDialog({ templateId, onClose }: Props) {
  const remove = useDeleteTemplate(templateId);
  return (
    <ConfirmDialog
      title="Delete this template?"
      body="This cannot be undone."
      confirmLabel="Delete"
      cancelLabel="Cancel"
      pending={remove.isPending}
      error={remove.error ? messageFor(remove.error) : null}
      onConfirm={() => remove.run(onClose)}
      onCancel={onClose}
    />
  );
}
