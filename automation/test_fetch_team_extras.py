"""Playoff labels from the WNBA schedule feed.

A Finals series is Won or Lost only when a team has the wins that end it.
From 2025 that is four. An unfinished series stays 'Reached WNBA Finals'.
"""
import json
import re
import unittest
from pathlib import Path

import fetch_team_extras as extras

ROOT = Path(__file__).resolve().parents[1]
ATL, GSV, NYL = 1611661330, 1611661331, 1611661313


def game(label, status, series, home, away, home_score, away_score, home_id=ATL, away_id=GSV):
    return {
        'seasonType': 'Playoffs',
        'gameStatus': status,
        'gameLabel': label,
        'seriesText': series,
        'homeTeam': {'teamId': home_id, 'teamTricode': home, 'score': home_score},
        'awayTeam': {'teamId': away_id, 'teamTricode': away, 'score': away_score},
    }


def finals_2026_through_game_5():
    """Best-of-seven at 3-2, with Games 6 and 7 still scheduled. Series line is a lead."""
    played = [
        game('WNBA Finals', 3, 'GSV leads 1-0', 'GSV', 'ATL', 68, 64, GSV, ATL),
        game('WNBA Finals', 3, 'Series tied 1-1', 'GSV', 'ATL', 65, 79, GSV, ATL),
        game('WNBA Finals', 3, 'ATL leads 2-1', 'ATL', 'GSV', 97, 71),
        game('WNBA Finals', 3, 'Series tied 2-2', 'ATL', 'GSV', 62, 67),
        game('WNBA Finals', 3, 'GSV leads 3-2', 'GSV', 'ATL', 64, 55, GSV, ATL),
    ]
    scheduled = [
        game('WNBA Finals', 1, 'GSV leads 3-2', 'ATL', 'GSV', None, None),
        game('WNBA Finals', 1, 'GSV leads 3-2', 'GSV', 'ATL', None, None, GSV, ATL),
    ]
    return played + scheduled


class PlayoffResultTests(unittest.TestCase):
    def test_unfinished_finals_are_reached_not_lost(self):
        labels = extras.playoff_results(finals_2026_through_game_5(), 2026)
        self.assertEqual(labels[ATL], 'Reached WNBA Finals')
        self.assertEqual(labels[GSV], 'Reached WNBA Finals')

    def test_a_wins_line_short_of_four_does_not_end_the_finals(self):
        games = finals_2026_through_game_5()
        games[4] = game('WNBA Finals', 3, 'GSV wins 3-2', 'GSV', 'ATL', 64, 55, GSV, ATL)
        labels = extras.playoff_results(games, 2026)
        self.assertEqual(labels[ATL], 'Reached WNBA Finals')
        self.assertEqual(labels[GSV], 'Reached WNBA Finals')

    def test_four_wins_ends_the_finals(self):
        games = [
            game('WNBA Finals', 3, 'GSV leads 1-0', 'GSV', 'ATL', 68, 64, GSV, ATL),
            game('WNBA Finals', 3, 'GSV leads 2-0', 'GSV', 'ATL', 80, 70, GSV, ATL),
            game('WNBA Finals', 3, 'GSV leads 2-1', 'ATL', 'GSV', 90, 80),
            game('WNBA Finals', 3, 'GSV leads 3-1', 'GSV', 'ATL', 75, 60, GSV, ATL),
            game('WNBA Finals', 3, 'GSV wins 4-1', 'GSV', 'ATL', 88, 70, GSV, ATL),
            game('WNBA Finals', 1, 'GSV wins 4-1', 'ATL', 'GSV', None, None),
            game('WNBA Finals', 1, 'GSV wins 4-1', 'GSV', 'ATL', None, None, GSV, ATL),
        ]
        labels = extras.playoff_results(games, 2026)
        self.assertEqual(labels[GSV], 'Won WNBA Finals')
        self.assertEqual(labels[ATL], 'Lost in WNBA Finals')

    def test_game_seven_winner_is_the_champion(self):
        games = finals_2026_through_game_5()
        games.append(game('WNBA Finals', 3, 'Series tied 3-3', 'ATL', 'GSV', 80, 70))
        games.append(game('WNBA Finals', 3, 'ATL wins 4-3', 'GSV', 'ATL', 60, 75, GSV, ATL))
        labels = extras.playoff_results(games, 2026)
        self.assertEqual(labels[ATL], 'Won WNBA Finals')
        self.assertEqual(labels[GSV], 'Lost in WNBA Finals')

    def test_pre_2025_finals_still_use_the_series_line(self):
        games = [
            game('WNBA Finals', 3, 'LVA leads 2-1', 'LVA', 'NYL', 80, 70, 10, NYL),
            game('WNBA Finals', 3, 'LVA wins 3-1', 'NYL', 'LVA', 75, 90, NYL, 10),
        ]
        labels = extras.playoff_results(games, 2024)
        self.assertEqual(labels[10], 'Won WNBA Finals')
        self.assertEqual(labels[NYL], 'Lost in WNBA Finals')

    def test_pre_2025_finals_without_a_winner_are_not_a_loss(self):
        games = [game('WNBA Finals', 3, 'LVA leads 2-2', 'LVA', 'NYL', 80, 78, 10, NYL)]
        labels = extras.playoff_results(games, 2024)
        self.assertEqual(labels[10], 'Reached WNBA Finals')
        self.assertEqual(labels[NYL], 'Reached WNBA Finals')

    def test_other_rounds_still_use_lost_or_reached(self):
        games = [
            game('Semi-Finals', 3, 'ATL leads 2-0', 'ATL', 'NYL', 101, 98, ATL, NYL),
            game('Semi-Finals', 3, 'ATL wins 3-0', 'NYL', 'ATL', 83, 85, NYL, ATL),
        ]
        labels = extras.playoff_results(games, 2026)
        self.assertEqual(labels[ATL], 'Reached Semifinals')
        self.assertEqual(labels[NYL], 'Lost in Semifinals')

    def test_in_progress_series_is_reached(self):
        games = [game('First Round', 3, 'ATL leads 1-0', 'ATL', 'WAS', 92, 77, ATL, 99)]
        labels = extras.playoff_results(games, 2026)
        self.assertEqual(labels[ATL], 'Reached First Round')
        self.assertEqual(labels[99], 'Reached First Round')


