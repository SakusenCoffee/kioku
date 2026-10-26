// Drive the streamed desktop in Chrome: log in, wait for the first
// video frame, then run the steps given as JSON in argv[2]. The remote
// screen is sized to the viewport, so coordinates are the remote's. Steps:
//   ["wait", ms]          ["click", x, y]      ["key", "Enter"] (or "Alt+y")
//   ["type", "text"]      ["shot", "name"]     (name.png in SHOTS)
//   ["upload", path]      a file (read here), as the sidebar's Upload does
//   ["painted"]           fails unless the stream shows a picture (not one colour)
// Env: URL (default http://localhost:3000/), LOGIN/PASSWORD (basic auth),
// CHROME (browser path, started headless) or CHROME_URL (a running Chrome's
// --remote-debugging-port, e.g. http://localhost:9222, to watch it), VIEWPORT (WxH; 430x932 is a phone: touch, 3x pixels),
// SHOTS (folder for screenshots, default .)
import { readFileSync } from "node:fs";
import { basename } from "node:path";
import puppeteer from "puppeteer-core";

const steps = JSON.parse(process.argv[2] || "[]");
const browser = process.env.CHROME_URL
  ? await puppeteer.connect({ browserURL: process.env.CHROME_URL, defaultViewport: null })
  : await puppeteer.launch({
      executablePath: process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
      headless: true,
      args: ["--autoplay-policy=no-user-gesture-required", "--ignore-certificate-errors", "--no-sandbox"],
    });
const t0 = Date.now();
const log = (s) => console.log(`[${((Date.now() - t0) / 1000).toFixed(1)}s] ${s}`);
let failed = false;
const page = await browser.newPage();
try {
  const [width, height] = (process.env.VIEWPORT || "1280x800").split("x").map(Number);
  const phone = width < 800;
  await page.setViewport({ width, height, deviceScaleFactor: phone ? 3 : 1, isMobile: phone, hasTouch: phone });
  if (process.env.PASSWORD) await page.authenticate({ username: process.env.LOGIN || "anki", password: process.env.PASSWORD });
  let frames = 0;
  page.on("console", (m) => { if (m.text().includes("Stream started")) frames++; });
  page.on("pageerror", (e) => log("pageerror " + e.message.slice(0, 500)));
  const res = await page.goto(process.env.URL || "http://localhost:3000/", { waitUntil: "networkidle2" });
  log(`page ${res.status()}`);
  if (res.status() !== 200) throw new Error(`page answered ${res.status()}`);
  for (let i = 0; i < 300 && !frames; i++) await new Promise((r) => setTimeout(r, 100));
  if (!frames) throw new Error("no video stream within 30 s");
  log("stream started");
  await new Promise((r) => setTimeout(r, 3000));
  for (const [op, ...a] of steps) {
    if (op === "wait") await new Promise((r) => setTimeout(r, a[0]));
    else if (op === "click") await page.mouse.click(a[0], a[1]);
    else if (op === "key") {
      // "Alt+y": modifiers held while the last key is pressed
      const keys = a[0].split("+");
      for (const k of keys.slice(0, -1)) await page.keyboard.down(k);
      await page.keyboard.press(keys.at(-1));
      for (const k of keys.slice(0, -1).reverse()) await page.keyboard.up(k);
    }
    else if (op === "type") await page.keyboard.type(a[0], { delay: 50 });
    else if (op === "shot") await page.screenshot({ path: `${process.env.SHOTS || "."}/${a[0]}.png` });
    // the sidebar's Upload button: the file lands in the session's ~/Desktop
    // (the bytes are handed to the page, so the browser may be on another computer)
    else if (op === "upload")
      await page.evaluate((name, b64) => {
        const input = document.getElementById("globalFileInput");
        const dt = new DataTransfer();
        dt.items.add(new File([Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))], name));
        input.files = dt.files;
        input.dispatchEvent(new Event("change", { bubbles: true }));
      }, basename(a[0]), readFileSync(a[0]).toString("base64"));
    else if (op === "painted") {
      // distinct colours on the video canvas: a blank or frozen-black stream
      // has 1 (the desktop is empty until Anki's first window, up to 30 s)
      let colours = 0;
      for (let i = 0; i < 60 && colours < 10; i++) {
        if (i) await new Promise((r) => setTimeout(r, 500));
        // counted on a screenshot: the video canvas is drawn by a worker
        const png = await page.screenshot({ encoding: "base64" });
        colours = await page.evaluate(async (png) => {
          const img = new Image();
          img.src = "data:image/png;base64," + png;
          await img.decode();
          const c = document.createElement("canvas");
          c.width = img.width; c.height = img.height;
          const g = c.getContext("2d");
          g.drawImage(img, 0, 0);
          const d = g.getImageData(0, 0, c.width, c.height).data;
          const seen = new Set();
          for (let i = 0; i < d.length; i += 4 * 97) seen.add((d[i] << 16) | (d[i + 1] << 8) | d[i + 2]);
          return seen.size;
        }, png);
      }
      log(`painted: ${colours} colours`);
      if (colours < 10) throw new Error("the stream shows no picture");
    } else throw new Error(`unknown step ${op}`);
    log(`${op} ${JSON.stringify(a)}`);
  }
} catch (e) {
  log(`FAIL ${e.message}`);
  failed = true;
}
await page.close();
if (process.env.CHROME_URL) browser.disconnect(); else await browser.close();
process.exit(failed ? 1 : 0);
