"""The legacy exception must not excuse corrupt files or incorrect approvals."""
import hashlib
import io
import unittest
from PIL import Image
from verify_portraits import VerificationError, decode_asset, normal_name

class VerifyPortraitTests(unittest.TestCase):
    def sample(self, size=(640,650)):
        im=Image.new('RGBA',size,(150,90,60,255)); im.putpixel((0,0),(0,0,0,0))
        out=io.BytesIO(); im.save(out,format='WEBP',lossless=True)
        raw=out.getvalue()
        return raw,{'src':'/images/players/example-player-approved.webp','width':size[0],'height':size[1],
                    'asset_sha256':hashlib.sha256(raw).hexdigest(),
                    'export_settings':{'upscaled':False,'source_width':1254,'source_height':1254}}
    def test_valid_real_transparency(self):
        raw,record=self.sample()
        self.assertEqual(decode_asset(raw,record,{})['width'],640)
    def test_corrupt_legacy_is_rejected(self):
        raw=b'not an image'; digest=hashlib.sha256(raw).hexdigest()
        record={'src':'/images/players/old.webp','asset_sha256':digest,'width':480,'height':480}
        with self.assertRaises(VerificationError): decode_asset(raw,record,{record['src']:digest})
    def test_wrong_approved_hash(self):
        raw,record=self.sample(); record['asset_sha256']='0'*64
        with self.assertRaises(VerificationError): decode_asset(raw,record,{})
    def test_dimension_claim_does_not_override_file(self):
        raw,record=self.sample((192,192)); record.update(width=640,height=650)
        with self.assertRaises(VerificationError): decode_asset(raw,record,{})
    def test_new_thumbnail_rejected(self):
        raw,record=self.sample((192,192))
        with self.assertRaises(VerificationError): decode_asset(raw,record,{})
    def test_native_dimensions_legacy_only(self):
        raw,record=self.sample((192,192))
        self.assertTrue(decode_asset(raw,record,{record['src']:record['asset_sha256']})['legacy_resolution'])
    def test_upscaled_master_rejected(self):
        raw,record=self.sample(); record['export_settings']['upscaled']=True
        with self.assertRaises(VerificationError): decode_asset(raw,record,{})
    def test_name_normalization(self):
        self.assertEqual(normal_name("A’JA\nWILSON"),normal_name("A'ja Wilson"))

if __name__=='__main__':unittest.main()
