// Wizard preview progress, slow warning and fake-AI note. Case IDs: TT-PP-<P|N|E><n>.
// Contract is also written in docs/test-tree/preview-progress-ui.md.
//
// CONTRACT (frontend/src, PreviewPanel in pages/wizard):
//   API     batch.preview.stage: "preparing" | "voice" | "lipsync" | "finishing" | null (optional).
//           GET /system/status -> ai_mode "fake" | "local" (absent on older servers).
//   Steps   while preview.status is PENDING: <ol role="list" aria-label="Preview progress"> with
//           four items whose text is exactly "Preparing", "Speaking the name", "Matching the lips",
//           "Finishing". Items before the current stage: data-state="done"; the current one:
//           aria-current="step" and data-state="current"; later ones: data-state="todo".
//           stage null (or missing) while pending -> "Preparing" is current. Not shown for
//           READY, FAILED, NONE, STALE or no preview.
//   Local   ai_mode "local" and PENDING: role="note" "First run after a restart is slow, a few
//           minutes. The AI models are loading."
//   Slow    PENDING for 30 s (fake mode, unchanged) or 180 s (local mode): "Preview is taking longer
//           than expected." plus a Retry button. Local mode at 31 s must not show it.
//   Fake    ai_mode "fake": role="note" "Fake AI is on: the video will have a beep instead of the
//           name." inside the Preview panel, in every preview state. Not in local mode, not while
//           the status call loads, not when it fails.
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { POLL_INTERVAL_MS } from '../../../frontend/src/config';
import { renderApp } from '../helpers';
import { IDS, batch, report } from '../mocks/data';
import { server } from '../mocks/server';

type Json = Record<string, unknown>;

const LIST_NAME = 'Preview progress';
const STEP_TEXTS = ['Preparing', 'Speaking the name', 'Matching the lips', 'Finishing'];
const LOCAL_NOTE = 'First run after a restart is slow, a few minutes. The AI models are loading.';
const FAKE_NOTE = 'Fake AI is on: the video will have a beep instead of the name.';
const SLOW_TEXT = /Preview is taking longer than expected\./;
const RETRY = 'Retry';
const FAKE_SLOW_MS = 30_000;
const LOCAL_SLOW_MS = 180_000;
const WIZARD_PATH = `/batches/new?batch=${IDS.batch}`;
const FAKE_BADGE = 'Fake AI: a beep stands in for the name until real AI is on';

/** Mutable server state: handlers read it on every request, so a test can change it mid-flight. */
interface Scene {
  preview: Json | undefined;
  aiMode: string | undefined;
  statusFault: 'http' | 'network' | undefined;
  statusGate: Promise<void> | undefined;
}

/** Register the status and batch handlers for the wizard resume page (a DRAFT with valid rows). */
function serve(over: Partial<Scene> = {}): Scene {
  const scene: Scene = {
    preview: undefined,
    aiMode: undefined,
    statusFault: undefined,
    statusGate: undefined,
    ...over,
  };
  server.use(
    http.get('*/system/status', async () => {
      if (scene.statusGate) await scene.statusGate;
      if (scene.statusFault === 'network') return HttpResponse.error();
      if (scene.statusFault === 'http') {
        return HttpResponse.json({ code: 'INTERNAL_ERROR', message: 'Down.' }, { status: 500 });
      }
      const aiField = scene.aiMode === undefined ? {} : { ai_mode: scene.aiMode };
      return HttpResponse.json({ worker_alive: true, queue_depth: 0, redis_ok: true, ...aiField });
    }),
    http.get('*/batches/:id', () =>
      HttpResponse.json(
        batch({ status: 'DRAFT', report: report({ valid_rows: 8 }), preview: scene.preview }),
      ),
    ),
  );
  return scene;
}

function preview(status: string, over: Json = {}): Json {
  return { status, approved: false, ...over };
}

async function openWizard(): Promise<void> {
  renderApp(WIZARD_PATH);
  await screen.findByRole('button', { name: 'Generate preview' });
}

/** Advance the fake clock; wrapped in act so React flushes the resulting renders. */
async function advance(ms: number): Promise<void> {
  await act(() => vi.advanceTimersByTimeAsync(ms));
}

function stepItems(): HTMLElement[] {
  const list = screen.getByRole('list', { name: LIST_NAME });
  return within(list).getAllByRole('listitem');
}

function progressList(): HTMLElement | null {
  return screen.queryByRole('list', { name: LIST_NAME });
}

