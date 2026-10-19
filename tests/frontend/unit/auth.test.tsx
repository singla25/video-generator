// UI-AC9 Auth. Cases: TT-UI-AC9-*
//
// CONTRACT (frontend/src):
//   App.tsx            export App            routes only; needs Router + QueryClientProvider above it
//   api/client.ts      export ApiError       {status, code, message, retryAfterSeconds?}
//                      export apiFetch<T>(path, init?)  absolute URL from window.location.origin,
//                        credentials 'same-origin', X-CSRF-Token (cookie vidgen_csrf) on every
//                        method except GET/HEAD, throws ApiError; never reads vidgen_session.
//   routes             /login -> LoginPage (field "Password", button "Log in", status text)
//   behaviour          any 401 UNAUTHENTICATED from the API sends the user to /login
import { act, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { ApiError, apiFetch } from '../../../frontend/src/api/client';
import { CSRF, renderApp, setCsrfCookie } from '../helpers';
import { apiError } from '../mocks/handlers';
import { server } from '../mocks/server';

describe('login screen', () => {
  it('TT-UI-AC9-P1 login with the right password posts JSON and opens the overview', async () => {
    let body: unknown;
    server.use(
      http.post('*/auth/login', async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ csrf_token: 'x' });
      }),
    );
    renderApp('/login');
    await userEvent.type(screen.getByLabelText('Password'), 'correct horse');
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Overview' })).toBeInTheDocument();
    expect(body).toEqual({ password: 'correct horse' });
  });

  it('TT-UI-AC9-N1 wrong password shows the API message and stays on login', async () => {
    server.use(
      http.post('*/auth/login', () =>
        apiError(401, 'INVALID_CREDENTIALS', 'The password is not correct.'),
      ),
    );
    renderApp('/login');
    await userEvent.type(screen.getByLabelText('Password'), 'nope');
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('The password is not correct.');
    expect(screen.getByRole('button', { name: 'Log in' })).toBeInTheDocument();
  });

  it('TT-UI-AC9-N2 a 429 shows a live countdown and disables the button until it ends', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    server.use(
      http.post('*/auth/login', () =>
        apiError(429, 'RATE_LIMITED', 'Too many attempts.', { 'Retry-After': '3' }),
      ),
    );
    renderApp('/login');
    await userEvent
      .setup({ advanceTimers: vi.advanceTimersByTime })
      .type(screen.getByLabelText('Password'), 'x');
    await userEvent
      .setup({ advanceTimers: vi.advanceTimersByTime })
      .click(screen.getByRole('button', { name: 'Log in' }));
    expect(await screen.findByText('Too many attempts, try again in 3 s')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Log in' })).toBeDisabled();
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(screen.getByText('Too many attempts, try again in 2 s')).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(2100));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Log in' })).toBeEnabled());
    expect(screen.queryByText(/Too many attempts, try again/)).not.toBeInTheDocument();
  });

  it('TT-UI-AC9-E1 a 429 without Retry-After still shows a calm message', async () => {
    server.use(
      http.post('*/auth/login', () => apiError(429, 'RATE_LIMITED', 'Too many attempts.')),
    );
    renderApp('/login');
    await userEvent.type(screen.getByLabelText('Password'), 'x');
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }));
    expect(await screen.findByText(/Too many attempts/)).toBeInTheDocument();
  });

  it('TT-UI-AC9-E2 an empty password is refused locally without a request', async () => {
    const seen = vi.fn();
    server.use(
      http.post('*/auth/login', () => {
        seen();
        return HttpResponse.json({});
      }),
    );
    renderApp('/login');
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }));
    expect(await screen.findByText('Enter the password')).toBeInTheDocument();
    expect(seen).not.toHaveBeenCalled();
  });

  it('TT-UI-AC9-E3 the password field is masked and offers no autofill of other users', () => {
    renderApp('/login');
    const field = screen.getByLabelText('Password');
    expect(field).toHaveAttribute('type', 'password');
    expect(field).toHaveAttribute('autocomplete', 'current-password');
  });

  it('TT-UI-AC9-E4 an unreachable server on login shows an error, not a crash', async () => {
    server.use(http.post('*/auth/login', () => HttpResponse.error()));
    renderApp('/login');
    await userEvent.type(screen.getByLabelText('Password'), 'x');
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not reach the server/i);
  });
});

