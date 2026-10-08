#!/usr/bin/env python3
"""Image optimizer keeps pixels, alt text, and a passing build when one file fails."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import optimize_images as opt


class OptimizeImagesTest(unittest.TestCase):
    def test_fit_never_upscales_or_stretches(self):
        self.assertEqual(opt.fit_size((400, 200), (800, 800)), (400, 200))
        self.assertEqual(opt.fit_size((1536, 1024), (760, 507)), (760, 507))
        width, height = opt.fit_size((1254, 1254), (732, 1140), cover=True, min_side=1024)
        self.assertGreaterEqual(min(width, height), 1024)
        self.assertLessEqual(max(width, height), 1254)
        self.assertAlmostEqual(width / height, 1, places=2)

    def test_markup_preserves_alt_and_marks_the_hero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = Image.new('RGB', (300, 150), (20, 40, 60))
            image.save(root / 'photo.jpg', quality=90)
            page = root / 'index.html'
            page.write_text(
                '<img class="feature-photo" id="featured-image" '
                'src="photo.jpg" alt="A&#x27;ja Wilson keeps the ball">'
                '<img src="photo.jpg">',
                encoding='utf-8',
            )
            opt.optimize_tree(root)
            html = page.read_text(encoding='utf-8')
            self.assertIn('alt="A&#x27;ja Wilson keeps the ball"', html)
            self.assertIn('type="image/webp"', html)
            self.assertIn('fetchpriority="high"', html)
            self.assertIn('loading="lazy"', html)
            self.assertIn('decoding="async"', html)
            self.assertIn('width="300"', html)
            self.assertEqual(html.count('fetchpriority="high"'), 1)
            missing = (root / 'docs' / 'missing-alt.md').read_text(encoding='utf-8')
            self.assertIn('photo.jpg', missing)
            self.assertIn('No alt text was written', missing)

    def test_closed_source_lead_is_eager_and_the_logo_stays_lazy(self):
        html = (
            '<img src="/logo.png" alt="Full Court Buckets" width="760" height="507">'
            '<figure class="lead-photo"><picture>'
            '<source srcset="/hero-1200.webp 1200w" type="image/webp" sizes="842px"></source>'
            '<img src="/hero-1200.webp" alt="A player at the line" width="1200" height="675" '
            'decoding="async" loading="lazy">'
            '</picture></figure>'
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            Image.new('RGB', (1200, 675), (30, 40, 50)).save(root / 'hero-1200.webp', quality=80)
            Image.new('RGB', (760, 507), (10, 10, 10)).save(root / 'logo.png')
            updated, _missing = opt.rewrite_html(root, html)
        lead = updated[updated.find('<figure'):]
        logo = updated[:updated.find('<figure')]
        self.assertIn('fetchpriority="high"', lead)
        self.assertNotIn('loading=', lead)
        self.assertIn('loading="lazy"', logo)
        self.assertNotIn('fetchpriority="high"', logo)
        self.assertEqual(updated.count('fetchpriority="high"'), 1)

    def test_broken_file_is_kept_and_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / 'broken.png'
            target.write_bytes(b'not an image')
            before = target.read_bytes()
            log: list[str] = []
            changed = opt.optimize_file(root, target, log, {}, set())
            self.assertFalse(changed)
            self.assertEqual(target.read_bytes(), before)
            self.assertTrue(any(line.startswith('KEPT ') for line in log))

    def test_portrait_resize_updates_the_hash_the_checker_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / 'images' / 'players' / 'test-player'
            folder.mkdir(parents=True)
            image = Image.new('RGBA', (1400, 1400), (0, 0, 0, 0))
            for pixel in ((10, 10), (800, 800)):
                image.putpixel(pixel, (200, 20, 20, 255))
            image.save(folder / 'portrait.png')
            record = {
                'schema_version': 1,
                'portraits': [{
                    'slug': 'test-player',
                    'src': '/images/players/test-player/portrait.png',
                    'width': 1400,
                    'height': 1400,
                    'asset_sha256': 'old',
                    'export_settings': {
                        'source_width': 1400,
                        'source_height': 1400,
                        'upscaled': False,
                    },
                }],
            }
            manifest = root / 'content'
            manifest.mkdir()
            (manifest / 'player-illustrations.json').write_text(json.dumps(record), encoding='utf-8')
            page = root / 'wnba' / 'test-player'
            page.mkdir(parents=True)
            (page / 'index.html').write_text(
                '<img class="player-illustration" src="/images/players/test-player/portrait.png?v=old" '
                'alt="Test Player illustrated portrait" width="1400" height="1400" '
                'fetchpriority="high" decoding="async">',
                encoding='utf-8',
            )
            opt.optimize_tree(root)
            self.assertFalse((folder / 'portrait.png').exists())
            webp = folder / 'portrait.webp'
            self.assertTrue(webp.is_file())
            saved = json.loads((manifest / 'player-illustrations.json').read_text(encoding='utf-8'))
            portrait = saved['portraits'][0]
            self.assertEqual(portrait['src'], '/images/players/test-player/portrait.webp')
            self.assertGreaterEqual(min(portrait['width'], portrait['height']), 1024)
            self.assertEqual(portrait['export_settings']['source_width'], 1400)
            self.assertFalse(portrait['export_settings']['upscaled'])
            html = (page / 'index.html').read_text(encoding='utf-8')
            self.assertIn('/images/players/test-player/portrait.webp?v=', html)
            self.assertNotIn('<picture>', html)
            self.assertIn('alt="Test Player illustrated portrait"', html)
            self.assertIn('fetchpriority="high"', html)
            self.assertNotIn('loading="lazy"', html)


if __name__ == '__main__':
    unittest.main()
