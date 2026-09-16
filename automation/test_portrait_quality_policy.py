"""Check real pixels without forcing original PNG uploads through a lossy export."""
import hashlib
import io
import json
from pathlib import Path
import unittest
from PIL import Image

class PortraitQualityPolicyTests(unittest.TestCase):
    def test_new_portraits_have_production_resolution(self):
        root=Path(__file__).resolve().parents[1]
        policy=json.loads((root/'content/portrait-quality.json').read_text())
        records=json.loads((root/'content/player-illustrations.json').read_text())['portraits']
        for record in records:
            with self.subTest(player=record['slug']):
                raw=(root/record['src'].lstrip('/')).read_bytes()
                digest=hashlib.sha256(raw).hexdigest()
                image=Image.open(io.BytesIO(raw)); image.load()
                self.assertIn(image.format,('PNG','WEBP','AVIF'))
                self.assertEqual(image.size,(record['width'],record['height']))
                alpha=image.convert('RGBA').getchannel('A').getextrema()
                self.assertLess(alpha[0],255)
                self.assertGreater(alpha[1],0)
                if policy['unchanged_legacy_assets'].get(record['src']) == digest:
                    continue
                self.assertGreaterEqual(record['width'],640)
                self.assertGreaterEqual(record['height'],650)
                self.assertEqual(record.get('quality_standard'),policy['version'])
                self.assertEqual(record.get('asset_sha256'),digest)

if __name__=='__main__': unittest.main()
