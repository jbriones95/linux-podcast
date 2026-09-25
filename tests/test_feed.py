import tempfile
import unittest
from pathlib import Path

from postcast.feed import _duration_to_seconds, _get_artwork, fetch_feed


FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Example Show</title>
    <description>A <b>test</b> show</description>
    <link>https://example.test/</link>
    <image><url>https://example.test/art.png</url></image>
    <item>
      <guid isPermaLink="false">episode-1</guid>
      <title>First &amp; Best</title>
      <description><![CDATA[<p>An episode description.</p>]]></description>
      <pubDate>Tue, 01 Jan 2030 00:00:00 GMT</pubDate>
      <itunes:duration>01:02:03</itunes:duration>
      <enclosure url="https://example.test/episode.mp3" type="audio/mpeg" />
    </item>
  </channel>
</rss>
"""


class FeedTests(unittest.TestCase):
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

    def test_artwork_supports_itunes_image_and_relative_urls(self):
        self.assertEqual(
            _get_artwork({"itunes_image": {"href": "art.jpg"}}, "https://example.test/feed.xml"),
            "https://example.test/art.jpg",
        )


if __name__ == "__main__":
    unittest.main()
