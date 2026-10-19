"""Every photo in every /news/ post is a true 16:9 file and renders 16:9.

Ryan, Oct 19, 2026: "all photos in all posts should be 16:9." No exemptions:
lead, body, screenshots, charts, cards. Photos are cropped with heads in
frame (automation/crop_16x9.py); charts, screenshots and cards are padded
with --pad so nothing is cut. Every srcset variant counts. og:image social
cards (1.91:1) are not post photos. Author bylines and table headshots
(not in a <figure>) are not post photos either.
"""
import re
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MIN_RATIO, MAX_RATIO = 1.74, 1.80

FIGURE_RE = re.compile(r'<figure\b([^>]*)>(.*?)</figure>', re.S)
URL_RE = re.compile(r'\b(?:src|srcset)="([^"]+)"')


def _files(inner):
    for value in URL_RE.findall(inner):
        for part in value.split(','):
            src = part.strip().split(' ')[0].split('?')[0]
            if src.startswith('/') and not src.startswith('/images/authors/'):
                yield src


def _ratio(rel):
    with Image.open(ROOT / rel.lstrip('/')) as im:
        w, h = im.size
    return w / h


class PhotoAspectTests(unittest.TestCase):
    def test_news_article_photos_are_16_9(self):
        bad, seen = [], 0
        for page in sorted((ROOT / 'news').glob('*/index.html')):
            html = page.read_text(encoding='utf-8')
            for _attrs, inner in FIGURE_RE.findall(html):
                for src in _files(inner):
                    path = ROOT / src.lstrip('/')
                    if not path.exists():
                        continue
                    seen += 1
                    r = _ratio(src)
                    if not MIN_RATIO <= r <= MAX_RATIO:
                        bad.append(f'{page.parent.name}: {src} is {r:.3f}:1')
        self.assertGreater(seen, 100)
        self.assertEqual(bad, [], 'Crop (photos) or --pad (charts) to 16:9 with automation/crop_16x9.py:\n' + '\n'.join(bad))

    def test_publisher_rejects_non_16_9(self):
        src = (ROOT / 'automation' / 'publish_articles.py').read_text(encoding='utf-8')
        self.assertIn('it must be 16:9', src)

    def test_drop_in_article_photos_are_16_9(self):
        bad = []
        for photo in sorted((ROOT / 'content' / 'articles').glob('*/photo.*')):
            with Image.open(photo) as im:
                r = im.size[0] / im.size[1]
            if not MIN_RATIO <= r <= MAX_RATIO:
                bad.append(f'{photo.relative_to(ROOT)} is {r:.3f}:1')
        self.assertEqual(bad, [], '\n'.join(bad))


SRCSET_RE = re.compile(r'\bsrcset="([^"]+)"')
# Story-card photo slots that show article photos outside the article.
CARD_SELECTORS = ('.article-visual img', '.news-item img', '.team-news-item img')
CARD_RULE_RE = re.compile(r'aspect-ratio:16/9!important;height:auto!important')


class PhotoSlotTests(unittest.TestCase):
    """The file being 16:9 is not enough; every slot must render it 16:9.

    Oct 19, 2026: the Game 2 preview hero was a 1200x675 file but the homepage
    lead card stretched it to 365x494 (0.74:1) and /news/ cut it to 3:2. The
    file-only test above never looked at card slots or rendered size.
    """

    def test_shared_css_forces_16_9_card_slots(self):
        css = (ROOT / 'automation' / 'site_nav.css').read_text(encoding='utf-8')
        for sel in CARD_SELECTORS:
            rule = re.search(r'([^{}]*' + re.escape(sel) + r'[^{}]*)\{([^}]*)\}', css)
            ok = any(sel in m.group(1) and CARD_RULE_RE.search(m.group(2))
                     for m in re.finditer(r'([^{}]*)\{([^}]*)\}', css))
            self.assertTrue(ok, f'site_nav.css must force 16:9 on {sel}')

    def test_rendered_photo_slots_are_16_9(self):
        """Render key pages at 1280 and 390 and measure every photo slot."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest('playwright not installed')
        import functools, http.server, os, shutil, threading
        chrome = shutil.which('google-chrome') or shutil.which('chromium')
        if not chrome:
            self.skipTest('no chrome')
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
        handler.log_message = lambda *a: None
        srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{srv.server_address[1]}'
        pages = ['/', '/news/'] + sorted(
            '/news/' + p.parent.name + '/' for p in (ROOT / 'news').glob('*/index.html')
            if 'http-equiv="refresh"' not in p.read_text(encoding='utf-8'))  # redirects leave the repo
        sel = ','.join(CARD_SELECTORS + ('.article figure img',))
        js = ("s=>[...document.querySelectorAll(s)].map(i=>{const b=i.getBoundingClientRect();"
              "return [i.getAttribute('src'),b.width,b.height]}).filter(x=>x[1]>40&&x[2]>0)")
        bad = []
        try:
            with sync_playwright() as p:
                b = p.chromium.launch(executable_path=chrome)
                for w in (1280, 390):
                    pg = b.new_page(viewport={'width': w, 'height': 900})
                    for path in pages:
                        pg.goto(base + path, wait_until='load')
                        for src, bw, bh in pg.evaluate(js, sel):
                            r = bw / bh
                            if not 1.70 <= r <= 1.85:
                                bad.append(f'{path} @{w}: {src} renders {bw:.0f}x{bh:.0f} ({r:.2f}:1)')
                b.close()
        finally:
            srv.shutdown()
        self.assertEqual(bad, [], 'Photo slots must render 16:9:\n' + '\n'.join(bad[:40]))


if __name__ == '__main__':
    unittest.main()
