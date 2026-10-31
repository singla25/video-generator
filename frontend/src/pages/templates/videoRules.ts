const VIDEO_EXTENSIONS = ['.mp4', '.mov', '.mkv', '.webm'];

/**
 * Plain-language problem with a chosen template video, or null when it may be uploaded.
 * The file type decides first; the name must also end in a supported extension. The API checks again.
 */
export function templateVideoProblem(file: File): string | null {
  if (!file.type.startsWith('video/')) return 'Choose a video file.';
  if (file.size === 0) return 'The video is empty.';
  const name = file.name.toLowerCase();
  return VIDEO_EXTENSIONS.some((ext) => name.endsWith(ext))
    ? null
    : 'Use an MP4, MOV, MKV or WebM video.';
}
