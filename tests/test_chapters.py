import unittest

from postcast.chapters import active_chapter, parse_extended_comments


class ChapterTests(unittest.TestCase):
    def test_parses_and_orders_extended_comments(self):
        chapters = parse_extended_comments([
            "CHAPTER002=00:10.500",
            "CHAPTER002NAME=Second",
            "CHAPTER001NAME=First",
            "CHAPTER001=00:00:05",
        ])
        self.assertEqual([chapter.title for chapter in chapters], ["First", "Second"])
        self.assertEqual(chapters[0].end_seconds, 10.5)

    def test_invalid_and_duplicate_starts_are_ignored(self):
        chapters = parse_extended_comments([
            "CHAPTER001=bad",
            "CHAPTER002=10",
            "CHAPTER003=10",
        ])
        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0].title, "Chapter 1")

    def test_active_chapter(self):
        chapters = parse_extended_comments(["CHAPTER001=0", "CHAPTER002=30"])
        self.assertEqual(active_chapter(chapters, 1).title, "Chapter 1")
        self.assertEqual(active_chapter(chapters, 30).title, "Chapter 2")
        self.assertIsNone(active_chapter(chapters, -1))


if __name__ == "__main__":
    unittest.main()
