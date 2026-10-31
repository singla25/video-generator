import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { useBatch } from '../api/queries';
import type { Batch, SheetInspection, SheetReport } from '../api/types';
import { EmptyState, ErrorState, Skeleton } from '../components/states';
import { ApiError } from '../api/client';
import { NoSheetDraft } from './wizard/NoSheetDraft';
import { StepMap } from './wizard/StepMap';
import { StepOutput } from './wizard/StepOutput';
import { StepSlot } from './wizard/StepSlot';
import { StepUpload } from './wizard/StepUpload';
import { Stepper } from './wizard/Stepper';
import { isClientError, resumeOf, type Resume } from './wizard/resume';

const CANNOT_CONTINUE = "This batch can't be continued.";

interface Initial {
  step: number;
  batchId: string | null;
  templateId: string;
  report: SheetReport | null;
}

const FRESH: Initial = { step: 1, batchId: null, templateId: '', report: null };

function Wizard({ initial }: { initial: Initial }) {
  const [step, setStep] = useState(initial.step);
  const [batchId, setBatchId] = useState(initial.batchId);
  const [report, setReport] = useState(initial.report);
  const [templateId, setTemplateId] = useState(initial.templateId);
  const [file, setFile] = useState<File | null>(null);
  const [inspection, setInspection] = useState<SheetInspection | null>(null);

  // A different sheet or template means a different batch: forget the old draft.
  function changeInputs(nextFile: File | null, nextTemplate: string) {
    if (nextFile !== file || nextTemplate !== templateId) {
      setBatchId(null);
      setReport(null);
    }
    setFile(nextFile);
    setTemplateId(nextTemplate);
  }

  function validated(batch: Batch) {
    setBatchId(batch.id);
    setReport(batch.report ?? null);
  }

  return (
    <div>
      <Stepper current={step} />
      {step === 1 && (
        <StepUpload
          file={file}
          templateId={templateId}
          onChange={changeInputs}
          onInspected={(found) => {
            setInspection(found);
            setStep(2);
          }}
        />
      )}
      {step === 2 && (
        <StepMap
          inspection={inspection}
          file={file}
          templateId={templateId}
          batchId={batchId}
          report={report}
          onValidated={validated}
          onBack={() => setStep(1)}
          onNext={() => setStep(3)}
        />
      )}
      {step === 3 && batchId && (
        <StepSlot batchId={batchId} onBack={() => setStep(2)} onNext={() => setStep(4)} />
      )}
      {step === 4 && batchId && (
        <StepOutput
          batchId={batchId}
          validRows={report?.valid_rows ?? 0}
          onBack={() => setStep(3)}
        />
      )}
    </div>
  );
}

/** Shown for a batch that exists but is not a draft, so it cannot be continued (DD-38). */
function CannotContinue() {
  return (
    <EmptyState title={CANNOT_CONTINUE}>
      <Link to="/" className="font-semibold text-emerald underline">
        Back to Overview
      </Link>
    </EmptyState>
  );
}

/** Shown for a missing batch: the API's own message, as an alert, with a way back (DD-38). */
function MissingBatch({ message }: { message: string }) {
  return (
    <div role="alert" className="space-y-3 rounded-card border bg-card p-8 text-center">
      <p className="font-semibold text-status-failed">{message}</p>
      <Link to="/" className="font-semibold text-emerald underline">
        Back to Overview
      </Link>
    </div>
  );
}

/**
 * Decides once, from the batch as it first loaded, what to show. Later refetches (for example
 * after the batch is started, when it is no longer a draft) never swap the open wizard out.
 */
function ResumeChoice({ batchId, batch }: { batchId: string; batch: Batch }) {
  const [resume] = useState<Resume>(() => resumeOf(batch));
  if (resume.kind === 'cannot') return <CannotContinue />;
  if (resume.kind === 'no-sheet') return <NoSheetDraft batchId={batchId} />;
  return (
    <Wizard
      initial={{
        step: 3,
        batchId,
        templateId: batch.template_id,
        report: resume.report,
      }}
    />
  );
}

function ResumedWizard({ batchId }: { batchId: string }) {
  const batch = useBatch(batchId);
  // Only a failed first load replaces the page; a failed refetch keeps the batch on screen.
  if (batch.isError && !batch.data) {
    if (isClientError(batch.error)) return <MissingBatch message={batch.error.message} />;
    const detail =
      batch.error instanceof ApiError ? batch.error.message : 'Could not load this batch';
    return <ErrorState title={detail} onRetry={() => void batch.refetch()} />;
  }
  if (!batch.data) return <Skeleton className="h-72" />;
  return <ResumeChoice batchId={batchId} batch={batch.data} />;
}

/** New batch wizard: upload, map columns, slot and preview, output and start. */
export function WizardPage() {
  const [params] = useSearchParams();
  const resume = params.get('batch');
  return resume ? <ResumedWizard key={resume} batchId={resume} /> : <Wizard initial={FRESH} />;
}
