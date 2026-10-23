#!/bin/bash
# Assemble the site-packages that the iOS and native Android apps bundle:
# Anki's Python packages (from the PyPI wheels: aqt is pure Python with the
# web assets compiled, anki's wheel is only used for its Python files), the
# pure-Python dependencies, and the Python halves of orjson and markupsafe
# (their native parts are built into the app or not needed).
# Usage: prepare_site.sh <python with pip> <sdist dir> <output dir>
set -euo pipefail
SHARED=$(cd "$(dirname "$0")/.." && pwd)
source "$SHARED/versions.env"
PYTHON=$1
SDIST=$2
SITE=$3
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
rm -rf "$SITE" && mkdir -p "$SITE"

grep -vE '^(orjson|rpds-py|markupsafe)==|^ *#' "$SHARED/requirements.txt" > "$TMP/pure.txt"
"$PYTHON" -m pip download -q --no-deps --only-binary :all: \
    --platform any --python-version "$PYTHON_VERSION" --implementation py --abi none \
    -d "$TMP/wheels" -r "$TMP/pure.txt" "aqt==$ANKI_PY_VERSION"
"$PYTHON" -m pip download -q --no-deps --only-binary :all: \
    --platform manylinux_2_35_x86_64 -d "$TMP/anki" "anki==$ANKI_PY_VERSION"
# -DD: today's time, not the wheel's fixed one (2020-02-02 in Anki's wheels),
# so a file of the same size in a new release isn't skipped by rsync -a
for w in "$TMP"/wheels/*.whl "$TMP"/anki/*.whl; do unzip -qo -DD "$w" -d "$SITE"; done
find "$SITE" -name '*.so' -delete

cp -R "$SDIST/markupsafe-$MARKUPSAFE_VERSION/src/markupsafe" "$SITE/"
rm -f "$SITE/markupsafe/_speedups.c"
cp -R "$SDIST/orjson-$ORJSON_VERSION/pysrc/orjson" "$SITE/"
