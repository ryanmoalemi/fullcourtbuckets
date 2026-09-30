"""The shared gtag snippet skips automated browsers and stays on every tracked page."""
import unittest
from pathlib import Path

from analytics import GA4_TAG, MEASUREMENT_ID
from link_graph import iter_html

ROOT = Path(__file__).resolve().parents[1]
UNCONDITIONAL = f'<script async src="https://www.googletagmanager.com/gtag/js?id={MEASUREMENT_ID}"></script>'
ADSENSE = 'adsbygoogle.js?client=ca-pub-6621195315204235'


class AnalyticsGuardTests(unittest.TestCase):
    def test_guard_skips_automated_browsers(self):
        self.assertIn('if (navigator.webdriver) return;', GA4_TAG)
        self.assertIn('HeadlessChrome|Headless|bot|crawler|spider|Lighthouse|PageSpeed|Playwright|Puppeteer|Selenium', GA4_TAG)
        self.assertIn('window.outerWidth === 0 || window.outerHeight === 0', GA4_TAG)
        self.assertIn(f"gtag('config','{MEASUREMENT_ID}')", GA4_TAG)
        self.assertNotIn(UNCONDITIONAL, GA4_TAG)
        self.assertNotIn('adsbygoogle', GA4_TAG)

    def test_every_tracked_page_uses_the_shared_snippet(self):
        tracked = []
        bare = []
        for path in iter_html(ROOT):
            text = path.read_text(encoding='utf-8')
            rel = path.relative_to(ROOT).as_posix()
            if MEASUREMENT_ID not in text:
                continue
            tracked.append(rel)
            if GA4_TAG not in text or UNCONDITIONAL in text:
                bare.append(rel)
        self.assertGreater(len(tracked), 100)
        self.assertEqual(bare, [])
        home = (ROOT / 'index.html').read_text(encoding='utf-8')
        self.assertIn(ADSENSE, home)
        self.assertLess(home.index(GA4_TAG), home.index(ADSENSE))
        self.assertIn('googlefc.showRevocationMessage', home)
        player = (ROOT / 'wnba' / 'aja-wilson' / 'index.html').read_text(encoding='utf-8')
        self.assertIn(ADSENSE, player)
        self.assertIn('googlefc.showRevocationMessage', player)
        self.assertLess(player.index(GA4_TAG), player.index(ADSENSE))
