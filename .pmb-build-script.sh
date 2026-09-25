#!/usr/bin/env bash
# Build postcast .apk natively (aarch64) in the Lima VM. Files already staged at
# /tmp/pmhome99/work/cache_git/pmaports/testing/postcast/ by earlier limactl copy.
set -euo pipefail

export HOME=/tmp/pmhome99
export PATH=/tmp/pmbvenv/bin:$PATH

REAL=/tmp/pmhome99/work/cache_git/pmaports
PKG="$REAL/testing/postcast"

echo "== 1. tree in place? =="
ls -la "$PKG"
test -f "$PKG/APKBUILD" && test -f "$PKG/postcast-0.1.7.tar.gz" && echo "OK files present"

echo
echo "== 2. point pmbootstrap aports at the REAL pmaports (has PM.CFG-must-be-pmaports.cfg) =="
CFG="$HOME/.config/pmbootstrap.cfg"
sed -i "s|^aports = .*|aports = $REAL|" "$CFG"
grep -E "^(aports|work|arch|device|vendor)" "$CFG"

echo
echo "== 3. checksum: fills sha512sums into APKBUILD, validates tarball =="
cd "$PKG"
pmbootstrap checksum postcast 2>&1 | grep -iE "checksum|sha512|postcast|OK|ERROR|fail|done" | head -12 || true

echo
echo "== 4. native aarch64 build =="
pmbootstrap build postcast 2>&1 | grep -iE "build|postcast|ERROR|fail|apk|installed|done|aarch64" | grep -viE "^\s*$" | tail -30 || true

echo
echo "== 5. locate produced .apk =="
find /tmp/pmhome99/work -name "postcast-*.apk" 2>/dev/null
