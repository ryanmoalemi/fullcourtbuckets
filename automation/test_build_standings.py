"""Standings come from the stats-feed rows, with the other feed only as a cross-check."""
import datetime as dt
import json
import unittest
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo

import offline_tests
import build_standings as standings
import playoff_board

offline_tests.install()

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


def provider_rows():
    """Same final table, in the standings-endpoint shape the page builder reads."""
    payload = final_2026_payload()
    rows = []
    for child in payload['children']:
        conference = 'Eastern' if 'east' in child['name'].casefold() else 'Western'
        for entry in child['standings']['entries']:
            team = entry['team']
            stats = {stat['name'].casefold(): stat for stat in entry['stats']}
            stats.update({stat.get('type', '').casefold(): stat for stat in entry['stats'] if stat.get('type')})
            rows.append({
                'team': {'full_name': team['displayName'], 'abbreviation': team['abbreviation'], 'conference': conference},
                'season': 2026,
                'conference': conference,
                'wins': stats['wins']['value'],
                'losses': stats['losses']['value'],
                'win_percentage': stats['winpercent']['value'],
                'home_record': stats['home']['displayValue'],
                'away_record': stats['road']['displayValue'],
            })
    return {'season': 2026, 'teams': rows}


def _scoreboard_event(day, away, away_score, home, home_score, wins, completed):
    moment = dt.datetime.fromisoformat(day + 'T19:00:00-07:00')
    return {
        'when': moment,
        'day': moment.date(),
        'state': 'post',
        'final': True,
        'away': away,
        'home': home,
        'away_score': away_score,
        'home_score': home_score,
        'wins': wins,
        'completed': completed,
        'length': 3,
        'pair': frozenset((away, home)),
    }


