import { BadgeCheck, Film, ShieldAlert } from 'lucide-react';
import { useState } from 'react';

import { useSystemStatus } from '../../api/queries';
import type { Template } from '../../api/types';
import { hasDevanagari } from '../../format';
import { SlotEditor } from '../wizard/SlotEditor';
import { slotStateKey } from '../wizard/slotChecks';
import { ConsentForm } from './ConsentForm';
import { DeleteTemplateDialog } from './DeleteTemplateDialog';

/** "Slot 4.2 s - 5.1 s" for one slot, "Slots 2 s - 3 s, 10 s - 11 s" for several (DD-40). */
function slotText(template: Template): string {
  if (!template.slot) return 'No slot yet';
  const pairs: [number, number][] =
    template.slots.length > 0 ? template.slots : [[template.slot.start_s, template.slot.end_s]];
  const parts = pairs.map(([start, end]) => `${start} s - ${end} s`);
  return pairs.length === 1 ? `Slot ${parts[0]}` : `Slots ${parts.join(', ')}`;
}

/** One template: placeholder thumbnail, name, slot, consent badge and usable state. */
export function TemplateCard({ template }: { template: Template }) {
  const [asking, setAsking] = useState(false);
  const [deleting, setDeleting] = useState(false);
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
          <SlotEditor key={slotStateKey(template)} template={template} showVideo={false} />
        </div>
      )}
      {asking && <ConsentForm templateId={template.id} onDone={() => setAsking(false)} />}
      <div className="mt-4 flex justify-end">
        <button
          type="button"
          onClick={() => setDeleting(true)}
          className="rounded-full border px-4 py-1.5 text-sm font-semibold text-status-failed hover:bg-mint"
        >
          Delete template
        </button>
      </div>
      {deleting && (
        <DeleteTemplateDialog templateId={template.id} onClose={() => setDeleting(false)} />
      )}
    </article>
  );
}
