"""Score rows link our own pages only (Ryan, Oct 19, 2026): FCB recap, else our
play-by-play/game page, else unlinked. Never ESPN or another outside site."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'automation'))
import homepage_rail  # noqa: E402

BOX_RE = re.compile(r'<section class="rail-box" id="(?:latest-scores|playoff-series)">.*?</section>', re.S)


class ScoreLinkTests(unittest.TestCase):
    def test_no_score_link_points_off_site(self):
        bad = []
        for page in ROOT.rglob('*.html'):
            if '.git' in page.parts:
                continue
            text = page.read_text(encoding='utf-8', errors='ignore')
            for box in BOX_RE.findall(text):
                for href in re.findall(r'href="([^"]+)"', box):
                    if not href.startswith('/') or href.startswith('//'):
                        bad.append(f'{page.relative_to(ROOT)}: {href}')
        self.assertEqual(bad, [], '\n'.join(bad))

    def test_resolver_order(self):
        recaps = {'1': '/news/recap/'}
        self.assertEqual(homepage_rail.fcb_game_url('1', recaps), '/news/recap/')
        self.assertEqual(homepage_rail.fcb_game_url('401918306', {}), '/wnba/finals/2026/game-2/play-by-play/')
        self.assertEqual(homepage_rail.fcb_game_url('999', {}), '')

    def test_unlinked_when_no_fcb_page(self):
        html = homepage_rail.render_scores([{'line': 'A 1, B 0', 'when_label': '', 'recap': ''}])
        self.assertNotIn('href', html)


if __name__ == '__main__':
    unittest.main()
