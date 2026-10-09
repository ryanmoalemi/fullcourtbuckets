"""Synthetic offline fixtures only. These records are never published."""
import copy
import html
import json
from pathlib import Path
import re
import tempfile
import unittest

import offline_tests
import build_players as b

offline_tests.install()

ROOT=Path(__file__).resolve().parent
P={'slug':'example-player','player':{'id':1,'first_name':'Example','last_name':'Player','position':'G','height':"6' 0\"",'weight':'Iowa','college':None,'jersey_number':'22'},'active_in_provider_feed':True,'current_team':{'id':1,'full_name':'Example Team'},'checked_at':'2026-09-16T05:48:36+00:00','season_stats':[{'player_id':1,'season':2026,'season_type':2,'team':{'id':1,'full_name':'Example Team'},'games_played':10,'pts':12.3,'reb':4.5,'ast':6.7,'min':30,'fg_pct':45,'fg3_pct':37,'ft_pct':85}], 'recent_completed_games':[], 'coverage_start':2008}

def setup(root,p=None):
    p=copy.deepcopy(p or P)
    data=root/'data/wnba';(data/'players').mkdir(parents=True)
    (data/'players/example-player.json').write_text(json.dumps(p))
    index={'checked_at':p['checked_at'],'players':[{'id':1,'slug':'example-player','name':'Example Player','current_team':p['current_team'],'active_in_provider_feed':True}]}
    (data/'players-index.json').write_text(json.dumps(index))
    (data/'status.json').write_text(json.dumps({'status':'ok'}))
    (root/'automation').mkdir()
    for name in ('players.css','players.js'):(root/'automation'/name).write_text((ROOT/name).read_text())
    (root/'index.html').write_text('<title>Full Court Buckets</title><nav><a href="/">News</a></nav><p>Keep the homepage.</p>')
    return data

