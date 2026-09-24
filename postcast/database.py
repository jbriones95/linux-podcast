import sqlite3
import threading
from pathlib import Path

from .config import db_path
from .models import Episode, Podcast

SCHEMA = """
CREATE TABLE IF NOT EXISTS podcasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_url TEXT UNIQUE NOT NULL,
    title TEXT DEFAULT '',
    author TEXT DEFAULT '',
    description TEXT DEFAULT '',
    image_url TEXT DEFAULT '',
    link TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    podcast_id INTEGER NOT NULL REFERENCES podcasts(id) ON DELETE CASCADE,
    guid TEXT DEFAULT '',
    title TEXT DEFAULT '',
    description TEXT DEFAULT '',
    audio_url TEXT DEFAULT '',
    duration_seconds INTEGER DEFAULT 0,
    published INTEGER,
    downloaded_path TEXT DEFAULT '',
    played INTEGER DEFAULT 0,
    position_seconds INTEGER DEFAULT 0,
    UNIQUE(podcast_id, guid)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_episodes_podcast ON episodes(podcast_id);
CREATE INDEX IF NOT EXISTS idx_episodes_published ON episodes(published);
"""


class Database:
    def __init__(self, path=None):
        self.path = str(path or db_path())
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        with self._lock:
            self.conn.close()

    # ---- podcasts ----
    def upsert_podcast(self, data: dict) -> int:
        with self._lock:
            cur = self.conn.execute(
                """INSERT INTO podcasts (feed_url, title, author, description, image_url, link)
                   VALUES (:feed_url, :title, :author, :description, :image_url, :link)
                   ON CONFLICT(feed_url) DO UPDATE SET
                     title=excluded.title, author=excluded.author,
                     description=excluded.description, image_url=excluded.image_url,
                     link=excluded.link""",
                data,
            )
            self.conn.commit()
            row = self.conn.execute(
                "SELECT id FROM podcasts WHERE feed_url = ?", (data["feed_url"],)
            ).fetchone()
            return row["id"]

    def podcasts(self):
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM podcasts ORDER BY title COLLATE NOCASE"
            ).fetchall()
            pod = [Podcast.from_row(r) for r in rows]
            # episode counts
            counts = dict(
                self.conn.execute(
                    "SELECT podcast_id, COUNT(*) FROM episodes GROUP BY podcast_id"
                ).fetchall()
            )
            for p in pod:
                p.episode_count = counts.get(p.id, 0)
            return pod

    def podcast(self, podcast_id) -> Podcast:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM podcasts WHERE id = ?", (podcast_id,)
            ).fetchone()
            return Podcast.from_row(row)

    def delete_podcast(self, podcast_id):
        with self._lock:
            self.conn.execute("DELETE FROM episodes WHERE podcast_id = ?", (podcast_id,))
            self.conn.execute("DELETE FROM podcasts WHERE id = ?", (podcast_id,))
            self.conn.commit()

    # ---- episodes ----
    def episodes(self, podcast_id):
        with self._lock:
            rows = self.conn.execute(
                """SELECT * FROM episodes WHERE podcast_id = ?
                   ORDER BY COALESCE(published, 0) DESC""",
                (podcast_id,),
            ).fetchall()
            return [Episode.from_row(r) for r in rows]

    def episode(self, episode_id) -> Episode:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM episodes WHERE id = ?", (episode_id,)
            ).fetchone()
            return Episode.from_row(row)

    def sync_episodes(self, podcast_id, episodes):
        with self._lock:
            seen = []
            for ep in episodes:
                if not ep.get("audio_url"):
                    continue
                guid = ep.get("guid") or ep["audio_url"]
                seen.append(guid)
                self.conn.execute(
                    """INSERT INTO episodes
                       (podcast_id, guid, title, description, audio_url,
                        duration_seconds, published)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(podcast_id, guid) DO UPDATE SET
                         title=excluded.title, description=excluded.description,
                         audio_url=excluded.audio_url,
                         duration_seconds=excluded.duration_seconds,
                         published=excluded.published""",
                    (
                        podcast_id,
                        guid,
                        ep.get("title", ""),
                        ep.get("description", ""),
                        ep["audio_url"],
                        int(ep.get("duration_seconds") or 0),
                        ep.get("published"),
                    ),
                )
            self.conn.commit()

    def mark_played(self, episode_id, played=True, position_seconds=0):
        with self._lock:
            self.conn.execute(
                "UPDATE episodes SET played=?, position_seconds=? WHERE id=?",
                (1 if played else 0, position_seconds, episode_id),
            )
            self.conn.commit()

    def set_position(self, episode_id, position_seconds):
        with self._lock:
            self.conn.execute(
                "UPDATE episodes SET position_seconds=? WHERE id=?", (position_seconds, episode_id)
            )
            self.conn.commit()

    def set_downloaded(self, episode_id, path):
        with self._lock:
            self.conn.execute(
                "UPDATE episodes SET downloaded_path=? WHERE id=?", (str(path), episode_id)
            )
            self.conn.commit()

    def clear_download(self, episode_id):
        with self._lock:
            self.conn.execute("UPDATE episodes SET downloaded_path='' WHERE id=?", (episode_id,))
            self.conn.commit()

    # ---- settings ----
    def get_setting(self, key, default=None):
        with self._lock:
            row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default

    def set_setting(self, key, value):
        with self._lock:
            self.conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)),
            )
            self.conn.commit()