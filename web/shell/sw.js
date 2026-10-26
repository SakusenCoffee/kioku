// Serves Anki's pages without a socket: requests from Kioku's iframes, and
// any request for /_anki/ or /_addons/, go to the app page, which hands
// them to Python (kioku_platform.http) and posts back the response.

// WebKit (Safari, every iOS browser) has no credentialless
const WEBKIT = /AppleWebKit/.test(navigator.userAgent) && !/Chrome\//.test(navigator.userAgent);
const EMBEDDER_POLICY = WEBKIT ? "require-corp" : "credentialless";

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
  // so its iframes must be too (see embedder_policy in tools/serve.py)
  headers.set("Cross-Origin-Embedder-Policy", EMBEDDER_POLICY);
  headers.set("Cross-Origin-Resource-Policy", "same-origin");
  return new Response(empty ? null : reply.body, { status: reply.status, headers });
}

// require-corp (WebKit) blocks cross-origin images and scripts (cards'
// remote images, add-ons' CDNs) that don't send Cross-Origin-Resource-Policy.
// Fetched with CORS instead they load, from any host that allows it, as
// they would with credentialless
async function crossOrigin(request) {
  try {
    const response = await fetch(request.url, { mode: "cors", credentials: "omit", referrerPolicy: "no-referrer" });
    const headers = new Headers(response.headers);
    headers.set("Cross-Origin-Resource-Policy", "cross-origin");
    return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
  } catch {
    // no CORS: blocked, as it would be without this
    return fetch(request);
  }
}

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) {
    if (WEBKIT && event.request.mode === "no-cors" && event.request.method === "GET") {
      event.respondWith(crossOrigin(event.request));
    }
    return;
  }
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
