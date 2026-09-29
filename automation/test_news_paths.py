"""Posts live at /news/<slug>/. Root post URLs are redirect stubs, not links."""
import html
import json
import re
import unittest
from pathlib import Path

import internal_links as links
from link_graph import iter_html

ROOT = Path(__file__).resolve().parents[1]
SCAN_SUFFIXES = {'.html', '.xml', '.js'}


def _articles():
    return json.loads((ROOT / 'articles.json').read_text(encoding='utf-8'))


class NewsPathTests(unittest.TestCase):
    def test_every_article_resolves_under_news(self):
        articles = _articles()
        self.assertGreaterEqual(len(articles), 1)
        for article in articles:
            href = links.article_href(article)
            slug = article['slug']
            self.assertEqual(href, f'/news/{slug}/')
            self.assertEqual(article.get('url'), href)
            self.assertNotIn('/', slug)
            page = ROOT / 'news' / slug / 'index.html'
            self.assertTrue(page.is_file(), href)
            html = page.read_text(encoding='utf-8')
            absolute = 'https://fullcourtbuckets.com' + href
            self.assertIn(f'rel="canonical" href="{absolute}"', html)
            self.assertIn(f'property="og:url" content="{absolute}"', html)
            self.assertIn('"@type": "BreadcrumbList"', html)
            self.assertIn('"name": "Home"', html)
            self.assertIn('"name": "News"', html)
            self.assertIn(absolute, html)
            self.assertIn('>Home</a>', html)
            self.assertIn('>News</a>', html)
            data = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
            node = links._article_node(data)
            self.assertIsNotNone(node, slug)
            self.assertEqual(node['url'], absolute)
            self.assertEqual(node['mainEntityOfPage']['@id'], absolute)

    def test_news_hub_lists_every_post_newest_first(self):
        hub = (ROOT / 'news' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('<h1>WNBA news</h1>', hub)
        self.assertIn('CollectionPage', hub)
        self.assertIn('ItemList', hub)
        self.assertIn('BreadcrumbList', hub)
        self.assertIn('rel="canonical" href="https://fullcourtbuckets.com/news/"', hub)
        ordered = sorted(_articles(), key=lambda article: article.get('date') or '', reverse=True)
        for name in ('sitemap.xml', 'pages-sitemap.xml'):
            sitemap = (ROOT / name).read_text(encoding='utf-8')
            self.assertRegex(sitemap, r'<loc>\s*https://fullcourtbuckets\.com/news/\s*</loc>')
            for article in ordered:
                self.assertIn('https://fullcourtbuckets.com' + links.article_href(article), sitemap)
        positions = []
        for article in ordered:
            href = links.article_href(article)
            self.assertIn(f'href="{href}"', hub)
            self.assertIn(html.escape(article['title']), hub)
            self.assertIn(html.escape(article['description']), hub)
            self.assertIn(article['date'], hub)
            if article.get('image'):
                self.assertIn(article['image'], hub)
            positions.append(hub.find(href))
        self.assertEqual(positions, sorted(positions))

    def test_old_root_urls_are_stubs_and_not_linked(self):
        articles = _articles()
        pattern = links.legacy_post_link_pattern(articles)
        offenders = []
        for path in iter_html(ROOT):
            text = path.read_text(encoding='utf-8', errors='replace')
            if pattern.search(text):
                offenders.append(path.relative_to(ROOT).as_posix())
        for name in ('sitemap.xml', 'pages-sitemap.xml', 'player-sitemap.xml', 'articles.json', 'index.html'):
            text = (ROOT / name).read_text(encoding='utf-8', errors='replace')
            if pattern.search(text):
                offenders.append(name)
        self.assertEqual(offenders, [])
        self.assertNotIn('"/" + featured.slug + "/"', (ROOT / 'index.html').read_text(encoding='utf-8'))
        self.assertNotIn('"/" + a.slug + "/"', (ROOT / 'index.html').read_text(encoding='utf-8'))
        for article in articles:
            stub = (ROOT / article['slug'] / 'index.html').read_text(encoding='utf-8')
            target = 'https://fullcourtbuckets.com' + links.article_href(article)
            self.assertIn('http-equiv="refresh" content="0; url=' + target + '"', stub)
            self.assertIn(f'rel="canonical" href="{target}"', stub)
            self.assertIn('content="noindex"', stub)
            self.assertIn(f'location.replace("{target}")', stub)
            self.assertIsNone(pattern.search(stub), article['slug'])
