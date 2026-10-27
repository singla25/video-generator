import { useQueryClient } from '@tanstack/react-query';
import { useId, useState } from 'react';

import { apiUpload } from '../../api/client';
import { useUpload } from '../../api/useUpload';
import { UploadFeedback } from '../../components/UploadFeedback';

/** Upload the consent file and tick the confirmation for one template. */
export function ConsentForm({ templateId, onDone }: { templateId: string; onDone: () => void }) {
  const client = useQueryClient();
  const fileId = useId();
  const [file, setFile] = useState<File | null>(null);
  const [ticked, setTicked] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const submit = useUpload<unknown>(async () => {
    await client.invalidateQueries({ queryKey: ['templates'] });
    onDone();
  });

  function send() {
    const form = new FormData();
    form.append('file', file as File);
    form.append('confirmed', 'true');
    void submit.start((options) => apiUpload(`/templates/${templateId}/consent`, form, options));
  }

  function choose(candidate: File | undefined) {
    setFile(candidate && candidate.size > 0 ? candidate : null);
    setProblem(candidate && candidate.size === 0 ? 'The consent file is empty.' : null);
  }

  return (
    <div className="mt-4 space-y-3 border-t pt-4">
      <label htmlFor={fileId} className="block text-sm font-semibold">
        Consent file
      </label>
      <input
        id={fileId}
        type="file"
        accept=".pdf,image/*"
        onChange={(e) => choose(e.target.files?.[0])}
        className="block w-full text-sm"
      />
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          checked={ticked}
          onChange={(e) => setTicked(e.target.checked)}
          className="mt-1"
        />
        I confirm I have consent to use this video
      </label>
      {problem && <p className="text-sm text-status-failed">{problem}</p>}
      <UploadFeedback
        pending={submit.pending}
        percent={submit.percent}
        error={submit.error}
        label="Uploading consent file"
        onRetry={submit.retry}
      />
      <button
        type="button"
        disabled={!file || !ticked || submit.pending}
        onClick={send}
        className="rounded-full bg-lime px-4 py-1.5 text-sm font-semibold disabled:opacity-50"
      >
        Submit consent
      </button>
    </div>
  );
}
