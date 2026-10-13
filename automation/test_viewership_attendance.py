"""The viewership page is built from data/viewership-attendance.json.

A game row with no date fails. A number with no source URL fails. Empty
attendance and viewers are allowed, so a Finals game can be listed before a
network releases an audience.
"""
import copy
import json
import re
import unittest
from pathlib import Path

import build_players
import build_viewership_attendance as viewership

ROOT = Path(__file__).resolve().parents[1]
ROUTE = '/wnba/viewership-attendance/'


def _game(**overrides):
    row = {
        'date': '2026-10-17',
        'season': 2026,
        'game': 'Finals Game 1',
        'home': '',
        'away': '',
        'venue': '',
        'attendance': None,
        'attendance_source': '',
        'network': 'NBC, Peacock',
        'viewers': None,
        'viewers_source': '',
    }
    row.update(overrides)
    return row


def _payload():
    return json.loads((ROOT / viewership.DATA_FILE).read_text(encoding='utf-8'))


class ViewershipValidationTests(unittest.TestCase):
    def test_published_file_passes(self):
        viewership.validate(_payload())

    def test_missing_date_fails(self):
        payload = {'updated': '2026-10-13', 'games': [_game(date='')], 'seasons': []}
        with self.assertRaisesRegex(ValueError, 'missing a date'):
            viewership.validate(payload)
        payload['games'] = [_game()]
        payload['seasons'] = [{'total_attendance': 100, 'attendance_source': 'https://www.wnba.com/news/example'}]
        with self.assertRaisesRegex(ValueError, 'missing a date'):
            viewership.validate(payload)

    def test_number_without_source_fails(self):
        payload = {'updated': '2026-10-13', 'games': [_game(viewers=1500000, viewers_source='')], 'seasons': []}
        with self.assertRaisesRegex(ValueError, 'number but no source'):
            viewership.validate(payload)
        payload['games'] = [_game(attendance=17000, attendance_source='')]
        with self.assertRaisesRegex(ValueError, 'number but no source'):
            viewership.validate(payload)
        payload['games'] = [_game()]
        payload['seasons'] = [{'season': 2026, 'avg_attendance': 11474, 'avg_attendance_source': ''}]
        with self.assertRaisesRegex(ValueError, 'number but no source'):
            viewership.validate(payload)

    def test_empty_audience_needs_no_source(self):
        payload = {'updated': '2026-10-13', 'games': [_game()], 'seasons': [{'season': 2026, 'finals_matchup': 'Valkyries vs. Dream'}]}
        viewership.validate(payload)

    def test_source_must_be_a_page_url(self):
        payload = {'updated': '2026-10-13', 'games': [_game(viewers=10, viewers_source='AP')], 'seasons': []}
        with self.assertRaisesRegex(ValueError, 'number but no source'):
            viewership.validate(payload)


class ViewershipPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        viewership.build(ROOT)
        cls.page = (ROOT / 'wnba' / 'viewership-attendance' / 'index.html').read_text(encoding='utf-8')

    def test_question_page_uses_only_sourced_draft_figures(self):
        page = self.page
        self.assertIn('<h1>WNBA viewership and attendance stats 2026: How many people watch the WNBA?</h1>', page)
        self.assertIn('Last updated: Oct. 13, 2026.', page)
        self.assertIn('href="/authors/ryan-moalemi/">Ryan Moalemi</a>', page)
        self.assertIn('How many people watched the WNBA Finals?', page)
        self.assertIn('The 2024 Finals averaged 1.6 million viewers, the highest of the last 25 years.', page)
        self.assertIn('5.04 million', page)
        self.assertIn('3.31 million', page)
        self.assertIn('3.79 million', page)
        self.assertIn('11,474', page)
        self.assertIn('20,711', page)
        self.assertIn('340,715', page)
        self.assertIn('728,000', page)
        self.assertIn('534,000', page)
        self.assertIn('6,615', page)
        self.assertIn('Pending', page)
        self.assertIn('Sat. Oct. 17, 2026', page)
        self.assertIn('ESPN press release', page)
        self.assertIn('https://espnpressroom.com/press-release/espns-monumental-wnba-season-sets-new-viewership-records/', page)
        self.assertNotIn('per ESPN', page)
        self.assertNotIn('ESPN data', page)
        self.assertNotRegex(page, r'Source:\s*ESPN\b')
        self.assertNotIn('2.70 million', page)
        self.assertNotIn('2.58 million', page)
        self.assertNotIn('1.9 million', page)
        self.assertNotIn('1.4 million', page)
        self.assertNotIn('3.15 million', page)
        self.assertNotIn('11,148', page)
        self.assertNotIn('20%', page)
        self.assertNotIn('5%', page)
        self.assertNotIn('balldontlie', page.lower())
        self.assertLessEqual(len(re.search(r'name="description" content="([^"]*)"', page).group(1)), 155)
        nav = re.search(r'<nav class="site-nav".*?</nav>', page, re.S).group(0)
        self.assertNotIn(ROUTE, nav)
        self.assertIn('viewership-attendance', build_players.SKIP_PLAYER_DIRS)

    def test_not_in_the_menu_or_sitemap(self):
        for name in ('sitemap.xml', 'pages-sitemap.xml', 'player-sitemap.xml'):
            text = (ROOT / name).read_text(encoding='utf-8')
            self.assertNotIn(ROUTE, text, name)
        html_map = (ROOT / 'sitemap' / 'index.html').read_text(encoding='utf-8')
        self.assertNotIn(ROUTE, html_map)

    def test_appended_finals_game_renders_without_a_page_edit(self):
        payload = copy.deepcopy(_payload())
        payload['games'].append(_game(
            date='2026-10-27',
            game='Finals Game 5',
            network='NBC, Peacock',
            viewers=1800000,
            viewers_source='https://www.nbcsports.com/pressbox/press-releases/example-finals-audience',
            viewers_source_date='2026-10-28',
        ))
        viewership.validate(payload)
        html_text = viewership.render_page(ROOT, payload)
        self.assertIn('Tue. Oct. 27, 2026', html_text)
        self.assertIn('1.8 million', html_text)
        self.assertIn('https://www.nbcsports.com/pressbox/press-releases/example-finals-audience', html_text)


if __name__ == '__main__':
    unittest.main()
