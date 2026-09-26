import urllib.error
from dataclasses import dataclass


@dataclass(frozen=True)
class DownloadError:
    kind: str
    message: str
    retryable: bool = False


def classify_download_error(exc):
    if isinstance(exc, urllib.error.HTTPError):
        retryable = exc.code >= 500 or exc.code in (408, 429)
        return DownloadError("http", f"HTTP error {exc.code}.", retryable)
    if isinstance(exc, urllib.error.URLError):
        return DownloadError("network", "Network error while downloading.", True)
    if isinstance(exc, ValueError):
        return DownloadError("invalid-url", "The download URL is invalid.")
    if isinstance(exc, OSError):
        message = str(exc).lower()
        if "space" in message or getattr(exc, "errno", None) == 28:
            return DownloadError("disk-space", "Not enough free space for download.")
        return DownloadError("filesystem", "Could not save the download.")
    return DownloadError("unknown", "Download failed.")