/** Text of every role="note" element on the page. */
function noteTexts(): string[] {
  return screen.queryAllByRole('note').map((note) => note.textContent ?? '');
}

function slowMessage() {
  return screen.queryByText(SLOW_TEXT);
}

function retryButton() {
  return screen.queryByRole('button', { name: RETRY });
}

interface TimerLog {
  scheduled: { delay: unknown; id: unknown }[];
  cleared: unknown[];
}

/**
 * Log every setTimeout / clearTimeout call made while active. Replaces the globals by hand and
 * restores the originals by reference: a vi.spyOn on fake timers leaves the fake clock behind.
 */
function recordTimers(): { log: TimerLog; restore: () => void } {
  const setOriginal = globalThis.setTimeout;
  const clearOriginal = globalThis.clearTimeout;
  const log: TimerLog = { scheduled: [], cleared: [] };
  globalThis.setTimeout = ((...args: unknown[]) => {
    const id = (setOriginal as unknown as (...a: unknown[]) => unknown)(...args);
    log.scheduled.push({ delay: args[1], id });
    return id;
  }) as typeof setTimeout;
  globalThis.clearTimeout = ((id?: unknown) => {
    log.cleared.push(id);
    (clearOriginal as unknown as (id?: unknown) => void)(id);
  }) as typeof clearTimeout;
  return {
    log,
    restore: () => {
      globalThis.setTimeout = setOriginal;
      globalThis.clearTimeout = clearOriginal;
    },
  };
}

/** Expected data-state of each step when `current` is the index of the active step. */
function expectedStates(current: number): string[] {
  return STEP_TEXTS.map((_, i) => (i < current ? 'done' : i === current ? 'current' : 'todo'));
}

function actualStates(): string[] {
  return stepItems().map((item) => item.getAttribute('data-state') ?? '');
}

describe('progress list while pending', () => {
  it('TT-PP-P1 shows an ordered list labelled "Preview progress" with the four step texts', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    serve({ preview: preview('PENDING', { stage: 'preparing' }) });
    await openWizard();
    const list = screen.getByRole('list', { name: LIST_NAME });
    expect(list).toBeInTheDocument();
    expect(stepItems().map((item) => item.textContent)).toEqual(STEP_TEXTS);
  });

  it.each([
    ['preparing', 0],
    ['voice', 1],
    ['lipsync', 2],
    ['finishing', 3],
  ])(
    'TT-PP-P2 stage %s marks earlier steps done, that step current and later ones todo',
    async (stage, current) => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      serve({ preview: preview('PENDING', { stage }) });
      await openWizard();
      expect(actualStates()).toEqual(expectedStates(current));
      stepItems().forEach((item, i) => {
        if (i === current) {
          expect(item).toHaveAttribute('aria-current', 'step');
        } else {
          expect(item).not.toHaveAttribute('aria-current');
        }
      });
    },
  );

  it('TT-PP-P3 the step follows the stage as polling reports new values, then the list goes away on READY', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const scene = serve({ preview: preview('PENDING', { stage: 'preparing' }) });
    await openWizard();
    expect(actualStates()).toEqual(expectedStates(0));

    scene.preview = preview('PENDING', { stage: 'voice' });
    await advance(POLL_INTERVAL_MS + 100);
    await waitFor(() => expect(actualStates()).toEqual(expectedStates(1)));

    scene.preview = preview('PENDING', { stage: 'lipsync' });
    await advance(POLL_INTERVAL_MS + 100);
    await waitFor(() => expect(actualStates()).toEqual(expectedStates(2)));

    scene.preview = preview('PENDING', { stage: 'finishing' });
    await advance(POLL_INTERVAL_MS + 100);
    await waitFor(() => expect(actualStates()).toEqual(expectedStates(3)));

    scene.preview = preview('READY', { stage: 'finishing' });
    await advance(POLL_INTERVAL_MS + 100);
    await waitFor(() => expect(progressList()).not.toBeInTheDocument());
  });

  it.each([
    ['null', { stage: null }],
    ['missing', {}],
  ])(
    'TT-PP-E1 a %s stage while pending makes Preparing the current step',
    async (_label, extra) => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      serve({ preview: preview('PENDING', extra) });
      await openWizard();
      expect(actualStates()).toEqual(expectedStates(0));
      expect(stepItems()[0]).toHaveAttribute('aria-current', 'step');
    },
  );

  it.each(['rendering', ''])(
    'TT-PP-E2 an unknown stage (%j) does not crash and still shows the four steps',
    async (stage) => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      serve({ preview: preview('PENDING', { stage }) });
      await openWizard();
      expect(stepItems().map((item) => item.textContent)).toEqual(STEP_TEXTS);
      expect(screen.getByText('Generating preview...')).toBeInTheDocument();
      const current = stepItems().filter((item) => item.hasAttribute('aria-current'));
      expect(current.length).toBeLessThanOrEqual(1);
    },
  );

  it.each([
    ['fake', 'fake'],
    ['local', 'local'],
    ['older server (no ai_mode)', undefined],
  ])('TT-PP-E3 the list is shown the same way in %s mode', async (_label, aiMode) => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    serve({ aiMode, preview: preview('PENDING', { stage: 'voice' }) });
    await openWizard();
    expect(actualStates()).toEqual(expectedStates(1));
  });

  it.each([
    ['READY', { status: 'READY', approved: false, stage: 'finishing' }],
    ['READY and approved', { status: 'READY', approved: true, stage: 'finishing' }],
    ['FAILED', { status: 'FAILED', approved: false, stage: 'voice' }],
    ['STALE', { status: 'STALE', approved: false, stage: 'lipsync' }],
    ['NONE', { status: 'NONE', approved: false, stage: 'preparing' }],
    ['no preview at all', undefined],
  ])('TT-PP-N1 no progress list when the preview is %s', async (_label, value) => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    serve({ preview: value });
    await openWizard();
    expect(progressList()).not.toBeInTheDocument();
    expect(screen.queryByText('Generating preview...')).not.toBeInTheDocument();
  });
});

