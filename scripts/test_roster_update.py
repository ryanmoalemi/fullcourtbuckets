"""Fail-safe tests for the ESPN roster updater. No network."""
import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

import scripts.roster_update as roster

TODAY = dt.date(2026, 9, 28)
PLAYER = {
    'slug': 'aja-wilson',
    'name': "A'ja Wilson",
    'espnId': '3149391',
    'team': 'Las Vegas Aces',
    'position': 'Center',
    'jersey': '22',
    'active': True,
    'height': '6\' 4"',
    'season2026': {'GP': '41', 'GS': '41', 'MIN': '32.0', 'PTS': '26.2', 'REB': '9.4', 'AST': '3.2', 'STL': '1.4', 'BLK': '1.9', 'TO': '2.4', 'FG%': '52.7', '3P%': '40.4', 'FT%': '86.4'},
    'playoffs2026': None,
    'lastGame': None,
    'lastGameOnRecord': None,
    'photo': None,
    'faq': [
        {'q': 'How tall is A\'ja Wilson?', 'a': 'A\'ja Wilson is listed at 6-foot-4.', 'source': 'https://www.espn.com/wnba/player/_/id/3149391/aja-wilson'},
        {'q': 'What team does A\'ja Wilson play for?', 'a': 'A\'ja Wilson plays for the Las Vegas Aces and wears No. 22.', 'source': 'https://www.espn.com/wnba/player/_/id/3149391/aja-wilson'},
        {'q': 'What position does A\'ja Wilson play?', 'a': 'A\'ja Wilson plays center for the Las Vegas Aces.', 'source': 'https://www.espn.com/wnba/player/_/id/3149391/aja-wilson'},
    ],
    'related': [{'slug': 'aces-fever-game-1-aja-wilson-38', 'title': 'Aces roll', 'date': '2026-09-28'}],
}


def athlete(team='Las Vegas Aces', short='Aces', jersey='22', position='Center', active=True, slug='las-vegas-aces'):
    return {'athlete': {
        'id': '3149391', 'displayName': "A'ja Wilson", 'jersey': jersey, 'active': active,
        'position': {'displayName': position},
        'team': {'displayName': team, 'name': short, 'slug': slug},
    }}


def season_payload(points='26.2', team_slug='las-vegas-aces'):
    labels = list(roster.SEASON_KEYS)
    # The endpoint has extra labels. Include only the ones the page uses, in order,
    # which is enough for the parser.
    stats = ['41', '41', '32.0', points, '9.4', '3.2', '1.4', '1.9', '2.4', '52.7', '40.4', '86.4']
    return {'categories': [{'name': 'averages', 'labels': labels, 'statistics': [
        {'season': {'year': 2026}, 'teamSlug': team_slug, 'stats': stats},
    ]}]}


