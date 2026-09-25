import sqlite3
import threading
import time
from pathlib import Path

from .config import db_path
from .models import Episode, Podcast

SCHEMA_VERSION = 4

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
    favorite INTEGER DEFAULT 0,
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
        self._migrate()

    def _migrate(self):
        """Create or upgrade the database without dropping user data."""
        current = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if current > SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema {current} is newer than supported version "
                f"{SCHEMA_VERSION}"
            )

        if current < 1:
            # CREATE IF NOT EXISTS makes this safe for databases created before
            # schema versioning was introduced.
            self.conn.executescript(SCHEMA)
            self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self.conn.commit()

        if current < 2:
            columns = {
                row[1]
                for row in self.conn.execute("PRAGMA table_info(episodes)").fetchall()
            }
            if "favorite" not in columns:
                self.conn.execute(
                    "ALTER TABLE episodes ADD COLUMN favorite INTEGER DEFAULT 0"
                )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_episodes_favorite ON episodes(favorite)"
            )
            self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self.conn.commit()

        if current < 3:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    episode_id INTEGER NOT NULL UNIQUE REFERENCES episodes(id) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    added_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_queue_position ON queue(position, id);
                """
            )
            self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self.conn.commit()

        if current < 4:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS listening_stats (
                    episode_id INTEGER PRIMARY KEY REFERENCES episodes(id) ON DELETE CASCADE,
                    seconds INTEGER NOT NULL DEFAULT 0,
                    completed INTEGER NOT NULL DEFAULT 0,
                    last_played INTEGER NOT NULL
                );
                """
            )
            self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self.conn.commit()

    def close(self):
        with self._lock:
            if self.conn is not None:
                self.conn.close()
                self.conn = None

    # ---- podcasts ----
    def upsert_podcast(self, data: dict) -> int:
        with self._lock:
            values = {
                "feed_url": data["feed_url"],
                "title": data.get("title", ""),
                "author": data.get("author", ""),
                "description": data.get("description", ""),
                "image_url": data.get("image_url", ""),
                "link": data.get("link", ""),
            }
            self.conn.execute(
                """INSERT INTO podcasts (feed_url, title, author, description, image_url, link)
                   VALUES (:feed_url, :title, :author, :description, :image_url, :link)
                   ON CONFLICT(feed_url) DO UPDATE SET
                     title=excluded.title, author=excluded.author,
                     description=excluded.description, image_url=excluded.image_url,
                     link=excluded.link""",
                values,
            )
            self.conn.commit()
            row = self.conn.execute(
                "SELECT id FROM podcasts WHERE feed_url = ?", (values["feed_url"],)
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

    def search_episodes(
        self, query="", favorites_only=False, unplayed_only=False, downloaded_only=False
    ):
        """Search local episode and podcast metadata with optional filters."""
        with self._lock:
            clauses = []
            params = []
            if query.strip():
                term = f"%{query.strip()}%"
                clauses.append(
                    "(e.title LIKE ? COLLATE NOCASE OR e.description LIKE ? COLLATE NOCASE "
                    "OR p.title LIKE ? COLLATE NOCASE OR p.author LIKE ? COLLATE NOCASE)"
                )
                params.extend([term, term, term, term])
            if favorites_only:
                clauses.append("e.favorite = 1")
            if unplayed_only:
                clauses.append("e.played = 0")
            if downloaded_only:
                clauses.append("e.downloaded_path != ''")

            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            rows = self.conn.execute(
                f"""SELECT e.*, p.id AS result_podcast_id,
                           p.feed_url AS result_feed_url, p.title AS result_podcast_title,
                           p.author AS result_podcast_author, p.description AS result_podcast_description,
                           p.image_url AS result_podcast_image_url, p.link AS result_podcast_link
                    FROM episodes e JOIN podcasts p ON p.id = e.podcast_id
                    {where}
                    ORDER BY COALESCE(e.published, 0) DESC, e.id DESC""",
                params,
            ).fetchall()
            results = []
            for row in rows:
                episode = Episode.from_row(row)
                podcast = Podcast(
                    id=row["result_podcast_id"],
                    feed_url=row["result_feed_url"],
                    title=row["result_podcast_title"] or "",
                    author=row["result_podcast_author"] or "",
                    description=row["result_podcast_description"] or "",
                    image_url=row["result_podcast_image_url"] or "",
                    link=row["result_podcast_link"] or "",
                )
                results.append((episode, podcast))
            return results

    def episode(self, episode_id) -> Episode:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM episodes WHERE id = ?", (episode_id,)
            ).fetchone()
            return Episode.from_row(row)

    def sync_episodes(self, podcast_id, episodes):
        with self._lock:
            new_count = 0
            for ep in episodes:
                if not ep.get("audio_url"):
                    continue
                guid = ep.get("guid") or ep["audio_url"]
                exists = self.conn.execute(
                    "SELECT 1 FROM episodes WHERE podcast_id=? AND guid=?",
                    (podcast_id, guid),
                ).fetchone()
                if exists is None:
                    new_count += 1
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
            return new_count

    def mark_played(self, episode_id, played=True, position_seconds=0):
        with self._lock:
            self.conn.execute(
                "UPDATE episodes SET played=?, position_seconds=? WHERE id=?",
                (1 if played else 0, position_seconds, episode_id),
            )
            self.conn.commit()

    def set_favorite(self, episode_id, favorite=True):
        with self._lock:
            self.conn.execute(
                "UPDATE episodes SET favorite=? WHERE id=?",
                (1 if favorite else 0, episode_id),
            )
            self.conn.commit()

    # ---- playback queue ----
    def queue_items(self):
        with self._lock:
            rows = self.conn.execute(
                """SELECT e.*, p.id AS result_podcast_id,
                           p.feed_url AS result_feed_url, p.title AS result_podcast_title,
                           p.author AS result_podcast_author, p.description AS result_podcast_description,
                           p.image_url AS result_podcast_image_url, p.link AS result_podcast_link
                    FROM queue q
                    JOIN episodes e ON e.id = q.episode_id
                    JOIN podcasts p ON p.id = e.podcast_id
                    ORDER BY q.position, q.id"""
            ).fetchall()
            results = []
            for row in rows:
                results.append(
                    (
                        Episode.from_row(row),
                        Podcast(
                            id=row["result_podcast_id"],
                            feed_url=row["result_feed_url"],
                            title=row["result_podcast_title"] or "",
                            author=row["result_podcast_author"] or "",
                            description=row["result_podcast_description"] or "",
                            image_url=row["result_podcast_image_url"] or "",
                            link=row["result_podcast_link"] or "",
                        ),
                    )
                )
            return results

    def is_queued(self, episode_id):
        with self._lock:
            return self.conn.execute(
                "SELECT 1 FROM queue WHERE episode_id=?", (episode_id,)
            ).fetchone() is not None

    def add_to_queue(self, episode_id):
        with self._lock:
            if self.is_queued(episode_id):
                return False
            position = self.conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM queue"
            ).fetchone()[0]
            self.conn.execute(
                "INSERT INTO queue(episode_id, position, added_at) VALUES (?, ?, ?)",
                (episode_id, position, int(time.time())),
            )
            self.conn.commit()
            return True

    def remove_from_queue(self, episode_id):
        with self._lock:
            self.conn.execute("DELETE FROM queue WHERE episode_id=?", (episode_id,))
            self.conn.commit()

    def clear_queue(self):
        with self._lock:
            self.conn.execute("DELETE FROM queue")
            self.conn.commit()

    # ---- statistics ----
    def record_listening(self, episode_id, seconds, completed=False):
        seconds = max(0, int(seconds))
        if seconds == 0 and not completed:
            return
        with self._lock:
            self.conn.execute(
                """INSERT INTO listening_stats(episode_id, seconds, completed, last_played)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(episode_id) DO UPDATE SET
                     seconds=listening_stats.seconds + excluded.seconds,
                     completed=listening_stats.completed + excluded.completed,
                     last_played=excluded.last_played""",
                (episode_id, seconds, 1 if completed else 0, int(time.time())),
            )
            self.conn.commit()

    def listening_summary(self):
        with self._lock:
            return self.conn.execute(
                """SELECT p.id, p.title, SUM(s.seconds) AS seconds,
                          SUM(s.completed) AS completed
                   FROM listening_stats s
                   JOIN episodes e ON e.id=s.episode_id
                   JOIN podcasts p ON p.id=e.podcast_id
                   GROUP BY p.id, p.title
                   ORDER BY seconds DESC"""
            ).fetchall()

    # ---- portable sync state ----
    def export_sync_state(self):
        """Return mergeable library state without machine-specific file paths."""
        with self._lock:
            podcasts = [dict(row) for row in self.conn.execute("SELECT * FROM podcasts")]
            episodes = []
            for row in self.conn.execute(
                """SELECT e.*, p.feed_url FROM episodes e
                   JOIN podcasts p ON p.id=e.podcast_id"""
            ):
                item = dict(row)
                item.pop("id", None)
                item.pop("podcast_id", None)
                item.pop("downloaded_path", None)
                episodes.append(item)
            queue = [
                dict(row)
                for row in self.conn.execute(
                    """SELECT p.feed_url, e.guid, q.position
                       FROM queue q JOIN episodes e ON e.id=q.episode_id
                       JOIN podcasts p ON p.id=e.podcast_id
                       ORDER BY q.position, q.id"""
                )
            ]
            listening = []
            for row in self.conn.execute(
                """SELECT p.feed_url, e.guid, s.seconds, s.completed, s.last_played
                   FROM listening_stats s JOIN episodes e ON e.id=s.episode_id
                   JOIN podcasts p ON p.id=e.podcast_id"""
            ):
                listening.append(dict(row))
            settings = {
                key: self.get_setting(key)
                for key in ("playback_rate", "playback_volume")
                if self.get_setting(key) is not None
            }
            return {
                "version": 1,
                "podcasts": podcasts,
                "episodes": episodes,
                "queue": queue,
                "listening": listening,
                "settings": settings,
            }

    def import_sync_state(self, state):
        """Merge portable state, retaining local downloaded file paths."""
        with self._lock:
            podcast_ids = {}
            for podcast in state.get("podcasts", []):
                podcast_ids[podcast["feed_url"]] = self.upsert_podcast(podcast)

            episode_ids = {}
            for episode in state.get("episodes", []):
                podcast_id = podcast_ids.get(episode.get("feed_url"))
                if podcast_id is None:
                    continue
                guid = episode.get("guid") or episode.get("audio_url", "")
                existing = self.conn.execute(
                    "SELECT id, played, favorite, position_seconds FROM episodes "
                    "WHERE podcast_id=? AND guid=?",
                    (podcast_id, guid),
                ).fetchone()
                if existing is None:
                    self.conn.execute(
                        """INSERT INTO episodes
                           (podcast_id, guid, title, description, audio_url,
                            duration_seconds, published, played, favorite, position_seconds)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            podcast_id,
                            guid,
                            episode.get("title", ""),
                            episode.get("description", ""),
                            episode.get("audio_url", ""),
                            int(episode.get("duration_seconds") or 0),
                            episode.get("published"),
                            int(episode.get("played") or 0),
                            int(episode.get("favorite") or 0),
                            int(episode.get("position_seconds") or 0),
                        ),
                    )
                else:
                    self.conn.execute(
                        """UPDATE episodes SET
                           played=MAX(played, ?), favorite=MAX(favorite, ?),
                           position_seconds=MAX(position_seconds, ?)
                           WHERE id=?""",
                        (
                            int(episode.get("played") or 0),
                            int(episode.get("favorite") or 0),
                            int(episode.get("position_seconds") or 0),
                            existing["id"],
                        ),
                    )
                row = self.conn.execute(
                    "SELECT id FROM episodes WHERE podcast_id=? AND guid=?",
                    (podcast_id, guid),
                ).fetchone()
                episode_ids[(episode.get("feed_url"), guid)] = row["id"]

            for item in state.get("queue", []):
                episode_id = episode_ids.get((item.get("feed_url"), item.get("guid")))
                if episode_id is not None:
                    self.conn.execute(
                        "INSERT OR IGNORE INTO queue(episode_id, position, added_at) VALUES (?, ?, ?)",
                        (episode_id, int(item.get("position") or 0), int(time.time())),
                    )

            for item in state.get("listening", []):
                episode_id = episode_ids.get((item.get("feed_url"), item.get("guid")))
                if episode_id is not None:
                    self.conn.execute(
                        """INSERT INTO listening_stats(episode_id, seconds, completed, last_played)
                           VALUES (?, ?, ?, ?)
                           ON CONFLICT(episode_id) DO UPDATE SET
                             seconds=MAX(listening_stats.seconds, excluded.seconds),
                             completed=MAX(listening_stats.completed, excluded.completed),
                             last_played=MAX(listening_stats.last_played, excluded.last_played)""",
                        (
                            episode_id,
                            int(item.get("seconds") or 0),
                            int(item.get("completed") or 0),
                            int(item.get("last_played") or 0),
                        ),
                    )
            for key, value in state.get("settings", {}).items():
                self.set_setting(key, value)
            self.conn.commit()
            return len(episode_ids)

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
