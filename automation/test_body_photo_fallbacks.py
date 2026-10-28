"""Every in-body !photo: <picture> must point at files that exist: webp source and jpg fallback."""
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'automation'))
import publish_articles as pa  # noqa: E402

PICTURE_RE = re.compile(r'<figure class="inline-photo body-photo"><picture>(.*?)</picture>', re.S)
URL_RE = re.compile(r'(?:srcset|src)="(/images/[^"\s]+)"')


class BodyPhotoFallbacks(unittest.TestCase):
    def test_built_pages_reference_existing_files(self):
        for page in (ROOT / 'news').glob('*/index.html'):
            for block in PICTURE_RE.findall(page.read_text(encoding='utf-8')):
                for url in URL_RE.findall(block):
                    self.assertTrue((ROOT / url.lstrip('/')).is_file(), f'{page}: {url} missing')

    def test_missing_jpg_is_built_from_webp(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'images').mkdir()
            Image.new('RGB', (16, 9)).save(root / 'images/x.webp', 'WEBP')
            pa.ensure_body_photo_files('/images/x.jpg', '/images/x.webp', root)
            self.assertTrue((root / 'images/x.jpg').is_file())

    def test_missing_both_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                pa.ensure_body_photo_files('/images/y.jpg', '/images/y.webp', Path(tmp))


if __name__ == '__main__':
    unittest.main()
