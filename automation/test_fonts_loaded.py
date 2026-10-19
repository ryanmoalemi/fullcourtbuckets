"""Every page with the shared header loads Barlow/Inter (Oct 19, 2026: /players/ menu fell back)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'automation'))
import site_nav  # noqa: E402


class FontsLoadedTests(unittest.TestCase):
    def test_header_pages_load_barlow(self):
        missing = []
        for p in ROOT.rglob('*.html'):
            if '.git' in p.parts:
                continue
            h = p.read_text(encoding='utf-8', errors='ignore')
            if 'class="site-header"' in h and 'family=Barlow:' not in h:
                missing.append(p.relative_to(ROOT).as_posix())
        self.assertEqual(missing, [], 'Missing Barlow font link:\n' + '\n'.join(sorted(missing)[:50]))

    def test_ensure_assets_adds_fonts(self):
        out = site_nav.ensure_assets('<html><head></head><body></body></html>')
        self.assertIn('family=Barlow:', out)


if __name__ == '__main__':
    unittest.main()
