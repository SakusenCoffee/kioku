#!/bin/sh
# noVNC, the remote desktop's web viewer (ankidesk_remote.py), into
# OUT/share/novnc: only what a browser loads, checked against a pinned hash.
#
#   tools/fetch_novnc.sh OUT
set -eu

VERSION=1.7.0
SHA256=b1003a11b6e6e8d8f7f5e5586daae7f8ca651d8aee0aa155ff9ac841c48f52c6
OUT="$1"
CACHE=build/novnc-$VERSION.tar.gz

if [ ! -f "$CACHE" ] || ! echo "$SHA256  $CACHE" | shasum -a 256 -c - >/dev/null 2>&1; then
	curl -fsSL -o "$CACHE.part" "https://github.com/novnc/noVNC/archive/refs/tags/v$VERSION.tar.gz"
	echo "$SHA256  $CACHE.part" | shasum -a 256 -c - >/dev/null || { echo "noVNC checksum mismatch" >&2; exit 1; }
	mv "$CACHE.part" "$CACHE"
fi
rm -rf "$OUT/share/novnc"
mkdir -p "$OUT/share/novnc"
tar xzf "$CACHE" -C "$OUT/share/novnc" --strip-components 1 \
	"noVNC-$VERSION/app" "noVNC-$VERSION/core" "noVNC-$VERSION/vendor" \
	"noVNC-$VERSION/vnc.html" "noVNC-$VERSION/vnc_lite.html" "noVNC-$VERSION/LICENSE.txt"
# translations other than English are dropped, like the rest of the runtime's
find "$OUT/share/novnc/app/locale" -name '*.json' -delete 2>/dev/null || true
echo "noVNC $VERSION -> $OUT/share/novnc"
