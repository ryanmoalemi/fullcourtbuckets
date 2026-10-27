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
        self.assertIn('<h1>WNBA Viewership &amp; Attendance Statistics 2026</h1>', page)
        payload = json.loads((ROOT / 'data' / 'viewership-attendance.json').read_text(encoding='utf-8'))
        self.assertIn(f"Updated {viewership.format_updated(payload['updated'])}", page)
        self.assertIn('2026 playoff viewership', page)
        self.assertIn('https://www.sportsmediawatch.com/sports-ratings-tracker/', page)
        self.assertIn('semifinals Game 2', page)
        self.assertIn(viewership.links.BYLINE_HTML, page)
        self.assertIn('id="viewership"', page)
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
        self.assertIn('Awaiting release', page)
        self.assertIn('Sat. Oct. 17, 2026', page)
        self.assertIn('Wed. Oct. 21, 2026', page)
        self.assertIn('5:00 p.m. PT', page)
        self.assertIn('10:00 a.m. PT', page)
        self.assertIn('State Farm Arena', page)
        self.assertIn('USA Network, CNBC, Peacock', page)
        # CNBC is only named as the USA Network simulcast from USA Sports releases
        # (Game 2 audience, Game 3 TV); it never stands in for the USA listing.
        for row in re.findall(r'<tr>.*?</tr>', page, flags=re.S):
            if 'CNBC' in row:
                self.assertIn('USA', row)
        self.assertIn('if necessary', page)
        self.assertNotIn('Thu. Oct. 22, 2026', page)
        self.assertIn('397,408', page)
        self.assertIn('Unresolved', page)
        self.assertIn('scope="col"', page)
        self.assertIn('Download CSV', page)
        self.assertIn('Copy citation', page)
        self.assertIn('Embed link', page)
        self.assertIn('class="btn copy-embed"', page)
        self.assertIn('Copied!', page)
        self.assertIn('data-nav{position:sticky;top:80px;max-height:calc(100vh - 96px);overflow-y:auto', page)
        self.assertIn('Unresolved: Sports Business Journal prints 15,743, and 388,997 divided by 25 is 15,560.', page)
        self.assertIn('Unresolved: Sports Business Journal prints 11,148, and 3.15 million divided by 286 is 11,014.', page)
        self.assertIn('Indiana drew 340,715 in 2024.', page)
        self.assertNotIn('class="correction"', page)
        self.assertNotIn('Correction,', page)
        self.assertNotIn('was the record', page)
        self.assertNotIn('previously', page.lower())
        self.assertNotIn('<details', page)
        self.assertNotIn('<textarea', page)
        self.assertNotIn('18,604', page)
        self.assertIn('summary_large_image', page)
        self.assertIn('share-11474-landscape.png', page)
        self.assertIn('"@type": "Article"', page)
        self.assertEqual(page.count('class="stat-card"'), 4)
        self.assertNotIn('built-in boost', page)
        self.assertNotIn('3.00 million', page)
        self.assertNotIn('og.jpg', page)
        self.assertIn('ESPN press release', page)
        self.assertIn('https://espnpressroom.com/press-release/espns-monumental-wnba-season-sets-new-viewership-records/', page)
        self.assertIn('https://www.nielsen.com/news-center/2026/nielsen-46-billion-minutes-of-womens-sports-were-consumed-in-2025/', page)
        self.assertIn('WNBA Finals', page)
        self.assertNotIn('Audiences are awaiting release.', page)
        self.assertNotIn('per ESPN', page)
        self.assertNotIn('ESPN data', page)
        self.assertNotRegex(page, r'Source:\s*ESPN\b')
        self.assertNotIn('2.70 million', page)
        self.assertIn('2.58 million', page)
        self.assertIn('1.9 million', page)
        self.assertIn('1.4 million', page)
        self.assertIn('3.15 million', page)
        self.assertIn('11,148', page)
        self.assertIn('11,014', page)
        self.assertIn('484,615', page)
        self.assertIn('151,805', page)
        self.assertIn('636,420', page)
        self.assertIn('5,646', page)
        self.assertIn('286, calculated', page)
        self.assertIn('240, calculated', page)
        self.assertIn('3.82 million', page)
        self.assertIn('15,116', page)
        self.assertNotIn('nearly 7,000', page)
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

    def test_growth_chart_waits_for_both_sourced_years(self):
        page = self.page
        self.assertIn('Provisional', page)
        self.assertIn('attendance-growth.png', page)
        self.assertIn('484,615', page)
        payload = copy.deepcopy(_payload())
        prior = next(row for row in payload['seasons'] if row.get('season') == 2025 and not row.get('home_team'))
        prior.pop('avg_attendance_status', None)
        prior.pop('avg_attendance_printed', None)
        prior.update({
            'games_played': 220,
            'avg_attendance': 10000,
            'attendance_source': 'https://www.wnba.com/news/example-2025-attendance',
            'attendance_source_date': '2025-10-01',
            'avg_attendance_source': 'https://www.wnba.com/news/example-2025-attendance',
            'avg_attendance_source_date': '2025-10-01',
        })
        viewership.validate(payload)
        html_text = viewership.render_page(ROOT, payload)
        self.assertIn('Provisional', html_text)
        self.assertIn('1,100,000', html_text)
        self.assertIn('486,420', html_text)
        self.assertIn('attendance-growth.png', html_text)

    def test_team_ranking_stays_hidden_without_a_complete_season(self):
        self.assertIn('ranking chart stays hidden', self.page)
        self.assertNotIn('team-ranking.png', self.page)
        payload = copy.deepcopy(_payload())
        payload['home_rankings'] = [{'season': 2026, 'complete': True}]
        payload['seasons'].append({
            'season': 2026,
            'home_team': 'Atlanta Dream',
            'home_attendance': 200000,
            'home_games': 22,
            'home_attendance_source': 'https://www.wnba.com/news/example-dream-home',
            'home_attendance_source_date': '2026-09-20',
        })
        viewership.validate(payload)
        html_text = viewership.render_page(ROOT, payload)
        self.assertIn('team-ranking.png', html_text)
        self.assertIn('9,091', html_text)


if __name__ == '__main__':
    unittest.main()
