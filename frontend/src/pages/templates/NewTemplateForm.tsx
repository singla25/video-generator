import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { apiFetch, apiUpload, type UploadOptions } from '../../api/client';
import type { Template } from '../../api/types';
import { useUpload } from '../../api/useUpload';
import { UploadFeedback } from '../../components/UploadFeedback';
import { VideoDropZone } from './VideoDropZone';
import { templateVideoProblem } from './videoRules';

const FIELD =
  'w-full rounded-tile border px-3 py-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald';
const BUTTON_BASE =
  'rounded-full px-5 py-2 text-sm font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald';
const WORD_HELP = "The word spoken where each person's name goes, for example Krishan.";

/** Upload a template video and the word in it that will be replaced by each name. */
export function NewTemplateForm({ onDone }: { onDone: () => void }) {
  const client = useQueryClient();
  const [video, setVideo] = useState<File | null>(null);
  const [word, setWord] = useState('');
  const [problem, setProblem] = useState<string | null>(null);

  const create = useUpload<Template>(async () => {
    await client.invalidateQueries({ queryKey: ['templates'] });
    onDone();
  });

  function submit() {
    const form = new FormData();
    form.append('video', video as File);
    form.append('original_name', word.trim());
    void create.start(async (options: UploadOptions) => {
      const created = await apiUpload<Template>('/templates', form, options);
      // Best effort: finding the slot automatically; if it fails the user sets it by hand.
      await apiFetch(`/templates/${created.id}/analyse`, { method: 'POST' }).catch(() => undefined);
      return created;
    });
  }

  function choose(file: File) {
    const issue = templateVideoProblem(file);
    setProblem(issue);
    setVideo(issue === null ? file : null);
  }

  return (
    <form
      className="mb-6 space-y-5 rounded-card border bg-card p-6"
      onSubmit={(e) => {
        e.preventDefault();
        if (video && word.trim()) submit();
      }}
    >
      <h2 className="text-lg font-bold">New template</h2>
      <div className="space-y-2">
        <span className="block text-sm font-semibold">Template video</span>
        <VideoDropZone
          file={video}
          onChoose={choose}
          onRemove={() => {
            setVideo(null);
            setProblem(null);
          }}
        />
        {problem && (
          <p role="alert" className="text-sm font-semibold text-status-failed">
            {problem}
          </p>
        )}
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
          aria-describedby="template-word-help"
          onChange={(e) => setWord(e.target.value)}
          className={FIELD}
        />
        <p id="template-word-help" className="mt-1 text-sm text-muted">
          {WORD_HELP}
        </p>
      </div>
      <UploadFeedback
        pending={create.pending}
        percent={create.percent}
        error={create.error}
        label="Uploading video"
        onRetry={create.retry}
      />
      <p className="text-sm text-muted">
        After uploading, add the consent file on the template card.
      </p>
      <div className="flex justify-end gap-3 border-t pt-4">
        <button
          type="button"
          onClick={() => {
            create.cancel();
            onDone();
          }}
          className={`${BUTTON_BASE} border font-semibold hover:bg-mint`}
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={!video || !word.trim() || create.pending}
          className={`${BUTTON_BASE} bg-lime font-semibold disabled:opacity-50`}
        >
          Upload template
        </button>
      </div>
    </form>
  );
}
