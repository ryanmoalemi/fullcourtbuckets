"""The famous-relatives count in titles and meta comes from the data, never a hardcoded number."""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'automation'))
import seo_meta  # noqa: E402

PAGE = '/news/wnba-players-famous-relatives/'


def count() -> int:
    return len(json.loads((ROOT / 'data' / 'famous-relatives.json').read_text(encoding='utf-8'))['entries'])


class FamousRelativesCount(unittest.TestCase):
    def test_override_uses_token_not_number(self):
        raw = json.loads((ROOT / 'data' / 'seo-meta.json').read_text(encoding='utf-8'))[PAGE]
        for key, value in raw.items():
            if isinstance(value, str):
                self.assertNotRegex(value, r'\b\d+ WNBA players', f'{key} hardcodes the count; use {{famous_relatives}}')

    def test_token_fills_from_data(self):
        o = seo_meta.load_overrides(ROOT)[PAGE]
        self.assertTrue(o['title'].startswith(f'{count()} WNBA players'), o['title'])
        self.assertNotIn('{', o['title'])

    def test_fill_tokens_tracks_data(self):
        self.assertEqual(seo_meta.fill_tokens('{famous_relatives} x'), f'{count()} x')
        self.assertEqual(seo_meta.fill_tokens('{unknown} x'), '{unknown} x')

    def test_built_page_matches_data(self):
        html = (ROOT / PAGE.strip('/') / 'index.html').read_text(encoding='utf-8')
        n = count()
        title = re.search(r'<title>([^<]*)</title>', html).group(1)
        self.assertTrue(title.startswith(f'{n} '), title)
        for m in re.finditer(r'<meta (?:name|property)="(?:description|og:title|og:description|twitter:title)" content="([^"]*)"', html):
            for num in re.findall(r'\b(\d+) (?:famous relatives|WNBA players(?:\x27|&#x27;))', m.group(1)):
                self.assertEqual(int(num), n, m.group(0))
        article = next(a for a in json.loads((ROOT / 'articles.json').read_text(encoding='utf-8'))
                       if a.get('slug') == 'wnba-players-famous-relatives')
        for key in ('title', 'description', 'excerpt'):
            for num in re.findall(r'\b(\d+) (?:famous relatives|WNBA players(?:\x27|&#x27;))', str(article.get(key, ''))):
                self.assertEqual(int(num), n, key)


if __name__ == '__main__':
    unittest.main()
