import unittest

from postcast.playback_policy import rate_requires_seek


class PlaybackPolicyTests(unittest.TestCase):
    def test_normal_speed_never_requires_a_flushing_seek(self):
        self.assertFalse(rate_requires_seek(1.0))
        self.assertFalse(rate_requires_seek(1.0005))

    def test_nonstandard_speed_uses_rate_seek(self):
        self.assertTrue(rate_requires_seek(0.75))
        self.assertTrue(rate_requires_seek(1.25))


if __name__ == "__main__":
    unittest.main()
