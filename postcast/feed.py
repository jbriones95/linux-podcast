import calendar
import re
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import feedparser

from .config import USER_AGENT


class FeedError(Exception):
    pass


def normalize_feed_url(value):
    """Return a canonical HTTP(S) feed URL or raise ValueError."""
    value = (value or "").strip()
    parts = urlsplit(value)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https") or not parts.netloc:
        raise ValueError("Enter a valid http(s) RSS feed URL.")
    if parts.username or parts.password:
        raise ValueError("RSS feed URLs cannot include credentials.")
    hostname = parts.hostname.lower() if parts.hostname else ""
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError("Enter a valid http(s) RSS feed URL.") from exc
    netloc = hostname
    if port is not None and not ((scheme == "http" and port == 80) or
                                 (scheme == "https" and port == 443)):
        netloc = f"{netloc}:{port}"
    return urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))


def _duration_to_seconds(value):
    if not value:
        return 0
    value = str(value).strip()
    # "hh:mm:ss" or "mm:ss" or bare seconds
    parts = value.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    try:
        return int(float(value))
    except ValueError:
        return 0


def _optional_int(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _explicit(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "explicit"}


def resolve_audio_url(base_url, enclosures, fallback_link=""):
    """Choose a valid HTTP(S) audio enclosure and resolve relative URLs."""
    for enclosure in enclosures or ():
        href = (enclosure.get("href") or "").strip()
        media_type = (enclosure.get("type") or "").lower()
        if not href or (media_type and not media_type.startswith("audio/")):
            continue
        candidate = urljoin(base_url, href)
        if candidate.startswith(("http://", "https://")):
            return candidate
    candidate = urljoin(base_url, (fallback_link or "").strip())
    return candidate if candidate.startswith(("http://", "https://")) else ""


def _clean(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _image_value(value):
    if isinstance(value, dict):
        return value.get("href") or value.get("url") or value.get("href_url") or ""
    return value if isinstance(value, str) else ""


def _get_artwork(entry, base_url=""):
    for value in (
        entry.get("image", {}),
        entry.get("itunes_image", {}),
        entry.get("logo", ""),
    ):
        url = _image_value(value)
        if url:
            return urljoin(base_url, url)
    links = entry.get("links")
    if links:
        for link in links:
            if link.get("type", "").startswith("image/"):
                return urljoin(base_url, link.get("href", ""))
    return ""


def fetch_feed(feed_url):
    """Parse an RSS/Atom feed into (podcast dict, [episode dicts])."""
    parsed = feedparser.parse(feed_url, agent=USER_AGENT)
    if parsed.bozo and not parsed.entries and not getattr(parsed.feed, "title", None):
        exc = getattr(parsed, "bozo_exception", None)
        raise FeedError(f"Could not parse feed: {exc}")

    feed = parsed.feed
    image_url = _get_artwork(feed, feed_url)
    podcast = {
        "feed_url": feed_url,
        "title": _clean(feed.get("title", "")) or feed_url,
        "author": _clean(feed.get("author", "")),
        "description": _clean(
            feed.get("subtitle", "")
            or feed.get("summary", "")
            or feed.get("subtitle_detail", {}).get("value", "")
        ),
        "image_url": image_url,
        "link": feed.get("link", ""),
        "language": feed.get("language", ""),
        "categories": ", ".join(
            str(item.get("term", "")) for item in feed.get("tags", []) if item.get("term")
        ),
        "explicit": _explicit(feed.get("itunes_explicit")),
    }

    episodes = []
    for entry in parsed.entries:
        audio_url = resolve_audio_url(
            feed_url, entry.get("enclosures", []), entry.get("link", "")
        )

        published = None
        if entry.get("published_parsed"):
            published = calendar.timegm(entry.published_parsed)
        elif entry.get("updated_parsed"):
            published = calendar.timegm(entry.updated_parsed)

        episodes.append({
            "guid": entry.get("id") or audio_url,
            "title": _clean(entry.get("title", "")),
            "description": _clean(
                entry.get("summary", "")
                or entry.get("description", "")
                or (entry.get("content") or [{}])[0].get("value", "")
            ),
            "audio_url": audio_url,
            "duration_seconds": _duration_to_seconds(entry.get("itunes_duration")),
            "published": published,
            "season_number": _optional_int(entry.get("itunes_season")),
            "episode_number": _optional_int(entry.get("itunes_episode")),
            "explicit": _explicit(
                entry.get("itunes_explicit")
                if entry.get("itunes_explicit") is not None
                else feed.get("itunes_explicit")
            ),
        })
    return podcast, episodes
