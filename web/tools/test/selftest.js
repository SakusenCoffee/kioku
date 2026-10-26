// Self-test inside the page, for browsers that can't be driven from outside
// (Safari, iOS Safari): tools/serve.py injects this into app.html when
// KIOKU_SELFTEST is set, before kioku.js, so Emscripten's output goes
// through the console wrapper below. Every console line is posted to
// /__selftest/log; the steps come from /__selftest/steps.json (written by
// tools/test/selftest.py), one list per page load, with a reload between.
// Steps (layout-independent, unlike boot.mjs's coordinates):
//   ["wait", ms]                 ["py", code, 0, waitMs]   run Python (devexec)
//   ["firstrun"]                 accept the first-run language dialogs
//   ["frames", name, js, waitMs] CHECK name: js true in any web view iframe
//   ["probe", name, js]          log PROBE name: js's first non-null value
//   ["click", selector, text, waitMs]   click the first element in a web view
//                                matching selector (and with exactly text)
//   ["type", selector, index, text, waitMs]  insert text into an editable
//   ["fetch", url, path, waitMs] copy a file from the server into the wasm FS
//   ["dom", js]                  evaluate on the app page, log the result
//   ["shot", name]               log SHOT name (the runner takes it)
//   ["waitfor", text, ms]        wait until a console line contains text
(function () {
  "use strict";
  const lines = [];
  const send = () => {
    if (!lines.length) return;
    const body = lines.splice(0).join("\n") + "\n";
    fetch("/__selftest/log", { method: "POST", body, keepalive: true }).catch(() => {});
  };
  setInterval(send, 500);
  addEventListener("pagehide", send);
  const t0 = performance.now();
  const log = (text) => lines.push(`[${((performance.now() - t0) / 1000).toFixed(1)}s] ${text}`);
  const seen = [];
  for (const level of ["log", "info", "warn", "error", "debug"]) {
    const original = console[level].bind(console);
    console[level] = (...args) => {
      const text = args.map((a) => (a instanceof Error ? a.stack || a.message : String(a))).join(" ");
      if (!/OpenType|null function/.test(text)) log(text.slice(0, 2000));
      seen.push(text);
      original(...args);
    };
  }
  addEventListener("error", (e) => log("pageerror " + (e.error?.stack || e.message)));
  addEventListener("unhandledrejection", (e) => log("pageerror " + (e.reason?.stack || e.reason)));
  // downloads (kioku-web.js download(): an <a download> with a blob URL)
  const click = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function () {
    if (this.download && this.href.startsWith("blob:")) {
      fetch(this.href)
        .then((r) => r.blob())
        .then((b) => log(`download completed ${b.size} bytes (${this.download})`));
    }
    return click.call(this);
  };

  // thread pool use: workers created, and those that ever ran a thread
  // (Emscripten sends them {cmd: "run"}); the pool reuses free ones
  const workers = { created: 0, used: new Set() };
  const NativeWorker = window.Worker;
  window.Worker = class extends NativeWorker {
    constructor(...args) {
      super(...args);
      const id = ++workers.created;
      const post = this.postMessage.bind(this);
      this.postMessage = (message, ...rest) => {
        if (message && message.cmd === "run") workers.used.add(id);
        return post(message, ...rest);
      };
    }
  };

  // activity per second (memory investigations): bytes the service worker
  // relays to Anki's pages, pixels Qt paints, events posted to Python
  const activity = { relayed: 0, painted: 0, posts: 0 };
  const putImageData = CanvasRenderingContext2D.prototype.putImageData;
  CanvasRenderingContext2D.prototype.putImageData = function (data, ...rest) {
    activity.painted += data.width * data.height;
    return putImageData.call(this, data, ...rest);
  };
  const drawImage = CanvasRenderingContext2D.prototype.drawImage;
  CanvasRenderingContext2D.prototype.drawImage = function (image, ...rest) {
    activity.painted += (image.width || 0) * (image.height || 0);
    return drawImage.call(this, image, ...rest);
  };
  const watchWeb = setInterval(() => {
    const web = window.__kiokuWeb;
    if (!web) return;
    clearInterval(watchWeb);
    const respond = web.respond.bind(web);
    web.respond = (id, status, headers, body) => {
      activity.relayed += body ? body.byteLength : 0;
      return respond(id, status, headers, body);
    };
    const post = web.post.bind(web);
    web.post = (event) => {
      activity.posts++;
      return post(event);
    };
  }, 50);
  setInterval(() => {
    if (activity.relayed || activity.painted || activity.posts) {
      log(`ACTIVITY relayed ${(activity.relayed / 1e6).toFixed(1)} MB, painted ${(activity.painted / 1e6).toFixed(1)} Mpx, posts ${activity.posts}`);
    }
    activity.relayed = activity.painted = activity.posts = 0;
  }, 1000);

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms || 0));
  // web views are iframes inside Qt's screen (a shadow root)
  const frames = () =>
    deepAll(document, "iframe").flatMap((f) => {
      try {
        return f.contentDocument ? [f.contentDocument] : [];
      } catch {
        return [];
      }
    });
  // elements in a document and its shadow roots (Anki's editor fields)
  function deepAll(root, selector) {
    const found = [...root.querySelectorAll(selector)];
    for (const el of root.querySelectorAll("*")) if (el.shadowRoot) found.push(...deepAll(el.shadowRoot, selector));
    return found;
  }
  const visible = (el) => el.getClientRects().length > 0;
  const inFrames = (selector, text) =>
    frames()
      .flatMap((d) => deepAll(d, selector))
      .filter((el) => visible(el) && (!text || el.textContent.trim() === text));
  const py = (code) => window.__kiokuWeb.post({ type: "devexec", code });

  const FIRST_RUN = `from aqt.qt import QApplication, QDialog, QMessageBox
for w in QApplication.topLevelWidgets():
    if w.isVisible() and isinstance(w, QMessageBox):
        b = w.button(QMessageBox.StandardButton.Yes) or w.defaultButton()
        b.click() if b else w.accept()
    elif w.isVisible() and isinstance(w, QDialog):
        w.accept()`;

  async function run(step) {
    const [kind] = step;
    let wait = 0;
    if (kind === "wait") wait = step[1];
    else if (kind === "py") {
      py(step[1]);
      wait = step[3];
    } else if (kind === "firstrun") {
      for (let i = 0; i < 4; i++) {
        py(FIRST_RUN);
        await sleep(2500);
      }
    } else if (kind === "frames") {
      const [, name, js, w] = step;
      let ok = false;
      let detail = `${frames().length} frames`;
      for (const d of frames()) {
        try {
          if (new d.defaultView.Function("document", "deepAll", `return (${js})`)(d, deepAll)) ok = true;
        } catch (e) {
          detail = String(e);
        }
      }
      log(`CHECK ${name} ${ok ? "PASS" : "FAIL"} ${ok ? "" : detail}`);
      wait = w;
    } else if (kind === "probe") {
      const [, name, js] = step;
      const values = frames().map((d) => {
        try {
          return new d.defaultView.Function("document", `return (${js})`)(d);
        } catch (e) {
          return String(e);
        }
      });
      log(`PROBE ${name}: ${JSON.stringify(values.find((v) => v !== undefined && v !== null) ?? null)}`);
    } else if (kind === "click") {
      const [, selector, text, w] = step;
      const el = inFrames(selector, text)[0];
      log(el ? `clicked ${selector} ${text || ""}` : `CHECK click ${selector} ${text || ""} FAIL not found`);
      el?.click();
      wait = w;
    } else if (kind === "type") {
      const [, selector, index, text, w] = step;
      const el = inFrames(selector)[index];
      if (!el) log(`CHECK type into ${selector}[${index}] FAIL not found`);
      else {
        el.focus();
        el.ownerDocument.execCommand("insertText", false, text);
        log(`typed ${text}`);
      }
      wait = w;
    } else if (kind === "fetch") {
      const [, url, path, w] = step;
      const data = new Uint8Array(await (await fetch(url)).arrayBuffer());
      window.__kiokuFS.mkdirTree(path.slice(0, path.lastIndexOf("/")) || "/");
      window.__kiokuFS.writeFile(path, data);
      log(`fetched ${url} → ${path} (${data.length} bytes)`);
      wait = w;
    } else if (kind === "dom") {
      log("dom " + String((0, eval)(step[1])));
      wait = step[2];
    } else if (kind === "waitfor") {
      const [, text, ms] = step;
      const end = performance.now() + ms;
      while (!seen.some((s) => s.includes(text)) && performance.now() < end) await sleep(500);
      if (!seen.some((s) => s.includes(text))) log(`CHECK waitfor ${text} FAIL timed out`);
    } else if (kind === "shot") {
      log(`SHOT ${step[1]}`);
      // the runner polls the log every 2 s
      wait = step[2] || 4000;
    }
    await sleep(wait);
  }

  (async function () {
    // ?selftestPhase=N: the runner opened this phase in a new tab (newtab)
    const params = new URLSearchParams(location.search);
    const newTab = params.has("selftestPhase");
    const phase = Number(params.get("selftestPhase") || sessionStorage.getItem("kiokuSelftestPhase") || 0);
    const { phases } = await (await fetch("/__selftest/steps.json")).json();
    if (phase >= phases.length) return;
    log(`SELFTEST phase ${phase + 1}/${phases.length}: ${navigator.userAgent}`);
    log(`crossOriginIsolated ${self.crossOriginIsolated}`);
    // the experimental notice; then wait for aqt (as boot.mjs does)
    const notice = () => document.querySelector("#warning")?.close();
    if (document.readyState === "complete") notice();
    else addEventListener("load", notice);
    const start = performance.now();
    while (!seen.some((s) => s.includes("Starting Anki"))) {
      if (performance.now() - start > 300000) {
        log("SELFTEST FAIL: Anki not started after 5 minutes");
        log("SELFTEST DONE");
        return;
      }
      await sleep(300);
    }
    await sleep(1500);
    for (const step of phases[phase]) {
      try {
        await run(step);
      } catch (e) {
        log(`CHECK step ${step[0]} FAIL ${e}`);
      }
    }
    log(`WORKERS created ${workers.created}, ran threads ${workers.used.size}`);
    sessionStorage.setItem("kiokuSelftestPhase", String(phase + 1));
    if (phase + 1 < phases.length && newTab) {
      // a fresh tab (its own web process), as when the app is opened again
      log(`SELFTEST newtab ${phase + 1}`);
      send();
      // and this one closes, as the app would be: an old tab holding its
      // memory in the background isn't what a user has
      setTimeout(() => location.replace("about:blank"), 1500);
    } else if (phase + 1 < phases.length) {
      log("SELFTEST reload");
      send();
      await sleep(1000);
      location.reload();
    } else {
      log("SELFTEST DONE");
    }
  })();
})();
