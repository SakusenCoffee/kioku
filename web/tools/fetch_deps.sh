#!/bin/bash
# Emscripten 4.0.7 (the version Qt 6.11's wasm libraries are built with) and
# Qt 6.11 for WebAssembly (multithread) into deps/. Host Qt comes from the
# Kioku repository's iOS build (tools/env.sh).
set -euo pipefail
source "$(dirname "$0")/env.sh"
mkdir -p "$ROOT/deps"
cd "$ROOT/deps"
if [ ! -d emsdk ]; then
    git clone -q --depth 1 https://github.com/emscripten-core/emsdk.git
    emsdk/emsdk install 4.0.7
    emsdk/emsdk activate 4.0.7
fi
if [ ! -d qt/6.11.0/wasm_multithread ]; then
    uvx --from aqtinstall aqt install-qt all_os wasm 6.11.0 wasm_multithread -O qt \
        -b https://mirrors.ocf.berkeley.edu/qt/
fi
ln -sfn "$KIOKU_REPO/ios/deps/qt/6.11.0/macos" qt/6.11.0/macos
# aqt's qmake wrapper calls host qmake relative to the current directory
sed -i '' 's#^qt/6.11.0/macos/bin/qmake6#"$script_dir_path/../../macos/bin/qmake6"#' \
    qt/6.11.0/wasm_multithread/bin/qmake
