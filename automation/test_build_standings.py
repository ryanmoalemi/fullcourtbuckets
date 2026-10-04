"""Standings come from the ESPN feed shape, not a hardcoded table."""
import json
import unittest
from pathlib import Path
import tempfile

import build_standings as standings

ROOT = Path(__file__).resolve().parents[1]


def _entry(name, abbr, wins, losses):
    played = wins + losses
    return {
        'team': {'displayName': name, 'abbreviation': abbr},
        'stats': [
            {'name': 'wins', 'value': wins, 'displayValue': str(wins)},
            {'name': 'losses', 'value': losses, 'displayValue': str(losses)},
            {'name': 'winPercent', 'value': wins / played, 'displayValue': f'{wins / played:.3f}'},
            {'name': 'gamesBehind', 'displayValue': '-'},
            {'name': 'Home', 'type': 'home', 'displayValue': '1-0'},
            {'name': 'Road', 'type': 'road', 'displayValue': '0-1'},
            {'name': 'streak', 'displayValue': 'W1'},
            {'name': 'Last Ten Games', 'type': 'lasttengames', 'displayValue': '6-4'},
        ],
    }


def final_2026_payload():
    """Final 2026 table, including one repeated East row the parser must drop."""
    east = [
        ('Atlanta Dream', 'ATL', 30, 14),
        ('Washington Mystics', 'WSH', 28, 16),
        ('Indiana Fever', 'IND', 28, 16),
        ('New York Liberty', 'NY', 26, 18),
        ('Chicago Sky', 'CHI', 16, 28),
        ('Toronto Tempo', 'TOR', 11, 33),
        ('Connecticut Sun', 'CON', 11, 33),
        ('Atlanta Dream', 'ATL', 11, 29),
    ]
    west = [
        ('Minnesota Lynx', 'MIN', 33, 11),
        ('Golden State Valkyries', 'GS', 32, 12),
        ('Las Vegas Aces', 'LV', 31, 13),
        ('Dallas Wings', 'DAL', 27, 17),
        ('Portland Fire', 'POR', 17, 27),
        ('Los Angeles Sparks', 'LA', 16, 28),
        ('Phoenix Mercury', 'PHX', 16, 28),
        ('Seattle Storm', 'SEA', 8, 36),
    ]
    return {
        'season': {'year': 2026},
        'children': [
            {'name': 'Eastern Conference', 'standings': {'entries': [_entry(*row) for row in east]}},
            {'name': 'Western Conference', 'standings': {'entries': [_entry(*row) for row in west]}},
        ],
    }


class StandingsFeedTests(unittest.TestCase):
    def test_final_table_has_15_teams_and_league_seeds(self):
        table = standings.parse_standings(final_2026_payload(), '2026-10-01T12:00:00-07:00')
        names = [team['name'] for team in table['teams']]
        self.assertEqual(len(names), 15)
        self.assertEqual(len(set(names)), 15)
        self.assertIn('Portland Fire', names)
        self.assertIn('Toronto Tempo', names)
        self.assertEqual(names.count('Atlanta Dream'), 1)
        dream = next(team for team in table['teams'] if team['name'] == 'Atlanta Dream')
        self.assertEqual((dream['wins'], dream['losses']), (30, 14))
        for team in table['teams']:
            self.assertEqual(team['wins'] + team['losses'], 44)
        seeds = [team['name'] for team in table['teams'] if team['playoffSeed']]
        self.assertEqual(seeds, [
            'Minnesota Lynx',
            'Golden State Valkyries',
            'Las Vegas Aces',
            'Atlanta Dream',
            'Washington Mystics',
            'Indiana Fever',
            'Dallas Wings',
            'New York Liberty',
        ])
        self.assertEqual(table['teams'][0]['playoffSeed'], 1)
        self.assertIsNone(table['teams'][8]['playoffSeed'])
        east = [team for team in table['teams'] if team['conference'] == 'Eastern']
        self.assertEqual(east[0]['name'], 'Atlanta Dream')
        self.assertEqual([team['conferenceRank'] for team in east], list(range(1, 8)))

    def test_page_lists_each_team_once_and_keeps_the_last_page_on_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            page = root / 'standings' / 'index.html'
            page.parent.mkdir(parents=True)
            page.write_text('LAST GOOD PAGE', encoding='utf-8')
            self.assertFalse(standings.build(root, payload={'children': []}, updated_at='2026-10-01T12:00:00-07:00'))
            self.assertEqual(page.read_text(encoding='utf-8'), 'LAST GOOD PAGE')
            self.assertTrue(standings.build(root, payload=final_2026_payload(), updated_at='2026-10-01T12:00:00-07:00'))
            html_text = page.read_text(encoding='utf-8')
            self.assertIn('rel="canonical" href="https://fullcourtbuckets.com/standings/"', html_text)
            self.assertIn('href="https://www.espn.com/wnba/standings" target="_blank" rel="noopener"', html_text)
            self.assertIn('Updated October 1, 2026', html_text)
            body = html_text.split('id="standingsBody"', 1)[1].split('</tbody>', 1)[0]
            for name in (
                'Minnesota Lynx', 'Golden State Valkyries', 'Las Vegas Aces', 'Atlanta Dream',
                'Washington Mystics', 'Indiana Fever', 'Dallas Wings', 'New York Liberty',
                'Chicago Sky', 'Toronto Tempo', 'Connecticut Sun', 'Portland Fire',
                'Los Angeles Sparks', 'Phoenix Mercury', 'Seattle Storm',
            ):
                self.assertEqual(body.count(name), 1, name)
            self.assertEqual(body.count('class="team-name"'), 15)
            self.assertIn('WebPage', html_text)
            self.assertIn('BreadcrumbList', html_text)
            saved = json.loads((root / 'api' / 'wnba-standings').read_text(encoding='utf-8'))
            self.assertEqual(len(saved['teams']), 15)
            self.assertEqual(saved['teams'][0]['name'], 'Minnesota Lynx')
            self.assertIn('Final 2026 regular-season standings', html_text)
            self.assertIn('"dateModified": "2026-10-01"', html_text)
            self.assertIn('How do WNBA playoff tiebreakers work?', html_text)
            self.assertIn('What is the 2026 WNBA playoff format by round?', html_text)
            self.assertIn('best-of-three', html_text)
            self.assertIn('best-of-five', html_text)
            self.assertIn('best-of-seven', html_text)
            self.assertIn('https://www.wnba.com/standings', html_text)
            self.assertIn('target="_blank" rel="noopener">WNBA standings</a>', html_text)
            self.assertIn('The 2026 regular season on this page is 44 games.', html_text)
            self.assertIn('no regular-season games are left.', html_text)
            self.assertIn('4:17 AM PT', html_text)
            self.assertNotIn('6:45 AM PT', html_text)
            self.assertIn('"@type": "FAQPage"', html_text)
            self.assertNotIn('\u2014', html_text)
            self.assertTrue(standings.build(root, payload=final_2026_payload(), updated_at='2026-10-04T01:48:18-07:00'))
            again = page.read_text(encoding='utf-8')
            self.assertIn('Updated October 1, 2026', again)
            self.assertNotIn('October 4, 2026', again)
            kept = json.loads((root / 'api' / 'wnba-standings').read_text(encoding='utf-8'))
            self.assertEqual(kept['updatedAt'], '2026-10-01T12:00:00-07:00')


if __name__ == '__main__':
    unittest.main()
