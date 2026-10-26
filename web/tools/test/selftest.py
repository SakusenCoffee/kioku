"""The smoke test (smoke.py) in browsers that can't be driven from outside:
Safari, iOS Safari (the iOS Simulator or an iPhone). tools/serve.py runs with
KIOKU_SELFTEST on a fresh port (so a fresh origin: empty storage), the page
runs the steps itself (selftest.js) and posts its console back; this prints
one PASS/FAIL line per check, as smoke.py does. The steps find buttons and
fields in Anki's pages by selector instead of screen coordinates, so any
window size works.

Usage: python3 tools/test/selftest.py safari|ios|iphone|chrome [deck.apkg with media]
THREADS=N, MEMORY=MB open the page with ?threads=N (workers made up
front), ?memory=MB (the wasm memory's maximum).
ONLY=idle only starts the app, ONLY=import also imports the deck, ONLY=restart then opens
it 3 more times with the saved collection (memory measurements). ONLY=bench runs only the benchmark, twice (bench_code.py; in the native iOS
app: ios/tools/devcmd.sh < tools/test/bench_code.py). ONLY=cross runs only
the cross-origin check (a card with images and a script from another
origin, served here: with CORS but no CORP, and with neither).
  safari  opens a tab in Safari (left open afterwards)
  ios     boots an iPhone simulator and opens Safari there (IOS_DEVICE=<name
          or UDID> to pick one); screenshots of the SHOT steps
  iphone  Safari on a connected iPhone (IPHONE=<UDID>, else the first paired
          one) over the LAN, each phase in a new tab as when the app is
          opened again (RELOAD=1: reload the tab, as the other browsers do;
          the old page's memory is still held then). The page needs https there (a secure context):
          a certificate for the Mac's LAN address in build/tls/lan.pem and
          lan-key.pem (mkcert), whose CA the iPhone trusts (KIOKU_LAN_IP to
          pick the address, else en0's)
  chrome  headless Chrome, to check the self-test itself against smoke.py
Needs tools/serve.py's build (build/cmake by default; BUILD=<dir>)."""

import http.server
import json
import os
import re
import shutil
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "../.."))
sys.argv, ARGS = sys.argv[:1], sys.argv[1:]
import smoke  # noqa: E402  (reads sys.argv at import)
from smoke import AV_HOOK, CLOSE_OTHERS, check, py  # noqa: E402

BROWSER = ARGS[0] if ARGS else "safari"
DECK = os.path.abspath(ARGS[1] if len(ARGS) > 1 else smoke.DECK)
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def rest_of_first() -> list:
    """smoke.first after its import check, its toolbar clicks as Python."""
    steps = smoke.first
    start = next(i for i, s in enumerate(steps) if s[0] == "py" and "SoundOrVideoTag" in s[1])
    out = []
    for s in steps[start:]:
        if s[:3] == ["click", 500, 37]:
            out.append(py("import aqt\naqt.dialogs.open('Browser', aqt.mw)", s[3]))
        elif s[:3] == ["click", 575, 37]:
            out.append(py("import aqt\naqt.mw.onStats()", s[3]))
            out.append(["frames", "stats: graphs render", "document.querySelectorAll('svg').length > 0", 0])
        else:
            out.append(s)
    return out


