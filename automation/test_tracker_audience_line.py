"""Guard: the Finals tracker keeps its sourced audience line below the data table (Ryan, Oct. 22, 2026)."""
import unittest
from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / 'news' / '2026-wnba-finals-ratings-tracker' / 'index.html'


class TrackerAudienceLine(unittest.TestCase):
    def test_sourced_line_present_below_table(self):
        html = PAGE.read_text(encoding='utf-8')
        self.assertNotIn('audience: no verified figure', html)
        i = html.find('id="finals-audience-line"')
        self.assertGreater(i, 0)
        self.assertLess(html.find('<table'), i)
        self.assertIn('nbcsports.com/pressbox/press-releases/nbc-and-peacock-deliver-most-watched-wnba-finals-game-1-ever', html)
        self.assertIn('Game 2 averaged 1.33 million', html)
        self.assertNotIn('espn.com', html[i:i + 2000].lower())


if __name__ == '__main__':
    unittest.main()
