"""Whole-site layout, identity and no-invented-portrait regression tests."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import rollout_player_design as r

PROFILE={'slug':'test-player','player':{'id':5,'first_name':'Test','last_name':'Player','jersey_number':'9'}}
TABLE='<table><tr><td>15.6</td><td>2026</td></tr></table>'
PAGE=('''<!doctype html><html><head><link rel="canonical" href="https://fullcourtbuckets.com/wnba/test-player/"></head><body>'''
      '''<section class="hero" aria-labelledby="player-name"><h1 id="player-name">Test Player</h1>'''
      '''<div class="hero-art" aria-hidden="true"><span class="ghost-number">9</span><div class="number-card"><strong>9</strong></div><small>FCB</small></div></section>'''+TABLE+'</body></html>')

class RolloutTests(unittest.TestCase):
    def test_compact_layout_is_shared(self):
        page=r.render_layout(PAGE,PROFILE,False)
        self.assertIn('fcb-player-compact',page)
        self.assertIn('grid-template-columns:55% 45%',page)
        self.assertIn('class="portrait-backdrop"',page)
        self.assertIn('class="ghost-number"',page)
        self.assertNotIn('class="number-card"',page)
    def test_no_portrait_is_not_a_fake_face(self):
        page=r.render_layout(PAGE,PROFILE,False)
        self.assertNotIn('<img',page)
        self.assertNotIn('<figcaption',page)
        self.assertNotIn('AI-generated',page)
    def test_statistics_untouched(self):
        self.assertIn(TABLE,r.render_layout(PAGE,PROFILE,False))
    def test_idempotent(self):
        page=r.render_layout(PAGE,PROFILE,False)
        self.assertEqual(page,r.render_layout(page,PROFILE,False))
    def test_caption_not_added(self):
        self.assertNotIn('<figcaption',r.render_layout(PAGE,PROFILE,False))
    def test_missing_expected_image_fails(self):
        with self.assertRaises(ValueError):r.render_layout(PAGE,PROFILE,True)
    def test_unapproved_image_fails(self):
        page=PAGE.replace(TABLE,'<img class="player-illustration">'+TABLE)
        with self.assertRaises(ValueError):r.render_layout(page,PROFILE,False)
    def test_wrong_canonical_fails(self):
        with self.assertRaises(ValueError):r.render_layout(PAGE.replace('/wnba/test-player/','/wnba/wrong-player/'),PROFILE,False)
    def test_wrong_heading_count_fails(self):
        with self.assertRaises(ValueError):r.render_layout(PAGE.replace(TABLE,'<h1 id="extra">Name</h1>'+TABLE),PROFILE,False)
    def test_unsafe_slug_fails(self):
        p=copy.deepcopy(PROFILE);p['slug']='../../outside'
        with self.assertRaises(ValueError):r.render_layout(PAGE,p,False)
    def test_long_names_fit_class(self):
        self.assertEqual(r.name_size({'last_name':'Clark'}),'normal')
        self.assertEqual(r.name_size({'last_name':'Laney-Hamilton'}),'long')
        self.assertEqual(r.name_size({'last_name':'Herbert Harrigan-Long'}),'xlong')
    def test_queue_reports_pending_honestly(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); data=root/'data/wnba';(data/'players').mkdir(parents=True)
            entry={'id':5,'slug':'test-player','name':'Test Player','active_in_provider_feed':True}
            (data/'players-index.json').write_text(json.dumps({'checked_at':'2026-09-16','players':[entry]}))
            (data/'players/test-player.json').write_text(json.dumps(PROFILE))
            page=root/'wnba/test-player/index.html';page.parent.mkdir(parents=True);page.write_text(PAGE)
            report=r.rollout(root)
            self.assertEqual(report['profile_count'],1)
            self.assertEqual(report['profiles_with_approved_illustrations'],0)
            self.assertEqual(report['profiles_awaiting_illustrations'],1)
            self.assertFalse(report['illustration_generation_started'])
            self.assertFalse(report['automatic_paid_generation_enabled'])
            queue=json.loads((data/'illustration-queue.json').read_text())
            self.assertEqual(queue['entries'][0]['player_id'],5)
            self.assertEqual(queue['entries'][0]['state'],'awaiting_illustration')
            before=page.read_text();r.rollout(root);self.assertEqual(before,page.read_text())
    def test_failed_validation_does_not_change_pages(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); data=root/'data/wnba';(data/'players').mkdir(parents=True)
            entries=[{'id':5,'slug':'test-player','name':'Wrong name'}]
            (data/'players-index.json').write_text(json.dumps({'players':entries}))
            (data/'players/test-player.json').write_text(json.dumps(PROFILE))
            page=root/'wnba/test-player/index.html';page.parent.mkdir(parents=True);page.write_text(PAGE)
            with self.assertRaises(ValueError):r.rollout(root)
            self.assertEqual(page.read_text(),PAGE)

if __name__=='__main__':unittest.main()
