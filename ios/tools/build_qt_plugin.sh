#!/bin/bash
# Rebuild the sources of Qt's iOS platform plugin that ios/patches/qios-*.patch
# change (qtplugin/CMakeLists.txt) and replace their objects in the arm64
# slice of the prebuilt static libqios.a in deps/qt, keeping that as
# deps/qt/<ver>/ios/plugins/platforms/libqios.orig.a. Skips when nothing
# changed. Only the Release library (libqios.a) is patched.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
source "$ROOT/../shared/versions.env"
QT=$ROOT/deps/qt/$QT_VERSION
SRC=$ROOT/deps/qtbase-$QT_VERSION
BUILD=$ROOT/build/qtplugin
PLUGIN=$QT/ios/plugins/platforms/libqios.a
ORIG=$QT/ios/plugins/platforms/libqios.orig.a
STAMP=$QT/ios/plugins/platforms/libqios.kioku

INPUTS=$(cat "$0" "$ROOT/qtplugin/CMakeLists.txt" "$ROOT/patches/"qios-*.patch | shasum)
if [ -f "$STAMP" ] && [ "$(cat "$STAMP")" = "$INPUTS" ]; then
    exit 0
fi

if [ ! -d "$SRC" ]; then
    git clone -q --depth 1 --branch "v$QT_VERSION" --filter=blob:none --sparse \
        https://github.com/qt/qtbase.git "$SRC"
    git -C "$SRC" sparse-checkout set src/plugins/platforms/ios
fi
git -C "$SRC" checkout -q -- .
for p in "$ROOT/patches/"qios-*.patch; do
    git -C "$SRC" apply "$p"
done

mkdir -p "$ROOT/build"
rm -rf "$BUILD"
"$QT/ios/bin/qt-cmake" -S "$ROOT/qtplugin" -B "$BUILD" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release -DQT_HOST_PATH="$QT/macos" -DQTBASE_SRC="$SRC" \
    -DCMAKE_OSX_SYSROOT=iphoneos -DCMAKE_OSX_ARCHITECTURES=arm64 \
    -DCMAKE_OSX_DEPLOYMENT_TARGET=16.0 -DQT_NO_PRIVATE_MODULE_WARNING=ON \
    > "$ROOT/build/qtplugin-cmake.log"
cmake --build "$BUILD" > "$ROOT/build/qtplugin-build.log" 2>&1 || {
    grep -E 'error:|FAILED|undefined' -A3 "$ROOT/build/qtplugin-build.log" | head -40
    exit 1
}

[ -f "$ORIG" ] || cp "$PLUGIN" "$ORIG"
WORK=$BUILD/archive
mkdir -p "$WORK"
lipo "$ORIG" -thin arm64 -output "$WORK/arm64.a"
lipo "$ORIG" -thin x86_64 -output "$WORK/x86_64.a"
# the archive's members are named after their sources (qiosplatformaccessibility.mm.o),
# like the objects CMake builds, so `ar r` replaces them
OBJECTS=$(find "$BUILD/CMakeFiles/qios.dir" -name '*.o')
for o in $OBJECTS; do
    ar t "$WORK/arm64.a" | grep -qx "$(basename "$o")" || {
        echo "$(basename "$o") is not a member of libqios.a" >&2
        exit 1
    }
done
(cd "$WORK" && cp $OBJECTS . && ar r arm64.a $(for o in $OBJECTS; do basename "$o"; done) \
    && ranlib arm64.a)
lipo -create "$WORK/arm64.a" "$WORK/x86_64.a" -output "$PLUGIN"
echo "$INPUTS" > "$STAMP"
echo "Patched $PLUGIN"
