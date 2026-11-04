"""The where-to-watch refresh must keep the current bar list and title.

The Nov 4 data refresh republished a frozen Finals title and a 251-bar
description from data/seo-meta.json. The venue rows were still in the HTML.
These checks fail if that template comes back, or if a rebuild would publish
fewer venues than the page already lists.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'automation'))
import build_where_to_watch as watch  # noqa: E402
import seo_meta  # noqa: E402

PAGE = '/wnba/where-to-watch/'
STALE_TITLE = 'Where to watch the 2026 WNBA Finals: bars showing games'
STALE_DESC = (
    '251 bars and restaurants in 74 U.S. and Canadian cities that show WNBA games, '
    'from team watch-party lists, venue pages and confirmations. Search by city.'
)


class WhereToWatchCount(unittest.TestCase):
    def test_override_uses_live_counts_not_the_finals_template(self):
        raw = json.loads((ROOT / 'data' / 'seo-meta.json').read_text(encoding='utf-8'))[PAGE]
        self.assertEqual(raw['title'], watch.TITLE)
        self.assertNotIn('Finals', raw['title'])
        self.assertIn('{wtw_venues}', raw['description'])
        self.assertIn('{wtw_cities}', raw['description'])
        self.assertNotIn('251', raw['description'])

    def test_filled_wording_matches_the_bar_file(self):
        rows = watch.load()
        summary = watch.stats(rows)
        title, description = seo_meta.where_to_watch_meta(ROOT)
        self.assertEqual(title, watch.TITLE)
        self.assertEqual(description, watch.description(summary))
        filled = seo_meta.load_overrides(ROOT)[PAGE]
        self.assertEqual(filled['title'], title)
        self.assertEqual(filled['description'], description)
        self.assertGreaterEqual(summary['venues'], 388)
        self.assertGreaterEqual(summary['confirmed'], 292)

    def test_published_page_lists_every_venue(self):
        html = (ROOT / 'wnba' / 'where-to-watch' / 'index.html').read_text(encoding='utf-8')
        summary = watch.stats(watch.load())
        self.assertEqual(html.count('class="ww-row"'), summary['venues'])
        self.assertIn(f'<strong>{summary["venues"]}</strong> venues', html)
        self.assertIn(f'<strong>{summary["confirmed"]}</strong> confirmed with staff', html)
        self.assertIn(f'<title>{watch.TITLE}</title>', html)
        self.assertIn(watch.description(summary), html)
        self.assertNotIn(STALE_TITLE, html)
        self.assertNotIn('251 bars', html)
        out = seo_meta.apply_text(html, PAGE, seo_meta.load_overrides(ROOT))
        self.assertEqual(out, html)

    def test_refresh_replaces_the_stale_finals_title_without_dropping_rows(self):
        rows = '<li class="ww-row"></li>' * 3
        html = (
            '<html><head>'
            f'<title>{STALE_TITLE}</title>'
            f'<meta name="description" content="{STALE_DESC}">'
            f'<meta property="og:description" content="{STALE_DESC}">'
            f'</head><body>{rows}</body></html>'
        )
        out = seo_meta.apply_text(html, PAGE, {})
        self.assertIn(f'<title>{watch.TITLE}</title>', out)
        self.assertIn(watch.description(watch.stats(watch.load())), out)
        self.assertNotIn('251 bars', out)
        self.assertNotIn(STALE_TITLE, out)
        self.assertEqual(out.count('class="ww-row"'), 3)

    def test_guard_fails_when_the_venue_count_would_drop(self):
        with self.assertRaises(SystemExit) as caught:
            watch.refuse_venue_drop(388, 251)
        self.assertIn('388', str(caught.exception))
        self.assertIn('251', str(caught.exception))
        watch.refuse_venue_drop(388, 388)
        watch.refuse_venue_drop(388, 389)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            page = root / 'wnba' / 'where-to-watch'
            page.mkdir(parents=True)
            (page / 'index.html').write_text('<li class="ww-row"></li>' * 400, encoding='utf-8')
            with self.assertRaises(SystemExit) as caught:
                seo_meta.guard_where_to_watch(root)
            self.assertIn('400', str(caught.exception))
        seo_meta.guard_where_to_watch(ROOT)

    def test_allow_drop_is_explicit(self):
        os.environ['WTW_ALLOW_DROP'] = '1'
        try:
            watch.refuse_venue_drop(388, 251)
        finally:
            del os.environ['WTW_ALLOW_DROP']


if __name__ == '__main__':
    unittest.main()
