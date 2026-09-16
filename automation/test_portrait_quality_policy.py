"""Prevent new hero portraits from silently becoming enlarged thumbnails."""
import hashlib
import json
from pathlib import Path
import unittest

class PortraitQualityPolicyTests(unittest.TestCase):
    def test_new_portraits_have_production_resolution(self):
        root=Path(__file__).resolve().parents[1]
        policy=json.loads((root/'content/portrait-quality.json').read_text())
        records=json.loads((root/'content/player-illustrations.json').read_text())['portraits']
        for record in records:
            with self.subTest(player=record['slug']):
                raw=(root/record['src'].lstrip('/')).read_bytes()
                digest=hashlib.sha256(raw).hexdigest()
                if policy['unchanged_legacy_assets'].get(record['src']) == digest:
                    continue
                self.assertGreaterEqual(record['width'],640)
                self.assertGreaterEqual(record['height'],650)
                self.assertEqual(record.get('quality_standard'),policy['version'])
                self.assertEqual(record.get('asset_sha256'),digest)
                self.assertEqual(raw[:4],b'RIFF')
                self.assertEqual(raw[8:12],b'WEBP')
                self.assertEqual(int.from_bytes(raw[4:8],'little')+8,len(raw))
                offset=12
                dimensions=None
                while offset+8<=len(raw):
                    tag=raw[offset:offset+4]
                    size=int.from_bytes(raw[offset+4:offset+8],'little')
                    payload=raw[offset+8:offset+8+size]
                    self.assertEqual(len(payload),size)
                    if tag==b'VP8X':
                        self.assertGreaterEqual(len(payload),10)
                        self.assertTrue(payload[0]&16,'Native alpha required')
                        dimensions=(int.from_bytes(payload[4:7],'little')+1,int.from_bytes(payload[7:10],'little')+1)
                    offset+=8+size+(size%2)
                self.assertEqual(dimensions,(record['width'],record['height']))

if __name__=='__main__':
    unittest.main()
