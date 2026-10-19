// UI-AC7 Templates, UI-AC8 History and Security. Cases: TT-UI-AC7-*, TT-UI-AC8-*
//
// CONTRACT (frontend/src):
//   pages/TemplatesPage.tsx  route /templates
//     [data-testid=template-card] per template: original name, "Slot 4.2 s - 5.1 s" (or "No slot yet"),
//       consent badge [data-testid=consent-badge] with text "Consent confirmed" | "Consent missing",
//       usable state text "Ready to use" | "Not usable", a placeholder icon [data-testid=template-thumb-placeholder] (no thumbnail endpoint; no <img>).
//       Missing consent -> button "Upload consent" opens a form: file input "Consent file", checkbox
//       "I confirm I have consent to use this video", button "Submit consent" (disabled until both)
//       -> POST /templates/<id>/consent multipart {file, confirmed:"true"}
//     empty "No templates yet", error role=alert "Could not load templates"
//   pages/HistoryPage.tsx    route /history  table: Date, Batch (sheet name), Template, Total, Success
//       rate "80 %" (null -> "-"), each row links to /batches/<id>; paging like RowsTable
//       empty "No past batches yet", error role=alert
//   pages/SecurityPage.tsx   route /security  audit table (Time, Actor, Event) one row per entry with
//       data-action="<CODE>"; combobox "Event" filter (All + codes present) -> GET /audit?action=CODE;
//       empty "No security events", error role=alert
//   Security alert banner    in AppShell on every page: [data-testid=security-banner] role=alert
//       "Repeated failed logins were blocked" + link "Review in Security" when /audit?action=
//       SECURITY_LOGIN_THROTTLED returns an entry; absent otherwise (and absent if the audit call fails)
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { renderApp } from '../helpers';
import { IDS, TEMPLATE_NO_CONSENT, auditEntry, batch, template } from '../mocks/data';
import { apiError } from '../mocks/handlers';
import { server } from '../mocks/server';

