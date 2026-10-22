#!/bin/bash
# Host tests for Kioku's Python code (shared/tests) on the build machine:
# desktop Anki's Python packages in a venv, with an rsbridge built from
# android/deps/anki, which android/tools/fetch_deps.sh patched with
# shared/patches/. No device needed.
# Usage: shared/tests/run.sh [pytest args]
# Env: PYTHON (default python3.14), PROTOC (default: on PATH)
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
source "$ROOT/shared/versions.env"
ANKI_SRC=$ROOT/android/deps/anki
WORK=$ROOT/build/host-tests
VENV=$WORK/venv
PYTHON=${PYTHON:-python3.14}

[ -d "$ANKI_SRC/rslib" ] || { echo "run android/tools/fetch_deps.sh first" >&2; exit 1; }
for patch in "$ROOT"/shared/patches/anki-*.patch; do
    git -C "$ANKI_SRC" apply -R --check "$patch" 2> /dev/null \
        || { echo "$patch is not applied to $ANKI_SRC" >&2; exit 1; }
done

if [ ! -x "$VENV/bin/python" ]; then
    mkdir -p "$WORK"
    "$PYTHON" -m venv "$VENV"
    "$VENV/bin/pip" install -q "anki==$ANKI_PY_VERSION" "aqt==$ANKI_PY_VERSION" PyQt6 pytest
fi

# rsbridge refuses to load unless its build hash matches the Python package's
mkdir -p "$ANKI_SRC/out"
HASH=$(git -C "$ANKI_SRC" rev-parse --short=8 HEAD)
[ "$(cat "$ANKI_SRC/out/buildhash" 2>/dev/null)" = "$HASH" ] || echo "$HASH" > "$ANKI_SRC/out/buildhash"
export PROTOC=${PROTOC:-$(command -v protoc)}
(cd "$ANKI_SRC" && cargo build -q -p rsbridge --release --features rustls)
# anki is a namespace package (no __init__.py)
SITE=$("$VENV/bin/python" -c "import anki; print(list(anki.__path__)[0])")
LIB=$ANKI_SRC/target/release/librsbridge.$([ "$(uname)" = Darwin ] && echo dylib || echo so)
cp "$LIB" "$SITE/_rsbridge.so"

cd "$ROOT/shared/tests"
exec "$VENV/bin/python" -m pytest -q -p no:cacheprovider "$@"
