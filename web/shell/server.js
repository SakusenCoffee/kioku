// Server mode (docs/server.md): when a Kioku server serves the page
// (tools/serve.py with KIOKU_DATA), the collection stays on it and the app
// only shows it (python/kioku_platform/remote.py). storage.js then keeps
// /home/web_user's small files (profiles, preferences, add-ons) on the
// server instead of in IndexedDB; collections, media and backups are not
// copied into the app. Elsewhere (Cloudflare, plain serve.py) there is no
// /__kioku/server.json and nothing here is used.
(() => {
  // same pattern as server/kioku_server.py
  const SERVER_ONLY = /(^|\/)(collection\.anki2[^/]*|collection\.media[^/]*|backups)(\/|$)/;
  // one per tab, kept across reloads: the server's lease is per client
  let client;
  try {
    client = sessionStorage.getItem("kiokuClient") || crypto.randomUUID();
    sessionStorage.setItem("kiokuClient", client);
  } catch {
    client = crypto.randomUUID();
  }
  const config = fetch("/__kioku/server.json")
    .then((r) => (r.ok && (r.headers.get("Content-Type") || "").includes("json") ? r.json() : null))
    .then((c) => c && { ...c, client })
    .catch(() => null);
  const url = (rel) => "/__kioku/home/" + rel.split("/").map(encodeURIComponent).join("/");
  // relative path -> modification time when last loaded or saved
  let known = new Map();

  async function sync(mount, populate, { FS, IDBFS }) {
    const root = mount.mountpoint;
    if (populate) {
      const list = await (await fetch("/__kioku/home")).json();
      for (const rel of Object.keys(list).sort()) {
        const path = `${root}/${rel}`;
        if (list[rel]) {
          FS.mkdirTree(path);
          continue;
        }
        const r = await fetch(url(rel));
        if (!r.ok) continue;
        FS.mkdirTree(path.slice(0, path.lastIndexOf("/")));
        FS.writeFile(path, new Uint8Array(await r.arrayBuffer()));
      }
    }
    const local = await new Promise((ok, fail) => IDBFS.getLocalSet(mount, (e, set) => (e ? fail(e) : ok(set))));
    const now = new Map();
    for (const [path, entry] of Object.entries(local.entries)) {
      const rel = path.slice(root.length + 1);
      if (rel && !SERVER_ONLY.test(rel)) now.set(rel, entry.timestamp.getTime());
    }
    if (!populate) {
      // folders before the files in them
      for (const rel of [...now.keys()].sort()) {
        if (known.get(rel) === now.get(rel)) continue;
        let dir, body;
        try {
          dir = FS.isDir(FS.stat(`${root}/${rel}`).mode);
          body = dir ? null : FS.readFile(`${root}/${rel}`);
        } catch {
          now.delete(rel); // removed meanwhile
          continue;
        }
        const r = await fetch(url(rel) + (dir ? "?dir=1" : ""), { method: "PUT", body });
        if (!r.ok) throw new Error(`saving ${rel}: ${r.status}`);
      }
      for (const rel of [...known.keys()].sort().reverse()) {
        if (!now.has(rel)) await fetch(url(rel), { method: "DELETE" });
      }
    }
    known = now;
  }

  globalThis.__kiokuServer = { config, sync };

  // closing or reloading the tab frees the collection for other devices
  // at once, rather than after the lease's minute
  // (synchronously: a promise's callback may not run while the page goes)
  let served = false;
  config.then((c) => (served = !!c));
  window.addEventListener("pagehide", () => served && navigator.sendBeacon("/__kioku/release", client));

  // remote.py: another device took the collection over
  const web = window.__kiokuWeb;
  web.takenOver = () => {
    if (document.getElementById("kioku-taken")) return "1";
    const cover = document.createElement("div");
    cover.id = "kioku-taken";
    cover.style.cssText =
      "position:fixed;inset:0;z-index:2147483647;display:grid;place-items:center;padding:16px;" +
      "background:rgba(0,0,0,.8);color:#fff;font:16px system-ui,sans-serif;text-align:center";
    cover.innerHTML = "<div><p>Kioku is open on another device.</p><button style='font:inherit;padding:8px 16px'>Use it here</button></div>";
    cover.querySelector("button").onclick = () => location.reload();
    document.body.appendChild(cover);
    return "1";
  };
})();
