"""`refs` palette and motion curve on arrays (references/reference-video.md,
step 1). The FFmpeg part is in tests/integration/short_video/test_refs.py."""
import unittest

import numpy as np

from short_video_tool import refs


class PaletteTest(unittest.TestCase):
    def test_two_colours_with_shares(self):
        """The palette finds both colours of a two-colour image, sorted by share."""
        px = np.array([[255, 0, 0]] * 300 + [[0, 0, 255]] * 100)
        p = refs.palette(px)
        self.assertEqual([c["hex"] for c in p], ["#ff0000", "#0000ff"])
        self.assertEqual([c["share"] for c in p], [0.75, 0.25])

    def test_single_colour(self):
        """An image of one colour gives one palette entry with share 1."""
        self.assertEqual(refs.palette(np.full((50, 3), 17)), [{"hex": "#111111", "share": 1.0}])


class MotionTest(unittest.TestCase):
    def test_motion_curve(self):
        """The motion curve is the mean absolute frame difference, 0 to 1, timed at the later frame."""
        f = np.zeros((3, 4, 4), np.uint8)
        f[2] = 255
        self.assertEqual(refs.motion_curve(f, 2.0), [[0.5, 0.0], [1.0, 1.0]])


class StampTest(unittest.TestCase):
    def test_stamp(self):
        """Frame file names carry the time with millisecond precision and sort by time."""
        self.assertEqual(refs.stamp(3.25), "003.250")
        self.assertLess(refs.stamp(9.5), refs.stamp(10.0))


if __name__ == "__main__":
    unittest.main()
