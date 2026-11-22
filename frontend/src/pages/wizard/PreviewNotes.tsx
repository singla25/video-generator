/** Shown while a local-AI preview is pending; the first run loads the models. */
export const FIRST_RUN_NOTE_TEXT =
  'First run after a restart is slow, a few minutes. The AI models are loading.';

/** Shown in fake-AI mode so nobody mistakes the beep for the real name. */
export const FAKE_NOTE_TEXT = 'Fake AI is on: the video will have a beep instead of the name.';

const SUFFIX_SETTING = '(VIDGEN_SPOKEN_SUFFIX)';

/** Advisory line inside the Preview panel, announced by screen readers as a note. */
function PreviewNote({ text, testId }: { text: string; testId?: string }) {
  return (
    <p role="note" data-testid={testId} className="text-sm text-muted">
      {text}
    </p>
  );
}

export function FirstRunNote() {
  return <PreviewNote text={FIRST_RUN_NOTE_TEXT} />;
}

export function FakeAiNote() {
  return <PreviewNote text={FAKE_NOTE_TEXT} />;
}

/** Note text for a suffix the server sent, already trimmed. "" means the suffix is off. */
export function spokenSuffixNoteText(suffix: string): string {
  if (suffix === '') {
    return `No spoken suffix is set. This is a global setting ${SUFFIX_SETTING}.`;
  }
  return `After the name the voice also says: ${suffix}. This is a global setting ${SUFFIX_SETTING} that applies to every template.`;
}

/**
 * Says which spoken suffix the server applies to every template. Renders nothing when the
 * suffix is unknown (status still loading, failed, or an older server without the key).
 */
export function SpokenSuffixNote({ suffix }: { suffix: string | undefined }) {
  if (typeof suffix !== 'string') return null;
  return <PreviewNote text={spokenSuffixNoteText(suffix.trim())} testId="spoken-suffix-note" />;
}
