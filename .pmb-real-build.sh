#!/usr/bin/env bash
# Drives the real pmbootstrap build from *inside* the VM, then locates the apk.
# Deliberately has NO quoting gymnastics in the outer limactl call.
set -uo pipefail

export HOME=/tmp/pmhome99
export PATH=/tmp/pmbvenv/bin:$PATH

WORK=/tmp/pmhome99/work
APORTS="$HOME/.config/pmbootstrap_v3.cfg"

echo "== which cfg does Home actually read =="
ls -la "$HOME/.config/"
for f in "$HOME/.config/pmbootstrap.cfg" "$HOME/.config/pmbootstrap_v3.cfg"; do
  [ -f "$f" ] && { echo "## $f"; grep -E "^(aports|work|jobs|arch|device|vendor)" "$f"; echo "---"; }
done

echo
echo "== find every pmaports root that HAS pmaports.cfg (shallow only) =="
for c in "$WORK"/cache_git/pmaports/pmaports.cfg \
         "$WORK"/cache_git_pmaports/pmaports.cfg \
         "$WORK"/cache_git/pmaports*/*/pmaports.cfg; do
  [ -f "$c" ] && echo "PMAPORTS-ROOT: $(dirname "$c")"
done

echo
echo "== where does the RP build put apks? try known pmb roots =="
for d in "$WORK/packages" "$WORK/packages/pkg" "$WORK/cache_git_pmaports_packages" ; do
  [ -d "$d" ] && echo "dir exists: $d"
done

echo
echo "== THE BUILD =="
# use interractive-less: reuse existing cfg since aports already points at real clone
cd "$APORTS" 2>/dev/null
pmbootstrap build postcast --ignore-depends 2>&1 \
  | grep -iE "postcast|apk|sha512|checksum|error|warn|fail|done|build|installed" \
  | grep -viE "^\s*$" | tail -30

echo
echo "== locate postcast apk (shallow, maxdepth 5) =="
find "$WORK" -maxdepth 5 -name "postcast*.apk" 2>/dev/null | head
echo
echo "== also the cache_git testing result dir =="
ls -la "$WORK/cache_git/pmaports/testing/postcast/" 2>/dev/null
echo
echo "== pmb log tail 30 =="
ls -t "$WORK"/log*.txt 2>/dev/null | head -1
LOG=$(ls -t "$WORK"/log*.txt 2>/dev/null | head -1)
[ -n "$LOG" ] && tail -30 "$LOG" | sed -E 's/\x1b\[[0-9;]*m//g' | grep -viE "^\s*$" | tail -25
