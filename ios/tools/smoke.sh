#!/bin/bash
# Run tools/smoke.py in the app (launched with KIOKU_DEV=1, see run_device.sh)
# and print only its result: the SWEEP lines, tracebacks and new crash
# reports.
# Env: KIOKU_DEVICE  device id (default: the first connected iPhone)
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
DEV=${KIOKU_DEVICE:-$(xcrun devicectl list devices 2>/dev/null | grep physical \
    | grep -oE '[0-9A-F]{8}-[0-9A-F]{16}' | head -1)}
LOG=$ROOT/build/device-logs/kioku.log
crashes() {
    xcrun devicectl device info files --device "$DEV" --domain-type systemCrashLogs 2>/dev/null \
        | grep -oE 'Kioku-[0-9-]+\.ips' | sort
}
fetch() {
    xcrun devicectl device copy from --device "$DEV" --domain-type appDataContainer \
        --domain-identifier io.ankidesk.kioku --source Documents/kioku.log \
        --destination "$LOG" > /dev/null 2>&1
}
BEFORE=$(crashes)
"$ROOT/tools/devcmd.sh" < "$ROOT/tools/smoke.py" | tail -1
STEPS=$(grep -c '^    ("' "$ROOT/tools/smoke.py")
for _ in $(seq 1 $((STEPS * 3 + 20))); do
    sleep 2
    fetch
    grep -q "SWEEP done" "$LOG" 2> /dev/null && break
done
grep -q "SWEEP done" "$LOG" 2> /dev/null || echo "!! no \"SWEEP done\": Kioku crashed, quit or hangs"
# steps that left nothing open are only counted; a step that never finished
# is the one that crashed
grep -E "^SWEEP |^Traceback|Error:" "$LOG" \
    | awk '/: start$/ {last=$0; next} /: ok$/ {last=""; next} /: ok/ {last=""} {print}
           END {if (last) print "!! never finished:", last}'
NEW=$(comm -13 <(echo "$BEFORE") <(crashes))
[ -n "$NEW" ] && echo "!! new crash reports: $NEW"
echo "steps ok: $(grep -c '^SWEEP .*: ok' "$LOG")/$STEPS"
