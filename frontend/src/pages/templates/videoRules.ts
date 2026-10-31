/** Extensions accepted when the browser gives no file type (some systems do this for video). */
const VIDEO_EXTENSIONS = ['.mp4', '.mov', '.m4v', '.mkv', '.webm'];

/**
 * True for a video: a video/* type, or an empty type with a supported extension.
 * Any other non-empty type (for example text/plain) is refused even if the name looks like a video.
 */
export function isVideoFile(file: File): boolean {
  if (file.type.startsWith('video/')) return true;
  if (file.type !== '') return false;
  const name = file.name.toLowerCase();
  return VIDEO_EXTENSIONS.some((ext) => name.endsWith(ext));
}

/**
 * Plain-language problem with a chosen template video, or null when it may be uploaded.
 * Used by both the click and the drop path. The API checks again.
 */
export function templateVideoProblem(file: File): string | null {
  if (!isVideoFile(file)) return 'Choose a video file.';
  if (file.size === 0) return 'The video is empty.';
  return null;
}
