"""Removed ADU redirect stubs must stay deleted so those URLs 404."""
import unittest
from pathlib import Path
import build_players as builder

ROOT = Path(__file__).resolve().parents[1]
SCAN = (
    'sitemap.xml',
    'pages-sitemap.xml',
    'player-sitemap.xml',
    'robots.txt',
    'index.html',
    'articles.json',
)


class NoAduContent(unittest.TestCase):
    def test_removed_paths_are_absent(self):
        self.assertGreaterEqual(len(builder.REMOVED_ADU_PATHS), 16)
        for relative in sorted(builder.REMOVED_ADU_PATHS):
            self.assertFalse((ROOT / relative).exists(), relative)

    def test_sitemaps_and_homepage_do_not_list_adu_urls(self):
        for name in SCAN:
            text = (ROOT / name).read_text().casefold()
            self.assertNotIn('sandiegoadubuilder', text, name)
            self.assertNotIn('accessory dwelling', text, name)
            for relative in builder.REMOVED_ADU_PATHS:
                self.assertNotIn(relative.casefold(), text, name)

    def test_builder_refuses_adu_output(self):
        for relative in builder.REMOVED_ADU_PATHS:
            with self.assertRaises(builder.BuildError):
                builder.reject_removed_adu(relative, '<p>WNBA</p>')
        with self.assertRaises(builder.BuildError):
            builder.reject_removed_adu('wnba/index.html', 'https://sandiegoadubuilder.com/adu-cost.html')
        builder.reject_removed_adu('wnba/caitlin-clark/index.html', '<p>WNBA stats</p>')
