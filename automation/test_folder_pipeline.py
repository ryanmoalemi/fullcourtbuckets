"""A whole original file must survive both template stages and keep its pixels."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image
import apply_portraits
import rollout_player_design
from test_rollout_player_design import PAGE, PROFILE, TABLE

class FolderPipelineTests(unittest.TestCase):
    def test_upload_to_render_and_archive_layout(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            data=root/'data/wnba'; (data/'players').mkdir(parents=True)
            (data/'players-index.json').write_text(json.dumps({'players':[
                {'id':5,'slug':'test-player','name':'Test Player','active_in_provider_feed':True}]}))
            (data/'players/test-player.json').write_text(json.dumps(PROFILE))
            page=root/'wnba/test-player/index.html'; page.parent.mkdir(parents=True);page.write_text(PAGE)
            image=root/'images/players/test-player/portrait.png'; image.parent.mkdir(parents=True)
            im=Image.new('RGBA',(1254,1254),(120,70,50,255));im.putpixel((0,0),(0,0,0,0));im.save(image)
            before=image.read_bytes()
            self.assertEqual(apply_portraits.apply(root),1)
            report=rollout_player_design.rollout(root)
            self.assertEqual(report['profiles_with_approved_illustrations'],1)
            text=page.read_text()
            self.assertIn('/images/players/test-player/portrait.png?v='+hashlib.sha256(before).hexdigest()[:12],text)
            self.assertIn('width="1254" height="1254"',text)
            self.assertIn('object-fit:cover',text)
            self.assertIn('height:100%',text)
            self.assertNotIn('height:130%',text)
            self.assertIn(TABLE,text)
            self.assertNotIn('<figcaption',text)
            self.assertNotIn('class="number-card"',text)
            self.assertEqual(image.read_bytes(),before)

if __name__=='__main__':unittest.main()
