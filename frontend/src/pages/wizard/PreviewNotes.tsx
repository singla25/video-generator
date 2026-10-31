/** Shown while a local-AI preview is pending; the first run loads the models. */
export const FIRST_RUN_NOTE_TEXT =
  'First run after a restart is slow, a few minutes. The AI models are loading.';

/** Shown in fake-AI mode so nobody mistakes the beep for the real name. */
export const FAKE_NOTE_TEXT = 'Fake AI is on: the video will have a beep instead of the name.';

/** Advisory line inside the Preview panel, announced by screen readers as a note. */
function PreviewNote({ text }: { text: string }) {
  return (
    <p role="note" className="text-sm text-muted">
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
