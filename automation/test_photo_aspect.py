"""Every /news/ article photo file is 16:9 (docs/EDITORIAL_STYLE.md, Photo shape).

The lead photo and every body photo must be a 16:9 landscape file, ratio
1.74 to 1.80, cropped with heads in frame. CSS cover alone is not enough: the
file itself is the shape. Screenshots and charts (figure.no-crop, .screenshot,
.chart, .stat-board) may be taller and are skipped. Decorative stat-card
backgrounds with alt="" are not article photos.

ALLOWLIST is for a photo-like graphic that has to keep its own shape. Keep it
short and say why.
"""
import re
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MIN_RATIO, MAX_RATIO = 1.74, 1.80
SKIP_CLASSES = {'no-crop', 'screenshot', 'chart', 'stat-board', 'card'}
# file name -> reason
ALLOWLIST = {}

FIGURE_RE = re.compile(r'<figure\b([^>]*)>(.*?)</figure>', re.S)
SRC_RE = re.compile(r'\bsrc="(/images/[^"?]+)')


def _ratio(rel):
    with Image.open(ROOT / rel.lstrip('/')) as im:
        w, h = im.size
    return w / h


class PhotoAspectTests(unittest.TestCase):
    def test_news_article_photos_are_16_9(self):
        bad = []
        for page in sorted((ROOT / 'news').glob('*/index.html')):
            html = page.read_text(encoding='utf-8')
            for attrs, inner in FIGURE_RE.findall(html):
                cls = re.search(r'class="([^"]*)"', attrs)
                classes = set(cls.group(1).split()) if cls else set()
                if classes & SKIP_CLASSES or not classes & {'lead-photo', 'body-photo'}:
                    continue
                for src in SRC_RE.findall(inner):
                    if src.rsplit('/', 1)[-1] in ALLOWLIST or src.startswith('/images/authors/'):
                        continue
                    if not (ROOT / src.lstrip('/')).exists():
                        continue
                    r = _ratio(src)
                    if not MIN_RATIO <= r <= MAX_RATIO:
                        bad.append(f'{page.parent.name}: {src} is {r:.3f}:1')
        self.assertEqual(bad, [], 'Crop these to 16:9 with heads in frame:\n' + '\n'.join(bad))

    def test_drop_in_article_photos_are_16_9(self):
        bad = []
        for photo in sorted((ROOT / 'content' / 'articles').glob('*/photo.*')):
            with Image.open(photo) as im:
                r = im.size[0] / im.size[1]
            if not MIN_RATIO <= r <= MAX_RATIO:
                bad.append(f'{photo.relative_to(ROOT)} is {r:.3f}:1')
        self.assertEqual(bad, [], '\n'.join(bad))


if __name__ == '__main__':
    unittest.main()
