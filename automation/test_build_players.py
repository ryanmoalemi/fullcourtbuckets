"""Synthetic offline fixtures only. These records are never published."""
import copy
import html
import json
from pathlib import Path
import re
import tempfile
import unittest
import build_players as b

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
        result=b.profile_page(p);self.assertIn('Archive profile',result);self.assertNotIn('>Retired<',result)
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
        self.assertIn('The page does not call that retirement or free agency.', archive)
        self.assertNotIn('That alone does not establish retirement', archive)
        self.assertNotIn('active-player', archive)
        self.assertNotIn('Provider status', archive)
    def test_no_browser_api_key_or_provider_fetch(self):
        js=(ROOT/'players.js').read_text();self.assertNotIn('api.balldontlie.io',js);self.assertNotIn('Authorization',js)

    def _write_faq(self, root, slug, items, slug_field=None):
        faq_dir = root / 'data/wnba/faq'
        faq_dir.mkdir(parents=True, exist_ok=True)
        payload = {'slug': slug if slug_field is None else slug_field, 'items': items}
        (faq_dir / f'{slug}.json').write_text(json.dumps(payload))
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

    def test_curated_faq_renders_every_item_before_sources(self):
        items = [{'question': f'Question {i}?', 'answer': f'Answer {i} about <b>facts</b>.'} for i in range(15)]
        items[0]['answer'] = "A'ja is listed at 6 feet 4 inches."
        with tempfile.TemporaryDirectory() as d:
            root = self._write_faq(Path(d), 'example-player', items)
            html, entity = b.faq_section(P, root)
            self.assertEqual(len(entity['mainEntity']), 15)
            self.assertEqual([q['name'] for q in entity['mainEntity']], [f'Question {i}?' for i in range(15)])
            self.assertEqual(entity['@type'], 'FAQPage')
            self.assertEqual(entity['@id'], 'https://fullcourtbuckets.com/wnba/example-player/#faq')
            self.assertIn("A'ja is listed at 6 feet 4 inches.", entity['mainEntity'][0]['acceptedAnswer']['text'])
            self.assertEqual(html.count('class="faq-item"'), 15)
            self.assertIn('A&#x27;ja is listed at 6 feet 4 inches.', html)
            self.assertIn('Answer 14 about &lt;b&gt;facts&lt;/b&gt;.', html)
            self.assertNotIn('<b>facts</b>', html)
            page = b.profile_page(P, root)
            sources = page.find('id="sources"')
            faq = page.find('id="faq"')
            archive = page.find('archive-band')
            self.assertGreater(faq, 0)
            self.assertGreater(sources, faq)
            self.assertGreater(archive, sources)
            self.assertEqual(page.count('"@type": "Question"'), 15)
            self.assertIn('"@type": "FAQPage"', page)
            self.assertNotIn('regular-season averages', page)
            self.assertNotIn('google_keyword', page)

    def test_empty_faq_file_omits_section(self):
        with tempfile.TemporaryDirectory() as d:
            root = self._write_faq(Path(d), 'example-player', [])
            html, entity = b.faq_section(P, root)
            self.assertEqual(html, '')
            self.assertIsNone(entity)

    def test_mismatched_or_broken_faq_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self._write_faq(root, 'example-player', [{'question': 'Q?', 'answer': 'A.'}], slug_field='someone-else')
            with self.assertRaises(b.BuildError):
                b.faq_section(P, root)
            path = root / 'data/wnba/faq/example-player.json'
            path.write_text('{not json')
            with self.assertRaises(b.BuildError):
                b.faq_section(P, root)
            path.write_text(json.dumps({'slug': 'example-player', 'items': [{'question': 'Q?'}]}))
            with self.assertRaises(b.BuildError):
                b.faq_section(P, root)

    def test_aja_wilson_curated_faq_file(self):
        faq_path = ROOT.parent / 'data/wnba/faq/aja-wilson.json'
        faq = json.loads(faq_path.read_text())
        self.assertEqual(faq['slug'], 'aja-wilson')
        self.assertGreaterEqual(len(faq['items']), 15)
        profile = json.loads((ROOT.parent / 'data/wnba/players/aja-wilson.json').read_text())
        html, entity = b.faq_section(profile)
        self.assertEqual(len(entity['mainEntity']), len(faq['items']))
        self.assertEqual([q['name'] for q in entity['mainEntity']], [item['question'] for item in faq['items']])
        for item, node in zip(faq['items'], entity['mainEntity']):
            if not b.faq_stat_kind(item['question']):
                self.assertEqual(node['acceptedAnswer']['text'], item['answer'])
        b.assert_faq_matches_tables(profile, [
            (node['name'], node['acceptedAnswer']['text']) for node in entity['mainEntity']
        ])
        self.assertIn('How tall is A&#x27;ja Wilson?', html)
        self.assertIn('How many MVPs does A&#x27;ja Wilson have?', html)
        self.assertIn('What did A&#x27;ja Wilson score in her last game?', html)
        answers = {node['name']: node['acceptedAnswer']['text'] for node in entity['mainEntity']}
        self.assertEqual(
            answers["How many years has A'ja Wilson been in the WNBA?"],
            "A'ja Wilson has 9 regular seasons on this page, from 2018 to 2026.",
        )
        self.assertIn(
            '<a href="/news/fiba-womens-basketball-world-cup-2026/">This Is the Olympics of the WNBA</a>',
            answers["Where can I read about A'ja Wilson and the 2026 FIBA World Cup?"],
        )
        self.assertIn('How many years has A&#x27;ja Wilson been in the WNBA?', html)
        self.assertNotIn('target="_blank"', html[html.find('id="faq"'):html.find('id="sources"')])
        self.assertNotIn('regular-season averages', html)
        self.assertNotIn('google_keyword', html)
        self.assertNotIn('\u2014', faq_path.read_text())
        self.assertNotIn('\u2014', html)
        answers = ' '.join(item['answer'] for item in faq['items'])
        for banned in ('imported log', 'imported window', 'BALLDONTLIE', 'tracked on Full Court Buckets', "in our imported"):
            self.assertNotIn(banned, answers)
            self.assertNotIn(banned, html)

    def test_plum_and_clark_questions_use_page_data(self):
        root = ROOT.parent
        plum = json.loads((root / 'data/wnba/players/kelsey-plum.json').read_text())
        _html, entity = b.faq_section(plum, root)
        answers = {node['name']: node['acceptedAnswer']['text'] for node in entity['mainEntity']}
        self.assertEqual(
            answers["What was Kelsey Plum's rookie year?"],
            'The first regular-season row for Kelsey Plum is 2017. She played 31 games in that row. That row is highlighted in the regular-season table.',
        )
        self.assertEqual(
            answers['Which teams has Kelsey Plum played for?'],
            'The regular-season table lists the San Antonio Stars, the Las Vegas Aces, and the Los Angeles Sparks for Kelsey Plum. Her current team on this page is the Phoenix Mercury.',
        )
        self.assertNotIn('championship', ' '.join(answers).casefold())
        page = b.profile_page(plum, root)
        self.assertIn('<tr class="rookie-year" data-season="2017">', page)
        clark = json.loads((root / 'data/wnba/players/caitlin-clark.json').read_text())
        _html, entity = b.faq_section(clark, root)
        answers = {node['name']: node['acceptedAnswer']['text'] for node in entity['mainEntity']}
        self.assertEqual(
            answers["What is Caitlin Clark's three-point percentage?"],
            "In the 2026 regular season, Caitlin Clark's three-point percentage on this page is 36.1.",
        )
        self.assertEqual(
            answers['How many years has Caitlin Clark been in the WNBA?'],
            'Caitlin Clark has 3 regular seasons on this page: 2024, 2025, and 2026.',
        )
        self.assertNotIn('card', ' '.join(node['name'] for node in entity['mainEntity']).casefold())

    def test_build_publishes_curated_faq_only(self):
        items = [{'question': f'Q{i}?', 'answer': f'A{i}.'} for i in range(12)]
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            setup(root)
            self._write_faq(root, 'example-player', items)
            self.assertEqual(b.build(root), 1)
            page = (root / 'wnba/example-player/index.html').read_text()
            self.assertEqual(page.count('class="faq-item"'), 12)
            self.assertEqual(page.count('"@type": "Question"'), 12)
            sources = page.find('id="sources"')
            faq = page.find('id="faq"')
            archive = page.find('archive-band')
            self.assertGreater(sources, faq)
            self.assertGreater(archive, sources)
            self.assertNotIn('regular-season averages', page)

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
        items = [
            {'question': "What are Example Player's stats / points per game?", 'answer': 'She averaged 16.6 points in 42 games.'},
            {'question': 'What did Example Player score in her last game?', 'answer': 'Her last game was September 21, 2026.'},
            {'question': 'How tall is Example Player?', 'answer': 'Example Player is listed at 6 feet.'},
        ]
        with tempfile.TemporaryDirectory() as folder:
            root = self._write_faq(Path(folder), 'example-player', items)
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
        self.assertEqual(answers[2], 'Example Player is listed at 6 feet.')
        self.assertEqual(entity['mainEntity'][0]['acceptedAnswer']['text'], answers[0])
        self.assertIn('16.4 points', html)
        self.assertIn('Sep 30, 2026', html)
        with self.assertRaises(b.BuildError):
            b.assert_faq_matches_tables(profile, [(items[0]['question'], items[0]['answer'])])

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
        items = [{
            'question': "What are Example Player's stats / points per game?",
            'answer': 'In her most recent 1 tracked games, Example Player averaged 9.9 points.',
        }]
        with tempfile.TemporaryDirectory() as folder:
            root = self._write_faq(Path(folder), 'example-player', items)
            _html, entity = b.faq_section(profile, root)
            self.assertFalse(b.player_indexable(profile, root))
        answer = entity['mainEntity'][0]['acceptedAnswer']['text']
        self.assertIn('1 tracked game', answer)
        self.assertNotIn('1 tracked games', answer)
        self.assertIn('4.0 points', answer)

    def test_published_faq_matches_angel_reese_caitlin_clark_and_yvonne_turner(self):
        root = ROOT.parent
        expected = {
            'angel-reese': ('16.4 points', 'in 43 games', 'Sep 30, 2026'),
            'caitlin-clark': ('22.3 points', 'in 40 games', None),
            'yvonne-turner': ('6.5 points', 'in 29 games', None),
        }
        for slug, (points, games, last_date) in expected.items():
            profile = json.loads((root / 'data/wnba/players' / f'{slug}.json').read_text())
            _html, entity = b.faq_section(profile, root)
            answers = {node['name']: node['acceptedAnswer']['text'] for node in entity['mainEntity']}
            season = next(text for question, text in answers.items() if 'points per game' in question.casefold())
            self.assertIn(points, season, slug)
            self.assertIn(games, season, slug)
            self.assertNotIn('16.6', season)
            self.assertNotIn('in 42 games', season)
            if last_date:
                last = next(text for question, text in answers.items() if 'last game' in question.casefold())
                self.assertIn(last_date, last, slug)
                self.assertIn('Playoffs', last, slug)
            b.assert_faq_matches_tables(profile, list(answers.items()))

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
