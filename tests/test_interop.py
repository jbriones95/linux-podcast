import tempfile
import unittest
from pathlib import Path

from postcast.database import Database
from postcast.interop import export_opml, import_opml


class InteropTests(unittest.TestCase):
    def test_opml_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "library.db")
            db.upsert_podcast(
                {
                    "feed_url": "https://example.test/feed.xml",
                    "title": "Example Show",
                    "link": "https://example.test/",
                }
            )
            path = export_opml(db, Path(tmp) / "subscriptions.opml")
            self.assertEqual(import_opml(path), ["https://example.test/feed.xml"])
            db.close()


if __name__ == "__main__":
    unittest.main()
