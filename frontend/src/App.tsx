import { useEffect } from 'react';
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';

import { setUnauthorizedHandler } from './api/client';
import { LOGIN_PATH } from './config';
import { AppShell } from './layout/AppShell';
import { BatchDetailPage } from './pages/BatchDetailPage';
import { HistoryPage } from './pages/HistoryPage';
import { LoginPage } from './pages/LoginPage';
import { SecurityPage } from './pages/SecurityPage';
import { TemplatesPage } from './pages/TemplatesPage';
import { OverviewPage } from './pages/OverviewPage';
import { PlaceholderPage } from './pages/PlaceholderPage';
import { WizardPage } from './pages/WizardPage';

function NotFound() {
  return (
    <div className="rounded-card border bg-card p-8 text-center">
      <p className="font-semibold">Page not found</p>
      <Link to="/" className="mt-3 inline-block font-semibold text-emerald underline">
        Back to Overview
      </Link>
    </div>
  );
}

/** Any 401 from the API sends the user to the login screen. */
function useRedirectOnUnauthorized(): void {
  const navigate = useNavigate();
  const location = useLocation();
  useEffect(() => {
    setUnauthorizedHandler(() => {
      if (location.pathname !== LOGIN_PATH) navigate(LOGIN_PATH);
    });
    return () => setUnauthorizedHandler(null);
  }, [navigate, location.pathname]);
}

const IMPLEMENTED = new Set([
  '/',
  '/batches/new',
  '/batches/:id',
  '/templates',
  '/history',
  '/security',
]);

const PAGES: [string, string][] = [
  ['/', 'Overview'],
  ['/batches/running', 'Running batches'],
  ['/batches/completed', 'Completed batches'],
  ['/batches/failed', 'Failed batches'],
  ['/batches/new', 'New batch'],
  ['/batches/:id', 'Batch'],
  ['/templates', 'Templates'],
  ['/history', 'History'],
  ['/security', 'Security'],
  ['/settings', 'Settings'],
  ['/help', 'Help'],
];

/** Routes only: Router and QueryClientProvider are supplied by the caller. */
export function App() {
  useRedirectOnUnauthorized();
  return (
    <Routes>
      <Route path={LOGIN_PATH} element={<LoginPage />} />
      <Route element={<AppShell />}>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/batches/new" element={<WizardPage />} />
        <Route path="/batches/:id" element={<BatchDetailPage />} />
        <Route path="/templates" element={<TemplatesPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/security" element={<SecurityPage />} />
        {PAGES.filter(([path]) => !IMPLEMENTED.has(path)).map(([path, name]) => (
          <Route key={path} path={path} element={<PlaceholderPage name={name} />} />
        ))}
        <Route path="*" element={<NotFound />} />
      </Route>
      <Route path="/index.html" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
