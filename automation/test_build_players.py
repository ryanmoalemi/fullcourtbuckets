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
    def test_invalid_input_leaves_existing_page(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);data=setup(root);b.build(root)
            before=(root/'wnba/example-player/index.html').read_bytes()
            p=copy.deepcopy(P);p['slug']='wrong-slug';(data/'players/example-player.json').write_text(json.dumps(p))
            with self.assertRaises(b.BuildError):b.build(root)
            self.assertEqual(before,(root/'wnba/example-player/index.html').read_bytes())
    def test_no_synthetic_career_totals(self):
        result=b.profile_page(P);self.assertIn('Statistics since 2008',result);self.assertNotIn('<h2>Career totals',result)
    def test_no_browser_api_key_or_provider_fetch(self):
        js=(ROOT/'players.js').read_text();self.assertNotIn('api.balldontlie.io',js);self.assertNotIn('Authorization',js)

    def test_faq_between_sources_and_archive(self):
        result = b.profile_page(P)
        sources = result.find('id="sources"')
        faq = result.find('id="faq"')
        archive = result.find('archive-band')
        self.assertGreater(sources, 0)
        self.assertGreater(faq, sources)
        self.assertGreater(archive, faq)
        self.assertIn('"@type": "FAQPage"', result)
        self.assertIn("What are Example Player's 2026 regular-season averages?", result)
        self.assertNotIn('How tall is Example Player?', result)

    def test_faq_omitted_when_fewer_than_three_answers(self):
        p = copy.deepcopy(P)
        p['season_stats'] = []
        p['recent_completed_games'] = []
        p['current_team'] = None
        p['active_in_provider_feed'] = False
        p['player'] = {'id': 1, 'first_name': 'Sparse', 'last_name': 'Player', 'position': None, 'height': None, 'jersey_number': None, 'college': None, 'weight': None}
        html, entity = b.faq_section(p)
        self.assertEqual(html, '')
        self.assertIsNone(entity)
        page = b.profile_page(p)
        self.assertNotIn('id="faq"', page)
        self.assertNotIn('FAQPage', page)

    def test_faq_prefers_stats_over_hero_bio_restatements(self):
        p = copy.deepcopy(P)
        p['season_stats'] = [
            {'player_id': 1, 'season': 2026, 'season_type': 2, 'team': {'id': 1, 'full_name': 'Example Team'}, 'games_played': 10, 'pts': 12.3, 'reb': 4.5, 'ast': 6.7},
            {'player_id': 1, 'season': 2025, 'season_type': 2, 'team': {'id': 1, 'full_name': 'Example Team'}, 'games_played': 20, 'pts': 11.0, 'reb': 4.0, 'ast': 5.0},
            {'player_id': 1, 'season': 2025, 'season_type': 3, 'team': {'id': 1, 'full_name': 'Example Team'}, 'games_played': 5, 'pts': 14.0, 'reb': 5.0, 'ast': 4.0},
            {'player_id': 1, 'season': 2024, 'season_type': 2, 'team': {'id': 2, 'full_name': 'Other Team'}, 'games_played': 15, 'pts': 9.5, 'reb': 3.0, 'ast': 4.5},
        ]
        p['recent_completed_games'] = [
            {'date': '2026-09-20', 'pts': 18, 'reb': 5, 'ast': 7, 'team': {'id': 1}, 'home_team': {'id': 1}, 'visitor_team': {'id': 2}},
            {'date': '2026-09-18', 'pts': 10, 'reb': 4, 'ast': 3, 'team': {'id': 1}, 'home_team': {'id': 2}, 'visitor_team': {'id': 1}},
            {'date': '2026-09-15', 'pts': 22, 'reb': 8, 'ast': 6, 'team': {'id': 1}, 'home_team': {'id': 1}, 'visitor_team': {'id': 3}},
        ]
        p['game_log_window_start'] = '2026-08-18'
        html, entity = b.faq_section(p)
        questions = [q['name'] for q in entity['mainEntity']]
        self.assertTrue(any('regular-season averages' in q for q in questions))
        self.assertTrue(any('playoff averages compare' in q for q in questions))
        self.assertTrue(any('teams has Example Player played for' in q for q in questions))
        self.assertTrue(any('scoring trends' in q for q in questions))
        self.assertTrue(any('recent games' in q for q in questions))
        self.assertFalse(any(q.startswith('How tall') for q in questions))
        self.assertFalse(any('jersey number' in q for q in questions))
        self.assertFalse(any('college' in q.lower() for q in questions))
        joined = ' '.join(questions)
        self.assertNotIn('Iowa', html)  # invalid weight must not become college FAQ

    def test_faq_never_uses_invalid_weight_as_college(self):
        p = copy.deepcopy(P)
        p['player']['college'] = None
        p['player']['weight'] = 'South Carolina'
        html, entity = b.faq_section(p)
        blob = html + json.dumps(entity)
        self.assertNotIn('South Carolina', blob)
        self.assertNotIn('college', blob.lower())


if __name__=='__main__':unittest.main()
