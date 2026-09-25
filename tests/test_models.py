import tempfile
import unittest
from pathlib import Path

from postcast.models import Episode


class ModelTests(unittest.TestCase):
    def test_downloaded_episode_prefers_existing_local_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "episode.mp3"
            path.write_bytes(b"audio")
            episode = Episode(
                id=1,
                podcast_id=1,
                audio_url="https://example.test/episode.mp3",
                downloaded_path=str(path),
            )
            self.assertEqual(episode.playable_uri(), path.as_uri())

    def test_missing_download_falls_back_to_remote_url(self):
        episode = Episode(
            id=1,
            podcast_id=1,
            audio_url="https://example.test/episode.mp3",
            downloaded_path="/does/not/exist.mp3",
        )
        self.assertEqual(episode.playable_uri(), "https://example.test/episode.mp3")


if __name__ == "__main__":
    unittest.main()
