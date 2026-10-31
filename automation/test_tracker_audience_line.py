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
        self.assertIn('Game 6 averaged 1.5 million', html)
        self.assertIn('usa-sports-delivers-15-million-viewers-valkyries-dream-game-6-thursday', html)
        self.assertIn('Nielsen panel-only data and digital data from Adobe Analytics', html)
        self.assertIn('https://x.com/MylesEhrlich/status/2116589348288127085', html)
        self.assertNotIn('Game 6 not yet released', html)
        self.assertNotIn('espn.com', html[i:i + 2500].lower())


if __name__ == '__main__':
    unittest.main()
