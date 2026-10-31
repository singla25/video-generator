// DD-37 D: new template form on the Templates page (drop zone, file summary, word helper).
// Cases: TT-DD37-D-*
//
// CONTRACT (frontend/src/pages/templates/NewTemplateForm.tsx):
//   drop zone element with the accessible name "Template video" containing the text
//     "Drop the video here or choose a file" and a file input (accept video/*)
//   after a file is chosen (click or drop) the zone shows "<file name> · <size> MB" (one decimal)
//     and a "Remove file" button that clears it
//   field "Word to replace" with helper text "The word spoken where each person's name goes, for example Krishan."
//   the line "After uploading, add the consent file on the template card." stays
//   "Upload template" disabled until a file is chosen and the word is not blank; "Cancel" stays
//   a non-video file (type not starting with video/) shows "Choose a video file." in role=alert
//     and is not accepted, by choice or by drop
import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it } from 'vitest';

import { renderApp } from '../helpers';
import { IDS, template } from '../mocks/data';
import { server } from '../mocks/server';

const DROP_HINT = 'Drop the video here or choose a file';
const HELPER = "The word spoken where each person's name goes, for example Krishan.";
const CONSENT_LINE = 'After uploading, add the consent file on the template card.';
const NOT_VIDEO = 'Choose a video file.';
/** 100 000 bytes is 0.1 MB under both the decimal and the binary definition. */
const SMALL_BYTES = 100_000;

async function openForm() {
  renderApp('/templates');
  await userEvent.click(await screen.findByRole('button', { name: 'New template' }));
}

function videoFile(name = 'intro.mp4', bytes = SMALL_BYTES, type = 'video/mp4'): File {
  return new File([new Uint8Array(bytes)], name, { type });
}

/** The drop zone, found by its accessible name. */
function dropZone(): HTMLElement {
  return screen.getByLabelText('Template video');
}

/** The file input inside the drop zone (the zone itself when the input carries the name). */
function fileInput(): HTMLInputElement {
  const zone = dropZone();
  if (zone instanceof HTMLInputElement) return zone;
  const input = zone.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error('no file input inside the Template video drop zone');
  return input;
}

function uploadButton() {
  return screen.getByRole('button', { name: 'Upload template' });
}

async function chooseVideo(file: File) {
  await userEvent.upload(fileInput(), file, { applyAccept: false });
}

function drop(file: File) {
  fireEvent.drop(dropZone(), { dataTransfer: { files: [file], types: ['Files'] } });
}

