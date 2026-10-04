"""Forced FAQ mismatches stay in temp directories. Nothing here is published."""
import copy
import json
from pathlib import Path
import re
import tempfile
import unittest

import build_players as players
import heal_stat_text as heal
from test_build_players import P, setup

ROOT = Path(__file__).resolve().parents[1]


def _rich_profile():
    profile = copy.deepcopy(P)
    profile['season_stats'][0]['pts'] = 16.4
    profile['season_stats'][0]['reb'] = 12.12
    profile['season_stats'][0]['ast'] = 2.79
    profile['season_stats'][0]['games_played'] = 43
    profile['recent_completed_games'] = [
        {
            'player_id': 1, 'date': '2026-09-21T02:00:00+00:00', 'postseason': False,
            'team': {'id': 1, 'full_name': 'Example Team'},
            'home_team': {'id': 2, 'full_name': 'Other Team'},
            'visitor_team': {'id': 1, 'full_name': 'Example Team'},
            'home_score': 80, 'away_score': 90,
            'pts': 18, 'reb': 10, 'ast': 2,
        },
        {
            'player_id': 1, 'date': '2026-09-30T23:00:00+00:00', 'postseason': True,
            'team': {'id': 1, 'full_name': 'Example Team'},
            'home_team': {'id': 2, 'full_name': 'Other Team'},
            'visitor_team': {'id': 1, 'full_name': 'Example Team'},
            'home_score': 75, 'away_score': 93,
            'pts': 15, 'reb': 7, 'ast': 2,
        },
    ]
    return profile


def _write_faq(root: Path, slug: str, items: list) -> None:
    faq_dir = root / 'data' / 'wnba' / 'faq'
    faq_dir.mkdir(parents=True, exist_ok=True)
    (faq_dir / f'{slug}.json').write_text(json.dumps({'slug': slug, 'items': items}), encoding='utf-8')


FAQ_ITEMS = [
    {'question': "What are Example Player's stats / points per game?", 'answer': 'She averaged 16.6 points in 42 games.'},
    {'question': 'What did Example Player score in her last game?', 'answer': 'Her last game was September 21, 2026.'},
    {'question': 'How tall is Example Player?', 'answer': 'Example Player is listed at 6 feet.'},
]


