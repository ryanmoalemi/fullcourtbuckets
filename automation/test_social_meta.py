import re
import unittest
from pathlib import Path

import social_meta as sm

ROOT = Path(__file__).resolve().parents[1]


class SocialMetaTest(unittest.TestCase):
    def test_every_page_has_share_tags(self):
        missing = []
        for page in sm.pages(ROOT):
            text = page.read_text(encoding='utf-8', errors='replace')
            if '</head>' not in text or re.search(r'http-equiv="?refresh', text, re.I):
                continue
            for key in ('og:image', 'twitter:card', 'twitter:image'):
                if not sm._has(text, key):
                    missing.append(f'{page.relative_to(ROOT)} {key}')
        self.assertEqual(missing, [], missing[:20])

    def test_generated_cards_are_1200x630(self):
        from PIL import Image
        for path in [sm.DEFAULT_CARD, *sorted((sm.SOCIAL_DIR / 'players').glob('*.jpg'))[:25]]:
            with Image.open(path) as im:
                self.assertEqual(im.size, (1200, 630), path)

    def test_block_is_idempotent(self):
        html = '<html><head><title>x</title></head><body></body></html>'
        once = sm.social_block(html, 'https://fullcourtbuckets.com/a.jpg', 'alt', 1200, 630)
        self.assertEqual(sm.social_block(once, 'https://fullcourtbuckets.com/a.jpg', 'alt', 1200, 630), once)
        self.assertIn('twitter:card', once)

    def test_share_tags_sit_at_top_of_head(self):
        # X's card crawler only reads the start of the page: every og/twitter tag
        # must come before any <script>, <style> or JSON-LD, use absolute https
        # image URLs, appear once, and include twitter:site/title.
        bad = []
        for page in sm.pages(ROOT):
            text = page.read_text(encoding='utf-8', errors='replace')
            if '</head>' not in text or re.search(r'http-equiv="?refresh', text, re.I):
                continue
            head = text.split('</head>', 1)[0]
            rel = page.relative_to(ROOT)
            first = min([i for i in (head.find('<script'), head.find('<style'), head.find('<link')) if i >= 0] or [len(head)])
            tags = [(m.start(), m.group(0)) for m in sm.SOCIAL_TAG_RE.finditer(head)]
            if not tags or tags[-1][0] > first or tags[-1][0] > 4096:
                bad.append(f'{rel} social tags not at top of <head>')
            keys = [sm._key(t) for _, t in tags]
            for k in set(keys):
                if keys.count(k) > 1 and not k.startswith('og:image'):
                    bad.append(f'{rel} duplicate {k}')
            for k in ('twitter:site', 'twitter:title', 'twitter:card', 'twitter:image', 'og:image'):
                if k not in keys:
                    bad.append(f'{rel} missing {k}')
            for _, t in tags:
                if sm._key(t) in ('og:image', 'twitter:image') and not sm._content(t).startswith('https://'):
                    bad.append(f'{rel} relative image {sm._content(t)}')
        self.assertEqual(bad, [], bad[:20])

    def test_block_moves_late_tags_to_top(self):
        html = ('<html><head><meta charset="utf-8"><script>x()</script><style>a{}</style>'
                '<meta property="og:title" content="T"><meta property="og:image" content="https://fullcourtbuckets.com/a.jpg">'
                '<meta property="og:title" content="T2"></head><body></body></html>')
        out = sm.social_block(html, 'https://fullcourtbuckets.com/b.jpg', 'alt', 1200, 630)
        self.assertLess(out.find('og:image'), out.find('<script'))
        self.assertEqual(out.count('property="og:title"'), 1)
        self.assertIn('name="twitter:title" content="T"', out)
        self.assertIn('name="twitter:site" content="@fullcourtbucket"', out)
        self.assertIn('name="twitter:image" content="https://fullcourtbuckets.com/a.jpg"', out)


if __name__ == '__main__':
    unittest.main()
