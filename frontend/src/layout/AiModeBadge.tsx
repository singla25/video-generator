import { Bot } from 'lucide-react';

import { useSystemStatus } from '../api/queries';

export const FAKE_AI_TEXT = 'Fake AI: a beep stands in for the name until real AI is on';
export const LOCAL_AI_TEXT = 'Local AI';

/** Shows which AI is active; renders nothing while the status loads, fails or lacks ai_mode. */
export function AiModeBadge() {
  const mode = useSystemStatus().data?.ai_mode;
  if (mode !== 'fake' && mode !== 'local') return null;
  return (
    <p
      data-testid="ai-mode-badge"
      className="mb-4 inline-flex items-center gap-1.5 rounded-full bg-mint px-3 py-1 text-xs font-semibold text-emerald"
    >
      <Bot aria-hidden="true" strokeWidth={1.5} className="size-4" />
      {mode === 'fake' ? FAKE_AI_TEXT : LOCAL_AI_TEXT}
    </p>
  );
}
