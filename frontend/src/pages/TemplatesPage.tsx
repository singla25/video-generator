import { Plus } from 'lucide-react';
import { useState } from 'react';

import { useTemplates } from '../api/queries';
import { EmptyState, ErrorState, Skeleton } from '../components/states';
import { NewTemplateForm } from './templates/NewTemplateForm';
import { TemplateCard } from './templates/TemplateCard';

/** Template library: cards, consent upload and a form for new templates. */
export function TemplatesPage() {
  const templates = useTemplates();
  const [adding, setAdding] = useState(false);

  return (
    <div>
      <div className="mb-4 flex justify-end">
        <button
          type="button"
          onClick={() => setAdding(true)}
          className="inline-flex items-center gap-1.5 rounded-full border px-4 py-1.5 text-sm font-semibold hover:bg-mint"
        >
          <Plus aria-hidden="true" strokeWidth={1.5} className="size-4" />
          New template
        </button>
      </div>
      {adding && <NewTemplateForm onDone={() => setAdding(false)} />}
      {templates.isPending ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-64" />
          ))}
        </div>
      ) : templates.isError ? (
        <ErrorState title="Could not load templates" onRetry={() => void templates.refetch()} />
      ) : templates.data.templates.length === 0 ? (
        <EmptyState title="No templates yet" />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {templates.data.templates.map((t) => (
            <TemplateCard key={t.id} template={t} />
          ))}
        </div>
      )}
    </div>
  );
}