class RosterTests(unittest.TestCase):
    def test_athlete_error_keeps_stored_player(self):
        original = copy.deepcopy(PLAYER)
        updated, info = roster.refresh_player(original, lambda url: None, TODAY)
        self.assertEqual(updated, original)
        self.assertEqual(info['skipped'], 'athlete request failed')
        self.assertEqual(PLAYER['team'], 'Las Vegas Aces')

    def test_blank_team_and_jersey_do_not_erase_data(self):
        def fetch(url):
            if url.endswith('/stats?seasontype=2') or url.endswith('/stats?seasontype=3') or url.endswith('/overview'):
                return {}
            payload = athlete()
            payload['athlete']['team'] = {}
            payload['athlete']['jersey'] = ''
            payload['athlete']['position'] = {}
            return payload
        updated, info = roster.refresh_player(copy.deepcopy(PLAYER), fetch, TODAY)
        self.assertEqual(updated['team'], 'Las Vegas Aces')
        self.assertEqual(updated['jersey'], '22')
        self.assertEqual(updated['position'], 'Center')
        self.assertEqual(updated['season2026']['PTS'], '26.2')
        self.assertFalse(info['changed'])

    def test_team_change_updates_faq_and_move_without_rewriting_other_answers(self):
        def fetch(url):
            if '/stats?seasontype=2' in url:
                return season_payload()
            if '/stats?seasontype=3' in url or url.endswith('/overview'):
                return {}
            return athlete(team='Los Angeles Sparks', short='Sparks', slug='los-angeles-sparks', jersey='3')
        updated, info = roster.refresh_player(copy.deepcopy(PLAYER), fetch, TODAY)
        self.assertEqual(updated['team'], 'Los Angeles Sparks')
        self.assertEqual(updated['jersey'], '3')
        self.assertEqual(info['roster']['move'], ('Aces', 'Sparks'))
        self.assertEqual(updated['rosterMoves'][0]['line'], 'Traded/moved from Aces to Sparks on September 28, 2026.')
        answers = {item['q']: item['a'] for item in updated['faq']}
        self.assertEqual(answers['What team does A\'ja Wilson play for?'], 'A\'ja Wilson plays for the Los Angeles Sparks and wears No. 3.')
        self.assertEqual(answers['How tall is A\'ja Wilson?'], 'A\'ja Wilson is listed at 6-foot-4.')
        self.assertEqual(answers['What position does A\'ja Wilson play?'], 'A\'ja Wilson plays center for the Las Vegas Aces.')
        self.assertEqual(updated['season2026']['PTS'], '26.2')

    def test_combined_season_totals_win_and_split_rows_do_not_replace_stored_stats(self):
        labels = list(roster.SEASON_KEYS)
        def row(team, gp, pts):
            stats = [gp, '0', '20.0', pts, '1.0', '1.0', '1.0', '0.0', '1.0', '40.0', '30.0', '80.0']
            return {'season': {'year': 2026}, 'teamSlug': team, 'stats': stats}
        split = {'categories': [{'name': 'averages', 'labels': labels, 'statistics': [
            row('phoenix-mercury', '37', '10.6'),
            row('atlanta-dream', '5', '8.6'),
        ]}]}
        self.assertIsNone(roster.averages_2026(split, 'atlanta-dream'))
        combined = {'categories': [{'name': 'averages', 'labels': labels, 'statistics': [
            row('phoenix-mercury', '37', '10.6'),
            row('atlanta-dream', '5', '8.6'),
            row('2026 Totals', '42', '10.4'),
        ]}]}
        self.assertEqual(roster.averages_2026(combined, 'atlanta-dream')['GP'], '42')
        self.assertEqual(roster.averages_2026(combined, 'atlanta-dream')['PTS'], '10.4')

    def test_missing_or_partial_stats_do_not_blank_the_season(self):
        def fetch(url):
            if '/stats' in url:
                return {'categories': [{'name': 'averages', 'labels': ['GP'], 'statistics': [
                    {'season': {'year': 2026}, 'teamSlug': 'las-vegas-aces', 'stats': ['41']},
                ]}]}
            if url.endswith('/overview'):
                return {}
            return athlete()
        updated, info = roster.refresh_player(copy.deepcopy(PLAYER), fetch, TODAY)
        self.assertEqual(updated['season2026']['PTS'], '26.2')
        self.assertFalse(info['stats'])

    def test_name_mismatch_skips_player(self):
        def fetch(url):
            payload = athlete()
            payload['athlete']['displayName'] = 'Someone Else'
            return payload
        updated, info = roster.refresh_player(copy.deepcopy(PLAYER), fetch, TODAY)
        self.assertEqual(updated['team'], 'Las Vegas Aces')
        self.assertEqual(info['skipped'], 'athlete record rejected')

    def test_stats_only_commit_is_once_a_day_but_a_trade_still_publishes(self):
        self.assertFalse(roster.should_publish(False, True, True))
        self.assertTrue(roster.should_publish(False, True, False))
        self.assertTrue(roster.should_publish(True, True, True))
        self.assertFalse(roster.should_publish(False, False, False))

    def test_commit_message_lists_the_move(self):
        message = roster.commit_message([
            {'name': 'Jordin Canada', 'roster': {'move': ('Dream', 'Sparks'), 'jersey': ('3', '5')}},
            {'name': 'Arike Ogunbowale', 'roster': {'position': ('Guard', 'Forward')}},
        ])
        self.assertEqual(message, 'Roster update: Jordin Canada Dream to Sparks, jersey 3 to 5; Arike Ogunbowale position Guard to Forward')
        self.assertEqual(roster.commit_message([]), 'Roster update: refresh 2026 stats')

    def test_page_renders_move_faq_and_omits_empty_faq(self):
        style = '<style>body{margin:0}</style>'
        player = copy.deepcopy(PLAYER)
        player['team'] = 'Los Angeles Sparks'
        player['jersey'] = '3'
        player['rosterMoves'] = [{'line': 'Traded/moved from Aces to Sparks on September 28, 2026.'}]
        roster.update_team_faq(player)
        page = roster.render_page(player, style)
        self.assertIn('Traded/moved from Aces to Sparks on September 28, 2026.', page)
        self.assertIn('Los Angeles Sparks', page)
        self.assertIn('"@type": "FAQPage"', page)
        self.assertIn('wears No. 3.', page)
        self.assertIn('target="_blank" rel="noopener"', page)
        self.assertNotIn('aces-fever', page.replace('aces-fever-game-1-aja-wilson-38', ''))
        empty = copy.deepcopy(player)
        empty['faq'] = []
        bare = roster.render_page(empty, style)
        self.assertNotIn('FAQPage', bare)
        self.assertNotIn('section-title">FAQ', bare)
        self.assertIn('Traded/moved from Aces to Sparks on September 28, 2026.', bare)

    def test_writer_refuses_article_paths(self):
        root = Path('/tmp/fcb-roster-root')
        with self.assertRaises(roster.RosterError):
            roster.safe_path(root, 'aces-fever-game-1-aja-wilson-38/index.html')
        with self.assertRaises(roster.RosterError):
            roster.safe_path(root, '../outside.html')
        self.assertTrue(str(roster.safe_path(root, 'players/aja-wilson/index.html')).endswith('players/aja-wilson/index.html'))

    def test_run_does_not_write_on_fetch_failure_or_repeat_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'players' / 'aja-wilson').mkdir(parents=True)
            (root / 'players.json').write_text(json.dumps([PLAYER]), encoding='utf-8')
            style = (Path('/workspace/players/aja-wilson/index.html').read_text(encoding='utf-8'))
            match_style = style[style.index('<style>'):style.index('</style>') + len('</style>')]
            (root / 'players' / 'aja-wilson' / 'index.html').write_text(f'<html>{match_style}</html>', encoding='utf-8')
            (root / 'players' / 'index.html').write_text('<div class="player-list">old</div>', encoding='utf-8')
            before = (root / 'players.json').read_text(encoding='utf-8')
            result = roster.run(root, fetch=lambda url: None, today=TODAY, already_today=False, dry_run=False, pause=0)
            self.assertFalse(result['commit'])
            self.assertEqual((root / 'players.json').read_text(encoding='utf-8'), before)

            def fetch(url):
                if '/stats?seasontype=2' in url:
                    return season_payload(points='27.0')
                if '/stats' in url or url.endswith('/overview'):
                    return {}
                return athlete()
            blocked = roster.run(root, fetch=fetch, today=TODAY, already_today=True, dry_run=False, pause=0)
            self.assertFalse(blocked['commit'])
            self.assertEqual(json.loads((root / 'players.json').read_text(encoding='utf-8'))[0]['season2026']['PTS'], '26.2')
            allowed = roster.run(root, fetch=fetch, today=TODAY, already_today=False, dry_run=False, pause=0)
            self.assertTrue(allowed['commit'])
            self.assertEqual(allowed['message'], 'Roster update: refresh 2026 stats')
            self.assertEqual(json.loads((root / 'players.json').read_text(encoding='utf-8'))[0]['season2026']['PTS'], '27.0')
            page = (root / 'players' / 'aja-wilson' / 'index.html').read_text(encoding='utf-8')
            self.assertIn('>27.0<', page)
            self.assertNotIn('aces-fever-game-1-aja-wilson-38/index.html', '\n'.join(allowed['written']))
            for relative in allowed['written']:
                self.assertFalse(relative.startswith('aces-'))


if __name__ == '__main__':
    unittest.main()
