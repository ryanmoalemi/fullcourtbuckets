"""No page credits ESPN for game stats (box score, game, play-by-play, scoreboard,
recap links or 'Box score: ESPN' lines). ESPN story/press-release links are allowed."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'automation'))
import strip_espn_stats  # noqa: E402

BAD = re.compile(r'href="' + strip_espn_stats.STAT_HREF + '"|Box score: <a[^>]*>ESPN|Box scores?:[^<]*\\(ESPN\\)')


class NoEspnGameStatsTests(unittest.TestCase):
    def test_no_page_links_espn_game_stats(self):
        bad = []
        for p in ROOT.rglob('*.html'):
            if '.git' in p.parts:
                continue
            for m in BAD.finditer(p.read_text(encoding='utf-8', errors='ignore')):
                bad.append(f'{p.relative_to(ROOT)}: {m.group(0)[:90]}')
        self.assertEqual(bad, [], 'Run automation/strip_espn_stats.py:\n' + '\n'.join(bad[:40]))

    def test_clean_keeps_press_release_links(self):
        html = ('<p>Viewers (<a href="https://www.espn.com/wnba/story/_/id/1/x">ESPN</a>).</p>'
                '<p>Won 90-80 (<a href="https://www.espn.com/wnba/boxscore/_/gameId/1">box score</a>).</p>'
                '<p class="box-score">Box score: <a href="https://www.espn.com/wnba/game/_/gameId/1">ESPN</a>.</p>')
        out = strip_espn_stats.clean(html, {})
        self.assertIn('/wnba/story/', out)
        self.assertNotIn('gameId', out)
        self.assertIn('<p>Won 90-80.</p>', out)

    def test_clean_swaps_to_our_page(self):
        out = strip_espn_stats.clean('<p>(<a href="https://www.espn.com/wnba/playbyplay/_/gameId/9">ESPN play-by-play</a>)</p>',
                                     {'9': '/wnba/finals/2026/game-1/play-by-play/'})
        self.assertIn('href="/wnba/finals/2026/game-1/play-by-play/"', out)
        self.assertNotIn('ESPN', out)


if __name__ == '__main__':
    unittest.main()
