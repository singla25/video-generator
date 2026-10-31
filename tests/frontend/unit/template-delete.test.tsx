// DD-37 C: delete a template from its card on the Templates page. Cases: TT-DD37-C-*
//
// CONTRACT (frontend/src/pages/templates/TemplateCard.tsx):
//   every card has a button "Delete template"
//   it opens a dialog (role dialog, name "Delete this template?") with the text
//     "This cannot be undone." and the buttons "Delete" and "Cancel"
//   Cancel closes the dialog and sends nothing
//   Delete sends DELETE /api/templates/<id>; on 204 the dialog closes and the templates list is
//     refetched (the card disappears)
//   on 409 the dialog stays open and shows the API error message in an element with role alert
//   the Delete button is disabled while the request runs
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, delay, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { renderApp } from '../helpers';
import { IDS, TEMPLATE_NO_CONSENT, template } from '../mocks/data';
import { apiError } from '../mocks/handlers';
import { server } from '../mocks/server';

const IN_USE = 'This template is used by 2 batches. Delete those batches first.';

/**
 * Serve the templates list from a store that DELETE /templates/<id> really changes, like the API.
 * Records every DELETE and every list request.
 */
function serveTemplates(initial = [template(), TEMPLATE_NO_CONSENT], deleteDelayMs = 0) {
  let stock = [...initial];
  const deletes: string[] = [];
  let lists = 0;
  server.use(
    http.get('*/templates', () => {
      lists += 1;
      return HttpResponse.json({ templates: stock });
    }),
    http.delete('*/templates/:id', async ({ params }) => {
      deletes.push(String(params.id));
      if (deleteDelayMs > 0) await delay(deleteDelayMs);
      stock = stock.filter((t) => t.id !== params.id);
      return new HttpResponse(null, { status: 204 });
    }),
  );
  return { deletes, lists: () => lists };
}

function cardFor(name: string): HTMLElement {
  const card = screen.getAllByTestId('template-card').find((c) => within(c).queryByText(name));
  if (!card) throw new Error(`no card for ${name}`);
  return card;
}

/** Open the delete dialog for the named template and return it. */
async function openDeleteFor(name: string) {
  await userEvent.click(within(cardFor(name)).getByRole('button', { name: 'Delete template' }));
  return within(await screen.findByRole('dialog', { name: 'Delete this template?' }));
}

describe('positive', () => {
  it('TT-DD37-C-P1 every template card has a Delete template button', async () => {
    serveTemplates();
    renderApp('/templates');
    const cards = await screen.findAllByTestId('template-card');
    expect(cards).toHaveLength(2);
    for (const card of cards) {
      expect(within(card).getByRole('button', { name: 'Delete template' })).toBeInTheDocument();
    }
  });

  it('TT-DD37-C-P2 Delete template opens a confirmation dialog with the warning and both buttons', async () => {
    serveTemplates();
    renderApp('/templates');
    await screen.findAllByTestId('template-card');
    const dialog = await openDeleteFor('Rahul');
    expect(dialog.getByText('This cannot be undone.')).toBeInTheDocument();
    expect(dialog.getByRole('button', { name: 'Delete' })).toBeInTheDocument();
    expect(dialog.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
  });

  it('TT-DD37-C-P3 confirming sends DELETE for that template and the card disappears', async () => {
    const store = serveTemplates();
    renderApp('/templates');
    await screen.findAllByTestId('template-card');
    const dialog = await openDeleteFor('Rahul');
    await userEvent.click(dialog.getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(store.deletes).toEqual([IDS.template]));
    await waitFor(() =>
      expect(
        screen.queryByRole('dialog', { name: 'Delete this template?' }),
      ).not.toBeInTheDocument(),
    );
    await waitFor(() => expect(screen.queryByText('Rahul')).not.toBeInTheDocument());
    expect(screen.getByText('Priya')).toBeInTheDocument();
  });

  it('TT-DD37-C-P4 a successful delete refetches the templates list', async () => {
    const store = serveTemplates();
    renderApp('/templates');
    await screen.findAllByTestId('template-card');
    const before = store.lists();
    const dialog = await openDeleteFor('Priya');
    await userEvent.click(dialog.getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(store.lists()).toBeGreaterThan(before));
  });
});

describe('negative', () => {
  it('TT-DD37-C-N1 Cancel closes the dialog and sends no request', async () => {
    const store = serveTemplates();
    renderApp('/templates');
    await screen.findAllByTestId('template-card');
    const dialog = await openDeleteFor('Rahul');
    await userEvent.click(dialog.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('dialog', { name: 'Delete this template?' })).not.toBeInTheDocument();
    expect(store.deletes).toEqual([]);
    expect(cardFor('Rahul')).toBeInTheDocument();
  });

  it('TT-DD37-C-N2 a 409 keeps the dialog open and shows the API message in an alert', async () => {
    server.use(
      http.get('*/templates', () =>
        HttpResponse.json({ templates: [template(), TEMPLATE_NO_CONSENT] }),
      ),
      http.delete('*/templates/:id', () => apiError(409, 'TEMPLATE_IN_USE', IN_USE)),
    );
    renderApp('/templates');
    await screen.findAllByTestId('template-card');
    const dialog = await openDeleteFor('Rahul');
    await userEvent.click(dialog.getByRole('button', { name: 'Delete' }));
    expect(await dialog.findByRole('alert')).toHaveTextContent(IN_USE);
    expect(screen.getByRole('dialog', { name: 'Delete this template?' })).toBeInTheDocument();
    expect(cardFor('Rahul')).toBeInTheDocument();
  });

  it('TT-DD37-C-N3 a network failure keeps the dialog open with an alert and the card', async () => {
    server.use(
      http.get('*/templates', () => HttpResponse.json({ templates: [template()] })),
      http.delete('*/templates/:id', () => HttpResponse.error()),
    );
    renderApp('/templates');
    await screen.findAllByTestId('template-card');
    const dialog = await openDeleteFor('Rahul');
    await userEvent.click(dialog.getByRole('button', { name: 'Delete' }));
    expect(await dialog.findByRole('alert')).toBeInTheDocument();
    expect(cardFor('Rahul')).toBeInTheDocument();
  });
});

describe('edge', () => {
  it('TT-DD37-C-E1 the Delete button is disabled while the request runs', async () => {
    serveTemplates(undefined, 300);
    renderApp('/templates');
    await screen.findAllByTestId('template-card');
    const dialog = await openDeleteFor('Rahul');
    const confirm = dialog.getByRole('button', { name: 'Delete' });
    await userEvent.click(confirm);
    expect(confirm).toBeDisabled();
    await waitFor(() => expect(screen.queryByText('Rahul')).not.toBeInTheDocument());
  });

  it('TT-DD37-C-E2 a double click on Delete sends a single DELETE', async () => {
    const store = serveTemplates(undefined, 300);
    renderApp('/templates');
    await screen.findAllByTestId('template-card');
    const dialog = await openDeleteFor('Rahul');
    await userEvent.dblClick(dialog.getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(store.deletes).toHaveLength(1));
    await waitFor(() => expect(screen.queryByText('Rahul')).not.toBeInTheDocument());
    expect(store.deletes).toEqual([IDS.template]);
  });

  it('TT-DD37-C-E3 deleting the last template shows the empty state', async () => {
    serveTemplates([template()]);
    renderApp('/templates');
    await screen.findAllByTestId('template-card');
    const dialog = await openDeleteFor('Rahul');
    await userEvent.click(dialog.getByRole('button', { name: 'Delete' }));
    expect(await screen.findByText('No templates yet')).toBeInTheDocument();
  });
});
