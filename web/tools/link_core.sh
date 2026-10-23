#!/bin/bash
source "$(dirname "$0")/env.sh"
cd "$ROOT"
source deps/emsdk/emsdk_env.sh >/dev/null 2>&1
B=deps/Python-3.14.0/cross-build/wasm32-emscripten
mkdir -p build/core
emcc -O2 -pthread tools/core/core_main.c -I$B/build/python -I deps/Python-3.14.0/Include -o build/core/core.mjs \
  build/rust-target/wasm32-unknown-emscripten/release/librsbridge.a $B/build/python/libpython3.14.a $B/build/python/Modules/expat/libexpat.a $B/build/python/Modules/_hacl/*.o $B/prefix/lib/libmpdec.a $B/prefix/lib/libffi.a \
  -sUSE_ZLIB -sUSE_BZIP2 -sALLOW_MEMORY_GROWTH -sINITIAL_MEMORY=64MB -sSTACK_SIZE=5MB -sPROXY_TO_PTHREAD -sEXIT_RUNTIME -sFORCE_FILESYSTEM \
  --preload-file build/stdlib@/python/lib/python3.14 --preload-file build/site@/site --preload-file tools/core@/app "$@" 2>&1 \
  | grep -v "pthreads-mem-growth" | head -30
