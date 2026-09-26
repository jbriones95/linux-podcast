import unittest

from postcast.mpris_policy import seek_target


class MprisPolicyTests(unittest.TestCase):
    def test_seek_is_clamped_to_track_bounds(self):
        self.assertEqual(seek_target(120, 300, 10), 130)
        self.assertEqual(seek_target(5, 300, -10), 0)
        self.assertEqual(seek_target(295, 300, 30), 300)

    def test_seek_can_be_requested_before_duration_is_known(self):
        self.assertEqual(seek_target(0, 0, 10), 10)


if __name__ == "__main__":
    unittest.main()
