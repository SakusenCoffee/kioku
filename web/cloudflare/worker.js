// Kioku on Cloudflare Workers. Runs first for every request:
// - every response gets the cross-origin isolation headers threads need,
//   with the embedder policy the browser supports (embedderPolicy());
// - /kioku.wasm and /kioku.data: Cloudflare takes files up to 25 MiB, so
//   they are stored brotli-compressed (.br, tools/dist.sh) and served with
//   Content-Encoding: br, which the browser undoes;
// - /__relay/<host>:<port>: Emscripten's sockets as WebSockets, passed on
//   over TCP like tools/serve.py does (TLS stays inside wasm).
import { connect } from "cloudflare:sockets";

const RELAY = "/__relay/";
const PACKED = { "/kioku.wasm": "application/wasm", "/kioku.data": "application/octet-stream" };
// credentialless: cross-origin scripts and images (add-ons' CDNs) load
// without opting in. WebKit (Safari, every iOS browser) lacks it and takes
// require-corp only (see embedder_policy in tools/serve.py)
function embedderPolicy(request) {
  const agent = request.headers.get("User-Agent") || "";
  return /AppleWebKit/.test(agent) && !/Chrome\//.test(agent) ? "require-corp" : "credentialless";
}

function isolated(response, request, init = {}) {
  const headers = new Headers(response.headers);
  for (const [name, value] of Object.entries(init.headers || {})) headers.set(name, value);
  headers.set("Cross-Origin-Opener-Policy", "same-origin");
  headers.set("Cross-Origin-Embedder-Policy", embedderPolicy(request));
  headers.append("Vary", "User-Agent");
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers, ...init.response });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname.startsWith(RELAY)) return relay(request, env, url.pathname.slice(RELAY.length));
    const type = PACKED[url.pathname];
    if (!type) return isolated(await env.ASSETS.fetch(request), request);
    const asset = await env.ASSETS.fetch(new Request(new URL(url.pathname + ".br", url), request));
    // 304 (If-None-Match) or 404 as they are
    if (asset.status !== 200) return isolated(asset, request);
    return isolated(asset, request, {
      headers: { "Content-Type": type, "Content-Encoding": "br" },
      response: { encodeBody: "manual" },
    });
  },
};

function allowed(target, env) {
  const rules = (env.RELAY_ALLOW || "").split(",").map((r) => r.trim().toLowerCase()).filter(Boolean);
  return rules.some((rule) => {
    const pattern = rule.replace(/[.+?^${}()|[\]\\]/g, "\\$&").replaceAll("*", ".*");
    return new RegExp(`^${pattern}$`).test(target.toLowerCase());
  });
}

async function relay(request, env, target) {
  if (request.headers.get("Upgrade")?.toLowerCase() !== "websocket") {
    return new Response("WebSockets only", { status: 426 });
  }
  // WebSockets aren't bound by CORS: without this any website open in the
  // browser could use the relay. Other clients can send any Origin, which
  // is why only the hosts in RELAY_ALLOW are reached
  if (request.headers.get("Origin") !== new URL(request.url).origin) {
    return new Response("relay is for the app page only", { status: 403 });
  }
  const colon = target.lastIndexOf(":");
  const hostname = target.slice(0, colon);
  const port = target.slice(colon + 1);
  if (colon < 1 || !/^\d+$/.test(port) || !allowed(target, env)) {
    return new Response(`not relayed: ${target}`, { status: 403 });
  }
  const socket = connect({ hostname, port: Number(port) });
  try {
    await socket.opened;
  } catch (e) {
    return new Response(`${target}: ${e}`, { status: 502 });
  }
  const [client, server] = Object.values(new WebSocketPair());
  // binary messages would be Blobs (the standard default)
  server.binaryType = "arraybuffer";
  server.accept();
  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    try {
      server.close(1000);
    } catch {}
    socket.close().catch(() => {});
  };
  const writer = socket.writable.getWriter();
  server.addEventListener("message", (event) => {
    const data = typeof event.data === "string" ? new TextEncoder().encode(event.data) : new Uint8Array(event.data);
    writer.write(data).catch(close);
  });
  server.addEventListener("close", close);
  server.addEventListener("error", close);
  socket.readable
    .pipeTo(new WritableStream({ write: (chunk) => server.send(chunk), close, abort: close }))
    .catch(close);
  const headers = {};
  if ((request.headers.get("Sec-WebSocket-Protocol") || "").includes("binary")) {
    headers["Sec-WebSocket-Protocol"] = "binary";
  }
  return new Response(null, { status: 101, webSocket: client, headers });
}
