// Drive Kioku in headless Chrome: open app.html (served by tools/serve.py on
// port 8765), get through the first-run language dialogs, then run the
// steps given as JSON in argv[2]. The coordinates in steps are for the
// 1000x700 viewport. Steps:
//   ["wait", ms]              ["click", x, y, waitMs]    ["key", "Space", waitMs]
//   ["type", "text"]          ["shot", "name"]           (name.png)
//   ["upload", path, [x, y], waitMs]   click (x, y), which opens the file picker
//   ["py", "code"]            run Python in Kioku (dev hook), prints `result`
//   ["dom", "js"]             evaluate JavaScript on the app page
//   ["frames"]                state of each web view iframe
//   ["pause"]                 stack of the main thread (link with --profiling-funcs)
// Env: URL (app page, default http://127.0.0.1:8765/app.html), CHROME (browser path), NOFIRSTRUN=1 (profile already set up),
// PROFILE (Chrome user data folder; keep it to test saved data across runs)
import puppeteer from "puppeteer-core";
const steps = JSON.parse(process.argv[2] || "[]");
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: true, protocolTimeout: 600000,
  userDataDir: process.env.PROFILE || undefined,
});
const page = await browser.newPage();
await page.setViewport({ width: 1000, height: 700 });
const t0 = Date.now();
const log = (s) => console.log(`[${((Date.now() - t0) / 1000).toFixed(1)}s] ${s}`);
page.on("console", (m) => { const t = m.text(); if (!/OpenType|null function/.test(t)) log(t.slice(0, 400)); });
page.on("pageerror", (e) => log("pageerror " + (process.env.STACK ? e.stack : e.message).slice(0, 3000)));
// exports (kioku_platform.files) land in the current folder
const bclient = await browser.target().createCDPSession();
await bclient.send("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: process.cwd(), eventsEnabled: true });
bclient.on("Browser.downloadWillBegin", (e) => log(`download ${e.suggestedFilename}`));
bclient.on("Browser.downloadProgress", (e) => { if (e.state !== "inProgress") log(`download ${e.state} ${e.receivedBytes} bytes`); });
const client = await page.createCDPSession();
await client.send("Debugger.enable");
let started = false;
page.on("console", (m) => { if (m.text().includes("Starting Anki")) started = true; });
await page.goto(process.env.URL || "http://127.0.0.1:8765/app.html");
// the "experimental" notice would take the clicks and keys
await page.evaluate(() => document.querySelector("#warning")?.close());
while (!started) await new Promise((r) => setTimeout(r, 300));
await new Promise((r) => setTimeout(r, 1500));
if (!process.env.NOFIRSTRUN) {
  page.keyboard.press("Enter").catch(() => {});
  await new Promise((r) => setTimeout(r, 3000));
  page.mouse.click(854, 376).catch(() => {});
}
for (const s of steps) {
  const [kind, a, b, wait] = s;
  if (kind === "wait") await new Promise((r) => setTimeout(r, a));
  else if (kind === "click") page.mouse.click(a, b).catch(() => {});
  else if (kind === "key") page.keyboard.press(a).catch(() => {});
  else if (kind === "type") await page.keyboard.type(a, { delay: 30 });
  else if (kind === "shot") {
    const ok = await Promise.race([page.screenshot({ path: `${a}.png` }).then(() => true), new Promise((r) => setTimeout(() => r(false), 15000))]);
    log(`shot ${a}: ${ok ? "ok" : "TIMED OUT"}`);
  } else if (kind === "py") {
    await page.evaluate((code) => window.__kiokuWeb.post({ type: "devexec", code }), a);
  } else if (kind === "dom") {
    log("dom " + await page.evaluate((code) => String(eval(code)), a));
  } else if (kind === "frames") {
    for (const f of page.frames()) {
      if (f === page.mainFrame()) continue;
      try {
        const info = await f.evaluate(() => JSON.stringify({
          url: location.pathname + location.search,
          kioku: typeof window.__kiokuNative, prelude: !!window.__kioku, init: !!window.__kiokuInit,
          pycmd: typeof window.pycmd, scripts: [...document.scripts].map((s) => s.src.replace(location.origin, "") || "inline").slice(0, 12),
        }));
        log("frame " + info);
      } catch (e) { log("frame error " + e.message); }
    }
  } else if (kind === "pause") {
    const paused = new Promise((r) => client.once("Debugger.paused", r));
    await client.send("Debugger.pause");
    const ev = await paused;
    for (const f of ev.callFrames.slice(0, 70)) log("  " + f.functionName + " " + (f.url || "").split("/").pop() + ":" + f.location.lineNumber);
    await client.send("Debugger.resume");
  } else if (kind === "upload") {
    const [chooser] = await Promise.all([page.waitForFileChooser({ timeout: 20000 }), page.mouse.click(b[0], b[1])]);
    await chooser.accept([a]);
    log("uploaded " + a);
  }
  if (wait) await new Promise((r) => setTimeout(r, wait));
}
await browser.close();
