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
            db.sync_episodes(
                podcast_id,
                [{"guid": "episode-1", "title": "Updated", "audio_url": "https://example.test/1.mp3"}],
            )
            updated = db.episode(episode.id)
            self.assertEqual(updated.title, "Updated")
            self.assertTrue(updated.played)
            self.assertEqual(updated.position_seconds, 42)
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


if __name__ == "__main__":
    unittest.main()
