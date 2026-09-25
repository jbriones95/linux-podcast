import calendar
import re
from pathlib import Path
from urllib.parse import urljoin

import feedparser

from .config import USER_AGENT


class FeedError(Exception):
    pass


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
    }

    episodes = []
    for entry in parsed.entries:
        enclosures = [e for e in entry.get("enclosures", []) if e.get("href")]
        audio_url = ""
        if enclosures:
            audio_url = enclosures[0]["href"]
        elif entry.get("link"):
            audio_url = entry["link"]

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
        })
    return podcast, episodes
