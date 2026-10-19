// Playwright skeletons for the M3 dashboard. They run only when E2E_BASE_URL points at a stack
// (frontend + real API with a seeded test admin). Env: E2E_ADMIN_PASSWORD (test password only).
// Cases: TT-UI-E2E-*  (projects desktop / reduced-motion / tablet come from playwright.config.ts)
import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

test.skip(!process.env.E2E_BASE_URL, 'set E2E_BASE_URL to run the dashboard E2E tests');

const PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? 'test-password-only';
const EXTERNAL = /^https?:\/\/(?!(127\.0\.0\.1|localhost)(:\d+)?\/)/;

async function login(page: Page): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Log in' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Overview' })).toBeVisible();
}

test('TT-UI-E2E-P1 main flow: login, overview, wizard entry, templates, history, security', async ({
  page,
}) => {
  await login(page);
  await expect(page.getByRole('navigation', { name: 'Primary' })).toContainText('VidGen Studio');
  await page
    .getByRole('banner')
    .getByRole('link', { name: /new batch/i })
    .click();
  await expect(page.getByRole('list', { name: 'Steps' })).toBeVisible();
  for (const [link, title] of [
    ['Templates', 'Templates'],
    ['History', 'History'],
    ['Security', 'Security'],
  ] as const) {
    await page
      .getByRole('navigation', { name: 'Primary' })
      .getByRole('link', { name: link })
      .click();
    await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible();
  }
});

test('TT-UI-E2E-N1 wrong password shows the error and stays on login', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Password').fill('definitely-wrong');
  await page.getByRole('button', { name: 'Log in' }).click();
  await expect(page.getByRole('alert')).toContainText('not correct');
});

test('TT-UI-E2E-N2 an unauthenticated visit is sent to login', async ({ page }) => {
  await page.goto('/templates');
  await expect(page.getByRole('button', { name: 'Log in' })).toBeVisible();
});

test('TT-UI-E2E-E1 tablet width keeps the header action and navigation usable', async ({
  page,
}, info) => {
  test.skip(info.project.name !== 'tablet', 'tablet project only');
  await login(page);
  await expect(page.getByRole('banner').getByRole('link', { name: /new batch/i })).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  );
  expect(overflow).toBe(false);
});

test('TT-UI-E2E-E2 reduced motion: no running CSS animations or transitions on the overview', async ({
  page,
}, info) => {
  test.skip(info.project.name !== 'reduced-motion', 'reduced-motion project only');
  await login(page);
  await page.getByTestId('kpi-total').waitFor();
  const running = await page.evaluate(
    () => document.getAnimations().filter((a) => a.playState === 'running').length,
  );
  expect(running).toBe(0);
});

test('TT-UI-E2E-E3 keyboard: Tab reaches the skip link first, Enter moves focus to main', async ({
  page,
}) => {
  await login(page);
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to content' })).toBeFocused();
});

test('TT-UI-E2E-E4 Devanagari text is not tofu: the Noto Sans Devanagari face is loaded locally', async ({
  page,
}) => {
  await login(page);
  const loaded = await page.evaluate(async () => {
    await document.fonts.ready;
    return [...document.fonts].some(
      (f) => /Noto Sans Devanagari/i.test(f.family) && f.status === 'loaded',
    );
  });
  expect(loaded).toBe(true);
});

test('TT-UI-E2E-E5 no request leaves the local origin', async ({ page }) => {
  const external: string[] = [];
  page.on('request', (r) => {
    if (EXTERNAL.test(r.url()) && !r.url().startsWith(process.env.E2E_BASE_URL ?? ''))
      external.push(r.url());
  });
  await login(page);
  await page
    .getByRole('navigation', { name: 'Primary' })
    .getByRole('link', { name: 'Templates' })
    .click();
  await page.waitForLoadState('networkidle');
  expect(external).toEqual([]);
});

for (const path of ['/', '/templates', '/history', '/security', '/batches/new']) {
  test(`TT-UI-E2E-A1 axe: no serious or critical violations on ${path}`, async ({ page }) => {
    await login(page);
    await page.goto(path);
    await page.waitForLoadState('networkidle');
    const results = await new AxeBuilder({ page }).analyze();
    const bad = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
    expect(bad.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
  });
}
