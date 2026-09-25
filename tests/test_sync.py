import tempfile
import unittest
from pathlib import Path

from postcast.database import Database
from postcast.sync import export_library, import_library


class SyncTests(unittest.TestCase):
    def test_library_state_merges_idempotently(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = Database(root / "source.db")
            podcast_id = source.upsert_podcast(
                {"feed_url": "https://example.test/feed.xml", "title": "Example"}
            )
            source.sync_episodes(
                podcast_id,
                [{"guid": "one", "title": "One", "audio_url": "https://example.test/one.mp3"}],
            )
            episode_id = source.episodes(podcast_id)[0].id
            source.mark_played(episode_id, True, 120)
            source.add_to_queue(episode_id)
            path = export_library(source, root / "library-sync.json")

            target = Database(root / "target.db")
            self.assertEqual(import_library(target, path), 1)
            self.assertEqual(import_library(target, path), 1)
            self.assertEqual(len(target.podcasts()), 1)
            self.assertEqual(target.episodes(1)[0].position_seconds, 120)
            self.assertEqual(len(target.queue_items()), 1)
            source.close()
            target.close()


if __name__ == "__main__":
    unittest.main()
