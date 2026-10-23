#!/bin/bash
# Pack the app's own Python (Kioku's shared package, kioku_platform, the
# probe) into app.data next to kioku.wasm and copy the page files (shell/).
# Run by ninja on every build; changing them needs no relink: kioku.js
# loads app.data through app-data.js (--pre-js), whose package details are
# in app-data.js.metadata.
set -euo pipefail
source "$(dirname "$0")/env.sh"
OUT=${1:-$ROOT/build/cmake}
TMP="$OUT/.pack"
mkdir -p "$TMP"
python3 "$ROOT/deps/emsdk/upstream/emscripten/tools/file_packager.py" "$TMP/app.data" \
    --preload "$KIOKU_REPO/shared/python/kioku@/app/kioku" \
              "$KIOKU_REPO/shared/python/PyQt6@/app/PyQt6" \
              "$ROOT/python/kioku_platform@/app/kioku_platform" \
              "$ROOT/app/probe.py@/app/probe.py" \
    --exclude '*__pycache__*' --js-output="$TMP/app-data.js" --separate-metadata --no-node \
    2> /dev/null
mv "$TMP/app.data" "$TMP/app-data.js.metadata" "$OUT/"
# keep the loader's timestamp unless it changed, so the link stays up to date
cmp -s "$TMP/app-data.js" "$OUT/app-data.js" || mv "$TMP/app-data.js" "$OUT/app-data.js"
rm -rf "$TMP"
cp "$ROOT/shell/app.html" "$ROOT/shell/sw.js" "$ROOT/shell/kioku-web.js" "$OUT/"
