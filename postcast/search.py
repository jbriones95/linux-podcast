import json
import urllib.parse
import urllib.request

from .config import USER_AGENT

SEARCH_API = "https://itunes.apple.com/search"


def search_podcasts(term, limit=25):
    query = urllib.parse.urlencode({
        "media": "podcast",
        "term": term,
        "limit": limit,
    })
    req = urllib.request.Request(f"{SEARCH_API}?{query}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    results = []
    for item in data.get("results", []):
        feed_url = item.get("feedUrl")
        if not feed_url:
            continue
        results.append({
            "feed_url": feed_url,
            "title": item.get("collectionName") or item.get("trackName") or "Unknown",
            "author": item.get("artistName", ""),
            "image_url": item.get("artworkUrl600") or item.get("artworkUrl100", ""),
            "track_count": item.get("trackCount", 0),
            "description": item.get("primaryGenreName", ""),
        })
    return results