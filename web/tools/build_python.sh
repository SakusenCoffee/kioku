#!/bin/bash
# Build CPython 3.14 for Emscripten 4.0.7 (Qt 6.11's version) with pthreads,
# statically, without the JS call trampoline (Asyncify can't unwind through
# JS frames; QDialog.exec() needs Asyncify). The stdlib copy for the virtual
# file system goes to build/stdlib.
set -euo pipefail
source "$(dirname "$0")/env.sh"
PY=$ROOT/deps/Python-3.14.0
source "$ROOT/deps/emsdk/emsdk_env.sh" >/dev/null 2>&1
if [ ! -d "$PY" ]; then
    curl -sL https://www.python.org/ftp/python/3.14.0/Python-3.14.0.tar.xz | tar xJ -C "$ROOT/deps"
    patch -s -p1 -d "$PY" < "$ROOT/patches/cpython-3.14.0-emsdk-4.0.7.patch"
fi
cd "$PY"
P() { python3.14 Tools/wasm/emscripten "$@"; }
P configure-build-python && P make-build-python && P make-libffi && P make-mpdec
P configure-host -- --enable-wasm-pthreads --disable-wasm-dynamic-linking
P make-host || true  # its own node smoke run fails; the static library is what we need
rsync -a --delete --exclude __pycache__ --exclude test --exclude tests --exclude idlelib \
    --exclude tkinter --exclude turtledemo --exclude ensurepip --exclude pydoc_data \
    Lib/ "$ROOT/build/stdlib/"
cp cross-build/wasm32-emscripten/build/python/build/lib.emscripten-*/_sysconfigdata__emscripten_wasm32-emscripten.py "$ROOT/build/stdlib/"
