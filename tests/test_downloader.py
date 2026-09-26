import errno
import unittest
import urllib.error

from postcast.download_errors import DownloadError, classify_download_error


class DownloadErrorTests(unittest.TestCase):
    def test_classifies_http_errors(self):
        error = classify_download_error(
            urllib.error.HTTPError("url", 404, "missing", {}, None)
        )
        self.assertEqual(error, DownloadError("http", "HTTP error 404.", False))

    def test_classifies_retryable_network_errors(self):
        error = classify_download_error(
            urllib.error.URLError("connection refused")
        )
        self.assertEqual(error.kind, "network")
        self.assertTrue(error.retryable)

    def test_classifies_disk_space_errors(self):
        error = classify_download_error(
            OSError(errno.ENOSPC, "No space left on device")
        )
        self.assertEqual(error, DownloadError(
            "disk-space", "Not enough free space for download."
        ))

    def test_classifies_invalid_urls(self):
        error = classify_download_error(ValueError("bad URL"))
        self.assertEqual(error.kind, "invalid-url")


if __name__ == "__main__":
    unittest.main()