class HealStatTextTests(unittest.TestCase):
    def setUp(self):
        self._opener = heal.issue_opener
        heal.issue_opener = None

    def tearDown(self):
        heal.issue_opener = self._opener

    def test_clean_page_needs_no_repair(self):
        profile = _rich_profile()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            _write_faq(root, 'example-player', FAQ_ITEMS)
            page = players.profile_page(profile, root)
            outcome = heal.heal_page(profile, page, root)
        self.assertEqual(outcome.action, 'ok')
        self.assertEqual(outcome.html, page)
        self.assertEqual(outcome.mismatches, [])

    def test_forced_mismatch_is_regenerated_from_the_stats(self):
        profile = _rich_profile()
        recorded = []
        heal.issue_opener = recorded.append
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            _write_faq(root, 'example-player', FAQ_ITEMS)
            page = players.profile_page(profile, root)
            section = re.search(r'<section class="section" id="faq">.*?</section>', page, re.S).group(0)
            bad_section = section.replace('16.4 points', '16.6 points').replace('in 43 games', 'in 42 games')
            bad = page.replace(section, bad_section, 1)
            bad = re.sub(
                r'(<meta name="description" content=")(.*?)(")',
                r'\1Example Player playoff records that are not on this page.\3',
                bad,
                count=1,
            )
            bad = re.sub(
                r'(<meta property="og:description" content=")(.*?)(")',
                r'\1Example Player playoff records that are not on this page.\3',
                bad,
                count=1,
            )
            bad = bad.replace('Stats \\u0026 Profile', 'Stats \\u0026 Player Profile', 1)
            self.assertTrue(heal.stat_text_mismatches(profile, bad, root))
            outcome = heal.heal_page(profile, bad, root)
            html = outcome.html
            visible = heal._visible_faq(html)
            schema, error = heal._load_schema(html)
            self.assertEqual(heal.stat_text_mismatches(profile, html, root), [])
        self.assertEqual(error, '')
        self.assertEqual(outcome.action, 'fixed')
        self.assertEqual(recorded, [])
        season = visible[0][1]
        self.assertIn('16.4 points', season)
        self.assertIn('in 43 games', season)
        self.assertIn('Sep 30, 2026', visible[1][1])
        self.assertNotIn('16.6', season)
        self.assertNotIn('42 games', season)
        description = players.player_description(profile)
        self.assertNotIn('playoff', description.casefold())
        self.assertIn(players.esc(description), html)
        title = heal._unescape(heal._first(heal._TITLE_RE, html))
        self.assertEqual(heal._webpage_name(schema), title)
        self.assertEqual(title, players.player_title('Example Player'))
        self.assertNotIn('Player Profile', title)
        self.assertEqual(heal._schema_faq_pairs(schema), visible)
        self.assertEqual(visible[2][1], 'Example Player is listed at 6 feet.')

    def test_unfixable_page_keeps_last_html_and_other_pages_still_publish(self):
        recorded = []
        heal.issue_opener = recorded.append
        original = players.season_faq_answer
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = setup(root)
            _write_faq(root, 'example-player', FAQ_ITEMS[:1])
            self.assertEqual(players.build(root), 1)
            before = (root / 'wnba/example-player/index.html').read_bytes()
            other = copy.deepcopy(P)
            other['slug'] = 'other-player'
            other['player']['id'] = 2
            other['player']['first_name'] = 'Other'
            other['player']['last_name'] = 'Player'
            other['season_stats'][0]['player_id'] = 2
            (data / 'players/other-player.json').write_text(json.dumps(other), encoding='utf-8')
            index = json.loads((data / 'players-index.json').read_text(encoding='utf-8'))
            index['players'].append({
                'id': 2,
                'slug': 'other-player',
                'name': 'Other Player',
                'current_team': P['current_team'],
                'active_in_provider_feed': True,
            })
            (data / 'players-index.json').write_text(json.dumps(index), encoding='utf-8')

            def bad_season(profile, name):
                if profile.get('slug') == 'example-player':
                    return 'She averaged 16.6 points in 42 games.'
                return original(profile, name)

            players.season_faq_answer = bad_season
            try:
                self.assertEqual(players.build(root), 2)
            finally:
                players.season_faq_answer = original
            kept = (root / 'wnba/example-player/index.html').read_bytes()
            other_page = (root / 'wnba/other-player/index.html').read_text(encoding='utf-8')
        self.assertEqual(kept, before)
        self.assertIn('Other Player', other_page)
        self.assertIn('12.3', other_page)
        self.assertEqual(len(recorded), 1)
        item = recorded[0]
        self.assertEqual(item['label'], 'needs-fix')
        self.assertIn('/wnba/example-player/', item['title'])
        blob = item['body']
        self.assertIn('https://fullcourtbuckets.com/wnba/example-player/', blob)
        self.assertIn('16.6', blob)
        self.assertIn('12.3 points', blob)
        self.assertIn('last published copy', blob)
        self.assertNotIn('/wnba/other-player/', item['title'])

    def test_daily_check_rewrites_a_bad_file_and_leaves_an_unfixable_file(self):
        recorded = []
        heal.issue_opener = recorded.append
        original = players.season_faq_answer
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = setup(root)
            _write_faq(root, 'example-player', FAQ_ITEMS[:1])
            players.build(root)
            path = root / 'wnba/example-player/index.html'
            good = path.read_bytes()
            text = path.read_text(encoding='utf-8')
            section = re.search(r'<section class="section" id="faq">.*?</section>', text, re.S).group(0)
            bad_section = section.replace('12.3 points', '16.6 points').replace('in 10 games', 'in 42 games')
            path.write_text(text.replace(section, bad_section, 1), encoding='utf-8')
            self.assertEqual(heal.heal_published_players(root), 0)
            repaired = path.read_text(encoding='utf-8')
            self.assertIn('12.3 points', repaired)
            self.assertNotIn('16.6 points', repaired)
            self.assertEqual(recorded, [])
            path.write_bytes(good)

            def bad_season(profile, name):
                return 'She averaged 16.6 points in 42 games.'

            players.season_faq_answer = bad_season
            try:
                self.assertEqual(heal.heal_published_players(root), 0)
            finally:
                players.season_faq_answer = original
            self.assertEqual(path.read_bytes(), good)
        self.assertEqual(len(recorded), 1)
        self.assertIn('16.6', recorded[0]['body'])
        self.assertIn('12.3 points', recorded[0]['body'])
        self.assertEqual(recorded[0]['label'], 'needs-fix')

    def test_published_angel_reese_repair_keeps_the_portrait(self):
        slug = 'angel-reese'
        profile = json.loads((ROOT / 'data/wnba/players' / f'{slug}.json').read_text(encoding='utf-8'))
        original = (ROOT / 'wnba' / slug / 'index.html').read_text(encoding='utf-8')
        self.assertEqual(heal.stat_text_mismatches(profile, original, ROOT), [])
        section = re.search(r'<section class="section" id="faq">.*?</section>', original, re.S).group(0)
        bad = original.replace(section, section.replace('16.4 points', '99.9 points', 1), 1)
        outcome = heal.heal_page(profile, bad, ROOT, previous=original)
        self.assertEqual(outcome.action, 'fixed')
        self.assertIn('class="player-illustration"', outcome.html)
        self.assertIn('AI-generated illustration', outcome.html)
        self.assertIn('FCB:approved-portrait:start', outcome.html)
        self.assertIn('16.4 points', outcome.html)
        self.assertNotIn('99.9 points', outcome.html)
        self.assertEqual(heal.stat_text_mismatches(profile, outcome.html, ROOT), [])

    def test_stat_text_failures_are_not_sitewide_build_errors(self):
        self.assertTrue(heal.is_stat_text_failure(players.BuildError('example-player FAQ does not match the stats table: table says 12.3 points.')))
        self.assertTrue(heal.is_stat_text_failure(players.BuildError('example-player mentions playoffs without playoff stats.')))
        self.assertTrue(heal.is_stat_text_failure(players.BuildError('example-player JSON-LD WebPage name was not updated.')))
        self.assertFalse(heal.is_stat_text_failure(players.BuildError('Unsafe, missing, or duplicate identity in directory.')))
        self.assertFalse(heal.is_stat_text_failure(players.BuildError('Too many contextual links on example-player.')))
        self.assertFalse(heal.is_stat_text_failure(RuntimeError('example-player FAQ does not match')))

    def test_published_player_pages_match_stats_data(self):
        index = json.loads((ROOT / 'data/wnba/players-index.json').read_text(encoding='utf-8'))
        problems = []
        for entry in index['players']:
            slug = entry.get('slug') or ''
            path = ROOT / 'wnba' / slug / 'index.html'
            profile_path = ROOT / 'data/wnba/players' / f'{slug}.json'
            if not path.is_file() or not profile_path.is_file():
                continue
            html = path.read_text(encoding='utf-8')
            if 'http-equiv="refresh"' in html:
                continue
            profile = json.loads(profile_path.read_text(encoding='utf-8'))
            found = heal.stat_text_mismatches(profile, html, ROOT)
            if found:
                problems.append((slug, found[:2]))
            if len(problems) >= 5:
                break
        self.assertEqual(problems, [])