class BuildTests(unittest.TestCase):
    def test_invalid_weight_not_relabelled(self):
        fields=b.bio_fields(P['player']); self.assertNotIn('weight',fields);self.assertNotIn('college',fields)
    def test_valid_weight_preserved(self):self.assertEqual(b.bio_fields({'weight':'157 lbs'})['weight'],'157 lbs')
    def test_null_not_zero(self):self.assertEqual(b.value(None),'-')
    def test_zero_preserved(self):self.assertEqual(b.value(0),'0.0')
    def test_unsafe_slug(self):
        with self.assertRaises(b.BuildError):b.validate(P,'../../outside')
    def test_wrong_player_rejected(self):
        p=copy.deepcopy(P);p['season_stats'][0]['player_id']=99
        with self.assertRaises(b.BuildError):b.validate(p,p['slug'])
    def test_duplicate_season_rejected(self):
        p=copy.deepcopy(P);p['season_stats']*=2
        with self.assertRaises(b.BuildError):b.validate(p,p['slug'])
    def test_multiple_stints_not_summed(self):
        p=copy.deepcopy(P);second=copy.deepcopy(p['season_stats'][0]);second['team']['id']=2;p['season_stats'].append(second)
        self.assertIsNone(b.headline(p))
    def test_archive_not_retirement(self):
        p=copy.deepcopy(P);p['active_in_provider_feed']=False
        result=b.profile_page(p);self.assertIn('Inactive player',result);self.assertNotIn('>Retired<',result);self.assertNotIn('Archive profile',result)
    def test_escaped_name(self):
        p=copy.deepcopy(P);p['player']['first_name']='<script>alert(1)</script>'
        result=b.profile_page(p);self.assertNotIn('<script>alert(1)</script>',result);self.assertIn('&lt;script&gt;',result)
    def test_complete_build_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);setup(root);self.assertEqual(b.build(root),1)
            before={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            b.build(root);after={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            self.assertEqual(before,after)
            homepage=(root/'index.html').read_text();self.assertIn('aria-label="Main"',homepage);self.assertIn('Keep the homepage.',homepage);self.assertIn('href="/wnba/"',homepage)
            output=(root/'wnba/example-player/index.html').read_text();self.assertEqual(output.count('<h1 '),1)
            self.assertIn('<td>12.3</td>',output);self.assertNotIn('BALLDONTLIE_API_KEY',output)
            self.assertEqual(output.count("gtag('config','G-ZJK92LK3XT')"),1)
            self.assertIn('navigator.webdriver', output)
            self.assertIn('window.outerWidth === 0 || window.outerHeight === 0', output)
            self.assertNotIn('<script async src="https://www.googletagmanager.com/gtag/js?id=G-ZJK92LK3XT">', output)
            self.assertEqual((root/'wnba/index.html').read_text().count("gtag('config','G-ZJK92LK3XT')"),1)
            adsense='adsbygoogle.js?client=ca-pub-6621195315204235'
            self.assertEqual(output.count(adsense),1)
            self.assertLess(output.index("gtag('config','G-ZJK92LK3XT')"), output.index(adsense))
            self.assertEqual((root/'wnba/index.html').read_text().count(adsense),1)
            self.assertNotIn('id="faq"',output);self.assertNotIn('FAQPage',output)
    def test_invalid_input_leaves_existing_page(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);data=setup(root);b.build(root)
            before=(root/'wnba/example-player/index.html').read_bytes()
            p=copy.deepcopy(P);p['slug']='wrong-slug';(data/'players/example-player.json').write_text(json.dumps(p))
            with self.assertRaises(b.BuildError):b.build(root)
            self.assertEqual(before,(root/'wnba/example-player/index.html').read_bytes())
    def test_no_synthetic_career_totals(self):
        result=b.profile_page(P);self.assertIn('Statistics since 2008',result);self.assertNotIn('<h2>Career totals',result)
    def test_team_change_sentence_newest_first(self):
        p=copy.deepcopy(P)
        p['team_changes']=[
            {'from':'Other Team','to':'Example Team','date':'2009-07-21'},
            {'from':'<First> Team','to':'Other Team','date':'2009-07-08'},
        ]
        page=b.profile_page(p)
        newer='Joined the Example Team from the Other Team on Jul 21, 2009.'
        older='Joined the Other Team from the &lt;First&gt; Team on Jul 8, 2009.'
        self.assertIn('<p class="muted small">Team change</p>', page)
        self.assertIn(newer, page)
        self.assertIn(older, page)
        self.assertLess(page.index('Team change'), page.index(newer))
        self.assertLess(page.index(newer), page.index(older))
        self.assertNotIn('Moved', page)
        self.assertNotIn('Traded', page)
        plain=b.profile_page(P)
        self.assertNotIn('Team change', plain)
        self.assertNotIn('Joined the', plain)

    def test_reader_copy_avoids_internal_jargon(self):
        p = copy.deepcopy(P)
        p['game_log_window_start'] = '2026-08-18'
        p['recent_completed_games'] = [{
            'player_id': 1, 'date': '2026-09-20T03:00:00+00:00', 'postseason': False,
            'team': {'id': 1, 'full_name': 'Example Team'},
            'home_team': {'id': 1, 'full_name': 'Example Team'},
            'visitor_team': {'id': 2, 'full_name': 'Other Team'},
            'home_score': 90, 'away_score': 80, 'minutes': '30',
            'pts': 10, 'reb': 4, 'ast': 5, 'stl': 1, 'blk': 0, 'turnover': 2,
        }]
        page = b.profile_page(p)
        for banned in (
            'imported log', 'imported window', 'Imported window', 'imported statistics',
            'imported data', "provider's active-player feed", 'active-player feed',
            'Provider status', 'BALLDONTLIE', 'this dataset', "View this player's imported data",
            'Source snapshot', 'API snapshot',
            'Automatic news and confirmed transaction feeds are not connected',
            'Scheduled data updates',
            'Team-specific lines are preserved when supplied',
            'That alone does not establish retirement',
            'Not a complete transaction history',
            'Archive status is not a retirement designation',
        ):
            self.assertNotIn(banned, page)
        self.assertIn('Player ID: 1.', page)
        self.assertIn('Each season stays with the team she played for that year.', page)
        self.assertIn('Page status', page)
        self.assertIn('This profile does not include news stories or a list of trades and signings.', page)
        self.assertIn('Privacy Policy', page)
        self.assertIn('Do not sell or share my personal information', page)
        self.assertIn('Current team:', page)
        self.assertIn('Recent games: 2026-08-18 onward.', page)
        self.assertIn('Last updated', page)
        self.assertIn('>View player data</a>', page)
        self.assertIn('Most recent completed game:', page)
        self.assertIn('<dt>Current team</dt><dd>Example Team</dd>', page)
        inactive = copy.deepcopy(P)
        inactive['active_in_provider_feed'] = False
        archive = b.profile_page(inactive)
        self.assertIn('not on a current roster', archive)
        self.assertNotIn('The page does not call that retirement or free agency.', archive)
        self.assertNotIn('That alone does not establish retirement', archive)
        self.assertNotIn('active-player', archive)
        self.assertNotIn('Provider status', archive)
        self.assertEqual(archive.count('Full Court Buckets gathers its own game data and verifies it.'), 1)
        self.assertNotIn('id="faq"', archive)
        self.assertNotIn('id="sources"', archive)
    def test_no_browser_api_key_or_provider_fetch(self):
        js=(ROOT/'players.js').read_text();self.assertNotIn('api.balldontlie.io',js);self.assertNotIn('Authorization',js)

    def _write_faq(self, root, slug, items, slug_field=None):
        faq_dir = root / 'data/wnba/faq'
        faq_dir.mkdir(parents=True, exist_ok=True)
        payload = {'slug': slug if slug_field is None else slug_field, 'items': items}
        (faq_dir / f'{slug}.json').write_text(json.dumps(payload))
        return root

    def _write_related(self, root, slug, queries, slug_field=None):
        folder = root / 'data' / 'wnba' / 'related-searches'
        folder.mkdir(parents=True, exist_ok=True)
        payload = {
            'slug': slug if slug_field is None else slug_field,
            'player': 'Example Player',
            'source': 'Google Search Console',
            'date_range': '2026-01-01/2026-10-01',
            'queries': queries,
        }
        (folder / f'{slug}.json').write_text(json.dumps(payload))
        return root

    def test_no_faq_file_omits_section(self):
        html, entity = b.faq_section(P)
        self.assertEqual(html, '')
        self.assertIsNone(entity)
        page = b.profile_page(P)
        self.assertNotIn('id="faq"', page)
        self.assertNotIn('FAQPage', page)
        self.assertNotIn("What are Example Player's 2026 regular-season averages?", page)
        self.assertNotIn('How tall is Example Player?', page)

    def test_rich_stats_do_not_generate_template_faq(self):
        p = copy.deepcopy(P)
        p['season_stats'] = [
            {'player_id': 1, 'season': 2026, 'season_type': 2, 'team': {'id': 1, 'full_name': 'Example Team'}, 'games_played': 10, 'pts': 12.3, 'reb': 4.5, 'ast': 6.7},
            {'player_id': 1, 'season': 2025, 'season_type': 2, 'team': {'id': 1, 'full_name': 'Example Team'}, 'games_played': 20, 'pts': 11.0, 'reb': 4.0, 'ast': 5.0},
            {'player_id': 1, 'season': 2025, 'season_type': 3, 'team': {'id': 1, 'full_name': 'Example Team'}, 'games_played': 5, 'pts': 14.0, 'reb': 5.0, 'ast': 4.0},
            {'player_id': 1, 'season': 2024, 'season_type': 2, 'team': {'id': 2, 'full_name': 'Other Team'}, 'games_played': 15, 'pts': 9.5, 'reb': 3.0, 'ast': 4.5},
        ]
        p['recent_completed_games'] = [
            {'date': '2026-09-20', 'pts': 18, 'reb': 5, 'ast': 7, 'team': {'id': 1}, 'home_team': {'id': 1}, 'visitor_team': {'id': 2}},
        ]
        p['player']['college'] = None
        p['player']['weight'] = 'South Carolina'
        html, entity = b.faq_section(p)
        self.assertEqual(html, '')
        self.assertIsNone(entity)
        page = b.profile_page(p)
        self.assertNotIn('id="faq"', page)
        self.assertNotIn('FAQPage', page)
        self.assertNotIn('South Carolina', page)
        self.assertNotIn('regular-season averages', page)
        self.assertNotIn('playoff averages', page)

    def test_related_searches_render_only_answerable_queries(self):
        queries = [
            {'query': f'Question {i}?', 'clicks': i, 'impressions': 10, 'question_like': True}
            for i in range(15)
        ]
        queries.append({
            'query': "What are Example Player's stats?",
            'clicks': 20, 'impressions': 100, 'question_like': True,
        })
        queries.append({
            'query': 'Does Example Player have kids?',
            'clicks': 9, 'impressions': 9, 'question_like': True,
        })
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._write_faq(root, 'example-player', [
                {'question': 'Does Example Player have kids?', 'answer': 'There is no widely reported public information.'},
            ])
            self._write_related(root, 'example-player', queries)
            html, entity = b.faq_section(P, root)
            self.assertEqual(entity['@type'], 'FAQPage')
            self.assertEqual(entity['@id'], 'https://fullcourtbuckets.com/wnba/example-player/#faq')
            self.assertEqual(len(entity['mainEntity']), 1)
            self.assertEqual(entity['mainEntity'][0]['name'], "What are Example Player's stats?")
            self.assertIn('12.3 points', entity['mainEntity'][0]['acceptedAnswer']['text'])
            self.assertEqual(html.count('class="faq-item"'), 1)
            self.assertIn('Related searches', html)
            self.assertNotIn('no widely', html.casefold())
            self.assertNotIn('have kids', html.casefold())
            self.assertNotIn('<b>', html)
            page = b.profile_page(P, root)
            sources = page.find('id="sources"')
            faq = page.find('id="faq"')
            archive = page.find('archive-band')
            self.assertGreater(faq, 0)
            self.assertGreater(sources, faq)
            self.assertGreater(archive, sources)
            self.assertEqual(page.count('"@type": "Question"'), 1)
            self.assertIn('"@type": "FAQPage"', page)
            self.assertNotIn('have kids', page.casefold())
            self.assertNotIn('no widely', page.casefold())
            self.assertNotIn('balldontlie', page.casefold())

    def test_empty_related_searches_omit_section(self):
        with tempfile.TemporaryDirectory() as d:
            root = self._write_related(Path(d), 'example-player', [])
            html, entity = b.faq_section(P, root)
            self.assertEqual(html, '')
            self.assertIsNone(entity)

    def test_broken_related_searches_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._write_related(
                root, 'example-player',
                [{'query': 'What are Example Player\'s stats?', 'clicks': 1, 'impressions': 1, 'question_like': True}],
                slug_field='someone-else',
            )
            with self.assertRaises(b.BuildError):
                b.faq_section(P, root)
            path = root / 'data/wnba/related-searches/example-player.json'
            path.write_text('{not json')
            with self.assertRaises(b.BuildError):
                b.faq_section(P, root)
            path.write_text(json.dumps({
                'slug': 'example-player', 'player': 'Example Player', 'source': 'Google Search Console',
                'date_range': '2026-01-01/2026-10-01', 'queries': [{}],
            }))
            with self.assertRaises(b.BuildError):
                b.faq_section(P, root)

    def test_aja_wilson_template_is_not_published(self):
        root = ROOT.parent
        profile = json.loads((root / 'data/wnba/players/aja-wilson.json').read_text())
        html, entity = b.faq_section(profile, root)
        self.assertEqual(html, '')
        self.assertIsNone(entity)
        self.assertEqual(
            b.answer_related_query(profile, "How many years has A'ja Wilson been in the WNBA?", root),
            "A'ja Wilson has 9 regular seasons on this page, from 2018 to 2026.",
        )
        self.assertEqual(b.answer_related_query(profile, "How many MVPs does A'ja Wilson have?", root), '')
        self.assertEqual(b.answer_related_query(profile, "Does A'ja Wilson have kids?", root), '')
        self.assertEqual(b.answer_related_query(profile, "What is A'ja Wilson's nationality?", root), '')
        fiba = b.answer_related_query(profile, "Where can I read about A'ja Wilson and the 2026 FIBA World Cup?", root)
        self.assertIn('<a href="/news/fiba-womens-basketball-world-cup-2026/">This Is the Olympics of the WNBA</a>', fiba)
        self.assertNotIn('balldontlie', fiba.casefold())
        self.assertIsNone(b._NOT_WIDELY_RE.search(fiba))

    def test_plum_and_clark_answers_come_from_page_data(self):
        root = ROOT.parent
        plum = json.loads((root / 'data/wnba/players/kelsey-plum.json').read_text())
        self.assertEqual(
            b.answer_related_query(plum, "What was Kelsey Plum's rookie year?", root),
            'The first regular-season row for Kelsey Plum is 2017. She played 31 games in that row. That row is highlighted in the regular-season table.',
        )
        self.assertEqual(
            b.answer_related_query(plum, 'Which teams has Kelsey Plum played for?', root),
            'The regular-season table lists the San Antonio Stars, the Las Vegas Aces, and the Los Angeles Sparks for Kelsey Plum. Her current team on this page is the Phoenix Mercury.',
        )
        page = b.profile_page(plum, root)
        self.assertIn('<tr class="rookie-year" data-season="2017">', page)
        self.assertNotIn('id="faq"', page)
        self.assertNotIn('FAQPage', page)
        clark = json.loads((root / 'data/wnba/players/caitlin-clark.json').read_text())
        self.assertEqual(
            b.answer_related_query(clark, "What is Caitlin Clark's three-point percentage?", root),
            "In the 2026 regular season, Caitlin Clark's three-point percentage on this page is 36.1.",
        )
        self.assertEqual(
            b.answer_related_query(clark, 'How many years has Caitlin Clark been in the WNBA?', root),
            'Caitlin Clark has 3 regular seasons on this page: 2024, 2025, and 2026.',
        )

    def test_build_publishes_related_searches_not_the_template(self):
        items = [{'question': f'Q{i}?', 'answer': f'There is no widely reported answer {i}.'} for i in range(12)]
        queries = [
            {'query': "What are Example Player's stats?", 'clicks': 3, 'impressions': 30, 'question_like': True},
            {'query': 'Does Example Player have kids?', 'clicks': 2, 'impressions': 20, 'question_like': True},
        ]
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            setup(root)
            self._write_faq(root, 'example-player', items)
            self._write_related(root, 'example-player', queries)
            self.assertEqual(b.build(root), 1)
            page = (root / 'wnba/example-player/index.html').read_text()
            self.assertEqual(page.count('class="faq-item"'), 1)
            self.assertEqual(page.count('"@type": "Question"'), 1)
            self.assertIn("What are Example Player&#x27;s stats?", page)
            self.assertNotIn('have kids', page.casefold())
            self.assertNotIn('no widely', page.casefold())
            sources = page.find('id="sources"')
            faq = page.find('id="faq"')
            archive = page.find('archive-band')
            self.assertGreater(sources, faq)
            self.assertGreater(archive, sources)

    def test_answer_summary_uses_only_real_numbers(self):
        text = b.answer_summary(P)
        self.assertEqual(
            text,
            'Example Player is a guard for the Example Team. In the 2026 season she averaged 12.3 points, 4.5 rebounds and 6.7 assists in 10 games.',
        )
        self.assertNotIn('\u2014', text)
        self.assertNotIn('\u2013', text)
        for banned in ('dataset', 'feed', 'imported', 'provider', 'snapshot', 'api'):
            self.assertNotIn(banned, text.lower())
        missing = copy.deepcopy(P)
        missing['season_stats'][0]['pts'] = None
        missing['season_stats'][0]['reb'] = None
        partial = b.answer_summary(missing)
        self.assertIn('6.7 assists', partial)
        self.assertIn('in 10 games', partial)
        self.assertNotIn('points', partial)
        self.assertNotIn('rebounds', partial)
        self.assertNotIn('0.0', partial)
        self.assertNotIn('0 assists', partial)
        self.assertNotIn('\u2014', partial)
        empty = copy.deepcopy(P)
        empty['season_stats'] = []
        empty['active_in_provider_feed'] = False
        empty['current_team'] = {'id': 9, 'full_name': 'Old Team'}
        archive = b.answer_summary(empty)
        self.assertEqual(archive, 'Example Player is a guard and is not on a current roster.')
        self.assertNotIn('averaged', archive)
        self.assertNotIn('Old Team', archive)
        self.assertNotIn('retired', archive.lower())
        self.assertNotIn('\u2014', archive)
        split = copy.deepcopy(P)
        other = copy.deepcopy(split['season_stats'][0])
        other['team'] = {'id': 2, 'full_name': 'Other Team'}
        other['pts'] = 99
        split['season_stats'].append(other)
        combined = b.answer_summary(split)
        self.assertNotIn('averaged', combined)
        self.assertNotIn('99', combined)
        page = b.profile_page(P)
        self.assertIn('</h1><p class="answer-summary">', page)
        self.assertIn('Stats updated September 15, 2026.', page)
        self.assertIn('Full Court Buckets gathers its own game data and verifies it.', page)
        self.assertNotIn('balldontlie', page.casefold())
        self.assertIn('"dateModified": "2026-09-15"', page)
        self.assertNotIn('\u2014', page[page.find('class="answer-summary"'):page.find('class="hero-meta"')])
        head, body = page.split('</head>', 1)
        visible = body.split('<script', 1)[0]
        self.assertIn('<td>12.3</td>', visible)
        self.assertLess(visible.find('<table>'), visible.find('</table>'))
        self.assertIn('<td>12.3</td>', visible[visible.find('<table>'):visible.find('</table>')])
        held = copy.deepcopy(P)
        held['checked_at'] = '2026-09-29T00:02:44+00:00'
        held['stats_updated_at'] = '2026-08-02T18:00:00+00:00'
        dated = b.profile_page(held)
        lead = dated[dated.find('class="stats-updated"'):dated.find('class="hero-meta"')]
        self.assertIn('Stats updated August 2, 2026.', lead)
        self.assertNotIn('September 28, 2026', lead)
        self.assertIn('"dateModified": "2026-08-02"', dated)


    def test_directory_search_is_above_teams_and_skips_couples(self):
        index={'checked_at':'2026-10-01T07:31:00+00:00','players':[{'id':1,'slug':'example-player','name':'Example Player','current_team':{'id':1,'full_name':'Example Team'},'active_in_provider_feed':True}]}
        linking={'by_id':{1:{'id':1,'slug':'example-team','full_name':'Example Team','players':[]}}}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            couples=root/'wnba'/'couples'
            couples.mkdir(parents=True)
            (couples/'index.html').write_text('<p>couples</p>', encoding='utf-8')
            page=b.directory_page(index, linking, include_standings=False, root=root)
        profiles=page.find('profiles. Available statistics from 2008 onward.')
        search=page.find('id="player-search"')
        show=page.find('id="active-filter"')
        updated=page.find('class="muted small directory-updated"')
        grid=page.find('class="player-grid"')
        teams=page.find('id="teams"')
        main=page.split('<main', 1)[1].split('</main>', 1)[0]
        self.assertNotIn('/wnba/couples/', main)
        self.assertNotIn('Confirmed WNBA relationships', main)
        self.assertTrue(0 <= profiles < search < show < grid < teams < updated)
        self.assertLess(page.find('</h1>'), search)
        self.assertNotIn('Current rosters', page)
        self.assertIn('Find a player', page)
        self.assertIn('>Inactive players</option>', page)
        self.assertIn('An inactive player is not on a current roster.', page)
        self.assertNotIn('Archive profile', page)
        self.assertNotIn('Archive profiles', page)
        self.assertIn('hub-links', page)
        self.assertNotIn('\u2014', page[profiles:updated])

    def test_player_name_has_a_space_between_the_spans(self):
        page = b.profile_page(P)
        self.assertIn('<h1 id="player-name"><span>Example</span> <b class="gradient">Player</b></h1>', page)
        heading = page.split('id="player-name">', 1)[1].split('</h1>', 1)[0]
        import html as html_lib
        import re
        self.assertEqual(re.sub(r'<[^>]+>', '', html_lib.unescape(heading)), 'Example Player')

    def test_faq_numbers_come_from_the_stats_table_including_playoffs(self):
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
        queries = [
            {'query': "What are Example Player's stats / points per game?", 'clicks': 8, 'impressions': 80, 'question_like': True},
            {'query': 'What did Example Player score in her last game?', 'clicks': 4, 'impressions': 40, 'question_like': True},
            {'query': 'How tall is Example Player?', 'clicks': 2, 'impressions': 20, 'question_like': True},
        ]
        with tempfile.TemporaryDirectory() as folder:
            root = self._write_related(Path(folder), 'example-player', queries)
            html, entity = b.faq_section(profile, root)
        answers = [node['acceptedAnswer']['text'] for node in entity['mainEntity']]
        self.assertIn('16.4 points', answers[0])
        self.assertIn('12.1 rebounds', answers[0])
        self.assertIn('2.8 assists', answers[0])
        self.assertIn('in 43 games', answers[0])
        self.assertNotIn('16.6', answers[0])
        self.assertNotIn('42 games', answers[0])
        self.assertIn('Sep 30, 2026', answers[1])
        self.assertIn('Playoffs', answers[1])
        self.assertIn('15 points', answers[1])
        self.assertNotIn('September 21', answers[1])
        self.assertEqual(answers[2], 'Example Player is listed at 6\' 0".')
        self.assertEqual(entity['mainEntity'][0]['acceptedAnswer']['text'], answers[0])
        self.assertIn('16.4 points', html)
        self.assertIn('Sep 30, 2026', html)
        with self.assertRaises(b.BuildError):
            b.assert_faq_matches_tables(profile, [(queries[0]['query'], 'She averaged 16.6 points in 42 games.')])

    def test_one_tracked_game_is_singular_and_empty_stats_stay_noindex(self):
        profile = copy.deepcopy(P)
        profile['season_stats'] = []
        profile['recent_completed_games'] = [{
            'player_id': 1, 'date': '2026-09-01T03:00:00+00:00', 'postseason': False,
            'team': {'id': 1, 'full_name': 'Example Team'},
            'home_team': {'id': 1, 'full_name': 'Example Team'},
            'visitor_team': {'id': 2, 'full_name': 'Other Team'},
            'home_score': 70, 'away_score': 60,
            'pts': 4, 'reb': 1, 'ast': 0,
        }]
        queries = [{
            'query': "What are Example Player's stats / points per game?",
            'clicks': 1, 'impressions': 4, 'question_like': True,
        }]
        with tempfile.TemporaryDirectory() as folder:
            root = self._write_related(Path(folder), 'example-player', queries)
            _html, entity = b.faq_section(profile, root)
            self.assertFalse(b.player_indexable(profile, root))
        answer = entity['mainEntity'][0]['acceptedAnswer']['text']
        self.assertIn('1 tracked game', answer)
        self.assertNotIn('1 tracked games', answer)
        self.assertIn('4.0 points', answer)

    def test_archive_record_keeps_stored_facts_and_drops_filler(self):
        profile = copy.deepcopy(P)
        profile['active_in_provider_feed'] = False
        profile['current_team'] = None
        profile['player']['college'] = None
        profile['player']['weight'] = 'Iowa'
        items = [
            {'question': 'Does Example Player have kids?', 'answer': 'There is no widely reported public information that Example Player has children.'},
            {'question': "What is Example Player's nationality?", 'answer': 'No widely reported nationality is listed.'},
            {'question': 'Who is Example Player?', 'answer': 'Example Player is a former professional with a long untold story.'},
        ]
        queries = [
            {'query': 'Does Example Player have kids?', 'clicks': 3, 'impressions': 12, 'question_like': True},
            {'query': "What is Example Player's nationality?", 'clicks': 2, 'impressions': 8, 'question_like': True},
            {'query': 'How old is Example Player?', 'clicks': 1, 'impressions': 4, 'question_like': True},
        ]
        with tempfile.TemporaryDirectory() as folder:
            root = self._write_faq(Path(folder), 'example-player', items)
            self._write_related(root, 'example-player', queries)
            html, entity = b.faq_section(profile, root)
            self.assertEqual(html, '')
            self.assertIsNone(entity)
            page = b.profile_page(profile, root)
        self.assertIn('Inactive player', page)
        self.assertNotIn('Archive profile', page)
        self.assertIn('Example Player is a guard and is not on a current roster.', page)
        self.assertIn('In the 2026 season she averaged 12.3 points, 4.5 rebounds and 6.7 assists in 10 games.', page)
        self.assertIn('<td>12.3</td>', page)
        self.assertIn('>2026</strong><span>Example Team</span>', page)
        self.assertIn('<dt>Years on record</dt><dd>2026</dd>', page)
        self.assertIn('content="index,follow,max-image-preview:large"', page)
        self.assertEqual(page.count('Full Court Buckets gathers its own game data and verifies it.'), 1)
        self.assertEqual(page.count('<h1 '), 1)
        for dropped in (
            'id="faq"', 'FAQPage', 'have kids', 'nationality', 'no widely reported',
            'untold story', 'id="sources"', 'About these numbers', 'class="ai-note"',
            'class="archive-band"', 'does not call that retirement',
            'This is not every roster move', 'Statistics since 2008',
            'not a full career total', 'The number artwork is a design element',
            'Iowa', 'balldontlie',
        ):
            self.assertNotIn(dropped, page, dropped)
        active = b.profile_page(P)
        self.assertIn('Statistics since 2008', active)
        self.assertIn('id="sources"', active)
        self.assertIn('class="ai-note"', active)
        self.assertIn('class="archive-band"', active)

    def test_published_faq_matches_angel_reese_caitlin_clark_and_yvonne_turner(self):
        root = ROOT.parent
        for slug in ('angel-reese', 'caitlin-clark'):
            profile = json.loads((root / 'data/wnba/players' / f'{slug}.json').read_text())
            html_text, entity = b.faq_section(profile, root)
            self.assertEqual(html_text, '')
            self.assertIsNone(entity)
            name = b.player_name(profile)
            season = b.answer_related_query(profile, f"What are {name}'s stats / points per game?", root)
            row = b.headline(profile)
            points = f"{b.value(row.get('pts'))} points"
            games = f"in {b.value(row.get('games_played'), True)} games"
            self.assertIn(points, season, slug)
            self.assertIn(games, season, slug)
            # The old Angel Reese FAQ said 16.6 points in 42 games. That copy must not return.
            self.assertNotIn('16.6', season)
            self.assertNotIn('in 42 games', season)
            last = b.answer_related_query(profile, f'What did {name} score in her last game?', root)
            game = b.latest_completed_game(profile)
            if last and game:
                shown = b.game_display(game)
                self.assertNotIn(shown['date'], ('', 'Not listed'), slug)
                self.assertIn(shown['date'], last, slug)
                if shown['kind'] not in ('', 'Not listed'):
                    self.assertIn(shown['kind'], last, slug)
            b.assert_faq_matches_tables(profile, [
                (f"What are {name}'s stats / points per game?", season),
                (f'What did {name} score in her last game?', last),
            ])
        turner = json.loads((root / 'data/wnba/players/yvonne-turner.json').read_text())
        html_text, entity = b.faq_section(turner, root)
        self.assertEqual(html_text, '')
        self.assertIsNone(entity)
        page = b.profile_page(turner, root, menu=[])
        self.assertNotIn('id="faq"', page)
        self.assertNotIn('FAQPage', page)
        self.assertNotIn('no widely reported', page.casefold())
        self.assertIn('Inactive player', page)
        self.assertNotIn('Archive profile', page)

    def test_build_blocks_an_unflagged_season_gap(self):
        root = ROOT.parent
        profile = json.loads((root / 'data/wnba/players/abby-bishop.json').read_text())
        with self.assertRaises(b.BuildError):
            b.require_flagged_season_gap(profile, '<p>Years on record 2015</p>', root)
        flagged = b.profile_page(profile, root, menu=[])
        b.require_flagged_season_gap(profile, flagged, root)
        self.assertIn('This record is partial.', b.player_description(profile, root))
        self.assertNotIn('Seasons on record', b.player_description(profile, root))

    def test_abby_bishop_record_is_partial_and_does_not_invent_seasons(self):
        root = ROOT.parent
        profile = json.loads((root / 'data/wnba/players/abby-bishop.json').read_text())
        check = b.season_cross_check(profile, root)
        self.assertEqual(check['missing'], [2010, 2016])
        self.assertEqual(check['games'], [])
        self.assertTrue(check['checked'])
        page = b.profile_page(profile, root, menu=[])
        self.assertIn('This record is partial.', page)
        self.assertIn('do not include 2010 and 2016.', page)
        self.assertIn('<td>26</td>', page)
        self.assertIn('>2015</strong>', page)
        self.assertNotIn('Years on record', page)
        self.assertIn('Verified seasons', page)
        self.assertNotIn('>2010</strong>', page)
        self.assertNotIn('>2016</strong>', page)
        self.assertNotIn('55', page)
        self.assertNotIn('balldontlie', page.casefold())
        self.assertEqual(page.count('Full Court Buckets gathers its own game data and verifies it.'), 1)

    def test_a_matching_season_is_not_called_partial(self):
        profile = copy.deepcopy(P)
        profile['active_in_provider_feed'] = False
        profile['current_team'] = None
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            table = {
                'players': {
                    '1': {
                        'name': 'Example Player',
                        'status': 'ok',
                        'stints': [{'season': 2026, 'season_type': 2, 'games_played': 10, 'team_slug': 'example'}],
                    }
                }
            }
            (root / 'data/wnba').mkdir(parents=True)
            (root / 'data/wnba/season-teams.json').write_text(json.dumps(table), encoding='utf-8')
            self.assertEqual(b.season_cross_check(profile, root)['missing'], [])
            self.assertEqual(b.season_cross_check(profile, root)['games'], [])
            page = b.profile_page(profile, root, menu=[])
            self.assertNotIn('This record is partial.', page)
            self.assertIn('Years on record', page)
            table['players']['1']['stints'].append(
                {'season': 2010, 'season_type': 2, 'games_played': 16, 'team_slug': 'example'}
            )
            (root / 'data/wnba/season-teams.json').write_text(json.dumps(table), encoding='utf-8')
            b._SEASON_TABLES.clear()
            page = b.profile_page(profile, root, menu=[])
            self.assertIn('do not include 2010.', page)
            self.assertNotIn('Years on record', page)
            table['players']['1']['stints'] = [
                {'season': 2026, 'season_type': 2, 'games_played': 99, 'team_slug': 'example'}
            ]
            (root / 'data/wnba/season-teams.json').write_text(json.dumps(table), encoding='utf-8')
            b._SEASON_TABLES.clear()
            disagreed = b.season_cross_check(profile, root)
            self.assertEqual(disagreed['games'], [2026])
            self.assertIn('could not be confirmed', b.partial_record_html(profile, root))

    def test_published_pages_flag_season_and_game_disagreements(self):
        root = ROOT.parent
        index = json.loads((root / 'data/wnba/players-index.json').read_text())
        problems = []
        for entry in index['players']:
            slug = entry.get('slug') or ''
            path = root / 'wnba' / slug / 'index.html'
            profile_path = root / 'data/wnba/players' / f'{slug}.json'
            if not path.is_file() or not profile_path.is_file():
                continue
            page = path.read_text(encoding='utf-8')
            if 'http-equiv="refresh"' in page:
                continue
            profile = json.loads(profile_path.read_text(encoding='utf-8'))
            check = b.season_cross_check(profile, root)
            incomplete = bool(check['missing'] or check['games'])
            flagged = 'This record is partial.' in page
            if incomplete != flagged:
                problems.append(slug)
            if incomplete:
                note = page[page.find('partial-record'):page.find('partial-record') + 1200]
                for year in check['missing'] + check['games']:
                    if str(year) not in note:
                        problems.append(f'{slug} omits {year}')
            elif 'class="partial-record"' in page:
                problems.append(slug + ' extra flag')
        self.assertEqual(problems, [])

    def test_normalized_questions_do_not_repeat_and_answers_are_not_filler(self):
        self.assertEqual(
            b.normalize_question("How old is A'ja Wilson?", "A'ja Wilson"),
            b.normalize_question('How old is Caitlin Clark?', 'Caitlin Clark'),
        )
        root = ROOT.parent
        index = json.loads((root / 'data/wnba/players-index.json').read_text())
        counts = {}
        for entry in index['players']:
            slug = entry.get('slug') or ''
            path = root / 'wnba' / slug / 'index.html'
            if not path.is_file():
                continue
            page = path.read_text(encoding='utf-8')
            if 'http-equiv="refresh"' in page:
                continue
            self.assertNotIn('balldontlie', page.casefold(), slug)
            if 'id="faq"' not in page:
                self.assertNotIn('FAQPage', page, slug)
                continue
            for question, answer in re.findall(r'<div class="faq-item"><h3>(.*?)</h3><p>(.*?)</p></div>', page):
                plain_q = html.unescape(question)
                plain_a = html.unescape(re.sub(r'<[^>]+>', '', answer))
                self.assertIsNone(b._NOT_WIDELY_RE.search(plain_a), slug)
                self.assertIsNone(b._NOT_WIDELY_RE.search(plain_q), slug)
                key = b.normalize_question(plain_q, entry.get('name') or '')
                counts.setdefault(key, []).append(slug)
        repeats = {key: slugs for key, slugs in counts.items() if len(slugs) >= 3}
        self.assertEqual(repeats, {})

    def test_meta_mentions_playoffs_only_when_the_profile_has_them(self):
        regular = copy.deepcopy(P)
        self.assertNotIn('playoff', b.player_description(regular).casefold())
        playoffs = copy.deepcopy(P)
        playoffs['season_stats'].append({
            'player_id': 1, 'season': 2026, 'season_type': 3,
            'team': {'id': 1, 'full_name': 'Example Team'},
            'games_played': 3, 'pts': 10, 'reb': 4, 'ast': 2,
        })
        self.assertIn('regular-season and playoff records', b.player_description(playoffs))
        with tempfile.TemporaryDirectory() as folder:
            page = b.profile_page(regular, Path(folder), menu=[])
        title = html.unescape(re.search(r'<title>(.*?)</title>', page).group(1))
        data = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', page).group(1))
        webpage = next(node for node in data['@graph'] if node.get('@type') == 'WebPage')
        self.assertEqual(webpage['name'], title)
        self.assertEqual(webpage['name'], b.player_title('Example Player'))
        self.assertNotIn('Stats & Player Profile', webpage['name'])

    def test_published_descriptions_match_playoff_rows_and_titles(self):
        root = ROOT.parent
        mismatches = []
        for path in (root / 'data/wnba/players').glob('*.json'):
            profile = json.loads(path.read_text())
            slug = profile.get('slug') or path.stem
            page_path = root / 'wnba' / slug / 'index.html'
            if not page_path.is_file():
                continue
            text = page_path.read_text(encoding='utf-8')
            if 'http-equiv="refresh"' in text:
                continue
            description = html.unescape(re.search(r'name="description" content="([^"]*)"', text).group(1))
            mentions = 'playoff' in description.casefold()
            if mentions != b.player_has_playoff_stats(profile):
                mismatches.append(slug)
            title = html.unescape(re.search(r'<title>(.*?)</title>', text).group(1))
            data = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', text).group(1))
            webpage = next(node for node in data['@graph'] if node.get('@type') == 'WebPage')
            if webpage.get('name') != title:
                mismatches.append(slug + ' schema name')
            if 'Stats & Player Profile' in webpage.get('name', ''):
                mismatches.append(slug + ' old schema name')
        self.assertEqual(mismatches, [])


if __name__=='__main__':unittest.main()
