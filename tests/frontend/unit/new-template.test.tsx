// UI-AC7 New template form on the Templates page (added in F6 after E2E showed the gap).
// Cases: TT-UI-AC7-P3, TT-UI-AC7-N3, TT-UI-AC7-N4, TT-UI-AC7-E5
// DD-37 D changed the structure: the file input sits inside the "Template video" drop zone and
// the refusal text is "Choose a video file." (see new-template-form.test.tsx).
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { renderApp } from '../helpers';
import { IDS, template } from '../mocks/data';
import { apiError } from '../mocks/handlers';
import { server } from '../mocks/server';

/** The file input inside the "Template video" drop zone (DD-37 D). */
function fileInput(): HTMLInputElement {
  const zone = screen.getByLabelText('Template video');
  if (zone instanceof HTMLInputElement) return zone;
  const input = zone.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error('no file input inside the Template video drop zone');
  return input;
}

async function openForm() {
  renderApp('/templates');
  await userEvent.click(await screen.findByRole('button', { name: 'New template' }));
}

const mp4 = () => new File(['video'], 'intro.mp4', { type: 'video/mp4' });

describe('new template form', () => {
  it('TT-UI-AC7-P3 uploads the video and the word as multipart and closes the form', async () => {
    let seen: Record<string, string> = {};
    server.use(
      http.post('*/templates', async ({ request }) => {
        const form = await request.formData();
        seen = {
          word: String(form.get('original_name')),
          video: form.get('video') instanceof File ? 'file' : 'none',
        };
        return HttpResponse.json(template({ id: IDS.template }), { status: 201 });
      }),
    );
    await openForm();
    await userEvent.upload(fileInput(), mp4(), { applyAccept: false });
    await userEvent.type(screen.getByLabelText('Word to replace'), 'Rahul');
    await userEvent.click(screen.getByRole('button', { name: 'Upload template' }));
    await waitFor(() => expect(seen).toEqual({ word: 'Rahul', video: 'file' }));
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Upload template' })).not.toBeInTheDocument(),
    );
  });

  it('TT-UI-AC7-N3 a non-video file is refused on the client without a request', async () => {
    await openForm();
    await userEvent.upload(fileInput(), new File(['a,b'], 'sheet.csv', { type: 'text/csv' }), {
      applyAccept: false,
    });
    await userEvent.type(screen.getByLabelText('Word to replace'), 'Zed');
    expect(await screen.findByRole('alert')).toHaveTextContent('Choose a video file.');
    expect(screen.getByRole('button', { name: 'Upload template' })).toBeDisabled();
  });

  it('TT-UI-AC7-N4 the API refusing the video shows its message and keeps the form open', async () => {
    server.use(
      http.post('*/templates', () =>
        apiError(422, 'CORRUPT_VIDEO', 'This video file could not be read.'),
      ),
    );
    await openForm();
    await userEvent.upload(fileInput(), mp4(), { applyAccept: false });
    await userEvent.type(screen.getByLabelText('Word to replace'), 'Rahul');
    await userEvent.click(screen.getByRole('button', { name: 'Upload template' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('could not be read');
    expect(screen.getByRole('button', { name: 'Upload template' })).toBeInTheDocument();
  });

  it('TT-UI-AC7-E5 Upload stays disabled until both a video and a word are given; Cancel closes', async () => {
    await openForm();
    const upload = screen.getByRole('button', { name: 'Upload template' });
    expect(upload).toBeDisabled();
    await userEvent.type(screen.getByLabelText('Word to replace'), '   ');
    expect(upload).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('button', { name: 'Upload template' })).not.toBeInTheDocument();
  });
});
