// D-F6-2 (DD-21): the API lives under /api. Cases: TT-UI-AC9-P3.. (client), TT-UI-AC4-P12 (links)
//
// CONTRACT (frontend/src):
//   config.ts            export API_PREFIX = '/api'
//   api/client.ts        apiFetch('/batches') requests <origin>/api/batches (every call, every
//                        method; callers keep passing paths without the prefix)
//   download links       ZIP, CSV and row-video hrefs and the player sources are <prefix> URLs
//                        (/api/batches/<id>/download.zip, /api/batches/<id>/rows/<n>/video, ...)
//   SPA routes           /templates, /batches/new, /batches/<id> stay application routes
import { screen } from '@testing-library/react';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { apiFetch } from '../../../frontend/src/api/client';
import { API_PREFIX } from '../../../frontend/src/config';
import { renderApp, setCsrfCookie, spyOnFetch } from '../helpers';
import { IDS } from '../mocks/data';
import { server } from '../mocks/server';

describe('api prefix', () => {
  it('TT-UI-AC9-P3 the prefix is /api', () => {
    expect(API_PREFIX).toBe('/api');
  });

  it('TT-UI-AC9-P4 apiFetch builds <origin>/api/<path> for GET and for state-changing calls', async () => {
    setCsrfCookie();
    const paths: string[] = [];
    server.use(
      http.get('*/batches', ({ request }) => {
        paths.push(`GET ${new URL(request.url).pathname}`);
        return HttpResponse.json({ batches: [] });
      }),
      http.post('*/batches/:id/pause', ({ request }) => {
        paths.push(`POST ${new URL(request.url).pathname}`);
        return HttpResponse.json({});
      }),
    );
    await apiFetch('/batches');
    await apiFetch('/batches/abc/pause', { method: 'POST' });
    expect(paths).toEqual(['GET /api/batches', 'POST /api/batches/abc/pause']);
  });

  it('TT-UI-AC9-E10 login goes to /api/auth/login', async () => {
    let path = '';
    server.use(
      http.post('*/auth/login', ({ request }) => {
        path = new URL(request.url).pathname;
        return HttpResponse.json({ csrf_token: 'x' });
      }),
    );
    await apiFetch('/auth/login', { method: 'POST', body: JSON.stringify({ password: 'p' }) });
    expect(path).toBe('/api/auth/login');
  });

  it('TT-UI-AC9-E11 a path is never prefixed twice', async () => {
    let path = '';
    server.use(
      http.get('*/batches', ({ request }) => {
        path = new URL(request.url).pathname;
        return HttpResponse.json({ batches: [] });
      }),
    );
    await apiFetch('/api/batches');
    expect(path).toBe('/api/batches');
  });

  it('TT-UI-AC9-P5 every request the app makes while rendering the overview is under /api', async () => {
    const spy = spyOnFetch();
    renderApp('/');
    await screen.findByTestId('current-batch');
    const pathnames = spy.urls().map((u) => new URL(u, window.location.origin).pathname);
    expect(pathnames.length).toBeGreaterThan(0);
    for (const p of pathnames) expect(p.startsWith('/api/')).toBe(true);
  });

  it('TT-UI-AC4-P12 the row video download link points under /api', async () => {
    renderApp(`/batches/${IDS.batch}`);
    const link = await screen.findByRole('link', { name: /Download video for/ });
    expect(link.getAttribute('href')).toMatch(
      new RegExp(`^/api/batches/${IDS.batch}/rows/\\d+/video$`),
    );
  });
});
