"""Synthetic offline fixtures only. These records are never published."""
import copy
import json
from pathlib import Path
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
        profile = {'slug': 'aja-wilson', 'player': {'first_name': "A'ja", 'last_name': 'Wilson'}}
        html, entity = b.faq_section(profile)
        self.assertEqual(len(entity['mainEntity']), len(faq['items']))
        self.assertEqual([q['name'] for q in entity['mainEntity']], [item['question'] for item in faq['items']])
        self.assertEqual(
            [q['acceptedAnswer']['text'] for q in entity['mainEntity']],
            [item['answer'] for item in faq['items']],
        )
        self.assertIn('How tall is A&#x27;ja Wilson?', html)
        self.assertIn('How many MVPs does A&#x27;ja Wilson have?', html)
        self.assertIn('What did A&#x27;ja Wilson score in her last game?', html)
        self.assertNotIn('regular-season averages', html)
        self.assertNotIn('google_keyword', html)
        self.assertNotIn('\u2014', faq_path.read_text())
        self.assertNotIn('\u2014', html)
        answers = ' '.join(item['answer'] for item in faq['items'])
        for banned in ('imported log', 'imported window', 'BALLDONTLIE', 'tracked on Full Court Buckets', "in our imported"):
            self.assertNotIn(banned, answers)
            self.assertNotIn(banned, html)

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
        self.assertIn('Stats from WNBA season averages and game records.', page)
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


    def test_directory_search_is_above_teams_and_couples(self):
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
        couples_link=page.find('Confirmed WNBA relationships')
        self.assertTrue(0 <= profiles < search < show < grid < teams < couples_link < updated)
        self.assertLess(page.find('</h1>'), search)
        self.assertNotIn('Current rosters', page)
        self.assertIn('Find a player', page)
        self.assertIn('hub-links', page)
        self.assertNotIn('\u2014', page[profiles:couples_link])


if __name__=='__main__':unittest.main()
