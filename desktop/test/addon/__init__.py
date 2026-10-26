# Test add-on for desktop/test/run.sh: runs /config/test/cmd.py on Anki's
# main thread when it appears, with `mw` and `out` (a dict) in scope, and
# writes `out` to /config/test/out.json. Also records profile open/close
# in /config/test/events.log.
import json
import os
import time
import traceback

from aqt import gui_hooks, mw
from aqt.qt import QTimer

DIR = "/config/test"
os.makedirs(DIR, exist_ok=True)


def event(name: str) -> None:
    with open(f"{DIR}/events.log", "a") as f:
        f.write(f"{time.time():.3f} {os.getpid()} {name}\n")


def poll() -> None:
    cmd = f"{DIR}/cmd.py"
    if not os.path.exists(cmd):
        return
    with open(cmd) as f:
        code = f.read()
    os.remove(cmd)
    out: dict = {}
    try:
        exec(code, {"mw": mw, "out": out})
    except Exception:
        out["error"] = traceback.format_exc()
    with open(f"{DIR}/out.json.tmp", "w") as f:
        json.dump(out, f, default=str)
    os.replace(f"{DIR}/out.json.tmp", f"{DIR}/out.json")


timer = QTimer(mw)
timer.timeout.connect(poll)
timer.start(200)
event("start")
gui_hooks.profile_did_open.append(lambda: event("open"))
gui_hooks.profile_will_close.append(lambda: event("close"))
