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


if __name__ == '__main__':
    unittest.main()
