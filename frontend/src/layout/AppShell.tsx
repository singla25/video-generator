import {
  CircleCheck,
  CircleHelp,
  CircleX,
  FileClock,
  Film,
  LayoutDashboard,
  type LucideIcon,
  Play,
  Plus,
  Settings,
  ShieldCheck,
  User,
} from 'lucide-react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';

import logo from '../assets/logo.svg';
import { useReducedMotion } from '../hooks';
import { SecurityBanner } from './SecurityBanner';

interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
  end?: boolean;
}

const MENU: NavItem[] = [{ label: 'Overview', to: '/', icon: LayoutDashboard, end: true }];
const BATCHES: NavItem[] = [
  { label: 'Running', to: '/batches/running', icon: Play },
  { label: 'Completed', to: '/batches/completed', icon: CircleCheck },
  { label: 'Failed', to: '/batches/failed', icon: CircleX },
];
const MENU_AFTER: NavItem[] = [
  { label: 'Templates', to: '/templates', icon: Film },
  { label: 'History', to: '/history', icon: FileClock },
  { label: 'Security', to: '/security', icon: ShieldCheck },
];
const GENERAL: NavItem[] = [
  { label: 'Settings', to: '/settings', icon: Settings },
  { label: 'Help', to: '/help', icon: CircleHelp },
];

const TITLES: Record<string, string> = {
  '/': 'Overview',
  '/batches/running': 'Running batches',
  '/batches/completed': 'Completed batches',
  '/batches/failed': 'Failed batches',
  '/batches/new': 'New batch',
  '/templates': 'Templates',
  '/history': 'History',
  '/security': 'Security',
  '/settings': 'Settings',
  '/help': 'Help',
};

function titleFor(pathname: string): string {
  const path = pathname.length > 1 ? pathname.replace(/\/$/, '') : pathname;
  if (TITLES[path]) return TITLES[path];
  return /^\/batches\/[^/]+$/.test(path) ? 'Batch' : 'Not found';
}

function SideLink({ item }: { item: NavItem }) {
  const Icon = item.icon;
  return (
    <NavLink
      to={item.to}
      end={item.end}
      className={({ isActive }) =>
        `flex items-center gap-3 rounded-tile px-3 py-2 text-sm font-medium hover:bg-mint ${
          isActive ? 'bg-mint text-emerald' : 'text-muted'
        }`
      }
    >
      <Icon aria-hidden="true" strokeWidth={1.5} className="size-5" />
      {item.label}
    </NavLink>
  );
}

function GroupLabel({ children }: { children: string }) {
  return (
    <p className="px-3 pb-1 pt-4 text-xs font-semibold tracking-wider text-muted">{children}</p>
  );
}

/** Page frame: sidebar, header with title and actions, and the main region. */
export function AppShell() {
  const { pathname } = useLocation();
  const reduced = useReducedMotion();
  return (
    <div data-testid="app-root" data-reduced-motion={String(reduced)} className="flex min-h-screen">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-10 focus:rounded-tile focus:bg-card focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <nav aria-label="Primary" className="w-60 shrink-0 border-r bg-card p-4">
        <div className="mb-4 flex items-center gap-2 px-3">
          <img src={logo} alt="" className="size-8" />
          <span className="font-bold">VidGen Studio</span>
        </div>
        <GroupLabel>MENU</GroupLabel>
        {MENU.map((item) => (
          <SideLink key={item.to} item={item} />
        ))}
        <div role="group" aria-label="Batches" className="my-1">
          <p className="px-3 pt-2 text-xs font-semibold text-muted">Batches</p>
          {BATCHES.map((item) => (
            <SideLink key={item.to} item={item} />
          ))}
        </div>
        {MENU_AFTER.map((item) => (
          <SideLink key={item.to} item={item} />
        ))}
        <GroupLabel>GENERAL</GroupLabel>
        {GENERAL.map((item) => (
          <SideLink key={item.to} item={item} />
        ))}
      </nav>
      <div className="min-w-0 flex-1">
        <header className="flex items-center gap-3 border-b bg-card px-6 py-4">
          <h1 className="text-xl font-bold">{titleFor(pathname)}</h1>
          <NavLink
            to="/batches/new"
            className="ml-auto inline-flex items-center gap-1.5 rounded-full bg-lime px-4 py-2 text-sm font-semibold"
          >
            <Plus aria-hidden="true" strokeWidth={1.5} className="size-4" />
            New batch
          </NavLink>
          <div
            role="img"
            aria-label="Account"
            className="grid size-9 place-items-center rounded-full bg-mint text-emerald"
          >
            <User aria-hidden="true" strokeWidth={1.5} className="size-5" />
          </div>
        </header>
        <main id="main" className="p-6">
          <SecurityBanner />
          <Outlet />
        </main>
      </div>
    </div>
  );
}
