import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useId, useState } from 'react';

import { ApiError, apiFetch } from '../../api/client';

/** Upload the consent file and tick the confirmation for one template. */
export function ConsentForm({ templateId, onDone }: { templateId: string; onDone: () => void }) {
  const client = useQueryClient();
  const fileId = useId();
  const [file, setFile] = useState<File | null>(null);
  const [ticked, setTicked] = useState(false);

  const submit = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.append('file', file as File);
      form.append('confirmed', 'true');
      return apiFetch(`/templates/${templateId}/consent`, { method: 'POST', body: form });
    },
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ['templates'] });
      onDone();
    },
  });

  return (
    <div className="mt-4 space-y-3 border-t pt-4">
      <label htmlFor={fileId} className="block text-sm font-semibold">
        Consent file
      </label>
      <input
        id={fileId}
        type="file"
        accept=".pdf,image/*"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
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
      {submit.isError && (
        <p role="alert" className="text-sm text-status-failed">
          {submit.error instanceof ApiError ? submit.error.message : 'Something went wrong.'}
        </p>
      )}
      <button
        type="button"
        disabled={!file || !ticked || submit.isPending}
        onClick={() => submit.mutate()}
        className="rounded-full bg-lime px-4 py-1.5 text-sm font-semibold disabled:opacity-50"
      >
        Submit consent
      </button>
    </div>
  );
}
