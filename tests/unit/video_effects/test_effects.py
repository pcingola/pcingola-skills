"""effects: region delay field and local times, crossfades."""

import unittest

import numpy as np

from video_effects_tool import effects

from .images import gradient, texture


class TestDelayField(unittest.TestCase):
    def test_range_and_seed(self) -> None:
        """effects.delay_field is normalised to [0, 1], deterministic for one seed and different for another.
        Guards --seed giving the same output (SKILL.md) and the normalisation local_time relies on."""
        end = gradient(160, 90).astype(np.float32)
        d = effects.delay_field(end, seed=7, lum_weight=0.35)
        self.assertEqual(d.shape, (90, 160))
        self.assertGreaterEqual(float(d.min()), 0)
        self.assertLessEqual(float(d.max()), 1)
        self.assertAlmostEqual(float(d.min()), 0, places=3)
        self.assertAlmostEqual(float(d.max()), 1, places=3)
        np.testing.assert_array_equal(d, effects.delay_field(end, seed=7, lum_weight=0.35))
        self.assertFalse(np.allclose(d, effects.delay_field(end, seed=8, lum_weight=0.35)))

    def test_noise_shape_as_method(self) -> None:
        """effects.noise_shape gives `cells` rows and int(cells*w/h)+1 columns, at least 2, on landscape and
        portrait canvases. Guards the noise octaves keeping the canvas aspect."""
        self.assertEqual(effects.noise_shape(3, 2304, 1296), (3, 6))
        self.assertEqual(effects.noise_shape(12, 2304, 1296), (12, 22))
        self.assertEqual(effects.noise_shape(3, 1166, 2074), (3, 2))

    def test_vertical_canvas(self) -> None:
        """effects.delay_field on a portrait image has the image's shape. Guards width and height in the noise
        resize."""
        d = effects.delay_field(gradient(90, 160).astype(np.float32), seed=1, lum_weight=0.35)
        self.assertEqual(d.shape, (160, 90))

    def test_bright_changes_first(self) -> None:
        """effects.delay_field with lum_weight 1 gives bright areas of the end image a smaller delay. Guards the
        inverted luminance rule of the region effect."""
        end = np.zeros((90, 160, 3), np.float32)
        end[:, 80:] = 255
        d = effects.delay_field(end, seed=7, lum_weight=1.0)
        self.assertLess(d[:, 140:].mean(), d[:, :20].mean())

    def test_local_times_differ_mid_transition(self) -> None:
        """effects.local_time spreads pixel times at mid-transition and is exactly 0 at the start and 1 at the
        end. Guards the region clip starting and ending on the keys."""
        d = effects.delay_field(gradient(160, 90).astype(np.float32), seed=7, lum_weight=0.35)
        lt = effects.local_time(0.5, d, 0.55)
        self.assertLess(float(lt.min()), 0.2)
        self.assertGreater(float(lt.max()), 0.8)
        self.assertTrue(np.all(effects.local_time(0.0, d, 0.55) == 0))
        self.assertTrue(np.all(effects.local_time(1.0, d, 0.55) == 1))


class TestRegion(unittest.TestCase):
    def test_endpoints_and_mid(self) -> None:
        """effects.region gives the start key at 0, the end key at 1 and a mid frame where some pixels are near
        each key, deterministically. Guards the per-pixel read of the flow sequence at delayed times."""
        a, b = texture(160, 90, seed=1), texture(160, 90, seed=2)
        frame = effects.region([a, b], steps=8, spread=0.55, lum_weight=0.35, seed=7)
        self.assertLess(np.abs(frame(0) - a).max(), 1.0)
        self.assertLess(np.abs(frame(1) - b).max(), 1.0)
        mid = frame(0.5)
        da, db = np.abs(mid - a).mean(axis=2), np.abs(mid - b).mean(axis=2)
        self.assertGreater(float((da < 0.3 * db).mean()), 0.05, "some pixels still near the start")
        self.assertGreater(float((db < 0.3 * da).mean()), 0.05, "some pixels already near the end")
        np.testing.assert_array_equal(mid, effects.region([a, b], 8, 0.55, 0.35, 7)(0.5))


class TestCrossfades(unittest.TestCase):
    def setUp(self) -> None:
        self.a = gradient(96, 54).astype(np.float32)
        self.b = gradient(96, 54, flip=True).astype(np.float32)

    def test_crossfade(self) -> None:
        """effects.crossfade blends with smoothstep easing at 0, 0.25, 0.5 and 1. Guards the eased, not linear,
        blend."""
        f = effects.crossfade(self.a, self.b)
        np.testing.assert_allclose(f(0), self.a)
        np.testing.assert_allclose(f(1), self.b)
        np.testing.assert_allclose(f(0.5), 0.5 * self.a + 0.5 * self.b)
        np.testing.assert_allclose(f(0.25), (1 - 0.15625) * self.a + 0.15625 * self.b, rtol=1e-5)

    def test_blur_crossfade(self) -> None:
        """effects.blur_crossfade is unblurred at the ends and blurred at mid-transition. Guards the sin-shaped
        blur sigma that rises and falls back to 0."""
        f = effects.blur_crossfade(self.a, self.b, 6.0)
        np.testing.assert_allclose(f(0), self.a, atol=1e-3)
        np.testing.assert_allclose(f(1), self.b, atol=1e-3)
        mid = f(0.5)
        plain = 0.5 * self.a + 0.5 * self.b
        self.assertGreater(np.abs(mid - plain).max(), 1.0, "blurred at mid-transition")
