// A controllable XMLHttpRequest for upload-progress tests (FIX-UPLOAD-1).
//
// fetch() cannot report upload progress, so an upload that shows a percentage must use XHR.
// jsdom never emits upload progress events, so tests install this fake, drive the events by
// hand and assert on what the screen shows. Other requests (plain fetch) are not affected.
import { vi } from "vitest";

type Listener = (event: Event) => void;

class Target {
  private listeners = new Map<string, Listener[]>();

  addEventListener(type: string, listener: Listener): void {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }

  removeEventListener(type: string, listener: Listener): void {
    this.listeners.set(
      type,
      (this.listeners.get(type) ?? []).filter((l) => l !== listener),
    );
  }

  emit(type: string, extra: Record<string, unknown> = {}): void {
    const event = Object.assign(new Event(type), extra);
    (this as unknown as Record<string, Listener | null | undefined>)[
      `on${type}`
    ]?.(event);
    for (const listener of this.listeners.get(type) ?? []) listener(event);
  }
}

export class FakeUpload extends Target {
  onprogress: Listener | null = null;
  onload: Listener | null = null;
  onerror: Listener | null = null;
}

export class FakeXhr extends Target {
  static instances: FakeXhr[] = [];

  readonly upload = new FakeUpload();
  method = "";
  url = "";
  body: unknown = null;
  headers: Record<string, string> = {};
  aborted = false;
  timeout = 0;
  withCredentials = false;
  responseType: XMLHttpRequestResponseType = "";
  readyState = 0;
  status = 0;
  statusText = "";
  responseText = "";
  responseHeaders: Record<string, string> = {};

  onload: Listener | null = null;
  onerror: Listener | null = null;
  onabort: Listener | null = null;
  ontimeout: Listener | null = null;
  onloadend: Listener | null = null;
  onreadystatechange: Listener | null = null;
  onprogress: Listener | null = null;

  constructor() {
    super();
    FakeXhr.instances.push(this);
  }

  get response(): unknown {
    return this.responseType === "json"
      ? JSON.parse(this.responseText || "null")
      : this.responseText;
  }

  get responseURL(): string {
    return this.url;
  }

  open(method: string, url: string | URL): void {
    this.method = method.toUpperCase();
    this.url = String(url);
    this.readyState = 1;
  }

  setRequestHeader(name: string, value: string): void {
    this.headers[name.toLowerCase()] = value;
  }

  getResponseHeader(name: string): string | null {
    return this.responseHeaders[name.toLowerCase()] ?? null;
  }

  getAllResponseHeaders(): string {
    return Object.entries(this.responseHeaders)
      .map(([k, v]) => `${k}: ${v}`)
      .join("\r\n");
  }

  overrideMimeType(): void {}

  send(body?: unknown): void {
    this.body = body ?? null;
  }

  abort(): void {
    this.aborted = true;
    this.readyState = 0;
    this.emit("abort");
    this.emit("loadend");
  }

  // ---- test controls -------------------------------------------------------------------

  /** The browser reports `loaded` of `total` bytes sent. */
  progress(loaded: number, total: number): void {
    const extra = { loaded, total, lengthComputable: true };
    this.upload.emit("progress", extra);
  }

  /** The server answers with a status and a body (an object is sent as JSON). */
  respond(status: number, body: unknown = {}): void {
    this.status = status;
    this.responseText = typeof body === "string" ? body : JSON.stringify(body);
    this.responseHeaders = { "content-type": "application/json" };
    this.readyState = 4;
    this.upload.emit("load");
    this.emit("readystatechange");
    this.emit("load");
    this.emit("loadend");
  }

  /** The connection fails (server down, offline). */
  networkError(): void {
    this.readyState = 4;
    this.upload.emit("error");
    this.emit("error");
    this.emit("loadend");
  }

  /** The request times out. */
  timedOut(): void {
    this.readyState = 4;
    this.emit("timeout");
    this.emit("loadend");
  }
}

/** Replace XMLHttpRequest for this test; restored by `vi.restoreAllMocks`/`vi.unstubAllGlobals`. */
export function installFakeXhr(): void {
  FakeXhr.instances = [];
  vi.stubGlobal("XMLHttpRequest", FakeXhr);
}

/** The newest fake request whose URL contains `fragment`, once the app has started it. */
export function uploads(fragment: string): FakeXhr[] {
  return FakeXhr.instances.filter(
    (x) => x.url.includes(fragment) && x.method === "POST",
  );
}
