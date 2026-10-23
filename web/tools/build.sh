#!/bin/bash
# Configure (once) and build kioku.wasm with the app page (build/cmake).
# The Python files are packed at link time: after changing only Python,
# `touch src/main.cpp` before building.
set -euo pipefail
source "$(dirname "$0")/env.sh"
source "$ROOT/deps/emsdk/emsdk_env.sh" >/dev/null 2>&1
if [ ! -f "$ROOT/build/cmake/build.ninja" ]; then
    "$ROOT/deps/qt/6.11.0/wasm_multithread/bin/qt-cmake" -S "$ROOT" -B "$ROOT/build/cmake" -G Ninja \
        -DCMAKE_BUILD_TYPE=Release -DQT_HOST_PATH="$ROOT/deps/qt/6.11.0/macos" \
        -DKIOKU_REPO="$KIOKU_REPO" -DKIOKU_ASYNCIFY=ON
fi
ninja -C "$ROOT/build/cmake"
