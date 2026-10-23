#!/bin/sh
# Run tests/ on the phone, in the app's own prefix (a debug build: run-as),
# with ankidesk_remote.py from this checkout, so no rebuild is needed.
# test_xscreen also uses the prefix's real Xvfb, x11vnc and JWM (on :7).
#
#   tools/test_on_device.sh        (ANDROID_SERIAL picks the device)
set -eu
cd "$(dirname "$0")/.."
APP=$(sed -n 's/^ankideskApplicationId=//p' gradle.properties)
ROOTFS=$(sed -n 's/^ankideskRootfsDir=//p' gradle.properties)
P=/data/data/$APP/$ROOTFS/usr
ADB=${ADB:-adb}
TMP=/data/local/tmp/kioku-tests
FILES="tests/test_remote.py tests/test_xscreen.py tests/vnc_client.py rootfs-overlay/share/ankidx/ankidesk_remote.py
	rootfs-overlay/share/ankidx/ankidesk_novnc.py rootfs-overlay/share/ankidx/ankidesk_xscreen.py"

$ADB shell mkdir -p $TMP
for f in $FILES; do
	$ADB push -q "$f" $TMP/ >/dev/null
	$ADB shell chmod 644 $TMP/"$(basename "$f")"
done
# /data/local/tmp is not listable by the app: copy each file by name
copy=""
for f in $FILES; do
	copy="$copy cp $TMP/$(basename "$f") tests/;"
done
$ADB shell run-as "$APP" sh -c "'cd /data/data/$APP/cache && rm -rf tests && mkdir tests && $copy \
	cd tests && TMPDIR=/data/data/$APP/cache PREFIX=$P PATH=$P/bin:/system/bin LANG=en_US.UTF-8 REAL_PREFIX=$P \
	$P/bin/python3 -m unittest -v ${TESTS:-test_remote test_xscreen} 2>&1'"
