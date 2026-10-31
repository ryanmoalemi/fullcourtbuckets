"""WNBA revenue multiples are Forbes values divided by Playbook revenue.

A missing source, a Sportico or CNBC value in the Forbes column, or a multiple
that is not that division fails the build. Portland and Toronto stay blank.
"""
import json
import unittest
from pathlib import Path

import build_players
import build_team_revenue as revenue
import internal_links as links

ROOT = Path(__file__).resolve().parents[1]
ROUTE = '/wnba/team-revenue/'


class TeamRevenueValidationTests(unittest.TestCase):
    def test_published_file_passes(self):
        payload = revenue.load(ROOT / revenue.DATA_FILE)
        revenue.validate(payload)

    def test_multiple_is_value_over_playbook_revenue(self):
        payload = revenue.enrich(revenue.load(ROOT / revenue.DATA_FILE))
        for team in payload['teams']:
            self.assertEqual(
                team['value_to_revenue_multiple'],
                revenue.multiple(team['forbes_2026_value_usd_m'], team['2025_revenue_usd_m']),
                team['team'],
            )
        by_slug = {team['slug']: team for team in payload['teams']}
        self.assertEqual(by_slug['golden-state-valkyries']['value_to_revenue_multiple'], 10.0)
        self.assertEqual(by_slug['atlanta-dream']['value_to_revenue_multiple'], 15.6)
        self.assertEqual(by_slug['washington-mystics']['value_to_revenue_multiple'], 17.5)
        self.assertEqual(by_slug['indiana-fever']['value_to_revenue_multiple'], 10.4)
        self.assertEqual(by_slug['seattle-storm']['playbook_graphic_multiple'], 15.4)
        self.assertEqual(
            sorted(team['slug'] for team in payload['teams'] if team['revenue_conflict']),
            ['indiana-fever', 'washington-mystics'],
        )
        self.assertEqual(payload['fcb_checks']['forbes_value_sum_usd_m'], 5385)
        self.assertEqual(payload['fcb_checks']['playbook_revenue_sum_usd_m'], 426)
        self.assertEqual(payload['fcb_checks']['forbes_revenue_sum_usd_m'], 430)

    def test_rejected_value_fails(self):
        payload = revenue.load(ROOT / revenue.DATA_FILE)
        payload['teams'][0]['forbes_2026_value_usd_m'] = 1000
        with self.assertRaises(ValueError):
            revenue.validate(payload)

    def test_expansion_number_fails(self):
        payload = revenue.load(ROOT / revenue.DATA_FILE)
        payload['not_in_source_set'][0]['forbes_2026_value_usd_m'] = 380
        with self.assertRaises(ValueError):
            revenue.validate(payload)

    def test_em_dash_fails(self):
        payload = revenue.load(ROOT / revenue.DATA_FILE)
        payload['teams'][0]['revenue_notes'] = 'A note with an em dash \u2014 inside.'
        with self.assertRaises(ValueError):
            revenue.validate(payload)


class TeamRevenuePageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        revenue.build(ROOT)
        cls.page = (ROOT / 'wnba' / 'team-revenue' / 'index.html').read_text(encoding='utf-8')
        cls.csv = (ROOT / 'wnba' / 'team-revenue' / revenue.CSV_NAME).read_text(encoding='utf-8')

    def test_page_answers_the_finals_gap(self):
        page = self.page
        self.assertIn(f'<h1>{revenue.H1}</h1>', page)
        self.assertIn('Updated Oct. 31, 2026', page)
        self.assertIn(links.BYLINE_HTML, page)
        self.assertIn('tied with', page)
        self.assertIn('$16 million', page)
        self.assertIn('4.875', page)
        self.assertIn('15.6', page)
        self.assertIn('10.0', page)
        self.assertIn('17.5', page)
        self.assertIn('10.4', page)
        self.assertIn('Not in the source set', page)
        self.assertIn('Portland Fire', page)
        self.assertIn('Toronto Tempo', page)
        self.assertIn('Download CSV', page)
        self.assertIn('Download JSON', page)
        self.assertIn('FAQPage', page)
        self.assertIn('"@type": "Dataset"', page)
        self.assertIn('Copy citation', page)
        self.assertIn('https://www.forbes.com/sites/brettknight/2026/05/07/the-wnbas-most-valuable-teams-2026/', page)
        self.assertIn('https://forbes.com.mx/estos-son-los-equipos-mas-valiosos-de-la-wnba-en-2026/', page)
        self.assertIn('https://x.com/katherinearowe/status/2116531655661834492', page)
        self.assertIn('/wnba/viewership-attendance/', page)
        self.assertIn('/news/2026-wnba-finals-ratings-tracker/', page)
        self.assertIn('/news/finals-game-7-preview-dream-valkyries/', page)
        self.assertIn('id="methods"', page)
        self.assertIn('id="sources"', page)
        self.assertIn('id="gap"', page)
        self.assertNotIn('\u2014', page)
        self.assertNotIn('\u2013', page)
        self.assertNotIn('ESPN data', page)
        self.assertNotIn('per ESPN', page)
        self.assertNotIn('balldontlie', page.lower())
        self.assertIn('team-revenue', build_players.SKIP_PLAYER_DIRS)
        self.assertIn('team-revenue', links.WNBA_NON_PLAYER_DIRS)
        self.assertLessEqual(len(__import__('re').search(r'name="description" content="([^"]*)"', page).group(1)), 160)
        nav = __import__('re').search(r'<nav class="site-nav".*?</nav>', page, flags=__import__('re').S).group(0)
        self.assertNotIn(ROUTE, nav)

    def test_csv_keeps_one_value_column_and_blank_expansion(self):
        self.assertIn('golden-state-valkyries', self.csv)
        self.assertIn('780', self.csv)
        self.assertIn('17.5', self.csv)
        self.assertIn('Not in the source set', self.csv)
        self.assertNotIn(',1000,', self.csv)
        self.assertNotIn(',850,', self.csv)
        lines = self.csv.splitlines()
        portland = next(line for line in lines if line.startswith('Portland Fire,'))
        self.assertIn('Not in the source set', portland)
        self.assertNotRegex(portland, r',380,|,850,|,1000,')

    def test_in_the_pages_sitemap_only(self):
        pages = (ROOT / 'pages-sitemap.xml').read_text(encoding='utf-8')
        self.assertIn(f'<loc>https://fullcourtbuckets.com{ROUTE}</loc>', pages)
        self.assertNotIn(ROUTE, (ROOT / 'player-sitemap.xml').read_text(encoding='utf-8'))
        html_map = (ROOT / 'sitemap' / 'index.html').read_text(encoding='utf-8')
        self.assertIn(f'href="{ROUTE}"', html_map)


if __name__ == '__main__':
    unittest.main()
