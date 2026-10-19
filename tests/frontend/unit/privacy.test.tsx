// UI-AC12 Privacy. Cases: TT-UI-AC12-*
//
// CONTRACT: the app never writes names or IDs to localStorage/sessionStorage, only calls its own
// origin (fonts self-hosted, no CDN, no analytics) and ships no third-party branding in frontend/src.
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { renderApp, spyOnFetch } from '../helpers';
import { DEVANAGARI_NAME } from '../mocks/data';

const SECRETS = [DEVANAGARI_NAME, 'TST000001', 'Test Person 2'];

function dumpStorage(): string {
  const out: string[] = [];
  for (const store of [window.localStorage, window.sessionStorage]) {
    for (let i = 0; i < store.length; i += 1) {
      const key = store.key(i)!;
      out.push(`${key}=${store.getItem(key)}`);
    }
  }
  return out.join('\n');
}

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) return sourceFiles(full);
    return /\.(tsx?|css|html|svg)$/.test(entry) ? [full] : [];
  });
}

describe('browser storage', () => {
  it('TT-UI-AC12-P1 names and IDs are never written to local or session storage', async () => {
    renderApp('/batches/11111111-1111-4111-8111-111111111111');
    await screen.findByText(DEVANAGARI_NAME);
    await userEvent.type(
      screen.getByRole('textbox', { name: 'Search by name or ID' }),
      'TST000001',
    );
    const dump = dumpStorage();
    for (const secret of SECRETS) expect(dump).not.toContain(secret);
  });

  it('TT-UI-AC12-P2 the login password is not stored anywhere', async () => {
    renderApp('/login');
    await userEvent.type(screen.getByLabelText('Password'), 'my-secret-pass');
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }));
    await screen.findByRole('heading', { level: 1, name: 'Overview' });
    expect(dumpStorage()).not.toContain('my-secret-pass');
    expect(document.cookie).not.toContain('my-secret-pass');
  });
});

describe('network', () => {
  it('TT-UI-AC12-P3 every request goes to the same origin', async () => {
    const spy = spyOnFetch();
    renderApp('/');
    await screen.findByTestId('current-batch');
    expect(spy.urls().length).toBeGreaterThan(0);
    for (const url of spy.urls()) {
      expect(new URL(url, window.location.origin).origin).toBe(window.location.origin);
    }
  });
});

describe('source hygiene', () => {
  const root = join(process.cwd(), 'src');
  const files = sourceFiles(root);

  it('TT-UI-AC12-N1 the source tree exists and is not empty', () => {
    expect(files.length).toBeGreaterThan(0);
  });

  it('TT-UI-AC12-N2 no external http(s) URLs except XML namespaces', () => {
    const offenders: string[] = [];
    for (const f of files) {
      const text = readFileSync(f, 'utf8');
      for (const m of text.matchAll(/https?:\/\/[^\s'"`)]+/g)) {
        if (!/^https?:\/\/(www\.w3\.org|localhost|127\.0\.0\.1)/.test(m[0]))
          offenders.push(`${f}: ${m[0]}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  it('TT-UI-AC12-N3 no third-party branding or CDN font loaders', () => {
    const bad =
      /trustvest|alamin|fonts\.googleapis|fonts\.gstatic|cdn\.|googletagmanager|google-analytics/i;
    const offenders = files.filter((f) => bad.test(readFileSync(f, 'utf8')));
    expect(offenders).toEqual([]);
  });

  it('TT-UI-AC12-N4 no use of localStorage or sessionStorage for app data', () => {
    const offenders = files.filter((f) =>
      /\b(localStorage|sessionStorage)\b/.test(readFileSync(f, 'utf8')),
    );
    expect(offenders).toEqual([]);
  });
});
