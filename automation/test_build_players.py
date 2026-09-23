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
    def test_null_not_zero(self):self.assertEqual(b.value(None),'&mdash;')
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
            homepage=(root/'index.html').read_text();self.assertEqual(homepage.count('href="/wnba/"'),1);self.assertIn('Keep the homepage.',homepage)
            output=(root/'wnba/example-player/index.html').read_text();self.assertEqual(output.count('<h1 '),1)
            self.assertIn('<td>12.3</td>',output);self.assertNotIn('BALLDONTLIE_API_KEY',output)
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
        ):
            self.assertNotIn(banned, page)
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

    def test_curated_faq_renders_every_item_between_sources_and_archive(self):
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
            self.assertGreater(sources, 0)
            self.assertGreater(faq, sources)
            self.assertGreater(archive, faq)
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
            self.assertGreater(faq, sources)
            self.assertGreater(archive, faq)
            self.assertNotIn('regular-season averages', page)


if __name__=='__main__':unittest.main()
