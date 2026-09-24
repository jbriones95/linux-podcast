#!/usr/bin/env bash
set -eo pipefail
export HOME=/home/jbriones.guest
export PATH=/tmp/pmbvenv/bin:$PATH

echo "=== find an existing real pmaports.cfg anywhere ==="
REAL=""
for p in /tmp/pmos/*/pmaports.cfg /tmp/pmos/pmwork/cache_git/pmaports/pmaports.cfg; do
  [ -f "$p" ] && REAL=$(dirname "$p") && break
done
echo "real pmaports candidate: $REAL"

# The pmbootstrap init must point aports at a *cloned pmaports*. If none, let init do the clone:
# (it prompts aports path: enter 'git' then it clones). We instead hand it to init with the git URL.
if [ -z "$REAL" ]; then
  echo "no pmaports clone found; seeding cfg then letting pmbootstrap clone pmaports git"
fi
echo "=== pmbootstrap init, answered fully ==="
# answers: work path, aports: choose "git" (default), extra space, boot, mirror..., arch, device, vendor
printf "\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n" | pmbootstrap init 2>&1 | grep -iE "Done|ERROR|work|aports|arch|device" | tail -12
echo "=== cfg ==="
grep -E "aports|work|arch|device" "$HOME/.config/pmbootstrap.cfg"
