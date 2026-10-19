import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { useBatch } from '../api/queries';
import type { Batch, SheetInspection, SheetReport } from '../api/types';
import { ErrorState, Skeleton } from '../components/states';
import { ApiError } from '../api/client';
import { StepMap } from './wizard/StepMap';
import { StepOutput } from './wizard/StepOutput';
import { StepSlot } from './wizard/StepSlot';
import { StepUpload } from './wizard/StepUpload';
import { Stepper } from './wizard/Stepper';

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

function ResumedWizard({ batchId }: { batchId: string }) {
  const batch = useBatch(batchId);
  if (batch.isError) {
    const detail =
      batch.error instanceof ApiError ? batch.error.message : 'Could not load this batch';
    return <ErrorState title={detail} onRetry={() => void batch.refetch()} />;
  }
  if (!batch.data) return <Skeleton className="h-72" />;
  const report = batch.data.report ?? null;
  return (
    <Wizard
      initial={{
        step: report && report.valid_rows > 0 ? 3 : 2,
        batchId,
        templateId: batch.data.template_id,
        report,
      }}
    />
  );
}

/** New batch wizard: upload, map columns, slot and preview, output and start. */
export function WizardPage() {
  const [params] = useSearchParams();
  const resume = params.get('batch');
  return resume ? <ResumedWizard key={resume} batchId={resume} /> : <Wizard initial={FRESH} />;
}
