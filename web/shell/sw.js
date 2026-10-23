// Serves Anki's pages without a socket: requests from Kioku's iframes, and
// any request for /_anki/ or /_addons/, go to the app page, which hands
// them to Python (kioku_platform.http) and posts back the response.

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

async function appWindow() {
  const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
  return windows.find((c) => c.frameType === "top-level");
}

async function forward(request) {
  const client = await appWindow();
  if (!client) return new Response("Kioku is not running", { status: 503 });
  const body =
    request.method === "GET" || request.method === "HEAD" ? null : await request.arrayBuffer();
  const requestHeaders = {};
  request.headers.forEach((value, name) => (requestHeaders[name] = value));
  const reply = await new Promise((resolve) => {
    const channel = new MessageChannel();
    channel.port1.onmessage = (event) => resolve(event.data);
    const message = { type: "http", method: request.method, url: request.url, headers: requestHeaders, body };
    client.postMessage(message, body ? [channel.port2, body] : [channel.port2]);
  });
  const empty = reply.status === 204 || reply.status === 304 || request.method === "HEAD";
  const headers = new Headers(reply.headers);
  // the app page is cross-origin isolated (threads need SharedArrayBuffer),
  // so its iframes and their resources must opt in too
  headers.set("Cross-Origin-Embedder-Policy", "require-corp");
  headers.set("Cross-Origin-Resource-Policy", "same-origin");
  return new Response(empty ? null : reply.body, { status: reply.status, headers });
}

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  const path = url.pathname;
  if (path.startsWith("/_anki/") || path.startsWith("/_addons/") || event.request.destination === "iframe") {
    event.respondWith(forward(event.request));
    return;
  }
  if (!event.clientId) return;
  // media files and other relative URLs of a page in one of the iframes
  event.respondWith(
    self.clients
      .get(event.clientId)
      .then((c) => (c && c.frameType === "nested" ? forward(event.request) : fetch(event.request))),
  );
});
