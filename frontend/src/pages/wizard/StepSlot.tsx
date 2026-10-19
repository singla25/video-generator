import { useBatch, useTemplate } from '../../api/queries';
import { ErrorState, Skeleton } from '../../components/states';
import { PreviewPanel } from './PreviewPanel';
import { SlotEditor } from './SlotEditor';

const BUTTON = 'rounded-full bg-lime px-5 py-2 font-semibold disabled:opacity-50';
const GHOST = 'rounded-full border px-5 py-2 font-semibold hover:bg-mint';

interface Props {
  batchId: string;
  onBack: () => void;
  onNext: () => void;
}

/** Step 3: set the name slot, make a preview and approve it before starting. */
export function StepSlot({ batchId, onBack, onNext }: Props) {
  const batch = useBatch(batchId);
  const template = useTemplate(batch.data?.template_id);

  if (batch.isError || template.isError) {
    return <ErrorState title="Could not load this batch" onRetry={() => void batch.refetch()} />;
  }
  if (!batch.data || !template.data) return <Skeleton className="h-72" />;

  const ready = batch.data.preview?.status === 'READY' && batch.data.preview.approved;
  const t = template.data;
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <SlotEditor key={`${t.id}-${t.slot?.start_s}-${t.slot?.end_s}`} template={t} />
        <PreviewPanel batch={batch.data} template={t} />
      </div>
      <div className="flex justify-between">
        <button type="button" className={GHOST} onClick={onBack}>
          Back
        </button>
        <button type="button" className={BUTTON} disabled={!ready} onClick={onNext}>
          Next
        </button>
      </div>
    </div>
  );
}
