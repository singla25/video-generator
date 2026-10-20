// UI-AC2 Layout and the shared shell. Cases: TT-UI-AC2-*, TT-UI-AC12-*
//
// CONTRACT (frontend/src):
//   layout/AppShell.tsx  export AppShell   sidebar <nav aria-label="Primary">, <header> (role banner),
//                        <main id="main">, "Skip to content" link, root [data-testid="app-root"]
//                        carrying data-reduced-motion="true|false"
//   routes               / Overview, /batches/running|completed|failed, /batches/new, /batches/:id,
//                        /templates, /history, /security, /settings, /help; others -> "Page not found"
//   brand                text "VidGen Studio" in the sidebar; never "TrustVest"
import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { renderApp } from '../helpers';
import { setReducedMotion } from '../motion';

const MENU = [
  ['Overview', '/'],
  ['Running', '/batches/running'],
  ['Completed', '/batches/completed'],
  ['Failed', '/batches/failed'],
  ['Templates', '/templates'],
  ['History', '/history'],
  ['Security', '/security'],
] as const;

describe('sidebar', () => {
  it('TT-UI-AC2-P1 shows the brand name and the MENU and GENERAL groups', async () => {
    renderApp('/');
    const nav = await screen.findByRole('navigation', { name: 'Primary' });
    expect(within(nav).getByText('VidGen Studio')).toBeInTheDocument();
    expect(within(nav).getByText('MENU')).toBeInTheDocument();
    expect(within(nav).getByText('GENERAL')).toBeInTheDocument();
  });

  it.each(MENU)('TT-UI-AC2-P2 menu item %s links to %s', async (label, href) => {
    renderApp('/');
    const nav = await screen.findByRole('navigation', { name: 'Primary' });
    expect(within(nav).getByRole('link', { name: label })).toHaveAttribute('href', href);
  });

  it.each([
    ['Settings', '/settings'],
    ['Help', '/help'],
  ])('TT-UI-AC2-P3 general item %s links to %s', async (label, href) => {
    renderApp('/');
    const nav = await screen.findByRole('navigation', { name: 'Primary' });
    expect(within(nav).getByRole('link', { name: label })).toHaveAttribute('href', href);
  });

  it('TT-UI-AC2-P4 Running, Completed and Failed sit under Batches', async () => {
    renderApp('/');
    const nav = await screen.findByRole('navigation', { name: 'Primary' });
    const group = within(nav).getByRole('group', { name: 'Batches' });
    for (const name of ['Running', 'Completed', 'Failed']) {
      expect(within(group).getByRole('link', { name })).toBeInTheDocument();
    }
  });

  it('TT-UI-AC2-P5 the current page link is marked aria-current', async () => {
    renderApp('/templates');
    const nav = await screen.findByRole('navigation', { name: 'Primary' });
    expect(within(nav).getByRole('link', { name: 'Templates' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(within(nav).getByRole('link', { name: 'Overview' })).not.toHaveAttribute('aria-current');
  });
});

describe('header', () => {
  it('TT-UI-AC2-P6 shows the page title, + New batch and the avatar', async () => {
    renderApp('/history');
    const header = await screen.findByRole('banner');
    expect(within(header).getByRole('heading', { level: 1, name: 'History' })).toBeInTheDocument();
    expect(within(header).getByRole('link', { name: /new batch/i })).toHaveAttribute(
      'href',
      '/batches/new',
    );
    expect(within(header).getByRole('img', { name: /account/i })).toBeInTheDocument();
  });

  it.each([
    ['/templates', 'Templates'],
    ['/security', 'Security'],
    ['/batches/new', 'New batch'],
  ])('TT-UI-AC2-P7 page title at %s is %s', async (path, title) => {
    renderApp(path);
    const header = await screen.findByRole('banner');
    expect(within(header).getByRole('heading', { level: 1 })).toHaveTextContent(title);
  });
});

describe('shell behaviour', () => {
  it('TT-UI-AC2-E1 an unknown route shows Page not found with a way home', async () => {
    renderApp('/does/not/exist');
    expect(await screen.findByText('Page not found')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /back to overview/i })).toHaveAttribute('href', '/');
  });

  it('TT-UI-AC2-E2 a skip link jumps to the main region (keyboard users)', async () => {
    renderApp('/');
    const skip = await screen.findByRole('link', { name: 'Skip to content' });
    expect(skip).toHaveAttribute('href', '#main');
    expect(document.getElementById('main')).not.toBeNull();
  });

  it('TT-UI-AC2-E3 main content is a single main landmark', async () => {
    renderApp('/');
    expect(await screen.findAllByRole('main')).toHaveLength(1);
  });

  it('TT-UI-AC10-E1 the shell exposes the reduced-motion preference', async () => {
    setReducedMotion(true);
    renderApp('/');
    expect((await screen.findByTestId('app-root')).dataset.reducedMotion).toBe('true');
  });

  it('TT-UI-AC12-N5 no TrustVest branding appears in the rendered shell', async () => {
    renderApp('/');
    await screen.findByRole('navigation', { name: 'Primary' });
    expect(document.body.textContent).not.toMatch(/trustvest/i);
    expect(document.body.innerHTML).not.toMatch(/trustvest/i);
  });
});
