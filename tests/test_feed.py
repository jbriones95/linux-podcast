import tempfile
import unittest
from pathlib import Path

from postcast.feed import (
    _duration_to_seconds,
    _get_artwork,
    fetch_feed,
    normalize_feed_url,
    resolve_audio_url,
)


FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
    <channel>
      <title>Example Show</title>
      <language>en-us</language>
      <itunes:explicit>yes</itunes:explicit>
    <description>A <b>test</b> show</description>
    <link>https://example.test/</link>
    <image><url>https://example.test/art.png</url></image>
    <item>
      <guid isPermaLink="false">episode-1</guid>
      <title>First &amp; Best</title>
      <description><![CDATA[<p>An episode description.</p>]]></description>
      <pubDate>Tue, 01 Jan 2030 00:00:00 GMT</pubDate>
        <itunes:duration>01:02:03</itunes:duration>
        <itunes:season>2</itunes:season>
        <itunes:episode>4</itunes:episode>
        <itunes:explicit>true</itunes:explicit>
      <enclosure url="https://example.test/episode.mp3" type="audio/mpeg" />
    </item>
  </channel>
</rss>
"""


class FeedTests(unittest.TestCase):
    def test_normalize_feed_url(self):
        self.assertEqual(
            normalize_feed_url(" HTTPS://Example.TEST:443/feed.xml#latest "),
            "https://example.test/feed.xml",
        )
        self.assertEqual(
            normalize_feed_url("http://example.test:8080/feed?format=rss"),
            "http://example.test:8080/feed?format=rss",
        )

    def test_normalize_feed_url_rejects_invalid_values(self):
        for value in ("", "example.test/feed.xml", "file:///tmp/feed.xml", "ftp://example.test/feed"):
            with self.assertRaises(ValueError):
                normalize_feed_url(value)

    def test_duration_formats(self):
        self.assertEqual(_duration_to_seconds("01:02:03"), 3723)
        self.assertEqual(_duration_to_seconds("02:03"), 123)
        self.assertEqual(_duration_to_seconds("42"), 42)
        self.assertEqual(_duration_to_seconds("not-a-duration"), 0)

    def test_feed_parser_normalizes_podcast_and_episode(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "feed.xml"
            path.write_text(FEED, encoding="utf-8")
            podcast, episodes = fetch_feed(path.as_uri())

        self.assertEqual(podcast["title"], "Example Show")
        self.assertEqual(podcast["description"], "A test show")
        self.assertEqual(len(episodes), 1)
        self.assertEqual(episodes[0]["guid"], "episode-1")
        self.assertEqual(episodes[0]["audio_url"], "https://example.test/episode.mp3")
        self.assertEqual(episodes[0]["duration_seconds"], 3723)
        self.assertGreater(episodes[0]["published"], 0)
        self.assertEqual(podcast["language"], "en-us")
        self.assertTrue(podcast["explicit"])
        self.assertEqual(episodes[0]["season_number"], 2)
        self.assertEqual(episodes[0]["episode_number"], 4)
        self.assertTrue(episodes[0]["explicit"])

    def test_artwork_supports_itunes_image_and_relative_urls(self):
        self.assertEqual(
            _get_artwork({"itunes_image": {"href": "art.jpg"}}, "https://example.test/feed.xml"),
            "https://example.test/art.jpg",
        )

    def test_relative_and_protocol_relative_audio_enclosures_are_resolved(self):
        self.assertEqual(
            resolve_audio_url(
                "https://example.test/feed.xml",
                [{"href": "//cdn.example.test/episode.mp3", "type": "audio/mpeg"}],
            ),
            "https://cdn.example.test/episode.mp3",
        )
        self.assertEqual(
            resolve_audio_url(
                "https://example.test/feed.xml",
                [{"href": "episode.mp3", "type": "audio/mpeg"}],
            ),
            "https://example.test/episode.mp3",
        )
        self.assertEqual(
            resolve_audio_url(
                "https://example.test/feed.xml",
                [
                    {"href": "show-page", "type": "text/html"},
                    {"href": "audio.mp3", "type": "audio/mpeg"},
                ],
            ),
            "https://example.test/audio.mp3",
        )


if __name__ == "__main__":
    unittest.main()