qa = "document.querySelector('#qa') && document.querySelector('#qa').innerText.includes"
FIRST = [
    ["wait", 5000],
    ["firstrun"],
    ["wait", 6000],
    check("start: profile and collection open", "mw.col is not None and mw.pm.name is not None"),
    ["frames", "deck list renders", "document.body.innerText.includes('Default')", 0],
    AV_HOOK,
    # Add: the editor page, two fields typed, the window's Add button
    py("import aqt\naqt.mw.onAddCard()", 9000),
    ["frames", "add: editor renders", "deepAll(document, 'anki-editable').length >= 2", 0],
    ["type", "anki-editable", 0, "Smoke front", 800],
    ["type", "anki-editable", 1, "Smoke back", 800],
    py("import aqt\nfrom aqt.qt import QApplication\n"
       "[w.addButton.click() for w in QApplication.topLevelWidgets() if type(w).__name__ == 'AddCards']", 4000),
    check("add note through the editor",
          "(mw.col.note_count() == 1 and 'Smoke front' in mw.col.get_note(mw.col.find_notes('')[0]).fields[0], "
          "[mw.col.get_note(i).fields for i in mw.col.find_notes('')])"),
    CLOSE_OTHERS,
    # study: overview's Study Now, question, answer, Good
    py("import aqt\naqt.mw.col.decks.select(1)\naqt.mw.moveToState('overview')", 4000),
    ["click", "#study", "", 5000],
    ["frames", "review: question shows", qa + "('Smoke front')", 0],
    py("import aqt\naqt.mw.reviewer._showAnswer()", 2500),
    ["frames", "review: answer shows", qa + "('Smoke back')", 0],
    py("import aqt\naqt.mw.reviewer._answerCard(3)", 3000),
    check("review: answer a card",
          "(mw.col.db.scalar('select count() from revlog') >= 1, mw.col.db.scalar('select count() from revlog'))"),
    py("import aqt\naqt.mw.moveToState('deckBrowser')", 3000),
    # import a deck with media: Anki's import page and its Import button
    ["fetch", "/__selftest/deck.apkg", "/tmp/selftest/deck.apkg", 0],
    py("import aqt\nfrom aqt.import_export.importing import import_file\nimport_file(aqt.mw, '/tmp/selftest/deck.apkg')", 15000),
    ["click", "button", "Import", 30000],
    check("import .apkg with media",
          "(mw.col.note_count() > 1 and len(os.listdir(mw.col.media.dir())) > 0, "
          "(mw.col.note_count(), len(os.listdir(mw.col.media.dir()))))"),
    CLOSE_OTHERS,
    ["shot", "imported"],
] + rest_of_first()

# what the page keeps in IndexedDB (storage.js): the profile folder
STORAGE = py("import os\nfiles = [os.path.join(d, f) for d, _, fs in os.walk('/home/web_user') for f in fs]\n"
             "sizes = sorted(((os.path.getsize(f), f) for f in files), reverse=True)\n"
             "print('STORAGE', len(files), 'files', sum(s for s, _ in sizes) // 1048576, 'MB; largest',"
             " [(f.replace('/home/web_user/', ''), s // 1048576) for s, f in sizes[:4]])", 1000)
FIRST.insert(len(FIRST) - len(rest_of_first()), STORAGE)
FIRST.append(STORAGE)

PHASES = [FIRST, smoke.second, smoke.extra]

def png() -> bytes:
    """A 1x1 PNG."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00\xff")) + chunk(b"IEND", b""))


PNG = png()


class OtherOrigin(http.server.BaseHTTPRequestHandler):
    """Another origin for the cross-origin check: cors.* with CORS but no
    Cross-Origin-Resource-Policy (blocked by require-corp unless sw.js
    fetches it with CORS), plain.png with neither."""

    def do_GET(self) -> None:
        name = self.path.split("?")[0].lstrip("/")
        body = {"cors.png": PNG, "plain.png": PNG, "cors.js": b"window.kiokuCorsScript = 1;"}.get(name)
        if body is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/javascript" if name.endswith(".js") else "image/png")
        if name.startswith("cors."):
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        pass


def cross_phase(origin: str) -> list:
    front = (f'<img id="cors" src="{origin}/cors.png"><img id="plain" src="{origin}/plain.png">'
             f'<script src="{origin}/cors.js"></script>Cross front')
    img = "(i => i && i.complete && i.naturalWidth > 0)(document.getElementById('{}'))"
    return [
        ["wait", 5000],
        ["firstrun"],
        ["wait", 6000],
        py("import aqt\nmw = aqt.mw\nn = mw.col.new_note(mw.col.models.by_name('Basic'))\n"
           f"n['Front'] = {front!r}\nn['Back'] = 'Cross back'\nmw.col.add_note(n, 1)\n"
           "mw.col.decks.select(1)\nmw.moveToState('review')", 10000),
        ["frames", "review: card with cross-origin content shows", "document.body.innerText.includes('Cross front')", 0],
        ["frames", "cross-origin image with CORS loads", img.format("cors"), 0],
        ["frames", "cross-origin script with CORS runs", "document.defaultView.kiokuCorsScript === 1", 0],
        ["probe", "image without CORS or CORP loads (credentialless only)", img.format("plain")],
        ["shot", "cross"],
    ]


def bench_phase() -> list:
    with open(os.path.join(HERE, "bench_code.py")) as f:
        code = f.read()
    return [["wait", 5000], ["firstrun"], ["wait", 6000], py(code, 1000), ["waitfor", "BENCH", 600000]]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def ios_device() -> str:
    want = os.environ.get("IOS_DEVICE", "")
    devices = json.loads(subprocess.check_output(["xcrun", "simctl", "list", "devices", "available", "-j"]))["devices"]
    phones = [
        (runtime, d) for runtime, ds in devices.items() if "iOS" in runtime for d in ds
        if (want and want in (d["name"], d["udid"])) or (not want and d["name"].startswith("iPhone"))
    ]
    if not phones:
        sys.exit("no iPhone simulator available")
    booted = [d for _, d in phones if d["state"] == "Booted"]
    device = booted[0] if booted else sorted(phones, key=lambda p: p[0])[-1][1]
    if device["state"] != "Booted":
        subprocess.run(["xcrun", "simctl", "boot", device["udid"]], check=True)
        subprocess.run(["xcrun", "simctl", "bootstatus", device["udid"]], check=True, capture_output=True)
    print(f"iOS simulator: {device['name']} ({device['udid']})")
    return device["udid"]


def iphone() -> str:
    want = os.environ.get("IPHONE")
    if want:
        return want
    out = os.path.join(tempfile.mkdtemp(), "devices.json")
    subprocess.run(["xcrun", "devicectl", "list", "devices", "--json-output", out], check=True, capture_output=True)
    for d in json.load(open(out))["result"]["devices"]:
        props = d.get("hardwareProperties", {})
        if props.get("reality") == "physical" and props.get("platform") == "iOS":
            print(f"iPhone: {d['deviceProperties']['name']} ({props['udid']})")
            return props["udid"]
    sys.exit("no iPhone connected")


def lan() -> tuple[str, ssl.SSLContext]:
    """The Mac's LAN address and a TLS context with its certificate."""
    ip = os.environ.get("KIOKU_LAN_IP") or subprocess.run(
        ["ipconfig", "getifaddr", "en0"], capture_output=True, text=True).stdout.strip()
    cert, key = os.path.join(ROOT, "build/tls/lan.pem"), os.path.join(ROOT, "build/tls/lan-key.pem")
    if not ip or not os.path.isfile(cert):
        sys.exit("needs a LAN address and build/tls/lan.pem (see Usage)")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    return ip, context