describe('local-mode first-run note', () => {
  it('TT-PP-P4 local mode while pending shows the first-run note as role="note"', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    serve({ aiMode: 'local', preview: preview('PENDING', { stage: 'preparing' }) });
    await openWizard();
    expect(noteTexts()).toContain(LOCAL_NOTE);
  });

  it('TT-PP-N2 fake mode while pending does not show the local note', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    serve({ aiMode: 'fake', preview: preview('PENDING', { stage: 'preparing' }) });
    await openWizard();
    expect(noteTexts()).not.toContain(LOCAL_NOTE);
  });

  it.each([
    ['READY', preview('READY')],
    ['FAILED', preview('FAILED')],
    ['NONE', preview('NONE')],
    ['no preview at all', undefined],
  ])('TT-PP-N3 local mode with a %s preview shows no first-run note', async (_label, value) => {
    serve({ aiMode: 'local', preview: value });
    await openWizard();
    expect(noteTexts()).not.toContain(LOCAL_NOTE);
  });

  it('TT-PP-N4 an older server without ai_mode shows no first-run note', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    serve({ aiMode: undefined, preview: preview('PENDING', { stage: 'voice' }) });
    await openWizard();
    expect(noteTexts()).not.toContain(LOCAL_NOTE);
  });

  it('TT-PP-E4 the local note disappears when the preview turns READY', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const scene = serve({ aiMode: 'local', preview: preview('PENDING', { stage: 'lipsync' }) });
    await openWizard();
    expect(noteTexts()).toContain(LOCAL_NOTE);
    scene.preview = preview('READY');
    await advance(POLL_INTERVAL_MS + 100);
    await waitFor(() => expect(noteTexts()).not.toContain(LOCAL_NOTE));
  });
});