class SnapshotFinalsTests(unittest.TestCase):
    def test_committed_2026_finals_label_matches_the_schedule(self):
        sched = json.loads((ROOT / 'data/wnba/schedule-2026.json').read_text(encoding='utf-8'))
        hist = json.loads((ROOT / 'data/wnba/team-history.json').read_text(encoding='utf-8'))
        wins = {}
        for g in sched['games']:
            if g.get('type') != 'Playoffs' or 'WNBA Finals' not in (g.get('label') or ''):
                continue
            if g.get('status') != 3:
                continue
            home, away = g['home'], g['away']
            if not isinstance(home.get('score'), int) or not isinstance(away.get('score'), int):
                continue
            if home['score'] == away['score']:
                continue
            winner = home['tricode'] if home['score'] > away['score'] else away['tricode']
            wins[winner] = wins.get(winner, 0) + 1
        best = max(wins.values()) if wins else 0
        names = {'ATL': 'Atlanta Dream', 'GSV': 'Golden State Valkyries'}
        pages = {'ATL': 'atlanta-dream', 'GSV': 'golden-state-valkyries'}
        for tri, name in names.items():
            row = next(r for r in hist['teams'][name] if r['season'] == 2026)
            if best >= extras.FINALS_WINS_TO_CLINCH:
                expected = 'Won WNBA Finals' if wins.get(tri, 0) >= extras.FINALS_WINS_TO_CLINCH else 'Lost in WNBA Finals'
            else:
                expected = 'Reached WNBA Finals'
            self.assertEqual(row['playoffs'], expected)
            slug = pages[tri]
            html = (ROOT / 'wnba/teams' / slug / 'index.html').read_text(encoding='utf-8')
            cell = re.search(
                rf'<td>2026</td><td>{re.escape(name)}</td><td>[^<]*</td><td>[^<]*</td><td>([^<]*)</td>',
                html,
            )
            self.assertIsNotNone(cell)
            self.assertEqual(cell.group(1), expected)
            csv_text = (ROOT / 'wnba/teams' / slug / f'{slug}-history.csv').read_text(encoding='utf-8')
            line = next(row_text for row_text in csv_text.splitlines() if row_text.startswith(f'{name},2026,'))
            self.assertIn(f',{expected},', line)


if __name__ == '__main__':
    unittest.main()
