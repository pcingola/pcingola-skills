"""Unit tests of `stills` (short_video_tool/stills.py): the warm-up seek before each still and which pages count as
WebGL pages for the blank check."""
import unittest

from short_video_tool import stills


class TestBlankStill(unittest.TestCase):

    def test_uses_webgl(self) -> None:
        """A three.js renderer or a webgl context makes a WebGL page; a 2D canvas or a GSAP page does not. Guards the
        blank check running only on pages whose canvas can come back black."""
        self.assertTrue(stills.uses_webgl("const r = new THREE.WebGLRenderer({ canvas });"))
        self.assertTrue(stills.uses_webgl("const gl = c.getContext('webgl2');"))
        self.assertFalse(stills.uses_webgl("const g = c.getContext(\"2d\"); gsap.timeline();"))


    def test_warm_times(self) -> None:
        """Each asked time follows its warm-up time WARM s later, so the kept (second) shot is the second draw of
        the asked state. Guards the black first draw of new shader programs on a hardware GPU."""
        w = stills.WARM
        self.assertEqual(stills.warm_times([0.0, 10.4]), [w, 0.0, 10.4 + w, 10.4])


if __name__ == "__main__":
    unittest.main()