describe('slow warning', () => {
  it('TT-PP-N5 fake mode shows nothing before 30 s pending', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    serve({ aiMode: 'fake', preview: preview('PENDING', { stage: 'voice' }) });
    await openWizard();
    await advance(29_000);
    expect(slowMessage()).not.toBeInTheDocument();
    expect(retryButton()).not.toBeInTheDocument();
  });

  it('TT-PP-P5 fake mode after 31 s pending shows the warning and Retry (unchanged)', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    serve({ aiMode: 'fake', preview: preview('PENDING', { stage: 'voice' }) });
    await openWizard();
    await advance(31_000);
    expect(await screen.findByText(SLOW_TEXT)).toBeInTheDocument();
    expect(retryButton()).toBeEnabled();
  });

  it('TT-PP-N6 local mode at 31 s pending does not show the warning yet', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    serve({ aiMode: 'local', preview: preview('PENDING', { stage: 'voice' }) });
    await openWizard();
    await advance(31_000);
    expect(slowMessage()).not.toBeInTheDocument();
    expect(retryButton()).not.toBeInTheDocument();
  });

  it('TT-PP-N7 local mode at 179 s pending still shows no warning', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    serve({ aiMode: 'local', preview: preview('PENDING', { stage: 'lipsync' }) });
    await openWizard();
    await advance(179_000);
    expect(slowMessage()).not.toBeInTheDocument();
    expect(retryButton()).not.toBeInTheDocument();
  });

  it('TT-PP-P6 local mode at 180 s pending shows the warning and Retry', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    serve({ aiMode: 'local', preview: preview('PENDING', { stage: 'lipsync' }) });
    await openWizard();
    await advance(LOCAL_SLOW_MS + 500);
    expect(await screen.findByText(SLOW_TEXT)).toBeInTheDocument();
    expect(retryButton()).toBeEnabled();
  });

  it('TT-PP-P7 local mode Retry posts the preview request again after the warning', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const posts: string[] = [];
    serve({ aiMode: 'local', preview: preview('PENDING', { stage: 'voice' }) });
    server.use(
      http.post('*/batches/:id/preview', ({ params }) => {
        posts.push(String(params.id));
        return HttpResponse.json(batch({ status: 'DRAFT', preview: preview('PENDING') }), {
          status: 202,
        });
      }),
    );
    await openWizard();
    await advance(LOCAL_SLOW_MS + 500);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.click(await screen.findByRole('button', { name: RETRY }));
    await waitFor(() => expect(posts).toEqual([IDS.batch]));
  });

  it('TT-PP-E5 a preview that turns READY after 181 s hides the warning and Retry', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const scene = serve({ aiMode: 'local', preview: preview('PENDING', { stage: 'finishing' }) });
    await openWizard();
    await advance(LOCAL_SLOW_MS + 1_000);
    expect(await screen.findByText(SLOW_TEXT)).toBeInTheDocument();
    scene.preview = preview('READY');
    await advance(POLL_INTERVAL_MS + 100);
    await waitFor(() => expect(slowMessage()).not.toBeInTheDocument());
    expect(retryButton()).not.toBeInTheDocument();
  });

  it('TT-PP-E6 a preview that finishes at 100 s never shows the warning later on', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const scene = serve({ aiMode: 'local', preview: preview('PENDING', { stage: 'lipsync' }) });
    await openWizard();
    await advance(100_000);
    scene.preview = preview('READY');
    await advance(POLL_INTERVAL_MS + 100);
    await advance(LOCAL_SLOW_MS);
    expect(slowMessage()).not.toBeInTheDocument();
  });

  it.each([
    ['fake', 'fake', FAKE_SLOW_MS],
    ['local', 'local', LOCAL_SLOW_MS],
  ])(
    'TT-PP-E7 unmounting in %s mode clears the slow timer so nothing fires later',
    async (_label, aiMode, delay) => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      serve({ aiMode, preview: preview('PENDING', { stage: 'voice' }) });
      const recorder = recordTimers();
      let scheduled: unknown[] = [];
      let cleared: unknown[] = [];
      try {
        const { unmount } = renderApp(WIZARD_PATH);
        await screen.findByRole('button', { name: 'Generate preview' });
        await advance(5_000);
        unmount();
        scheduled = recorder.log.scheduled.filter((t) => t.delay === delay).map((t) => t.id);
        cleared = recorder.log.cleared;
      } finally {
        recorder.restore();
      }
      // includes() instead of toHaveBeenCalledWith: a failing deep-equal would pretty-print fake timers.
      expect(scheduled.length).toBeGreaterThan(0);
      expect(scheduled.every((id) => cleared.includes(id))).toBe(true);
    },
  );
});

