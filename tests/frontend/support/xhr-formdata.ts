// Test-only shim. The shared test setup swaps the global FormData for Node's class so that
// fetch + MSW can read multipart bodies, but jsdom's XMLHttpRequest does not know that class and
// would send the text "[object FormData]". Browsers send multipart; this makes jsdom do the same
// so uploads that go through XMLHttpRequest can be tested against MSW.
const proto = XMLHttpRequest.prototype;
const originalSend = proto.send;

proto.send = function send(
  this: XMLHttpRequest,
  body?: Document | XMLHttpRequestBodyInit | null,
) {
  if (!(body instanceof FormData)) return originalSend.call(this, body);
  const encoded = new Response(body);
  void encoded.arrayBuffer().then((bytes) => {
    this.setRequestHeader(
      "Content-Type",
      encoded.headers.get("content-type") ?? "",
    );
    originalSend.call(this, bytes);
  });
  return undefined;
};
