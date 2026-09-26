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
            tables = {
                row[0]
                for row in db.conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            self.assertIn("queue", tables)
            self.assertIn("listening_stats", tables)
            db.close()

    def test_download_jobs_persist_and_reconcile(self):
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
            self.assertTrue(db.enqueue_download(
                episode_id, "https://example.test/one.mp3", "/tmp/one.mp3", "/tmp/one.part"
            ))
            self.assertFalse(db.enqueue_download(
                episode_id, "https://example.test/one.mp3", "/tmp/one.mp3", "/tmp/one.part"
            ))
            db.update_download_job(episode_id, status="downloading", bytes_downloaded=12)
            db.reconcile_download_jobs()
            job = db.download_job(episode_id)
            self.assertEqual(job["status"], "queued")
            self.assertEqual(job["bytes_downloaded"], 12)
            db.remove_download_job(episode_id)
            self.assertIsNone(db.download_job(episode_id))
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
            self.assertTrue(db.move_queue_item(episodes[1].id, 0))
            self.assertEqual([item[0].id for item in db.queue_items()], [episodes[1].id, episodes[0].id])
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

    def test_playback_progress_persists_position_and_listening_together(self):
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
            db.save_playback_progress(episode_id, 42, 12)
            self.assertEqual(db.episode(episode_id).position_seconds, 42)
            self.assertEqual(db.listening_summary()[0]["seconds"], 12)
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

    def test_recent_episodes_are_aggregated_across_podcasts(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "library.db")
            first = db.upsert_podcast(
                {"feed_url": "https://example.test/one.xml", "title": "One"}
            )
            second = db.upsert_podcast(
                {"feed_url": "https://example.test/two.xml", "title": "Two"}
            )
            db.sync_episodes(
                first,
                [{"guid": "old", "title": "Old", "audio_url": "https://example.test/old.mp3", "published": 10}],
            )
            db.sync_episodes(
                second,
                [{"guid": "new", "title": "New", "audio_url": "https://example.test/new.mp3", "published": 20}],
            )
            recent = db.recent_episodes()
            self.assertEqual([item[0].title for item in recent], ["New", "Old"])
            self.assertEqual([item[1].title for item in recent], ["Two", "One"])
            db.close()

    def test_episode_queries_support_pagination(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "library.db")
            podcast_id = db.upsert_podcast(
                {"feed_url": "https://example.test/feed.xml", "title": "Show"}
            )
            db.sync_episodes(
                podcast_id,
                [
                    {"guid": str(i), "title": f"Episode {i}", "audio_url": f"https://example.test/{i}.mp3", "published": i}
                    for i in range(5)
                ],
            )
            self.assertEqual([e.title for e in db.episodes(podcast_id, limit=2)], ["Episode 4", "Episode 3"])
            self.assertEqual(
                [e.title for e in db.episodes(podcast_id, limit=2, offset=2)],
                ["Episode 2", "Episode 1"],
            )
            self.assertEqual(
                [e.title for e, _ in db.recent_episodes(limit=2, offset=2)],
                ["Episode 2", "Episode 1"],
            )
            db.close()

    def test_recent_episodes_keeps_all_episodes_from_the_same_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "library.db")
            first = db.upsert_podcast(
                {"feed_url": "https://example.test/one.xml", "title": "One"}
            )
            second = db.upsert_podcast(
                {"feed_url": "https://example.test/two.xml", "title": "Two"}
            )
            timestamp = 1704067200
            db.sync_episodes(
                first,
                [{"guid": "one", "title": "One episode", "audio_url": "https://example.test/one.mp3", "published": timestamp}],
            )
            db.sync_episodes(
                second,
                [{"guid": "two", "title": "Two episode", "audio_url": "https://example.test/two.mp3", "published": timestamp}],
            )
            self.assertEqual(len(db.recent_episodes()), 2)
            self.assertEqual(
                {item[0].title for item in db.recent_episodes()},
                {"One episode", "Two episode"},
            )
            db.close()

    def test_favorite_episode_query_excludes_unfavorited_episodes(self):
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
            selected = db.episodes(podcast_id)[0]
            db.set_favorite(selected.id, True)
            favorites = db.search_episodes(favorites_only=True)
            self.assertEqual([item[0].title for item in favorites], [selected.title])
            db.close()

    def test_refresh_does_not_erase_existing_artwork(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "library.db")
            db.upsert_podcast(
                {
                    "feed_url": "https://example.test/feed.xml",
                    "title": "Show",
                    "image_url": "https://example.test/art.jpg",
                }
            )
            db.upsert_podcast(
                {"feed_url": "https://example.test/feed.xml", "title": "Show updated"}
            )
            self.assertEqual(db.podcasts()[0].image_url, "https://example.test/art.jpg")
            db.close()


if __name__ == "__main__":
    unittest.main()