describe('fake-AI note', () => {
  it.each([
    ['no preview yet', undefined],
    ['NONE', preview('NONE')],
    ['PENDING', preview('PENDING', { stage: 'voice' })],
    ['READY', preview('READY')],
    ['FAILED', preview('FAILED')],
    ['STALE', preview('STALE')],
  ])('TT-PP-P8 fake mode shows the note near Generate preview with a %s preview', async (_l, value) => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    serve({ aiMode: 'fake', preview: value });
    await openWizard();
    expect(noteTexts()).toContain(FAKE_NOTE);
    const panel = screen.getByRole('heading', { name: 'Preview' }).parentElement;
    expect(panel).not.toBeNull();
    const note = screen.getByText(FAKE_NOTE, { selector: '[role="note"]' });
    expect(panel as HTMLElement).toContainElement(note);
  });

  it('TT-PP-N8 local mode shows no fake-AI note in any preview state', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    serve({ aiMode: 'local', preview: preview('NONE') });
    await openWizard();
    expect(noteTexts()).not.toContain(FAKE_NOTE);
  });

  it('TT-PP-N9 local mode while pending shows no fake-AI note either', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    serve({ aiMode: 'local', preview: preview('PENDING', { stage: 'voice' }) });
    await openWizard();
    expect(noteTexts()).not.toContain(FAKE_NOTE);
  });

  it('TT-PP-N10 while the status call is still loading there is no fake-AI note', async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    serve({ aiMode: 'fake', preview: preview('NONE'), statusGate: gate });
    try {
      await openWizard();
      expect(noteTexts()).not.toContain(FAKE_NOTE);
      expect(screen.queryByText(FAKE_BADGE)).not.toBeInTheDocument();
    } finally {
      release();
    }
    await waitFor(() => expect(noteTexts()).toContain(FAKE_NOTE));
  });

  it.each([
    ['an HTTP error', 'http'],
    ['a network error', 'network'],
  ] as const)(
    'TT-PP-N11 a status call with %s shows no mode-specific note',
    async (_label, fault) => {
      serve({ preview: preview('NONE'), statusFault: fault });
      await openWizard();
      expect(noteTexts()).not.toContain(FAKE_NOTE);
      expect(noteTexts()).not.toContain(LOCAL_NOTE);
    },
  );

  it('TT-PP-N12 an older server without ai_mode shows no fake-AI note', async () => {
    serve({ aiMode: undefined, preview: preview('NONE') });
    await openWizard();
    expect(noteTexts()).not.toContain(FAKE_NOTE);
  });

  it('TT-PP-E8 switching fake to local mid-session swaps the notes', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const scene = serve({ aiMode: 'fake', preview: preview('PENDING', { stage: 'voice' }) });
    await openWizard();
    expect(noteTexts()).toContain(FAKE_NOTE);
    expect(noteTexts()).not.toContain(LOCAL_NOTE);
    scene.aiMode = 'local';
    await advance(POLL_INTERVAL_MS + 100);
    await waitFor(() => expect(noteTexts()).toContain(LOCAL_NOTE));
    expect(noteTexts()).not.toContain(FAKE_NOTE);
  });

  it('TT-PP-E9 switching local to fake mid-session removes the first-run note', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const scene = serve({ aiMode: 'local', preview: preview('PENDING', { stage: 'voice' }) });
    await openWizard();
    expect(noteTexts()).toContain(LOCAL_NOTE);
    scene.aiMode = 'fake';
    await advance(POLL_INTERVAL_MS + 100);
    await waitFor(() => expect(noteTexts()).toContain(FAKE_NOTE));
    expect(noteTexts()).not.toContain(LOCAL_NOTE);
  });
});

describe('READY hides the progress UI', () => {
  it('TT-PP-E10 in local mode READY hides the list, the first-run note and the warning', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const scene = serve({ aiMode: 'local', preview: preview('PENDING', { stage: 'finishing' }) });
    await openWizard();
    await advance(LOCAL_SLOW_MS + 1_000);
    expect(await screen.findByText(SLOW_TEXT)).toBeInTheDocument();
    scene.preview = preview('READY');
    await advance(POLL_INTERVAL_MS + 100);
    await waitFor(() => expect(progressList()).not.toBeInTheDocument());
    expect(noteTexts()).not.toContain(LOCAL_NOTE);
    expect(slowMessage()).not.toBeInTheDocument();
  });

  it('TT-PP-E11 in fake mode READY hides the list but keeps the fake-AI note', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const scene = serve({ aiMode: 'fake', preview: preview('PENDING', { stage: 'voice' }) });
    await openWizard();
    scene.preview = preview('READY');
    await advance(POLL_INTERVAL_MS + 100);
    await waitFor(() => expect(progressList()).not.toBeInTheDocument());
    expect(noteTexts()).toContain(FAKE_NOTE);
  });
});

describe('ai_mode switching and status failures', () => {
  it.each([
    ['an HTTP error', 'http'],
    ['a network error', 'network'],
  ] as const)(
    'TT-PP-E12 a failing status call keeps the progress list but adds no mode text (%s)',
    async (_label, fault) => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      serve({ preview: preview('PENDING', { stage: 'lipsync' }), statusFault: fault });
      await openWizard();
      expect(actualStates()).toEqual(expectedStates(2));
      expect(noteTexts()).not.toContain(FAKE_NOTE);
      expect(noteTexts()).not.toContain(LOCAL_NOTE);
    },
  );
});