def open_on_iphone(url: str, log_path: str) -> None:
    """Open url in Safari on the iPhone. devicectl sometimes reports
    "Connection reset by peer" although Safari did open it: retrying then
    opened a second tab running the same test (same storage, a 404 when one
    tab imported the other's file), so only retry when no page started."""
    udid = iphone()

    def pages() -> int:
        return open(log_path, encoding="utf-8", errors="replace").read().count("SELFTEST phase")

    before = pages()
    for _ in range(5):
        if subprocess.run(["xcrun", "devicectl", "device", "process", "launch", "--device", udid,
                           "--payload-url", url, "com.apple.mobilesafari"], capture_output=True).returncode == 0:
            return
        for _ in range(20):
            time.sleep(1)
            if pages() > before:
                return
    sys.exit("could not open Safari on the iPhone")


def main() -> None:
    work = tempfile.mkdtemp(prefix=f"kioku-selftest-{BROWSER}-")
    env = dict(os.environ, KIOKU_SELFTEST=work)
    host, scheme = "127.0.0.1", "http"
    other = http.server.ThreadingHTTPServer((host, free_port()), OtherOrigin)
    if BROWSER == "iphone":
        host, context = lan()
        scheme = "https"
        other = http.server.ThreadingHTTPServer((host, free_port()), OtherOrigin)
        other.socket = context.wrap_socket(other.socket, server_side=True)
        build_tls = os.path.join(ROOT, "build/tls")
        env.update(KIOKU_HOST=host, KIOKU_TLS=f"{build_tls}/lan.pem:{build_tls}/lan-key.pem")
    threading.Thread(target=other.serve_forever, daemon=True).start()
    port = free_port()
    build = os.environ.get("BUILD", os.path.join(ROOT, "build/cmake"))
    server = subprocess.Popen([sys.executable, os.path.join(ROOT, "tools/serve.py"), build, str(port)],
                              env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"{scheme}://{host}:{port}/app.html"
    other_origin = f"{scheme}://{host}:{other.server_address[1]}"
    params = [f"{name.lower()}={int(os.environ[name])}" for name in ("THREADS", "MEMORY") if os.environ.get(name)]
    new_tabs = BROWSER == "iphone" and not os.environ.get("RELOAD")
    if new_tabs:
        params.append("selftestPhase=0")
    if params:
        url += "?" + "&".join(params)
    cross = [cross_phase(other_origin)]
    with open(os.path.join(work, "steps.json"), "w") as f:
        only = os.environ.get("ONLY")
        idle = [["wait", 5000], ["firstrun"], ["wait", 30000]]
        imp = [["wait", 5000], ["firstrun"], ["wait", 10000], *[x for x in FIRST if x[0] == "fetch" or
               (x[0] == "py" and "import_file" in x[1]) or (x[0] == "click" and x[2] == "Import")], ["wait", 20000], STORAGE]
        phases = (cross if only == "cross" else [bench_phase(), bench_phase()] if only == "bench"
                  else [idle] if only == "idle" else [imp] if only == "import"
                  else [imp] + [[["wait", 15000], STORAGE]] * 3 if only == "restart" else PHASES + cross)
        json.dump({"phases": phases}, f)
    shutil.copy(DECK, os.path.join(work, "deck.apkg"))
    log_path = os.path.join(work, "log.txt")
    open(log_path, "w").close()
    browser = None
    udid = None
    time.sleep(1)
    try:
        if BROWSER == "iphone":
            open_on_iphone(url, log_path)
        elif BROWSER == "safari":
            subprocess.run(["open", "-a", "Safari", url], check=True)
        elif BROWSER == "ios":
            udid = ios_device()
            subprocess.run(["xcrun", "simctl", "openurl", udid, url], check=True)
        elif BROWSER == "chrome":
            browser = subprocess.Popen([CHROME, "--headless=new", f"--user-data-dir={work}/chrome",
                                        "--window-size=1000,700", "--autoplay-policy=no-user-gesture-required", url],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            sys.exit(f"unknown browser {BROWSER}")
        print(f"{BROWSER}: {url}; log in {log_path}")
        shots = 0
        opened = 0
        deadline = time.time() + 1500
        while time.time() < deadline:
            time.sleep(2)
            logs = open(log_path, encoding="utf-8", errors="replace").read()
            if new_tabs and (m := re.findall(r"SELFTEST newtab (\d+)", logs)) and len(m) > opened:
                opened = len(m)
                open_on_iphone(url.replace("selftestPhase=0", f"selftestPhase={m[-1]}"), log_path)
            for name in re.findall(r"SHOT (\S+)", logs)[shots:]:
                shots += 1
                if udid:
                    subprocess.run(["xcrun", "simctl", "io", udid, "screenshot", os.path.join(work, f"{name}.png")],
                                   capture_output=True)
            if "SELFTEST DONE" in logs:
                break
        else:
            logs += "\nSELFTEST FAIL: timed out\n"
        if udid:
            subprocess.run(["xcrun", "simctl", "io", udid, "screenshot", os.path.join(work, "end.png")],
                           capture_output=True)
    finally:
        if browser:
            browser.terminate()
        server.terminate()
    results = re.findall(r"CHECK '?(.+?)'? (PASS|FAIL) ?(.*)", logs)
    downloads = re.findall(r"download completed (\d+) bytes", logs)
    for bench in re.findall(r"BENCH (\{.+\})", logs):
        print("bench:", bench)
    if not os.environ.get("ONLY"):
        results.append(("export .apkg downloads", "PASS" if downloads else "FAIL", f"{downloads[0]} bytes" if downloads else ""))
    results += [(line, "FAIL", "") for line in re.findall(r"SELFTEST FAIL: (.+)", logs)]
    agent = re.search(r"SELFTEST phase 1/\d+: (.+)", logs)
    print("user agent:", agent.group(1) if agent else "?")
    print("isolated:", ", ".join(re.findall(r"crossOriginIsolated (\w+)", logs)))
    print("workers per page load:", "; ".join(re.findall(r"WORKERS (.+)", logs)))
    starts = re.findall(r"SELFTEST phase (\d+)/", logs)
    print("page loads per phase:", {p: starts.count(p) for p in sorted(set(starts), key=int)})
    for line in re.findall(r"STORAGE (.+)", logs):
        print("storage:", line)
    for name, status, detail in results:
        print(f"{status}  {name}  {detail}".rstrip())
    for probe in re.findall(r"PROBE (.+)", logs):
        print("info ", probe)
    for e in sorted(set(re.findall(r"pageerror (.+)", logs))):
        print("page error:", e[:160])
    failed = sum(1 for r in results if r[1] == "FAIL")
    print(f"\n{len(results) - failed}/{len(results)} passed; log and screenshots in {work}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