describe('layout', () => {
  it('TT-DD37-D-P1 the drop zone is named Template video, says where to drop and holds a video input', async () => {
    await openForm();
    expect(dropZone()).toHaveTextContent(DROP_HINT);
    expect(fileInput()).toHaveAttribute('accept', 'video/*');
    expect(screen.queryByRole('button', { name: 'Remove file' })).not.toBeInTheDocument();
  });

  it('TT-DD37-D-P2 the word field has its label, helper text and the consent reminder', async () => {
    await openForm();
    expect(screen.getByLabelText('Word to replace')).toBeInTheDocument();
    expect(screen.getByText(HELPER)).toBeInTheDocument();
    expect(screen.getByText(CONSENT_LINE)).toBeInTheDocument();
  });

  it('TT-DD37-D-P3 Cancel is still offered next to Upload template', async () => {
    await openForm();
    expect(screen.getByRole('button', { name: 'Upload template' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
  });
});

describe('choosing a file', () => {
  it('TT-DD37-D-P4 a chosen video shows its name and size in MB with one decimal', async () => {
    await openForm();
    await chooseVideo(videoFile('intro.mp4'));
    expect(dropZone()).toHaveTextContent('intro.mp4 · 0.1 MB');
    expect(dropZone()).not.toHaveTextContent(DROP_HINT);
  });

  it('TT-DD37-D-P5 Remove file clears the chosen video and brings the drop hint back', async () => {
    await openForm();
    await chooseVideo(videoFile('intro.mp4'));
    await userEvent.click(screen.getByRole('button', { name: 'Remove file' }));
    expect(dropZone()).toHaveTextContent(DROP_HINT);
    expect(dropZone()).not.toHaveTextContent('intro.mp4');
    expect(screen.queryByRole('button', { name: 'Remove file' })).not.toBeInTheDocument();
  });

  it('TT-DD37-D-P6 a dropped video behaves like a chosen one', async () => {
    await openForm();
    drop(videoFile('dropped.mp4'));
    expect(await screen.findByText(/dropped\.mp4 · 0\.1 MB/)).toBeInTheDocument();
    expect(dropZone()).toHaveTextContent('dropped.mp4 · 0.1 MB');
  });

  it('TT-DD37-D-P7 the size line shows one decimal for any size', async () => {
    await openForm();
    await chooseVideo(videoFile('big.mp4', 12_400_000));
    expect(dropZone().textContent).toMatch(/big\.mp4 · \d+\.\d MB/);
  });

  it('TT-DD37-D-P8 Upload is disabled until a file is chosen and the word is not blank', async () => {
    await openForm();
    expect(uploadButton()).toBeDisabled();
    await userEvent.type(screen.getByLabelText('Word to replace'), 'Rahul');
    expect(uploadButton()).toBeDisabled();
    await chooseVideo(videoFile());
    expect(uploadButton()).toBeEnabled();
  });

  it('TT-DD37-D-P9 uploads the chosen video and the trimmed word as multipart', async () => {
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
    await chooseVideo(videoFile());
    await userEvent.type(screen.getByLabelText('Word to replace'), '  Rahul  ');
    await userEvent.click(uploadButton());
    await waitFor(() => expect(seen).toEqual({ word: 'Rahul', video: 'file' }));
  });
});

describe('negative', () => {
  it('TT-DD37-D-N1 a non-video file is refused with Choose a video file. and not accepted', async () => {
    await openForm();
    await userEvent.type(screen.getByLabelText('Word to replace'), 'Zed');
    await chooseVideo(new File(['a,b'], 'sheet.csv', { type: 'text/csv' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(NOT_VIDEO);
    expect(dropZone()).not.toHaveTextContent('sheet.csv');
    expect(uploadButton()).toBeDisabled();
  });

  it('TT-DD37-D-N2 a dropped non-video file is refused the same way', async () => {
    await openForm();
    await userEvent.type(screen.getByLabelText('Word to replace'), 'Zed');
    drop(new File(['a,b'], 'sheet.csv', { type: 'text/csv' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(NOT_VIDEO);
    expect(dropZone()).not.toHaveTextContent('sheet.csv');
    expect(uploadButton()).toBeDisabled();
  });

  it('TT-DD37-D-N3 the decision is the MIME type: an .mp4 name with no video type is refused', async () => {
    await openForm();
    await userEvent.type(screen.getByLabelText('Word to replace'), 'Zed');
    await chooseVideo(videoFile('intro.mp4', SMALL_BYTES, ''));
    expect(await screen.findByRole('alert')).toHaveTextContent(NOT_VIDEO);
    expect(uploadButton()).toBeDisabled();
  });
});

describe('edge', () => {
  it('TT-DD37-D-E1 a word made only of spaces keeps Upload disabled even with a video', async () => {
    await openForm();
    await chooseVideo(videoFile());
    await userEvent.type(screen.getByLabelText('Word to replace'), '   ');
    expect(uploadButton()).toBeDisabled();
  });

  it('TT-DD37-D-E2 a file name with unicode and spaces is shown intact', async () => {
    await openForm();
    await chooseVideo(videoFile('मेरा वीडियो clip.mp4'));
    expect(dropZone()).toHaveTextContent('मेरा वीडियो clip.mp4 · 0.1 MB');
  });

  it('TT-DD37-D-E3 after Remove file a new video can be chosen', async () => {
    await openForm();
    await chooseVideo(videoFile('first.mp4'));
    await userEvent.click(screen.getByRole('button', { name: 'Remove file' }));
    await chooseVideo(videoFile('second.mp4'));
    expect(dropZone()).toHaveTextContent('second.mp4 · 0.1 MB');
  });
});
