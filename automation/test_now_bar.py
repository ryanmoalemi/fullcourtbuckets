"""One sitewide Now bar: same value on every page, always linked to a live page, never stale."""
import datetime as dt
import re
import unittest
from pathlib import Path

import site_nav
from link_graph import file_for_url, iter_html

ROOT = Path(__file__).resolve().parents[1]


def _exists(url: str) -> bool:
    path = url.split('#', 1)[0]
    return path.startswith('/') and file_for_url(ROOT, path) is not None


class NowBarTests(unittest.TestCase):
    def test_shared_value_is_current_and_linked(self):
        data = site_nav.load_now()
        for key in ('text', 'url', 'expires', 'fallback'):
            self.assertIn(key, data)
        self.assertNotIn('tonight', data['text'].lower())
        self.assertTrue(_exists(data['url']), data['url'])
        self.assertTrue(_exists(data['fallback']['url']), data['fallback']['url'])
        expires = dt.datetime.fromisoformat(data['expires'])
        self.assertGreater(expires, dt.datetime.now(dt.timezone.utc),
                           'data/now-ticker.json has expired: update it with a verified, linked item')

    def test_fallback_after_expiry(self):
        data = site_nav.load_now()
        later = dt.datetime.fromisoformat(data['expires']) + dt.timedelta(minutes=1)
        self.assertEqual(site_nav.now_item(later)['url'], data['fallback']['url'])

    def test_every_page_has_the_shared_bar(self):
        expected = site_nav.now_bar_html()
        bad = []
        for path in iter_html(ROOT):
            html = path.read_text(encoding='utf-8', errors='ignore')
            if 'site-header' not in html:
                continue
            bars = site_nav.NOW_RE.findall(html)
            if bars != [expected]:
                bad.append(str(path.relative_to(ROOT)))
                continue
            href = re.search(r'<a href="([^"]+)"', bars[0])
            if not href or not _exists(href.group(1)):
                bad.append(str(path.relative_to(ROOT)) + ' (link)')
        self.assertEqual(bad, [])


if __name__ == '__main__':
    unittest.main()
