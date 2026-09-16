"""Synthetic portrait integration fixtures. No API access or credentials."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import apply_portraits as portraits

PROFILE = {'slug': 'caitlin-clark', 'player': {'id': 708, 'first_name': 'Caitlin', 'last_name': 'Clark'}}
RECORD = {'player_id': 708, 'slug': 'caitlin-clark', 'player_name': 'Caitlin Clark', 'approved': True,
          'kind': 'illustration', 'src': '/images/players/test.avif', 'mask': '/images/players/test.svg',
          'width': 640, 'height': 596}
STATS = '<section id="stats"><table><tr><th>2024</th><td>19.2</td></tr></table></section>'
PAGE = ('<!doctype html><html><head><link rel="canonical" href="https://fullcourtbuckets.com/wnba/caitlin-clark/">'
        '<script type="application/ld+json">{"@graph":[{"@type":"Person","@id":"https://fullcourtbuckets.com/wnba/caitlin-clark/#player","name":"Caitlin Clark"}]}</script></head><body>'
        '<section class="hero" aria-labelledby="player-name"><h1 id="player-name">Caitlin Clark</h1>'
        '<div class="hero-art" aria-hidden="true"><span class="ghost-number">22</span><div class="number-card"><strong>22</strong></div><small>FCB</small></div></section>'
        + STATS + '<p>The number artwork is a design element, not a player photograph.</p></body></html>')

class PortraitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        assets = self.root / 'images/players'; assets.mkdir(parents=True)
        (assets/'test.avif').write_bytes(b'synthetic image fixture')
        (assets/'test.svg').write_text('<svg></svg>')
    def test_image_and_name_remain_html_without_hero_caption(self):
        page = portraits.render(PAGE, PROFILE, RECORD, self.root)
        self.assertIn('<img class="player-illustration"', page)
        self.assertIn('alt="Caitlin Clark illustrated portrait"', page)
        self.assertNotIn('<figcaption', page)
        self.assertNotIn('illustration-caption', page)
        self.assertNotIn('AI-generated', portraits.APPLIED.search(page).group())
        self.assertIn('AI-generated illustration', page)  # Metadata retains provenance.
        self.assertNotIn('ghost-number', page)
        self.assertIn(STATS, page)
        self.assertEqual(page.count('<h1 '), 1)
    def test_portrait_has_no_bottom_gap_on_desktop_or_mobile(self):
        self.assertIn('padding:16px 14px 0;', portraits.CSS)
        self.assertIn('min-height:0;padding:0 16px 0}', portraits.CSS)
        self.assertIn('align-items:flex-end;', portraits.CSS)
        self.assertIn('align-self:flex-end;margin:0;', portraits.CSS)
        self.assertNotIn('padding:16px 14px 28px', portraits.CSS)
        self.assertNotIn('padding:0 16px 29px', portraits.CSS)
    def test_removes_previous_caption_when_reapplying(self):
        page = portraits.render(PAGE, PROFILE, RECORD, self.root)
        old = page.replace('</figure>', '<figcaption class="illustration-caption">AI-generated illustration</figcaption></figure>')
        self.assertEqual(page, portraits.render(old, PROFILE, RECORD, self.root))
    def test_idempotent(self):
        first = portraits.render(PAGE, PROFILE, RECORD, self.root)
        self.assertEqual(first, portraits.render(first, PROFILE, RECORD, self.root))
    def test_id_mismatch_rejected(self):
        bad = copy.deepcopy(PROFILE); bad['player']['id'] = 709
        with self.assertRaises(ValueError): portraits.render(PAGE, bad, RECORD, self.root)
    def test_name_mismatch_rejected(self):
        bad = dict(RECORD, player_name='Different Player')
        with self.assertRaises(ValueError): portraits.render(PAGE, PROFILE, bad, self.root)
    def test_unapproved_rejected(self):
        with self.assertRaises(ValueError): portraits.render(PAGE, PROFILE, dict(RECORD, approved=False), self.root)
    def test_remote_or_unsafe_asset_rejected(self):
        for path in ['https://example.org/test.avif', '/images/players/../secret', '/images/players/test.avif\"']:
            with self.assertRaises(ValueError): portraits.render(PAGE, PROFILE, dict(RECORD, src=path), self.root)
    def test_missing_asset_rejected(self):
        (self.root/'images/players/test.avif').unlink()
        with self.assertRaises(ValueError): portraits.render(PAGE, PROFILE, RECORD, self.root)
    def test_missing_slot_rejected(self):
        with self.assertRaises(ValueError): portraits.render(PAGE.replace('class="hero-art"','class="unexpected"'), PROFILE, RECORD, self.root)
    def test_structured_image_data(self):
        page = portraits.render(PAGE, PROFILE, RECORD, self.root)
        self.assertIn('"@type": "ImageObject"', page)
        self.assertIn('"width": 640', page)
    def test_only_mapped_profile_changes_and_rebuild_preserves_art(self):
        (self.root/'content').mkdir()
        (self.root/'content/player-illustrations.json').write_text(json.dumps({'portraits':[RECORD]}))
        (self.root/'data/wnba/players').mkdir(parents=True)
        (self.root/'data/wnba/players/caitlin-clark.json').write_text(json.dumps(PROFILE))
        (self.root/'wnba/caitlin-clark').mkdir(parents=True)
        page = self.root/'wnba/caitlin-clark/index.html'; page.write_text(PAGE)
        (self.root/'wnba/sue-bird').mkdir()
        other = self.root/'wnba/sue-bird/index.html'; other.write_text('unchanged')
        self.assertEqual(portraits.apply(self.root), 1)
        first = page.read_text(); self.assertIn(STATS, first)
        self.assertEqual(other.read_text(), 'unchanged')
        page.write_text(PAGE)
        portraits.apply(self.root)
        self.assertEqual(first, page.read_text())

if __name__ == '__main__': unittest.main()