describe('expired session', () => {
  it('TT-UI-AC9-N3 a 401 from any call leads to the login screen', async () => {
    server.use(
      http.get('*/batches', () => apiError(401, 'UNAUTHENTICATED', 'Please log in to continue.')),
    );
    renderApp('/');
    expect(await screen.findByRole('button', { name: 'Log in' })).toBeInTheDocument();
  });

  it('TT-UI-AC9-N4 a 401 while polling a batch also leads to login', async () => {
    server.use(
      http.get('*/batches/:id', () => apiError(401, 'UNAUTHENTICATED', 'Please log in.')),
      http.get('*/batches/:id/status', () => apiError(401, 'UNAUTHENTICATED', 'Please log in.')),
    );
    renderApp('/batches/11111111-1111-4111-8111-111111111111');
    expect(await screen.findByRole('button', { name: 'Log in' })).toBeInTheDocument();
  });
});

describe('api client', () => {
  it('TT-UI-AC9-P2 sends X-CSRF-Token from the cookie on every state-changing call', async () => {
    setCsrfCookie();
    const headers: Record<string, string | null> = {};
    server.use(
      http.post('*/batches/:id/pause', ({ request }) => {
        headers.post = request.headers.get('x-csrf-token');
        return HttpResponse.json({});
      }),
      http.put('*/batches/:id/mapping', ({ request }) => {
        headers.put = request.headers.get('x-csrf-token');
        return HttpResponse.json({});
      }),
      http.delete('*/batches/:id', ({ request }) => {
        headers.del = request.headers.get('x-csrf-token');
        return new HttpResponse(null, { status: 204 });
      }),
    );
    await apiFetch('/batches/a/pause', { method: 'POST' });
    await apiFetch('/batches/a/mapping', { method: 'PUT', body: JSON.stringify({}) });
    await apiFetch('/batches/a', { method: 'DELETE' });
    expect(headers).toEqual({ post: CSRF, put: CSRF, del: CSRF });
  });

  it('TT-UI-AC9-E5 GET requests do not need the CSRF header', async () => {
    let header: string | null = 'unset';
    server.use(
      http.get('*/batches', ({ request }) => {
        header = request.headers.get('x-csrf-token');
        return HttpResponse.json({ batches: [] });
      }),
    );
    await apiFetch('/batches');
    expect(header).toBeNull();
  });

  it('TT-UI-AC9-N5 error bodies become ApiError with status, code and message', async () => {
    server.use(
      http.get('*/templates', () =>
        apiError(404, 'NOT_FOUND', 'The requested item was not found.'),
      ),
    );
    await expect(apiFetch('/templates')).rejects.toMatchObject({
      status: 404,
      code: 'NOT_FOUND',
      message: 'The requested item was not found.',
    });
    await expect(apiFetch('/templates')).rejects.toBeInstanceOf(ApiError);
  });

  it('TT-UI-AC9-N6 429 exposes Retry-After as retryAfterSeconds', async () => {
    server.use(
      http.post('*/auth/login', () => apiError(429, 'RATE_LIMITED', 'x', { 'Retry-After': '42' })),
    );
    await expect(apiFetch('/auth/login', { method: 'POST' })).rejects.toMatchObject({
      status: 429,
      retryAfterSeconds: 42,
    });
  });

  it('TT-UI-AC9-E6 a non-JSON failure body gives a generic ApiError, not a parse crash', async () => {
    server.use(
      http.get('*/templates', () => new HttpResponse('<html>boom</html>', { status: 502 })),
    );
    await expect(apiFetch('/templates')).rejects.toMatchObject({
      status: 502,
      code: 'UNKNOWN_ERROR',
    });
  });

  it('TT-UI-AC9-E7 a network failure gives ApiError NETWORK_ERROR', async () => {
    server.use(http.get('*/templates', () => HttpResponse.error()));
    await expect(apiFetch('/templates')).rejects.toMatchObject({ code: 'NETWORK_ERROR' });
  });

  it('TT-UI-AC9-E8 a 204 response resolves without trying to parse a body', async () => {
    server.use(http.delete('*/batches/:id', () => new HttpResponse(null, { status: 204 })));
    setCsrfCookie();
    await expect(apiFetch('/batches/a', { method: 'DELETE' })).resolves.toBeUndefined();
  });
});
