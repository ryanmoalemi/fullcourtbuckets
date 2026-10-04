"""The lead photo sits under the headline and above the byline and hook."""
import json
import re
import tempfile
import unittest
from pathlib import Path

import internal_links as links

ROOT = Path(__file__).resolve().parents[1]


def _articles():
    return json.loads((ROOT / 'articles.json').read_text(encoding='utf-8'))


def _lead_figure(html: str) -> str:
    match = re.search(r'<figure\b[^>]*class="[^"]*\blead-photo\b[^"]*"[^>]*>.*?</figure>', html, re.S)
    return match.group(0) if match else ''


class NewsLeadTests(unittest.TestCase):
    def test_published_stories_show_the_photo_before_the_hook(self):
        for article in _articles():
            html = (ROOT / 'news' / article['slug'] / 'index.html').read_text(encoding='utf-8')
            figure = _lead_figure(html)
            self.assertTrue(figure, article['slug'])
            photo = html.find(figure)
            h1 = html.find('</h1>')
            byline = html.find('class="byline"')
            hook = html.find('class="lead"')
            if hook < 0 or hook < byline:
                hook = html.find('class="deck"')
            self.assertLess(h1, photo, article['slug'])
            self.assertLess(photo, byline, article['slug'])
            self.assertLess(byline, hook, article['slug'])
            img = re.search(r'<img\b[^>]*>', figure).group(0)
            self.assertIn('fetchpriority="high"', img, article['slug'])
            self.assertNotIn('loading=', img, article['slug'])
            self.assertIn('width="', img, article['slug'])
            self.assertIn('height="', img, article['slug'])
            self.assertIn('object-position:', img, article['slug'])
            self.assertRegex(img, r'/hero-(?:1200|16x9)\.webp', article['slug'])
            width = int(re.search(r'width="(\d+)"', img).group(1))
            height = int(re.search(r'height="(\d+)"', img).group(1))
            self.assertAlmostEqual(width / height, 16 / 9, places=2, msg=article['slug'])
            self.assertIn('aspect-ratio:16/9', html, article['slug'])
            self.assertIn('object-fit:cover', html, article['slug'])
            self.assertNotIn('100vw', html, article['slug'])
            if str(article.get('imageCredit') or '').strip():
                self.assertIn('<figcaption', figure, article['slug'])
            self.assertIn('class="article-date"', html, article['slug'])
            self.assertEqual(len(re.findall(r'<figure\b[^>]*\blead-photo\b', html)), 1, article['slug'])

    def test_generator_moves_a_late_photo_under_the_headline(self):
        slug = 'future-photo'
        article = {
            'slug': slug,
            'url': f'/news/{slug}/',
            'title': 'Future Recap',
            'description': 'A later game recap.',
            'date': '2026-10-02',
            'category': 'WNBA',
        }
        bare = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Future Recap</title>
<style>.article h1{margin:0}</style></head>
<body><article class="article"><div class="meta-row"><span class="cat">WNBA</span><span class="divider"></span><span>October 2, 2026</span></div><h1>Future Recap</h1><p class="lead">Later.</p><figure><img src="/images/articles/future.webp" alt="A player" width="1200" height="800" loading="lazy"></figure></article></body></html>
'''
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'news' / slug).mkdir(parents=True)
            (root / 'news' / slug / 'index.html').write_text(bare, encoding='utf-8')
            (root / 'articles.json').write_text(json.dumps([article]), encoding='utf-8')
            html = links.prepare_article_page(root, article, [article])
            again = links.order_news_lead(html)
            self.assertEqual(len(re.findall(r'<figure\b[^>]*\blead-photo\b', again)), 1)
            self.assertEqual(again.count('class="byline"'), 1)
            self.assertEqual(again.count('class="article-date"'), 1)
            figure = _lead_figure(again)
            photo = again.find(figure)
            self.assertLess(again.find('</h1>'), photo)
            self.assertLess(photo, again.find('class="byline"'))
            self.assertLess(again.find('class="byline"'), again.find('class="lead"'))
            img = re.search(r'<img\b[^>]*>', figure).group(0)
            self.assertIn('fetchpriority="high"', img)
            self.assertNotIn('loading=', img)
            self.assertIn('width="1200"', img)
            self.assertIn('height="800"', img)
            self.assertIn('object-position:center 25%', img)
            self.assertIn('aspect-ratio:16/9', again)
            self.assertIn('object-fit:cover', again)
            self.assertNotIn('100vw', again)
            self.assertIn('datetime="2026-10-02"', again)
            self.assertNotIn('>October 2, 2026</span>', again)

    def test_focal_point_is_written_on_the_lead(self):
        slug = 'future-photo'
        article = {
            'slug': slug,
            'url': f'/news/{slug}/',
            'title': 'Future Recap',
            'description': 'A later game recap.',
            'date': '2026-10-02',
            'category': 'WNBA',
            'imageFocal': 'center 12%',
            'imageHero': '/images/articles/future/hero-1200.webp',
            'imageHeroWidth': 1200,
            'imageHeroHeight': 675,
            'imageHero2x': '/images/articles/future/hero-2x.webp',
            'imageHero2xWidth': 1680,
        }
        bare = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Future Recap</title>
<style>.article h1{margin:0}</style></head>
<body><article class="article"><h1>Future Recap</h1><p class="lead">Later.</p><figure><img src="/images/articles/future.webp" alt="A player" width="900" height="1400" loading="lazy"></figure></article></body></html>
'''
        html = links.order_news_lead(bare, article)
        img = re.search(r'<img\b[^>]*>', _lead_figure(html)).group(0)
        self.assertIn('src="/images/articles/future/hero-1200.webp"', img)
        self.assertIn('width="1200"', img)
        self.assertIn('height="675"', img)
        self.assertIn('object-position:center 12%', img)
        self.assertIn('hero-2x.webp 1680w', img)
        self.assertIn('fetchpriority="high"', img)
        self.assertNotIn('loading=', img)
