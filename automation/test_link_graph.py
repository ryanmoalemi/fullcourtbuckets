"""Internal link graph, honest anchors, and no broken added links."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import build_players as builder
import internal_links as links
import link_graph

ROOT = Path(__file__).resolve().parents[1]


def _page(body, robots='index,follow', extra_head=''):
    return (
        '<!doctype html><html><head><meta name="robots" content="' + robots + '">'
        + extra_head + '</head><body>' + body + '</body></html>'
    )


class GraphTests(unittest.TestCase):
    def test_orphans_dead_ends_and_skipped_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'index.html').write_text(_page(
                '<header><nav><a href="/orphan/">Orphan</a><a href="/standings/">Standings</a></nav></header>'
                '<main><a href="/story/">Story</a></main>'
                '<footer><a href="/privacy/">Privacy</a></footer>'
            ), encoding='utf-8')
            (root / 'story').mkdir()
            (root / 'story' / 'index.html').write_text(_page('<main><p>A story with no way onward.</p></main>'), encoding='utf-8')
            (root / 'orphan').mkdir()
            (root / 'orphan' / 'index.html').write_text(_page('<main><p>Only the nav points here.</p></main>'), encoding='utf-8')
            (root / 'standings').mkdir()
            (root / 'standings' / 'index.html').write_text(_page('<main><p>Table</p></main>'), encoding='utf-8')
            (root / 'privacy').mkdir()
            (root / 'privacy' / 'index.html').write_text(_page('<main><p>Policy</p></main>'), encoding='utf-8')
            (root / 'secret').mkdir()
            (root / 'secret' / 'index.html').write_text(_page('<main><p>Hidden</p></main>', robots='noindex'), encoding='utf-8')
            (root / '404.html').write_text(_page('<main><h1>Page not found</h1></main>', robots='noindex'), encoding='utf-8')
            (root / 'gone').mkdir()
            (root / 'gone' / 'index.html').write_text(_page(
                '<main><p>Moved</p></main>',
                extra_head='<meta http-equiv="refresh" content="0;url=/">',
            ), encoding='utf-8')
            (root / 'sitemap.xml').write_text(
                '<urlset><loc>https://fullcourtbuckets.com/orphan/</loc><loc>https://fullcourtbuckets.com/story/</loc></urlset>',
                encoding='utf-8',
            )
            report = link_graph.analyze(root)
            urls = {row['url'] for row in report['rows']}
            self.assertEqual(urls, {'/', '/story/', '/orphan/', '/standings/', '/privacy/'})
            self.assertIn('/orphan/', report['orphans'])
            self.assertNotIn('/story/', report['orphans'])
            self.assertIn('/standings/', report['dead_ends'])
            self.assertIn('/story/', report['dead_ends'])
            self.assertNotIn('/', report['dead_ends'])
            inbound = {row['url']: row['inbound_contextual_pages'] for row in report['rows']}
            self.assertEqual(inbound['/story/'], 1)
            self.assertEqual(inbound['/orphan/'], 0)
            self.assertGreaterEqual(report['contextual_links'], 1)
            reasons = {item['url']: item['reason'] for item in report['skipped']}
            self.assertEqual(reasons['/secret/'], 'noindex')
            self.assertEqual(reasons['/404.html'], '404')
            self.assertEqual(reasons['/gone/'], 'redirect')

    def test_expansion_team_pages_use_city_team_slugs(self):
        index = {'players': [
            {'id': 1, 'slug': 'one', 'name': 'One Player', 'active_in_provider_feed': True,
             'current_team': {'id': 31, 'full_name': 'Fire', 'name': 'Fire', 'city': ''}},
            {'id': 2, 'slug': 'two', 'name': 'Two Player', 'active_in_provider_feed': True,
             'current_team': {'id': 30, 'full_name': 'Tempo', 'name': 'Tempo', 'city': ''}},
        ]}
        linking = links.catalog_from_index(index)
        fire = linking['by_id'][31]
        tempo = linking['by_id'][30]
        self.assertEqual(fire['full_name'], 'Portland Fire')
        self.assertEqual(fire['slug'], 'portland-fire')
        self.assertEqual(fire['slug'], links.team_slug(fire['full_name']))
        self.assertEqual(links.team_href(fire), '/wnba/teams/portland-fire/')
        self.assertEqual(tempo['full_name'], 'Toronto Tempo')
        self.assertEqual(tempo['slug'], 'toronto-tempo')
        self.assertEqual(tempo['slug'], links.team_slug(tempo['full_name']))
        self.assertEqual(links.team_href(tempo), '/wnba/teams/toronto-tempo/')
        self.assertIs(linking['by_name']['Fire'], fire)
        self.assertIs(linking['by_name']['Portland Fire'], fire)

    def test_sitemap_replaces_legacy_team_urls(self):
        sample = (
            '<urlset>\n'
            '  <url><loc>https://fullcourtbuckets.com/wnba/teams/fire/</loc></url>\n'
            '  <url><loc>https://fullcourtbuckets.com/about/</loc></url>\n'
            '  <url><loc>https://fullcourtbuckets.com/wnba/teams/tempo/</loc></url>\n'
            '</urlset>'
        )
        updated = links.ensure_sitemap(
            sample,
            ['/wnba/teams/portland-fire/', '/wnba/teams/toronto-tempo/'],
            'https://fullcourtbuckets.com',
        )
        self.assertNotIn('/wnba/teams/fire/', updated)
        self.assertNotIn('/wnba/teams/tempo/', updated)
        self.assertIn('https://fullcourtbuckets.com/wnba/teams/portland-fire/', updated)
        self.assertIn('https://fullcourtbuckets.com/wnba/teams/toronto-tempo/', updated)
        self.assertIn('https://fullcourtbuckets.com/about/', updated)
        self.assertEqual(updated, links.ensure_sitemap(updated, ['/wnba/teams/portland-fire/', '/wnba/teams/toronto-tempo/'], 'https://fullcourtbuckets.com'))

    def test_normalize_internal_urls(self):
        self.assertEqual(link_graph.normalize_href('https://fullcourtbuckets.com/wnba/aja-wilson/', '/'), '/wnba/aja-wilson/')
        self.assertEqual(link_graph.normalize_href('/standings/#top', '/'), '/standings/')
        self.assertIsNone(link_graph.normalize_href('https://example.com/wnba/', '/'))
        self.assertEqual(link_graph.normalize_href('../standings/', '/wnba/aja-wilson/'), '/wnba/standings/')
        self.assertEqual(link_graph.normalize_href('../../standings/', '/wnba/aja-wilson/'), '/standings/')


PROFILE = {
    'slug': 'example-player',
    'player': {
        'id': 1, 'first_name': 'Example', 'last_name': 'Player', 'position': 'G',
        'height': "6' 0\"", 'weight': 'Iowa', 'college': None, 'jersey_number': '22',
    },
    'active_in_provider_feed': True,
    'current_team': {'id': 1, 'full_name': 'Example Team'},
    'checked_at': '2026-09-16T05:48:36+00:00',
    'season_stats': [{
        'player_id': 1, 'season': 2026, 'season_type': 2,
        'team': {'id': 1, 'full_name': 'Example Team'},
        'games_played': 10, 'pts': 12.3, 'reb': 4.5, 'ast': 6.7, 'min': 30,
        'fg_pct': 45, 'fg3_pct': 37, 'ft_pct': 85,
    }],
    'recent_completed_games': [],
    'coverage_start': 2008,
}


class AnchorTests(unittest.TestCase):
    def test_first_mention_only_and_skips_missing_or_ambiguous_names(self):
        index = {'players': [
            {'slug': 'aja-wilson', 'name': "A'ja Wilson"},
            {'slug': 'jackie-young', 'name': 'Jackie Young'},
            {'slug': 'alicia-florez', 'name': 'Alicia Florez'},
            {'slug': 'alicia-florez-2', 'name': 'Alicia Florez'},
        ]}
        linking = {'by_id': {
            8: {'id': 8, 'full_name': 'Las Vegas Aces', 'name': 'Aces', 'slug': 'las-vegas-aces', 'conference': 'Western Conference', 'players': []},
            2: {'id': 2, 'full_name': 'Connecticut Sun', 'name': 'Sun', 'slug': 'connecticut-sun', 'conference': 'Eastern Conference', 'players': []},
            4: {'id': 4, 'full_name': 'Atlanta Dream', 'name': 'Dream', 'slug': 'atlanta-dream', 'conference': 'Eastern Conference', 'players': []},
        }}
        compiled = links.article_phrases(index, linking)
        html = (
            '<article><h1>Aces notes</h1>'
            '<p>The Sun won, then the Connecticut Sun won again. The Atlanta Dream followed.</p>'
            '<p>A\'ja Wilson scored. Later A\'ja Wilson scored again. Jackie Young helped the Aces. '
            'Alicia Florez and Not A Real Person stayed in the text. The Las Vegas Aces closed it.</p>'
            '<p>Already linked: <a href="/wnba/jackie-young/">Jackie Young</a> is here.</p>'
            '</article>'
        )
        # Jackie is already linked later; the earlier plain mention should still link once.
        linked = links.link_copy(html, compiled)
        self.assertEqual(linked.count('href="/wnba/aja-wilson/"'), 1)
        self.assertEqual(linked.count('href="/wnba/jackie-young/"'), 2)
        self.assertNotIn('alicia-florez', linked)
        self.assertIn('Not A Real Person', linked)
        self.assertIn('href="/wnba/teams/connecticut-sun/"', linked)
        self.assertIn('href="/wnba/teams/atlanta-dream/"', linked)
        self.assertNotIn('>Sun</a>', linked)
        self.assertNotIn('>Dream</a>', linked)
        self.assertIn('>Aces</a>', linked)
        self.assertEqual(linked.count('href="/wnba/teams/las-vegas-aces/"'), 1)
        again = links.link_copy(linked, compiled)
        self.assertEqual(again, linked)

    def test_player_page_caps_teammates_and_links_only_real_roster(self):
        profile = copy.deepcopy(PROFILE)
        others = []
        players = [{'id': 1, 'slug': 'example-player', 'name': 'Example Player'}]
        for number in range(2, 14):
            players.append({'id': number, 'slug': f'team-mate-{number}', 'name': f'Team Mate {number}'})
            others.append(players[-1])
        linking = {'by_id': {1: {
            'id': 1, 'full_name': 'Example Team', 'name': 'Example', 'slug': 'example-team',
            'conference': 'Western Conference', 'players': players,
        }}, 'by_name': {}}
        linking['by_name']['Example Team'] = linking['by_id'][1]
        page = builder.profile_page(profile, linking=linking)
        self.assertLessEqual(page.count('class="inline-link"'), links.MAX_PLAYER_LINKS)
        self.assertIn('href="/wnba/teams/example-team/"', page)
        self.assertIn('id="teammates"', page)
        self.assertIn('Some of the other players listed on this roster.', page)
        self.assertNotIn('team-mate-13', page)
        self.assertIn('>Players</a>', page)
        self.assertIn('BreadcrumbList', page)
        self.assertIn('"name": "Players"', page)
        self.assertIn('Player ID: 1.', page)
        self.assertNotIn('\u2014', page[page.find('id="teammates"'):])
        for banned in ('dataset', 'feed', 'imported'):
            self.assertNotIn(banned, page[page.find('id="teammates"'):].casefold())
        plain = builder.profile_page(profile)
        self.assertNotIn('id="teammates"', plain)
        self.assertIn('Current team: <strong>Example Team</strong>.', plain)

    def test_archive_player_links_latest_team_only(self):
        profile = copy.deepcopy(PROFILE)
        profile['active_in_provider_feed'] = False
        profile['season_stats'].append({
            'player_id': 1, 'season': 2024, 'season_type': 2,
            'team': {'id': 9, 'full_name': 'Old Club'},
            'games_played': 4, 'pts': 3, 'reb': 1, 'ast': 1,
        })
        linking = links.catalog_from_index({'players': [
            {'id': 2, 'slug': 'other', 'name': 'Other Player', 'active_in_provider_feed': True,
             'current_team': {'id': 1, 'full_name': 'Example Team', 'name': 'Example'}},
        ]})
        page = builder.profile_page(profile, linking=linking)
        self.assertNotIn('id="teammates"', page)
        self.assertIn('href="/wnba/teams/example-team/"', page)
        self.assertNotIn('Old Club</a>', page)
        self.assertIn('>Old Club</span>', page)

    def test_build_writes_team_page_and_resolves_hrefs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / 'data' / 'wnba'
            (data / 'players').mkdir(parents=True)
            (root / 'automation').mkdir()
            for name in ('players.css', 'players.js'):
                (root / 'automation' / name).write_text((ROOT / 'automation' / name).read_text(encoding='utf-8'), encoding='utf-8')
            first = copy.deepcopy(PROFILE)
            second = copy.deepcopy(PROFILE)
            second['slug'] = 'second-player'
            second['player'] = dict(second['player'], id=2, first_name='Second', last_name='Player')
            second['season_stats'] = [dict(second['season_stats'][0], player_id=2)]
            (data / 'players' / 'example-player.json').write_text(json.dumps(first))
            (data / 'players' / 'second-player.json').write_text(json.dumps(second))
            index = {'checked_at': first['checked_at'], 'players': [
                {'id': 1, 'slug': 'example-player', 'name': 'Example Player', 'current_team': first['current_team'], 'active_in_provider_feed': True},
                {'id': 2, 'slug': 'second-player', 'name': 'Second Player', 'current_team': first['current_team'], 'active_in_provider_feed': True},
            ]}
            (data / 'players-index.json').write_text(json.dumps(index))
            (data / 'status.json').write_text(json.dumps({'status': 'ok'}))
            (root / 'index.html').write_text('<title>Full Court Buckets</title><nav><a href="/">News</a></nav><p>Keep the homepage.</p>', encoding='utf-8')
            (root / 'standings').mkdir()
            (root / 'standings' / 'index.html').write_text('<html><body><main><p>Standings</p></main><footer><p class="footer-links"></p></footer></body></html>', encoding='utf-8')
            (root / 'api').mkdir()
            (root / 'api' / 'wnba-standings').write_text(json.dumps({'teams': [{'rank': 1, 'name': 'Example Team', 'wins': 1, 'losses': 0, 'pct': 1, 'gamesBack': 0, 'home': '1-0', 'road': '0-0', 'streak': 'W1', 'last10': '1-0', 'conference': 'Western'}]}))
            self.assertEqual(builder.build(root), 2)
            team = (root / 'wnba' / 'teams' / 'example-team' / 'index.html').read_text(encoding='utf-8')
            self.assertIn('href="/wnba/example-player/"', team)
            self.assertIn('href="/wnba/second-player/"', team)
            self.assertIn('href="/standings/"', team)
            player = (root / 'wnba' / 'example-player' / 'index.html').read_text(encoding='utf-8')
            self.assertIn('href="/wnba/second-player/"', player)
            self.assertIn('href="/wnba/teams/example-team/"', player)
            self.assertLessEqual(player.count('class="inline-link"'), 8)
            self.assertIn('Second Player', player)
            homepage = (root / 'index.html').read_text(encoding='utf-8')
            self.assertIn('aria-label="Main"', homepage)
            self.assertIn('href="/wnba/"', homepage)
            self.assertIn('Keep the homepage.', homepage)
            standings = (root / 'standings' / 'index.html').read_text(encoding='utf-8')
            again = links.apply_standings(
                standings,
                links.catalog_from_index(index),
                json.loads((root / 'api' / 'wnba-standings').read_text(encoding='utf-8-sig')),
            )
            self.assertEqual(again, standings)


class CityTeamSlugTests(unittest.TestCase):
    def test_build_keeps_legacy_team_urls_as_redirects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / 'data' / 'wnba'
            (data / 'players').mkdir(parents=True)
            (root / 'automation').mkdir()
            for name in ('players.css', 'players.js'):
                (root / 'automation' / name).write_text((ROOT / 'automation' / name).read_text(encoding='utf-8'), encoding='utf-8')
            profile = copy.deepcopy(PROFILE)
            profile['current_team'] = {'id': 31, 'full_name': 'Fire', 'name': 'Fire', 'city': ''}
            profile['season_stats'] = [dict(profile['season_stats'][0], team={'id': 31, 'full_name': 'Fire'})]
            (data / 'players' / 'example-player.json').write_text(json.dumps(profile))
            index = {'checked_at': profile['checked_at'], 'players': [
                {'id': 1, 'slug': 'example-player', 'name': 'Example Player', 'current_team': profile['current_team'], 'active_in_provider_feed': True},
            ]}
            (data / 'players-index.json').write_text(json.dumps(index))
            (data / 'status.json').write_text(json.dumps({'status': 'ok'}))
            (root / 'index.html').write_text('<title>Full Court Buckets</title><nav><a href="/">News</a></nav><p>Keep the homepage.</p>', encoding='utf-8')
            self.assertEqual(builder.build(root), 1)
            page = (root / 'wnba' / 'teams' / 'portland-fire' / 'index.html').read_text(encoding='utf-8')
            self.assertIn('https://fullcourtbuckets.com/wnba/teams/portland-fire/', page)
            self.assertNotIn('/wnba/teams/fire/', page)
            stub = (root / 'wnba' / 'teams' / 'fire' / 'index.html').read_text(encoding='utf-8')
            self.assertIn('content="noindex"', stub)
            self.assertIn('rel="canonical" href="https://fullcourtbuckets.com/wnba/teams/portland-fire/"', stub)
            self.assertIn('http-equiv="refresh" content="0;url=https://fullcourtbuckets.com/wnba/teams/portland-fire/"', stub)
            self.assertIn('location.replace("https://fullcourtbuckets.com/wnba/teams/portland-fire/")', stub)
            self.assertNotIn('href="/wnba/teams/fire/"', stub)
            self.assertNotIn('href="https://fullcourtbuckets.com/wnba/teams/fire/"', stub)
            player = (root / 'wnba' / 'example-player' / 'index.html').read_text(encoding='utf-8')
            self.assertIn('href="/wnba/teams/portland-fire/"', player)
            self.assertNotIn('/wnba/teams/fire/', player)


class StandingsFreshnessTests(unittest.TestCase):
    def test_server_rendered_lead_replaces_js_placeholder(self):
        page = (
            '<h1>WNBA Standings</h1><p class="subhead">2026 Regular Season</p>'
            '<p class="support">Updated automatically throughout the season.</p>'
            '<span id="updatedAt">Updated: --</span>'
        )
        data = {
            'updatedAt': '2026-08-30T17:42:00-07:00',
            'teams': [{'rank': 1, 'name': 'Minnesota Lynx', 'wins': 31, 'losses': 9}],
        }
        updated = links.apply_standings_freshness(page, data)
        self.assertNotIn('Updated: --', updated)
        self.assertIn('The Minnesota Lynx lead the WNBA standings at 31-9.', updated)
        self.assertIn('Updated August 30, 2026.', updated)
        self.assertIn('Updated: August 30, 2026', updated)
        self.assertNotIn('\u2014', updated)
        again = links.apply_standings_freshness(updated, data)
        self.assertEqual(again, updated)
        no_record = links.apply_standings_freshness(page, {'updatedAt': '2026-08-30T17:42:00-07:00', 'teams': [{'rank': 1, 'name': 'Minnesota Lynx'}]})
        self.assertIn('Updated August 30, 2026.', no_record)
        self.assertNotIn('lead the WNBA standings at', no_record)
        self.assertNotIn('0-0', no_record)

LEGACY_TEAM_PATHS = ('/wnba/teams/fire/', '/wnba/teams/tempo/')
REDIRECT_STUBS = {
    'wnba/teams/fire/index.html',
    'wnba/teams/tempo/index.html',
}


def _published_files():
    skip = {'.git', 'automation'}
    allowed = {'.html', '.xml', '.js', '.json', '.css', '.md', '.txt', '.svg'}
    for path in ROOT.rglob('*'):
        if not path.is_file() or path.is_symlink():
            continue
        if any(part in skip for part in path.relative_to(ROOT).parts):
            continue
        if path.suffix.lower() not in allowed:
            continue
        yield path


class RepoLinkTests(unittest.TestCase):
    def test_published_html_targets_resolve(self):
        report = link_graph.analyze(ROOT)
        self.assertEqual(report['broken'], [])
        sample = ROOT / 'wnba' / 'aja-wilson' / 'index.html'
        if 'class="inline-link"' in sample.read_text(encoding='utf-8'):
            page = sample.read_text(encoding='utf-8')
            self.assertLessEqual(page.count('class="inline-link"'), links.MAX_PLAYER_LINKS)
            self.assertIn('Player ID:', page)
            self.assertIn('BreadcrumbList', page)

    def test_every_team_slug_is_city_team_and_legacy_paths_are_stubs_only(self):
        index = json.loads((ROOT / 'data' / 'wnba' / 'players-index.json').read_text(encoding='utf-8'))
        linking = links.catalog_from_index(index)
        self.assertEqual(len(linking['by_id']), 15)
        slugs = []
        for slot in linking['by_id'].values():
            expected = links.team_slug(slot['full_name'])
            self.assertEqual(slot['slug'], expected, slot['full_name'])
            self.assertIn('-', slot['slug'], slot['full_name'])
            self.assertNotEqual(slot['slug'], links.team_slug(slot['name']), slot['full_name'])
            slugs.append(slot['slug'])
        self.assertEqual(len(set(slugs)), 15)
        self.assertIn('portland-fire', slugs)
        self.assertIn('toronto-tempo', slugs)
        self.assertNotIn('fire', slugs)
        self.assertNotIn('tempo', slugs)
        leftovers = []
        for path in _published_files():
            text = path.read_text(encoding='utf-8')
            rel = path.relative_to(ROOT).as_posix()
            for legacy in LEGACY_TEAM_PATHS:
                if legacy not in text:
                    continue
                if rel not in REDIRECT_STUBS:
                    leftovers.append(f'{rel} still contains {legacy}')
                    continue
                if f'href="{legacy}"' in text or f"href='{legacy}'" in text:
                    leftovers.append(f'{rel} links to {legacy}')
                absolute = 'https://fullcourtbuckets.com' + legacy
                if f'href="{absolute}"' in text or f"href='{absolute}'" in text:
                    leftovers.append(f'{rel} links to {absolute}')
        self.assertEqual(leftovers, [])
        for rel, canonical in (
            ('wnba/teams/fire/index.html', 'https://fullcourtbuckets.com/wnba/teams/portland-fire/'),
            ('wnba/teams/tempo/index.html', 'https://fullcourtbuckets.com/wnba/teams/toronto-tempo/'),
        ):
            stub = (ROOT / rel).read_text(encoding='utf-8')
            self.assertIn('<meta name="robots" content="noindex">', stub, rel)
            self.assertIn(f'<link rel="canonical" href="{canonical}">', stub, rel)
            self.assertIn(f'<meta http-equiv="refresh" content="0;url={canonical}">', stub, rel)
            self.assertIn(f'location.replace("{canonical}")', stub, rel)
            page = (ROOT / 'wnba' / 'teams' / canonical.rstrip('/').split('/')[-1] / 'index.html').read_text(encoding='utf-8')
            self.assertIn(f'<link rel="canonical" href="{canonical}">', page)
            self.assertNotIn('noindex', page)


if __name__ == '__main__':
    unittest.main()
