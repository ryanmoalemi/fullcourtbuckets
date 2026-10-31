"""WNBA franchise multiples use Forbes value divided by Forbes revenue.

The same-12 block drops Golden State, which Forbes did not value in 2025.
A Sportico or CNBC value, a bad one-year change, or an expansion number fails.
"""
import unittest
from pathlib import Path

import build_players
import build_team_revenue as revenue
import internal_links as links

ROOT = Path(__file__).resolve().parents[1]
ROUTE = '/wnba/team-revenue/'


class TeamRevenueValidationTests(unittest.TestCase):
    def test_published_file_passes(self):
        revenue.validate(revenue.load(ROOT / revenue.DATA_FILE))

    def test_forbes_multiples_and_same_12(self):
        payload = revenue.enrich(revenue.load(ROOT / revenue.DATA_FILE))
        by_slug = {team['slug']: team for team in payload['teams']}
        self.assertEqual(by_slug['golden-state-valkyries']['value_per_revenue_2026'], 10.0)
        self.assertIsNone(by_slug['golden-state-valkyries']['forbes_2025_value_usd_m'])
        self.assertFalse(by_slug['golden-state-valkyries']['in_same_12'])
        self.assertEqual(by_slug['indiana-fever']['value_per_revenue_2026'], 10.0)
        self.assertEqual(by_slug['indiana-fever']['revenue_2025_usd_m'], 58)
        self.assertEqual(by_slug['washington-mystics']['value_per_revenue_2026'], 15.6)
        self.assertEqual(by_slug['washington-mystics']['revenue_2025_usd_m'], 18)
        self.assertEqual(by_slug['atlanta-dream']['value_per_revenue_2026'], 15.6)
        self.assertEqual(by_slug['seattle-storm']['value_per_revenue_2026'], 15.4)
        checks = payload['fcb_checks']
        self.assertEqual(checks['same_12_value_2025_usd_m'], 3260)
        self.assertEqual(checks['same_12_revenue_2024_usd_m'], 226)
        self.assertEqual(checks['same_12_value_2026_usd_m'], 4605)
        self.assertEqual(checks['same_12_revenue_2025_usd_m'], 352)
        self.assertEqual(checks['same_12_value_change_pct'], 41.3)
        self.assertEqual(checks['same_12_revenue_change_pct'], 55.8)
        self.assertEqual(checks['same_12_multiple_2025'], 14.42)
        self.assertEqual(checks['same_12_multiple_2026'], 13.08)
        self.assertEqual(checks['league_multiple'], 12.52)
        self.assertEqual(checks['team_count_same_12'], 12)
        ranked = revenue.revenue_ranked(payload['teams'])
        self.assertEqual([team['slug'] for team in ranked], list(revenue.REVENUE_ORDER))
        self.assertEqual([team['revenue_2025_usd_m'] for team in ranked], list(revenue.REVENUE_AMOUNTS))
        self.assertEqual([team['revenue_2025_rank'] for team in ranked], list(range(1, 14)))
        self.assertEqual(sum(team['revenue_2025_usd_m'] for team in ranked), 430)

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
        payload['teams'][0]['ownership'] = 'An owner \u2014 with a dash'
        with self.assertRaises(ValueError):
            revenue.validate(payload)


class TeamRevenuePageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        revenue.build(ROOT)
        cls.page = (ROOT / 'wnba' / 'team-revenue' / 'index.html').read_text(encoding='utf-8')
        cls.csv = (ROOT / 'wnba' / 'team-revenue' / revenue.CSV_NAME).read_text(encoding='utf-8')

    def test_page_uses_forbes_revenue_for_the_multiple(self):
        page = self.page
        self.assertIn(f'<h1>{revenue.H1}</h1>', page)
        self.assertEqual(revenue.H1, 'WNBA team revenue, ranked')
        self.assertIn(revenue.PAGE_TITLE, page)
        self.assertGreaterEqual(len(revenue.PAGE_TITLE), 45)
        self.assertLessEqual(len(revenue.PAGE_TITLE), 65)
        self.assertGreaterEqual(len(revenue.DESCRIPTION), 130)
        self.assertLessEqual(len(revenue.DESCRIPTION), 160)
        self.assertIn('Ryan Moalemi, Full Court Buckets', page)
        self.assertIn('October 31, 2026', page)
        self.assertIn(links.BYLINE_HTML.split('<span>')[0], page)
        self.assertIn('id="ranking"', page)
        self.assertIn('id="same-12-teams"', page)
        self.assertLess(page.find('id="ranking"'), page.find('id="same-12-teams"'))
        self.assertIn(revenue.LEDE, page)
        self.assertIn('Download the CSV', page)
        self.assertIn('View the Forbes source', page)
        self.assertIn('https://fullcourtbuckets.com/wnba/team-revenue/wnba-team-revenue-2025.csv', page)
        self.assertIn('Estimated revenue', page)
        self.assertIn(revenue.ATTRIBUTION, page)
        self.assertIn('fall outside this 2025 revenue dataset', page)
        self.assertIn('Nearly 5', page)
        self.assertIn('cite-sticky', page)
        self.assertIn('is-finals', page)
        self.assertIn('is-cluster', page)
        self.assertIn('@media print', page)
        self.assertIn('bigger than the entire', page)
        self.assertIn('$62 million difference exceeded Indiana', page)
        self.assertIn('4.9 times as much as the', page)
        self.assertIn('3.1 times as much by franchise value', page)
        self.assertIn('$15.63', page)
        self.assertIn('$10.00', page)
        self.assertIn('$3.260B', page)
        self.assertIn('$4.605B', page)
        self.assertIn('$226M in 2024', page)
        self.assertIn('$352M in 2025', page)
        self.assertIn('14.42', page)
        self.assertIn('13.08', page)
        self.assertIn('12.52', page)
        self.assertIn('+41.3%', page)
        self.assertIn('+55.8%', page)
        self.assertIn('Copy citation', page)
        chart = page[page.find('class="rev-rows"'):page.find('class="rev-axis-wrap"')]
        self.assertLess(chart.find('Golden State Valkyries'), chart.find('Indiana Fever'))
        self.assertLess(chart.find('Dallas Wings'), chart.find('Los Angeles Sparks'))
        self.assertLess(chart.find('Los Angeles Sparks'), chart.find('Phoenix Mercury'))
        self.assertLess(chart.find('Phoenix Mercury'), chart.find('Seattle Storm'))
        self.assertLess(chart.find('Seattle Storm'), chart.find('Atlanta Dream'))
        def before(name, back):
            at = chart.find(name)
            self.assertGreater(at, 0, name)
            return chart[max(0, at - back):at]
        golden = before('Golden State Valkyries', 220)
        atlanta = before('Atlanta Dream', 220)
        indiana = before('Indiana Fever', 160)
        self.assertIn('is-finals', golden)
        self.assertIn('is-finals', atlanta)
        self.assertNotIn('is-finals', indiana)
        self.assertIn('class="fold"', page)
        self.assertIn('Copy citation', page)
        self.assertIn('href="/wnba/owners/"', page)
        self.assertIn(revenue.FORBES_2026, page)
        self.assertIn(revenue.FORBES_2025, page)
        self.assertIn('began play in 2026', page)
        self.assertIn('Portland Fire', page)
        self.assertIn('Toronto Tempo', page)
        self.assertNotIn('10.4', page)
        self.assertNotIn('17.5', page)
        self.assertNotIn('CC0', page)
        self.assertNotIn('creativecommons', page.lower())
        self.assertNotIn('\u2014', page)
        self.assertNotIn('\u2013', page)
        self.assertIn('team-revenue', build_players.SKIP_PLAYER_DIRS)
        self.assertIn('team-revenue', links.WNBA_NON_PLAYER_DIRS)
        nav = __import__('re').search(r'<nav class="site-nav".*?</nav>', page, flags=__import__('re').S).group(0)
        self.assertNotIn(ROUTE, nav)

    def test_csv_has_both_forbes_years_and_blank_expansion(self):
        self.assertIn('value_per_revenue_2026', self.csv)
        self.assertIn('value_per_revenue_2025', self.csv)
        self.assertIn(revenue.FORBES_2026, self.csv)
        self.assertIn(revenue.FORBES_2025, self.csv)
        lines = self.csv.splitlines()
        golden = next(line for line in lines if line.startswith('Golden State Valkyries,'))
        self.assertIn(',780,78,10.0,1,', golden)
        self.assertNotIn(',400,', golden)
        atlanta = next(line for line in lines if line.startswith('Atlanta Dream,'))
        self.assertIn(',250,16,15.6,13,190,11,', atlanta)
        portland = next(line for line in lines if line.startswith('Portland Fire,'))
        self.assertIn('began play in 2026', portland)
        self.assertNotRegex(portland, r',380,|,780,|,850,')

    def test_in_the_pages_sitemap_only(self):
        pages = (ROOT / 'pages-sitemap.xml').read_text(encoding='utf-8')
        self.assertIn(f'<loc>https://fullcourtbuckets.com{ROUTE}</loc>', pages)
        self.assertNotIn(ROUTE, (ROOT / 'player-sitemap.xml').read_text(encoding='utf-8'))
        self.assertIn(f'href="{ROUTE}"', (ROOT / 'sitemap' / 'index.html').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
