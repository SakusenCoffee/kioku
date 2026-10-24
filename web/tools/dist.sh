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
cp "$SRC"/{app.html,kioku-web.js,sw.js,kioku.js,qtloader.js,app.data,app-data.js.metadata} "$OUT/"
cp "$ROOT"/cloudflare/{_headers,_redirects} "$OUT/"
for f in kioku.wasm kioku.data; do
    # compressing takes a minute or two: keep it while the file is unchanged
    # (brotli gives the .br its source's time)
    if [ ! -f "$SRC/$f.br" ] || [ "$SRC/$f" -nt "$SRC/$f.br" ]; then
        echo "compressing $f"
        brotli -f -q 11 -w 24 -o "$SRC/$f.br" "$SRC/$f"
    fi
    cp "$SRC/$f.br" "$OUT/"
done
for f in "$OUT"/*; do
    if [ "$(wc -c < "$f")" -gt "$LIMIT" ]; then
        echo "$f is over Cloudflare's 25 MiB limit" >&2
        exit 1
    fi
done
ls -l "$OUT"
