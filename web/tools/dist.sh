#!/bin/bash
# Assemble build/dist from a build (build/cmake) for hosting on Cloudflare
# (cloudflare/): the page's files, with kioku.wasm and kioku.data
# brotli-compressed because Cloudflare takes files up to 25 MiB
# (cloudflare/worker.js serves them with Content-Encoding: br).
# Usage: dist.sh [build dir] [out dir]
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
SRC=${1:-$ROOT/build/cmake}
OUT=${2:-$ROOT/build/dist}
LIMIT=$((25 * 1024 * 1024))
rm -rf "$OUT"
mkdir -p "$OUT"
cp "$SRC"/{app.html,kioku-web.js,server.js,sw.js,manifest.webmanifest,kioku.js,qtloader.js,app.data,app-data.js.metadata} "$OUT/"
cp -R "$SRC/icons" "$OUT/"
cp "$ROOT"/cloudflare/_redirects "$OUT/"
for f in kioku.wasm kioku.data; do
    # compressing takes a minute or two: keep it while the file is unchanged
    # (brotli gives the .br its source's time)
    if [ ! -f "$SRC/$f.br" ] || [ "$SRC/$f" -nt "$SRC/$f.br" ]; then
        echo "compressing $f"
        brotli -f -q 11 -w 24 -o "$SRC/$f.br" "$SRC/$f"
    fi
    cp "$SRC/$f.br" "$OUT/"
done
# their real sizes, for the page's download progress (Content-Length is
# the compressed size)
printf '{"kioku.wasm": %d, "kioku.data": %d, "app.data": %d}\n' \
    "$(wc -c < "$SRC/kioku.wasm")" "$(wc -c < "$SRC/kioku.data")" "$(wc -c < "$SRC/app.data")" > "$OUT/sizes.json"
for f in "$OUT"/*; do
    if [ "$(wc -c < "$f")" -gt "$LIMIT" ]; then
        echo "$f is over Cloudflare's 25 MiB limit" >&2
        exit 1
    fi
done
ls -l "$OUT"
