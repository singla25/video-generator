import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { ApiError, apiFetch } from '../../api/client';
import type { Template } from '../../api/types';

const VIDEO_EXTENSIONS = ['.mp4', '.mov', '.mkv', '.webm'];
const FIELD = 'w-full rounded-tile border px-3 py-2';

/** Upload a template video and the word in it that will be replaced by each name. */
export function NewTemplateForm({ onDone }: { onDone: () => void }) {
  const client = useQueryClient();
  const [video, setVideo] = useState<File | null>(null);
  const [word, setWord] = useState('');
  const [problem, setProblem] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: async () => {
      const form = new FormData();
      form.append('video', video as File);
      form.append('original_name', word.trim());
      const created = await apiFetch<Template>('/templates', { method: 'POST', body: form });
      // Best effort: finding the slot automatically; if it fails the user sets it by hand.
      await apiFetch(`/templates/${created.id}/analyse`, { method: 'POST' }).catch(() => undefined);
      return created;
    },
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ['templates'] });
      onDone();
    },
  });

  function choose(file: File | undefined) {
    if (!file) return;
    const ok = VIDEO_EXTENSIONS.some((ext) => file.name.toLowerCase().endsWith(ext));
    setProblem(
      file.size === 0 ? 'The video is empty.' : ok ? null : 'Use an MP4, MOV, MKV or WebM video.',
    );
    setVideo(ok && file.size > 0 ? file : null);
  }

  return (
    <form
      className="mb-6 space-y-3 rounded-card border bg-card p-5"
      onSubmit={(e) => {
        e.preventDefault();
        if (video && word.trim()) create.mutate();
      }}
    >
      <h2 className="font-semibold">New template</h2>
      <div>
        <label htmlFor="template-video" className="mb-1 block text-sm font-semibold">
          Template video
        </label>
        <input
          id="template-video"
          type="file"
          accept="video/*"
          onChange={(e) => choose(e.target.files?.[0])}
          className="block w-full text-sm"
        />
      </div>
      <div>
        <label htmlFor="template-word" className="mb-1 block text-sm font-semibold">
          Word to replace
        </label>
        <input
          id="template-word"
          type="text"
          value={word}
          maxLength={100}
          onChange={(e) => setWord(e.target.value)}
          className={FIELD}
        />
      </div>
      {problem && <p className="text-sm text-status-failed">{problem}</p>}
      {create.isError && (
        <p role="alert" className="text-sm text-status-failed">
          {create.error instanceof ApiError ? create.error.message : 'Something went wrong.'}
        </p>
      )}
      <p className="text-sm text-muted">
        After uploading, add the consent file on the template card.
      </p>
      <div className="flex gap-3">
        <button
          type="submit"
          disabled={!video || !word.trim() || create.isPending}
          className="rounded-full bg-lime px-4 py-1.5 text-sm font-semibold disabled:opacity-50"
        >
          Upload template
        </button>
        <button
          type="button"
          onClick={onDone}
          className="rounded-full border px-4 py-1.5 text-sm font-semibold hover:bg-mint"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