def _box(day, away, away_score, home, home_score, game_id):
    names = {
        'MIN': 'Minnesota Lynx',
        'NY': 'New York Liberty',
        'GS': 'Golden State Valkyries',
        'LV': 'Las Vegas Aces',
    }
    return {
        'postseason': True,
        'date': day,
        'status': 'final',
        'season': 2026,
        'balldontlie_game_id': game_id,
        'away': {'abbreviation': away, 'full_name': names[away], 'name': names[away].split()[-1], 'score': away_score},
        'home': {'abbreviation': home, 'full_name': names[home], 'name': names[home].split()[-1], 'score': home_score},
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
            self.assertTrue(standings.build(root, payload=provider_rows(), updated_at='2026-10-01T12:00:00-07:00', cross_check=final_2026_payload()))
            html_text = page.read_text(encoding='utf-8')
            self.assertIn('rel="canonical" href="https://fullcourtbuckets.com/standings/"', html_text)
            self.assertNotIn('espn.com', html_text.lower())
            self.assertNotIn('balldontlie', html_text.lower())
            self.assertNotIn('source-note', html_text)
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
            self.assertTrue(standings.build(root, payload=provider_rows(), updated_at='2026-10-04T01:48:18-07:00', cross_check=final_2026_payload()))
            again = page.read_text(encoding='utf-8')
            self.assertIn('Updated October 1, 2026', again)
            self.assertNotIn('October 4, 2026', again)
            kept = json.loads((root / 'api' / 'wnba-standings').read_text(encoding='utf-8'))
            self.assertEqual(kept['updatedAt'], '2026-10-01T12:00:00-07:00')

    def test_cross_check_disagreement_keeps_the_last_page(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            page = root / 'standings' / 'index.html'
            page.parent.mkdir(parents=True)
            page.write_text('LAST GOOD PAGE', encoding='utf-8')
            bad = final_2026_payload()
            bad['children'][0]['standings']['entries'][0]['stats'][0]['value'] = 29
            bad['children'][0]['standings']['entries'][0]['stats'][0]['displayValue'] = '29'
            self.assertFalse(standings.build(
                root,
                payload=provider_rows(),
                updated_at='2026-10-01T12:00:00-07:00',
                cross_check=bad,
            ))
            self.assertEqual(page.read_text(encoding='utf-8'), 'LAST GOOD PAGE')
            self.assertFalse((root / 'api' / 'wnba-standings').exists())

    def test_playoff_section_score_and_fresh_stamp(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            games = root / 'data' / 'games'
            games.mkdir(parents=True)
            (games / '2026-09-27-ny-min.json').write_text(json.dumps(_box('2026-09-27', 'NY', 91, 'MIN', 75, 1)), encoding='utf-8')
            (games / '2026-09-29-min-ny.json').write_text(json.dumps(_box('2026-09-29', 'MIN', 71, 'NY', 87, 2)), encoding='utf-8')
            now = dt.datetime(2026, 10, 9, 11, 17, tzinfo=ZoneInfo('America/Los_Angeles'))
            stamp = now.isoformat(timespec='seconds')
            events = [
                _scoreboard_event('2026-09-27', 'NY', 91, 'MIN', 75, {'NY': 1, 'MIN': 0}, False),
                _scoreboard_event('2026-09-29', 'MIN', 71, 'NY', 87, {'NY': 2, 'MIN': 0}, True),
            ]
            self.assertTrue(standings.build(root, payload=provider_rows(), updated_at=stamp, cross_check=final_2026_payload(), events=events))
            page = (root / 'standings' / 'index.html').read_text(encoding='utf-8')
            self.assertIn('id="playoffs"', page)
            self.assertIn('Liberty won 2-0', page)
            self.assertIn('(1)', page)
            self.assertIn('(8)', page)
            self.assertIn('Final 2026 regular-season standings', page)
            self.assertIn('2026 WNBA Playoffs', page)
            self.assertIn('no regular-season games are left.', page)
            self.assertIn('The playoffs are listed on this page', page)
            self.assertLess(page.find('id="playoffs"'), page.find('id="standingsBody"'))
            saved = json.loads((root / 'api' / 'wnba-standings').read_text(encoding='utf-8'))
            self.assertTrue(saved['playoffsActive'])
            self.assertTrue(standings.stamp_is_fresh(saved['updatedAt'], now))
            self.assertIn('Updated Oct 9, 2026, 11:17 AM PT', page)
            later = now + dt.timedelta(hours=20)
            self.assertTrue(standings.build(
                root,
                payload=provider_rows(),
                updated_at=later.isoformat(timespec='seconds'),
                cross_check=final_2026_payload(),
                events=events,
            ))
            refreshed = json.loads((root / 'api' / 'wnba-standings').read_text(encoding='utf-8'))
            self.assertTrue(standings.stamp_is_fresh(refreshed['updatedAt'], later))
            self.assertFalse(standings.stamp_is_fresh(saved['updatedAt'], later + dt.timedelta(hours=20)))
            self.assertIn('Updated Oct 10, 2026, 7:17 AM PT', (root / 'standings' / 'index.html').read_text(encoding='utf-8'))
            kept_page = (root / 'standings' / 'index.html').read_text(encoding='utf-8')
            self.assertFalse(standings.build(
                root,
                payload=provider_rows(),
                updated_at=later.isoformat(timespec='seconds'),
                cross_check=final_2026_payload(),
                events=[],
            ))
            self.assertEqual((root / 'standings' / 'index.html').read_text(encoding='utf-8'), kept_page)

    def test_series_score_matches_stored_games(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            games = root / 'data' / 'games'
            games.mkdir(parents=True)
            (games / 'g1.json').write_text(json.dumps(_box('2026-10-04', 'LV', 60, 'GS', 71, 11)), encoding='utf-8')
            (games / 'g2.json').write_text(json.dumps(_box('2026-10-07', 'LV', 81, 'GS', 83, 12)), encoding='utf-8')
            table = standings.table_from_provider(provider_rows(), '2026-10-09T04:17:00-07:00')
            board = playoff_board.build_board(playoff_board.load_results(root, 2026), [], table['teams'])
            playoff_board.verify_board(board)
            text = playoff_board.section_text(board)
            self.assertIn('(2) Golden State Valkyries vs (3) Las Vegas Aces', text)
            self.assertIn('Valkyries lead 2-0', text)
            series = board['rounds'][0]['series'][0]
            recounted = playoff_board.count_wins(series['games'])
            self.assertEqual(recounted['GS'], 2)
            self.assertEqual(recounted['LV'], 0)
            series['wins']['GS'] = 1
            with self.assertRaises(playoff_board.CheckError):
                playoff_board.verify_board(board)

    def test_workflow_refreshes_playoffs_before_the_page(self):
        workflow = (ROOT / '.github' / 'workflows' / 'fcb-wnba.yml').read_text(encoding='utf-8')
        refresh = workflow.split('Refresh playoff games and rebuild standings', 1)[1].split('- name:', 1)[0]
        self.assertIn('python -u automation/game_stats.py --postseason', refresh)
        self.assertIn('python -u automation/build_standings.py', refresh)
        self.assertNotIn('|| true', refresh)
        self.assertLess(refresh.find('game_stats.py --postseason'), refresh.find('build_standings.py'))


if __name__ == '__main__':
    unittest.main()
