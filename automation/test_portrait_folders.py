import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image
import portrait_folders as f

class FolderPortraitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.add_player('example-player', 1)

    def add_player(self, slug, pid):
        folder = self.root/'images/players'/slug
        folder.mkdir(parents=True)
        profile = self.root/'data/wnba/players'/f'{slug}.json'
        profile.parent.mkdir(parents=True, exist_ok=True)
        profile.write_text(json.dumps({'slug':slug,'player':{'id':pid,'first_name':'Example','last_name':slug},'season_stats':[]}))
        return folder/'portrait.png'

    def image(self, path=None, size=(1254,1254), opaque=False):
        path = path or self.file
        im = Image.new('RGBA', size, (120,70,50,255))
        if not opaque: im.putpixel((0,0),(0,0,0,0))
        im.save(path)

    def records(self):
        return json.loads((self.root/'content/player-illustrations.json').read_text())['portraits']

    def test_original_preserved_and_mapping_automatic(self):
        self.image(); before = self.file.read_bytes()
        self.assertEqual(f.sync(self.root),1)
        r = self.records()[0]
        self.assertEqual(r['player_id'],1)
        self.assertEqual((r['width'],r['height']),(1254,1254))
        self.assertEqual(r['src'],'/images/players/example-player/portrait.png')
        self.assertEqual(r['asset_sha256'],hashlib.sha256(before).hexdigest())
        self.assertEqual(self.file.read_bytes(),before)
        self.assertFalse(r['export_settings']['reencoded'])

    def test_repeat_is_idempotent(self):
        self.image(); f.sync(self.root)
        old = (self.root/'content/player-illustrations.json').read_bytes()
        f.sync(self.root)
        self.assertEqual((self.root/'content/player-illustrations.json').read_bytes(),old)

    def test_replacement_changes_cache_fingerprint(self):
        self.image(); f.sync(self.root); old=self.records()[0]['asset_sha256']
        im=Image.open(self.file); im.putpixel((20,20),(200,100,0,255)); im.save(self.file)
        f.sync(self.root)
        self.assertNotEqual(self.records()[0]['asset_sha256'],old)

    def test_missing_file_removes_managed_mapping(self):
        self.image(); f.sync(self.root); self.file.unlink(); f.sync(self.root)
        self.assertEqual(self.records(),[])

    def test_thumbnail_rejected(self):
        self.image(size=(256,256))
        with self.assertRaises(ValueError): f.sync(self.root)

    def test_unproven_small_master_rejected(self):
        self.image(size=(640,650))
        with self.assertRaises(ValueError): f.sync(self.root)

    def test_approved_existing_export_can_move_unchanged(self):
        self.image(size=(640,650)); raw=self.file.read_bytes()
        prior={'player_id':1,'slug':'example-player','asset_sha256':hashlib.sha256(raw).hexdigest(),
               'export_settings':{'source_width':1254,'source_height':1254,'upscaled':False}}
        r=f.record_for(self.root,self.file,prior)
        self.assertEqual(r['export_settings']['source_width'],1254)
        self.assertEqual(self.file.read_bytes(),raw)

    def test_corrupt_file_rejected(self):
        self.file.write_text('not a png')
        with self.assertRaises(ValueError): f.sync(self.root)

    def test_opaque_file_rejected(self):
        self.image(opaque=True)
        with self.assertRaises(ValueError): f.sync(self.root)

    def test_two_portraits_require_clear_choice(self):
        self.image(); Image.open(self.file).save(self.file.with_suffix('.webp'))
        with self.assertRaises(ValueError): f.sync(self.root)

    def test_unknown_player_rejected(self):
        self.image(); (self.root/'data/wnba/players/example-player.json').unlink()
        with self.assertRaises(ValueError): f.sync(self.root)

    def test_duplicate_face_bytes_rejected(self):
        self.image(); other=self.add_player('another-player',2);other.write_bytes(self.file.read_bytes())
        with self.assertRaises(ValueError): f.sync(self.root)
        self.assertFalse((self.root/'content/player-illustrations.json').exists())

    def test_symlink_rejected(self):
        self.image(); original=self.root/'original.png'; self.file.rename(original);self.file.symlink_to(original)
        with self.assertRaises(ValueError): f.sync(self.root)

    def test_safe_exact_player_paths(self):
        self.assertTrue(f.matches_player_path('/images/players/example-player/portrait.png','example-player'))
        self.assertTrue(f.matches_player_path('/images/players/example-player-approved-v2.webp','example-player'))
        for bad in ['/images/players/another-player/portrait.png','/images/players/example-player/../../portrait.png','https://example.com/portrait.png']:
            self.assertFalse(f.matches_player_path(bad,'example-player'))

if __name__=='__main__': unittest.main()
