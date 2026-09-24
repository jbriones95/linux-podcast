# Maintainer: Jose Briones <thedumbphoneshow@gmail.com>
# Contributor: Jose Briones <thedumbphoneshow@gmail.com>

pkgname=postcast
pkgver=0.1.0
pkgrel=0
pkgdesc="GTK4 podcast manager for postmarketOS"
url="https://github.com/jbriones95/linux-podcast"
arch="all"
license="GPL-3.0-or-later"
depends="python3 py3-gobject3 py3-feedparser gstreamer gst-plugins-base gst-plugins-good"
makedepends="py3-setuptools"
options="!check"
source="postcast-$pkgver.tar.gz"
builddir="$srcdir/postcast-$pkgver"

build() {
	python3 setup.py build
}

package() {
	python3 setup.py install --prefix=/usr --root="$pkgdir"

	# Install a *relocatable* launcher instead of the setuptools easy-install
	# console script. The generated script bakes in the buildroot's absolute
	# path to python (e.g. /usr/sbin/python3), which does not exist on the
	# target device and makes phosh report "Startup ... timed out". Running
	# the app as a module with the explicit interpreter is portable and was
	# verified on-device (io.postcast.Postcast owns its D-Bus name).
	install -Dm755 /dev/stdin "$pkgdir/usr/bin/postcast" <<'LAUNCH'
#!/usr/bin/python3
from postcast.__main__ import main
import sys

sys.exit(main(sys.argv[1:]))
LAUNCH

	install -Dm644 "$builddir/data/io.postcast.Postcast.desktop" \
		"$pkgdir/usr/share/applications/io.postcast.Postcast.desktop"
	install -Dm644 "$builddir/data/io.postcast.Postcast.metainfo.xml" \
		"$pkgdir/usr/share/metainfo/io.postcast.Postcast.metainfo.xml"
	install -Dm644 "$builddir/data/io.postcast.Postcast.svg" \
		"$pkgdir/usr/share/icons/hicolor/scalable/apps/io.postcast.Postcast.svg"
}