describe('templates', () => {
  it('TT-UI-AC7-P1 a consented template shows name, slot, badge and Ready to use', async () => {
    renderApp('/templates');
    const cards = await screen.findAllByTestId('template-card');
    const rahul = cards.find((c) => within(c).queryByText('Rahul'))!;
    expect(within(rahul).getByTestId('consent-badge')).toHaveTextContent('Consent confirmed');
    expect(rahul).toHaveTextContent('Slot 4.2 s - 5.1 s');
    expect(rahul).toHaveTextContent('Ready to use');
    expect(within(rahul).getByTestId('template-thumb-placeholder')).toBeInTheDocument();
    expect(rahul.querySelector('img')).toBeNull();
  });

  it('TT-UI-AC7-N1 missing consent shows the badge, Not usable and no use action', async () => {
    renderApp('/templates');
    const cards = await screen.findAllByTestId('template-card');
    const priya = cards.find((c) => within(c).queryByText('Priya'))!;
    expect(within(priya).getByTestId('consent-badge')).toHaveTextContent('Consent missing');
    expect(priya).toHaveTextContent('Not usable');
    expect(within(priya).getByRole('button', { name: 'Upload consent' })).toBeInTheDocument();
  });

  it('TT-UI-AC7-P2 consent upload needs a file and the tick, then posts multipart', async () => {
    let seen: Record<string, string> = {};
    server.use(
      http.post('*/templates/:id/consent', async ({ request, params }) => {
        const form = await request.formData();
        seen = {
          id: String(params.id),
          confirmed: String(form.get('confirmed')),
          file: form.get('file') instanceof File ? 'file' : 'none',
        };
        return HttpResponse.json(template({ id: IDS.templateNoConsent, original_name: 'Priya' }));
      }),
    );
    renderApp('/templates');
    const cards = await screen.findAllByTestId('template-card');
    const priya = cards.find((c) => within(c).queryByText('Priya'))!;
    await userEvent.click(within(priya).getByRole('button', { name: 'Upload consent' }));
    const submit = screen.getByRole('button', { name: 'Submit consent' });
    expect(submit).toBeDisabled();
    await userEvent.upload(
      screen.getByLabelText('Consent file'),
      new File(['x'], 'consent.pdf', { type: 'application/pdf' }),
      { applyAccept: false },
    );
    expect(submit).toBeDisabled();
    await userEvent.click(
      screen.getByRole('checkbox', { name: 'I confirm I have consent to use this video' }),
    );
    expect(submit).toBeEnabled();
    await userEvent.click(submit);
    await waitFor(() =>
      expect(seen).toEqual({ id: IDS.templateNoConsent, confirmed: 'true', file: 'file' }),
    );
  });

  it('TT-UI-AC7-N2 an invalid consent file shows the API message and the badge stays missing', async () => {
    server.use(
      http.post('*/templates/:id/consent', () =>
        apiError(
          422,
          'CONSENT_FILE_INVALID',
          'The consent file could not be used. Upload a PDF or image.',
        ),
      ),
    );
    renderApp('/templates');
    const cards = await screen.findAllByTestId('template-card');
    const priya = cards.find((c) => within(c).queryByText('Priya'))!;
    await userEvent.click(within(priya).getByRole('button', { name: 'Upload consent' }));
    await userEvent.upload(screen.getByLabelText('Consent file'), new File(['x'], 'c.pdf'), {
      applyAccept: false,
    });
    await userEvent.click(
      screen.getByRole('checkbox', { name: 'I confirm I have consent to use this video' }),
    );
    await userEvent.click(screen.getByRole('button', { name: 'Submit consent' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('could not be used');
    expect(within(priya).getByTestId('consent-badge')).toHaveTextContent('Consent missing');
  });

  it('TT-UI-AC7-E1 a template without a slot says No slot yet', async () => {
    server.use(
      http.get('*/templates', () =>
        HttpResponse.json({ templates: [template({ slot: null, needs_manual_slot: true })] }),
      ),
    );
    renderApp('/templates');
    expect(await screen.findByText('No slot yet')).toBeInTheDocument();
  });

  it('TT-UI-AC7-E2 no templates shows the empty state', async () => {
    server.use(http.get('*/templates', () => HttpResponse.json({ templates: [] })));
    renderApp('/templates');
    expect(await screen.findByText('No templates yet')).toBeInTheDocument();
  });

  it('TT-UI-AC7-E3 an API failure shows an error state', async () => {
    server.use(http.get('*/templates', () => HttpResponse.error()));
    renderApp('/templates');
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load templates');
  });

  it('TT-UI-AC7-E4 a Devanagari original name is shown intact with lang=hi', async () => {
    server.use(
      http.get('*/templates', () =>
        HttpResponse.json({
          templates: [template({ original_name: 'राहुल' }), TEMPLATE_NO_CONSENT],
        }),
      ),
    );
    renderApp('/templates');
    expect((await screen.findByText('राहुल')).closest('[lang]')).toHaveAttribute('lang', 'hi');
  });
});

describe('history', () => {
  const list = (batches: unknown[], total = batches.length) =>
    http.get('*/batches', () =>
      HttpResponse.json({ batches, page: 1, page_size: 50, total, total_pages: 1 }),
    );

  it('TT-UI-AC8-P1 lists past batches with date, totals and success rate', async () => {
    server.use(list([batch({ status: 'COMPLETED', success_rate: 0.8 })]));
    renderApp('/history');
    const row = (await screen.findAllByRole('row'))[1]!;
    expect(row).toHaveTextContent('sheet-a.csv');
    expect(row).toHaveTextContent('100');
    expect(row).toHaveTextContent('80 %');
    expect(within(row).getByRole('link')).toHaveAttribute('href', `/batches/${IDS.batch}`);
  });

  it('TT-UI-AC8-E1 a null success rate (no finished rows) shows a dash', async () => {
    server.use(list([batch({ status: 'DRAFT', success_rate: null })]));
    renderApp('/history');
    const row = (await screen.findAllByRole('row'))[1]!;
    expect(row).toHaveTextContent('-');
    expect(row.textContent).not.toMatch(/NaN|null/);
  });

  it('TT-UI-AC8-E2 no batches shows the empty state', async () => {
    server.use(list([]));
    renderApp('/history');
    expect(await screen.findByText('No past batches yet')).toBeInTheDocument();
  });

  it('TT-UI-AC8-N1 an API failure shows an error state', async () => {
    server.use(
      http.get('*/batches', () => apiError(500, 'INTERNAL_ERROR', 'Something went wrong.')),
    );
    renderApp('/history');
    expect(await screen.findByRole('alert')).toBeInTheDocument();
  });
});

describe('security log and alert banner', () => {
  function audit(entries: Record<string, unknown>[]) {
    return http.get('*/audit', ({ request }) => {
      const action = new URL(request.url).searchParams.get('action');
      return HttpResponse.json({
        entries: action ? entries.filter((e) => e.action === action) : entries,
      });
    });
  }

  it('TT-UI-AC8-P2 shows the audit entries', async () => {
    server.use(audit([auditEntry('LOGIN_SUCCEEDED'), auditEntry('LOGIN_FAILED')]));
    renderApp('/security');
    await screen.findAllByRole('row');
    await waitFor(() => expect(document.querySelectorAll('[data-action]')).toHaveLength(2));
  });

  it('TT-UI-AC8-P3 the Event filter requests only that action', async () => {
    const asked: (string | null)[] = [];
    server.use(
      http.get('*/audit', ({ request }) => {
        asked.push(new URL(request.url).searchParams.get('action'));
        return HttpResponse.json({ entries: [auditEntry('LOGIN_FAILED')] });
      }),
    );
    renderApp('/security');
    await userEvent.selectOptions(
      await screen.findByRole('combobox', { name: 'Event' }),
      'LOGIN_FAILED',
    );
    await waitFor(() => expect(asked).toContain('LOGIN_FAILED'));
  });

  it('TT-UI-AC8-P4 a throttled-login event shows the alert banner on every page', async () => {
    server.use(audit([auditEntry('SECURITY_LOGIN_THROTTLED')]));
    renderApp('/');
    const banner = await screen.findByTestId('security-banner');
    expect(banner).toHaveAttribute('role', 'alert');
    expect(banner).toHaveTextContent('Repeated failed logins were blocked');
    expect(within(banner).getByRole('link', { name: 'Review in Security' })).toHaveAttribute(
      'href',
      '/security',
    );
  });

  it('TT-UI-AC8-N2 no throttle event means no banner', async () => {
    server.use(audit([auditEntry('LOGIN_FAILED')]));
    renderApp('/templates');
    await screen.findAllByTestId('template-card');
    expect(screen.queryByTestId('security-banner')).not.toBeInTheDocument();
  });

  it('TT-UI-AC8-E3 if the audit call fails the page still works without a banner', async () => {
    server.use(http.get('*/audit', () => HttpResponse.error()));
    renderApp('/templates');
    expect((await screen.findAllByTestId('template-card')).length).toBeGreaterThan(0);
    expect(screen.queryByTestId('security-banner')).not.toBeInTheDocument();
  });

  it('TT-UI-AC8-E4 an empty audit log shows the empty state', async () => {
    renderApp('/security');
    expect(await screen.findByText('No security events')).toBeInTheDocument();
  });
});
