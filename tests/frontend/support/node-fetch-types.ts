import { File as NodeFile } from 'node:buffer';

// jsdom replaces Blob, File and FormData with its own classes, but fetch (and MSW) run
// on Node's. A multipart body holding a jsdom File would be sent as the text
// "[object File]". This FormData accepts jsdom files and stores them as Node files,
// so uploads in tests behave as they do in a browser.
// A urlencoded Response hands back an instance of Node's own FormData class.
const probe = await new Response(new URLSearchParams()).formData();
const NodeFormData = probe.constructor as new () => FormData;

interface JsdomBlob {
  type: string;
  name?: string;
  [key: symbol]: { _buffer?: Uint8Array } | undefined;
}

function isJsdomBlob(value: unknown): value is JsdomBlob {
  return (
    typeof value === 'object' &&
    value !== null &&
    Object.prototype.toString.call(value) === '[object File]'
  );
}

function jsdomBytes(blob: JsdomBlob): Uint8Array {
  const impl = Object.getOwnPropertySymbols(blob)
    .map((symbol) => blob[symbol])
    .find((candidate) => candidate && '_buffer' in candidate);
  return impl?._buffer ?? new Uint8Array();
}

class JsdomFriendlyFormData extends NodeFormData {
  append(name: string, value: string | Blob, filename?: string): void {
    if (isJsdomBlob(value)) {
      // Copy into a plain ArrayBuffer-backed array so it is a valid BlobPart.
      const file = new NodeFile(
        [new Uint8Array(jsdomBytes(value))],
        filename ?? value.name ?? 'blob',
        {
          type: value.type,
        },
      );
      super.append(name, file as unknown as Blob);
    } else {
      super.append(name, value as string);
    }
  }
}

globalThis.FormData = JsdomFriendlyFormData as unknown as typeof FormData;

// Node's multipart parser builds files with the global File. Use Node's File while
// parsing, and let `instanceof File` (jsdom's File in tests) accept Node files too.
const JsdomFile = globalThis.File;
Object.defineProperty(JsdomFile, Symbol.hasInstance, {
  value: (candidate: unknown) =>
    Function.prototype[Symbol.hasInstance].call(JsdomFile, candidate) ||
    candidate instanceof NodeFile,
});

for (const proto of [Request.prototype, Response.prototype]) {
  const parse = proto.formData;
  proto.formData = async function formData(this: Body) {
    const saved = globalThis.File;
    globalThis.File = NodeFile as unknown as typeof File;
    try {
      return await parse.call(this);
    } finally {
      globalThis.File = saved;
    }
  };
}
