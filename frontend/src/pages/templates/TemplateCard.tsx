import { BadgeCheck, Film, ShieldAlert } from 'lucide-react';
import { useState } from 'react';

import { useSystemStatus } from '../../api/queries';
import type { Template } from '../../api/types';
import { hasDevanagari } from '../../format';
import { SlotEditor } from '../wizard/SlotEditor';
import { ConsentForm } from './ConsentForm';

function slotText(template: Template): string {
  return template.slot
    ? `Slot ${template.slot.start_s} s - ${template.slot.end_s} s`
    : 'No slot yet';
}

/** One template: placeholder thumbnail, name, slot, consent badge and usable state. */
export function TemplateCard({ template }: { template: Template }) {
  const [asking, setAsking] = useState(false);
  const fakeAi = useSystemStatus().data?.ai_mode === 'fake';
  const Badge = template.consent_confirmed ? BadgeCheck : ShieldAlert;
  return (
    <article data-testid="template-card" className="rounded-card border bg-card p-5">
      <div
        data-testid="template-thumb-placeholder"
        aria-hidden="true"
        className="mb-4 grid h-28 place-items-center rounded-tile bg-mint text-emerald"
      >
        <Film strokeWidth={1.5} className="size-10" />
      </div>
      <h2 className="font-semibold">
        <span lang={hasDevanagari(template.original_name) ? 'hi' : undefined}>
          {template.original_name}
        </span>
      </h2>
      <p className="text-sm text-muted">{slotText(template)}</p>
      {fakeAi && template.needs_manual_slot && (
        <p className="text-sm text-muted">
          Automatic detection needs real AI, so set the slot by hand.
        </p>
      )}
      <p
        data-testid="consent-badge"
        className={`mt-2 inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${template.consent_confirmed ? 'bg-mint text-status-completed' : 'bg-amber-50 text-status-skipped'}`}
      >
        <Badge aria-hidden="true" strokeWidth={1.5} className="size-4" />
        {template.consent_confirmed ? 'Consent confirmed' : 'Consent missing'}
      </p>
      <p className="mt-2 text-sm font-semibold">
        {template.usable ? 'Ready to use' : 'Not usable'}
      </p>
      {!template.consent_confirmed && !asking && (
        <button
          type="button"
          onClick={() => setAsking(true)}
          className="mt-3 rounded-full border px-4 py-1.5 text-sm font-semibold hover:bg-mint"
        >
          Upload consent
        </button>
      )}
      {template.consent_confirmed && !template.slot_confirmed && (
        <div className="mt-4">
          <SlotEditor
            key={`${template.slot?.start_s}-${template.slot?.end_s}`}
            template={template}
            showVideo={false}
          />
        </div>
      )}
      {asking && <ConsentForm templateId={template.id} onDone={() => setAsking(false)} />}
    </article>
  );
}
