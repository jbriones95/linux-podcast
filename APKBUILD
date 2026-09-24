# Maintainer: Your Name <you@example.com>
# Contributor: Your Name <you@example.com>

pkgname=postcast
pkgver=0.1.0
pkgrel=0
pkgdesc="GTK4 podcast player for postmarketOS"
url="https://github.com/jbriones/linux-podcast"
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
	install -Dm644 "$builddir/data/io.postcast.Postcast.desktop" \
		"$pkgdir/usr/share/applications/io.postcast.Postcast.desktop"
	install -Dm644 "$builddir/data/io.postcast.Postcast.metainfo.xml" \
		"$pkgdir/usr/share/metainfo/io.postcast.Postcast.metainfo.xml"
	install -Dm644 "$builddir/data/io.postcast.Postcast.svg" \
		"$pkgdir/usr/share/icons/hicolor/scalable/apps/io.postcast.Postcast.svg"
}

sha512sums="replace_with_actual_sha512sum"