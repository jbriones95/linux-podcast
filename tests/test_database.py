import sqlite3
import tempfile
import unittest
from pathlib import Path

from postcast.database import Database, SCHEMA_VERSION


class DatabaseTests(unittest.TestCase):
    def test_legacy_database_is_migrated_without_losing_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "library.db"
            conn = sqlite3.connect(path)
            conn.executescript(
                """
                CREATE TABLE podcasts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    feed_url TEXT UNIQUE NOT NULL,
                    title TEXT DEFAULT '', author TEXT DEFAULT '',
                    description TEXT DEFAULT '', image_url TEXT DEFAULT '', link TEXT DEFAULT ''
                );
                CREATE TABLE episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    podcast_id INTEGER NOT NULL,
                    guid TEXT DEFAULT '', title TEXT DEFAULT '', description TEXT DEFAULT '',
                    audio_url TEXT DEFAULT '', duration_seconds INTEGER DEFAULT 0,
                    published INTEGER, downloaded_path TEXT DEFAULT '', played INTEGER DEFAULT 0,
                    position_seconds INTEGER DEFAULT 0, UNIQUE(podcast_id, guid)
                );
                CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
                INSERT INTO podcasts(feed_url, title) VALUES ('https://example.test/feed.xml', 'Saved show');
                """
            )
            conn.commit()
            conn.close()

            db = Database(path)
            self.assertEqual(
                db.conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION
            )
            self.assertEqual(db.podcasts()[0].title, "Saved show")
            db.close()

    def test_episode_state_survives_feed_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "library.db")
            podcast_id = db.upsert_podcast(
                {"feed_url": "https://example.test/feed.xml", "title": "Show"}
            )
            db.sync_episodes(
                podcast_id,
                [{"guid": "episode-1", "title": "First", "audio_url": "https://example.test/1.mp3"}],
            )
            episode = db.episodes(podcast_id)[0]
            db.mark_played(episode.id, True, 42)
            db.set_favorite(episode.id, True)
            db.sync_episodes(
                podcast_id,
                [{"guid": "episode-1", "title": "Updated", "audio_url": "https://example.test/1.mp3"}],
            )
            updated = db.episode(episode.id)
            self.assertEqual(updated.title, "Updated")
            self.assertTrue(updated.played)
            self.assertTrue(updated.favorite)
            self.assertEqual(updated.position_seconds, 42)
            results = db.search_episodes("updated", favorites_only=True)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0][0].id, episode.id)
            db.close()

    def test_future_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "library.db"
            conn = sqlite3.connect(path)
            conn.execute("PRAGMA user_version = 999")
            conn.commit()
            conn.close()
            with self.assertRaises(RuntimeError):
                Database(path)

    def test_schema_version_one_gets_favorite_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "library.db"
            conn = sqlite3.connect(path)
            conn.executescript(
                """
                CREATE TABLE podcasts (id INTEGER PRIMARY KEY, feed_url TEXT UNIQUE NOT NULL);
                CREATE TABLE episodes (
                    id INTEGER PRIMARY KEY, podcast_id INTEGER NOT NULL, guid TEXT,
                    title TEXT, description TEXT, audio_url TEXT, duration_seconds INTEGER,
                    published INTEGER, downloaded_path TEXT, played INTEGER DEFAULT 0,
                    position_seconds INTEGER DEFAULT 0, UNIQUE(podcast_id, guid)
                );
                CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
                PRAGMA user_version = 1;
                """
            )
            conn.commit()
            conn.close()

            db = Database(path)
            columns = {
                row[1] for row in db.conn.execute("PRAGMA table_info(episodes)").fetchall()
            }
            self.assertIn("favorite", columns)
            self.assertEqual(db.conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            db.close()

    def test_queue_is_persistent_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "library.db")
            podcast_id = db.upsert_podcast(
                {"feed_url": "https://example.test/feed.xml", "title": "Show"}
            )
            db.sync_episodes(
                podcast_id,
                [
                    {"guid": "one", "title": "One", "audio_url": "https://example.test/one.mp3"},
                    {"guid": "two", "title": "Two", "audio_url": "https://example.test/two.mp3"},
                ],
            )
            episodes = db.episodes(podcast_id)
            self.assertTrue(db.add_to_queue(episodes[0].id))
            self.assertFalse(db.add_to_queue(episodes[0].id))
            self.assertTrue(db.add_to_queue(episodes[1].id))
            self.assertEqual([item[0].id for item in db.queue_items()], [episodes[0].id, episodes[1].id])
            db.remove_from_queue(episodes[0].id)
            self.assertEqual([item[0].id for item in db.queue_items()], [episodes[1].id])
            db.clear_queue()
            self.assertEqual(db.queue_items(), [])
            db.close()

    def test_listening_statistics_accumulate(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "library.db")
            podcast_id = db.upsert_podcast(
                {"feed_url": "https://example.test/feed.xml", "title": "Show"}
            )
            db.sync_episodes(
                podcast_id,
                [{"guid": "one", "title": "One", "audio_url": "https://example.test/one.mp3"}],
            )
            episode_id = db.episodes(podcast_id)[0].id
            db.record_listening(episode_id, 30)
            db.record_listening(episode_id, 15, completed=True)
            summary = db.listening_summary()
            self.assertEqual(summary[0]["seconds"], 45)
            self.assertEqual(summary[0]["completed"], 1)
            db.close()

    def test_episode_can_be_resolved_for_external_playback(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "library.db")
            podcast_id = db.upsert_podcast(
                {"feed_url": "https://example.test/feed.xml", "title": "Show"}
            )
            db.sync_episodes(
                podcast_id,
                [{"guid": "one", "title": "One", "audio_url": "https://example.test/one.mp3"}],
            )
            match = db.episode_by_audio_url("https://example.test/one.mp3")
            self.assertEqual(match[0].title, "One")
            self.assertEqual(match[1].title, "Show")
            db.close()


if __name__ == "__main__":
    unittest.main()
