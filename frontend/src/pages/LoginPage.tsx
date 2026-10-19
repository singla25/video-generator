import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';

import { ApiError, apiFetch } from '../api/client';
import logo from '../assets/logo.svg';

type Problem = { kind: 'error'; text: string } | { kind: 'wait'; until: number } | null;

const TICK_MS = 200;

/** Password login screen with a live countdown after a rate-limit response. */
export function LoginPage() {
  const navigate = useNavigate();
  const [password, setPassword] = useState('');
  const [problem, setProblem] = useState<Problem>(null);
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const until = problem?.kind === 'wait' ? problem.until : 0;
  const waiting = Math.max(0, Math.ceil((until - now) / 1000));

  useEffect(() => {
    if (!until) return;
    const timer = setInterval(() => {
      const current = Date.now();
      setNow(current);
      if (current >= until) setProblem(null);
    }, TICK_MS);
    return () => clearInterval(timer);
  }, [until]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!password) {
      setProblem({ kind: 'error', text: 'Enter the password' });
      return;
    }
    setBusy(true);
    setProblem(null);
    try {
      await apiFetch('/auth/login', { method: 'POST', body: JSON.stringify({ password }) });
      setPassword('');
      navigate('/');
    } catch (error) {
      if (error instanceof ApiError && error.status === 429 && error.retryAfterSeconds) {
        setNow(Date.now());
        setProblem({ kind: 'wait', until: Date.now() + error.retryAfterSeconds * 1000 });
      } else if (error instanceof ApiError && error.status === 429) {
        setProblem({ kind: 'error', text: 'Too many attempts, please wait a moment.' });
      } else {
        const text = error instanceof ApiError ? error.message : 'Something went wrong.';
        setProblem({ kind: 'error', text });
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center p-4">
      <form
        onSubmit={submit}
        noValidate
        className="w-full max-w-sm rounded-card border bg-card p-8"
      >
        <div className="mb-6 flex items-center gap-2">
          <img src={logo} alt="" className="size-8" />
          <h1 className="text-xl font-bold">VidGen Studio</h1>
        </div>
        <label htmlFor="password" className="mb-1 block text-sm font-semibold">
          Password
        </label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded-tile border px-3 py-2"
        />
        {problem?.kind === 'error' && (
          <p role="alert" className="mt-3 text-sm text-status-failed">
            {problem.text}
          </p>
        )}
        {problem?.kind === 'wait' && (
          <p role="status" className="mt-3 text-sm text-status-failed">
            Too many attempts, try again in {waiting} s
          </p>
        )}
        <button
          type="submit"
          disabled={busy || waiting > 0}
          className="mt-5 w-full rounded-full bg-lime px-4 py-2 font-semibold disabled:opacity-50"
        >
          Log in
        </button>
      </form>
    </main>
  );
}
