"""flow: the morph of a translated shape and the forward-backward confidence."""

import unittest

import numpy as np

from video_effects_tool import flow
from video_effects_tool.flow import FlowChain

from .images import texture, with_disc

CX, CY, R, SHIFT = 106, 90, 8, 20


class TestTranslatedShape(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.a = with_disc(texture(), CX, CY, R)
        cls.b = np.roll(cls.a, SHIFT, axis=1)
        cls.chain = FlowChain([cls.a, cls.b])

    def test_flow_is_the_shift(self) -> None:
        """FlowChain.flows of a horizontally shifted image gives the shift forward and its negative backward.
        Guards pair_flows' half-resolution computation and upscaling of the flow vectors."""
        fab, fba = self.chain.flows(0)
        self.assertAlmostEqual(float(np.median(fab[..., 0])), SHIFT, delta=1)
        self.assertAlmostEqual(float(np.median(fba[..., 0])), -SHIFT, delta=1)

    def test_midpoint_is_one_shape(self) -> None:
        """FlowChain.blend at 0.5 moves a disc halfway, with no half-dark copies at the start and end positions.
        Guards the warp-both-keys morph against a plain crossfade."""
        mid = self.chain.blend(0, 0.5)
        x = CX + SHIFT // 2
        self.assertLess(mid[CY, x, 0], 20, "disc at the midpoint")
        # no half-dark ghosts at the start and end positions
        self.assertGreater(mid[CY, CX - R + 2, 0], 60)
        self.assertGreater(mid[CY, CX + SHIFT + R - 2, 0], 60)

    def test_endpoints(self) -> None:
        """FlowChain.at returns the first key at 0 and the last at 1 exactly. Guards blend's shortcut at s <= 0
        and s >= 1."""
        np.testing.assert_array_equal(self.chain.at(0), self.a)
        np.testing.assert_array_equal(self.chain.at(1), self.b)

    def test_chain_segments(self) -> None:
        """FlowChain.at of a three-key chain is the middle key at chain time 0.5. Guards equal spacing of keys
        given with --keys."""
        c = self.a + 10
        chain = FlowChain([self.a, self.b, c])
        np.testing.assert_array_equal(chain.at(0.5), self.b)


class TestKeyTimes(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.keys = [texture(160, 90, seed=i) for i in range(3)]

    def test_equal_spacing_default(self) -> None:
        """FlowChain without times spaces keys equally and FlowChain.segment maps chain time to segment and
        local time. Guards the --keys chain times."""
        chain = FlowChain(self.keys)
        self.assertEqual(chain.times, [0, 0.5, 1])
        self.assertEqual(chain.segment(0.25), (0, 0.5))
        self.assertEqual(chain.segment(0.75), (1, 0.5))

    def test_fractions_set_boundaries(self) -> None:
        """FlowChain.segment with key times [0, 0.2, 1] puts the segment boundary at 0.2 and returns the middle
        key there. Guards --from placing each in-between at its keys.json fraction."""
        chain = FlowChain(self.keys, [0.0, 0.2, 1.0])
        self.assertEqual(chain.segment(0.1), (0, 0.5))
        i, s = chain.segment(0.6)
        self.assertEqual(i, 1)
        self.assertAlmostEqual(s, 0.5)
        self.assertEqual(chain.segment(1.0), (1, 1.0))
        np.testing.assert_array_equal(chain.at(0.2), self.keys[1])

    def test_bad_times(self) -> None:
        """flow.check_times refuses a wrong count, a first time other than 0, repeated and decreasing times. A
        bad keys.json must not give a division by zero in segment."""
        for times in ([0, 0.5], [0.1, 0.5, 1], [0, 0.6, 0.6], [0, 0.7, 0.3]):
            with self.assertRaises(ValueError, msg=str(times)):
                FlowChain(self.keys, times)


class TestScale(unittest.TestCase):
    def test_reference_scale_is_one(self) -> None:
        """frames.canvas_scale is 1 on the 2304x1296 reference canvas and 0.5 at half the size. Guards the
        scaling of the tuned blur sigmas and flow tolerance."""
        from video_effects_tool.frames import canvas_scale
        self.assertEqual(canvas_scale(2304, 1296), 1.0)
        self.assertAlmostEqual(canvas_scale(1152, 648), 0.5)


class TestConfidence(unittest.TestCase):
    def test_agreeing_flows(self) -> None:
        """flow.confidence is 1 for opposite forward and backward flows and flow.reliable leaves such a flow
        unchanged. Guards consistent flow not being damped."""
        f = np.zeros((20, 30, 2), np.float32)
        f[..., 0] = 3
        conf = flow.confidence(f, -f)
        self.assertTrue(np.allclose(conf, 1))
        np.testing.assert_allclose(flow.reliable(f, -f), f, atol=1e-5)

    def test_disagreeing_flows_fade_to_blend(self) -> None:
        """flow.confidence is 0 when the forward-backward error exceeds FB_TOL and flow.reliable zeroes the
        flow. Guards inconsistent vectors fading to a plain blend."""
        f = np.zeros((20, 30, 2), np.float32)
        f[..., 0] = 5
        conf = flow.confidence(f, f)  # f + g = 10 px > FB_TOL
        self.assertTrue(np.allclose(conf, 0))
        self.assertTrue(np.allclose(flow.reliable(f, f), 0))

    def test_partial(self) -> None:
        """flow.confidence is 1 - err/FB_TOL for a 2 px forward-backward error. Guards the linear confidence
        formula."""
        f = np.zeros((10, 10, 2), np.float32)
        f[..., 0] = 2
        conf = flow.confidence(f, np.zeros_like(f))  # err 2 px
        self.assertTrue(np.allclose(conf, 1 - 2 / flow.FB_TOL))

    def test_inconsistent_flow_gives_plain_blend(self) -> None:
        """FlowChain.blend with zero flows is the linear blend of the keys. Guards the fallback where confidence
        has removed the flow."""
        a, b = texture(seed=1), texture(seed=2)
        chain = FlowChain([a, b])
        zero = np.zeros(a.shape[:2] + (2,), np.float32)
        chain.flows = lambda i: (zero, zero)
        np.testing.assert_allclose(chain.blend(0, 0.3), 0.7 * a + 0.3 * b, atol=1e-3)


class TestMemory(unittest.TestCase):
    def test_only_the_last_pair_is_kept(self) -> None:
        """FlowChain.flows caches the current pair and replaces it when a later segment is used. Guards memory
        use on long chains (only the last pair kept)."""
        keys = [texture(160, 90, seed=i) for i in range(3)]
        chain = FlowChain(keys)
        first = chain.flows(0)
        self.assertIs(chain.flows(0), first, "same pair: cached")
        chain.at(0.75)
        self.assertEqual(chain._flows[0], 1, "segment 1 replaced segment 0")

    def test_uint8_keys_give_float32_frames(self) -> None:
        """FlowChain.blend of uint8 keys returns float32 frames close to the blend of float32 keys. Guards
        warping keys in their own dtype (uint8 from the CLI) without losing precision."""
        a = with_disc(texture(), CX, CY, R)
        b = np.roll(a, SHIFT, axis=1)
        a8, b8 = (np.clip(x, 0, 255).round().astype(np.uint8) for x in (a, b))
        mid = FlowChain([a8, b8]).blend(0, 0.5)
        self.assertEqual(mid.dtype, np.float32)
        ref = FlowChain([a8.astype(np.float32), b8.astype(np.float32)]).blend(0, 0.5)
        self.assertLess(float(np.abs(mid - ref).mean()), 0.5)
