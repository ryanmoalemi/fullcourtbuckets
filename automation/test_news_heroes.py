"""16:9 hero crops stay inside the frame and do not upscale."""
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import news_heroes as heroes


class NewsHeroTests(unittest.TestCase):
    def test_default_focal_is_center_25(self):
        self.assertEqual(heroes.parse_focal(None), (0.5, 0.25))
        self.assertEqual(heroes.parse_focal('nope'), (0.5, 0.25))
        self.assertEqual(heroes.parse_focal('center 12%'), (0.5, 0.12))
        self.assertEqual(heroes.parse_focal('40% 10%'), (0.4, 0.1))

    def test_portrait_window_keeps_the_top_third(self):
        left, top, crop_w, crop_h = heroes.cover_window(1000, 2000, 0.5, 0.25)
        self.assertAlmostEqual(crop_w, 1000)
        self.assertAlmostEqual(crop_h, 1000 * 9 / 16)
        self.assertAlmostEqual(left, 0)
        self.assertGreater(top, 0)
        self.assertLess(top, 2000 - crop_h)

    def test_face_near_the_top_shifts_the_window_up(self):
        px, py = heroes.focal_keeping_face(1668, 2529, (627, 315, 296, 399))
        self.assertAlmostEqual(px, 0.5, places=2)
        self.assertLess(py, 0.25)
        _left, top, _crop_w, crop_h = heroes.cover_window(1668, 2529, px, py)
        self.assertLessEqual(top, 315)
        self.assertGreaterEqual(top + crop_h, 315 + 399)

    def test_face_already_in_frame_keeps_the_default(self):
        px, py = heroes.focal_keeping_face(1600, 1067, (700, 280, 140, 180))
        self.assertEqual((px, py), (0.5, 0.25))

    def test_write_heroes_makes_1200_and_a_larger_2x_without_upscaling(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'player.webp'
            Image.new('RGB', (2000, 3000), (20, 40, 80)).save(source, 'WEBP', quality=70)
            written = heroes.write_heroes(source, 'center 25%')
            one = Image.open(written['imageHero'])
            two = Image.open(written['imageHero2x'])
            self.assertEqual(one.size, (1200, 675))
            self.assertEqual(two.size[1] * 16, two.size[0] * 9)
            self.assertGreater(two.size[0], 1200)
            self.assertLessEqual(two.size[0], 2000)
            self.assertEqual(written['imageHero'].name, 'hero-1200.webp')

    def test_narrow_source_is_not_upscaled(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'card.webp'
            Image.new('RGB', (800, 1400), (10, 10, 10)).save(source, 'WEBP', quality=70)
            written = heroes.write_heroes(source, 'center 10%')
            image = Image.open(written['imageHero'])
            self.assertLessEqual(image.size[0], 800)
            self.assertEqual(image.size[0] * 9, image.size[1] * 16)
            self.assertIsNone(written['imageHero2x'])
            self.assertFalse((Path(tmp) / 'hero-1200.webp').exists())
