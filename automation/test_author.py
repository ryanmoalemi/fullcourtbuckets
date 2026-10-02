"""Ryan Moalemi is the author of every news post, including ones generated later."""
import json
import re
import tempfile
import unittest
from pathlib import Path

import internal_links as links
import site_nav

ROOT = Path(__file__).resolve().parents[1]
AUTHOR = {
    '@type': 'Person',
    'name': 'Ryan Moalemi',
    'url': 'https://fullcourtbuckets.com/authors/ryan-moalemi/',
}


def _articles():
    return json.loads((ROOT / 'articles.json').read_text(encoding='utf-8'))


def _ld_nodes(html: str):
    nodes = []
    for raw in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        nodes.append(json.loads(raw))
    return nodes


def _person(nodes):
    found = []

    def walk(node):
        if isinstance(node, dict):
            kind = node.get('@type')
            names = kind if isinstance(kind, list) else [kind]
            if 'Person' in names:
                found.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for node in nodes:
        walk(node)
    return found


class AuthorPageTests(unittest.TestCase):
    def test_author_page_bio_list_and_sitemap(self):
        page = (ROOT / 'authors' / 'ryan-moalemi' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('<h1>Ryan Moalemi</h1>', page)
        self.assertIn('src="/images/authors/ryan-moalemi.jpg', page)
        self.assertIn('alt="Ryan Moalemi"', page)
        self.assertIn('width="320"', page)
        self.assertIn('height="320"', page)
        self.assertIn('writing internet content since 2001', page)
        self.assertIn('started sports writing in 2026', page)
        self.assertIn('Angel Reese', page)
        self.assertIn('href="/wnba/angel-reese/">Angel Reese</a>', page)
        self.assertNotIn('href="/wnba/angel-reese/" target="_blank"', page)
        self.assertIn('positive effect the league is having on women', page)
        self.assertIn('bring new eyes to the movement', page)
        self.assertIn('runs Full Court Buckets', page)
        self.assertIn('<!-- TODO: add a LinkedIn sameAs link for Ryan Moalemi', page)
        bio_end = page.find('bring new eyes to the movement')
        tiktok_at = page.find('href="https://www.tiktok.com/@fullcourtbuckets" target="_blank" rel="noopener me"')
        self.assertGreater(bio_end, 0)
        self.assertGreater(tiktok_at, bio_end)
        self.assertNotIn('longer bio', page.casefold())
        self.assertNotIn('\u2014', page)
        self.assertIn('rel="canonical" href="https://fullcourtbuckets.com/authors/ryan-moalemi/"', page)
        self.assertIn('<meta name="author" content="Ryan Moalemi">', page)
        self.assertIn('>Home</a>', page)
        self.assertIn('>Authors</span>', page)
        self.assertIn('<h2>Stories</h2>', page)
        self.assertIn('href="/how-we-make-full-court-buckets/">How we make Full Court Buckets</a>', page)
        self.assertNotIn('href="/how-we-make-full-court-buckets/" target="_blank"', page)
        persons = _person(_ld_nodes(page))
        self.assertTrue(persons)
        profile = persons[0]
        self.assertEqual(profile['name'], 'Ryan Moalemi')
        self.assertEqual(profile['url'], AUTHOR['url'])
        self.assertEqual(profile['image'], links.AUTHOR_IMAGE_URL)
        self.assertIn(links.AUTHOR_PHOTO, profile['image'])
        self.assertEqual(profile['jobTitle'], 'Editor')
        self.assertIn('since 2001', profile['description'])
        self.assertIn('Full Court Buckets', profile['worksFor']['name'])
        self.assertNotIn('sameAs', profile)
        ordered = sorted(_articles(), key=lambda article: article.get('date') or '', reverse=True)
        positions = []
        for article in ordered:
            href = links.article_href(article)
            self.assertIn(f'href="{href}"', page)
            self.assertNotIn(f'href="{href}" target="_blank"', page)
            positions.append(page.find(href))
        self.assertEqual(positions, sorted(positions))
        about = (ROOT / 'about' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('href="/authors/ryan-moalemi/"', about)
        self.assertNotIn('href="/authors/ryan-moalemi/" target="_blank"', about)
        self.assertIn('TODO: owner, add the editor', about)
        self.assertIn('runs Full Court Buckets. He comes up with the stories, edits every one, and uses AI tools to help draft them.', about)
        self.assertIn('href="/how-we-make-full-court-buckets/">Here\'s how that works.</a>', about)
        self.assertNotIn('writes the news and game recaps.', about)
        menu = site_nav.render(site_nav.build_menu(ROOT), '/__none__')
        self.assertNotIn('/authors/', menu)
        self.assertIn('<li><a href="/news/">News</a></li>', menu)
        self.assertNotIn('site-nav-sub-news', menu)
        for name in ('sitemap.xml', 'pages-sitemap.xml'):
            sitemap = (ROOT / name).read_text(encoding='utf-8')
            self.assertIn('https://fullcourtbuckets.com/authors/ryan-moalemi/', sitemap)
        photo = ROOT / 'images' / 'authors' / 'ryan-moalemi.jpg'
        self.assertTrue(photo.is_file())
        self.assertGreater(photo.stat().st_size, 1000)

    def test_every_news_article_has_byline_and_person_author(self):
        articles = _articles()
        self.assertGreaterEqual(len(articles), 1)
        for article in articles:
            html = (ROOT / 'news' / article['slug'] / 'index.html').read_text(encoding='utf-8')
            self.assertIn(links.BYLINE_HTML, html, article['slug'])
            self.assertIn('<meta name="author" content="Ryan Moalemi">', html, article['slug'])
            self.assertNotIn('class="byline" href="/authors/ryan-moalemi/" target="_blank"', html, article['slug'])
            self.assertNotIn('\u2014', html, article['slug'])
            node = None
            for data in _ld_nodes(html):
                node = links._article_node(data)
                if node is not None:
                    break
            self.assertIsNotNone(node, article['slug'])
            self.assertEqual(node['author'], AUTHOR, article['slug'])
            self.assertEqual(node['publisher']['@type'], 'Organization', article['slug'])
            self.assertEqual(node['publisher']['name'], 'Full Court Buckets', article['slug'])
            expected = links.HOW_MADE_RECAP if links.story_uses_box_score(html, article) else links.HOW_MADE_OTHER
            self.assertIn(expected, html, article['slug'])
            self.assertEqual(html.count('class="how-made"'), 1, article['slug'])

    def test_generator_adds_byline_to_a_new_post(self):
        slug = 'future-recap'
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
<body><article class="article"><h1>Future Recap</h1><p class="deck">Later.</p></article></body></html>
'''
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'news' / slug).mkdir(parents=True)
            (root / 'news' / slug / 'index.html').write_text(bare, encoding='utf-8')
            (root / 'articles.json').write_text(json.dumps([article]), encoding='utf-8')
            html = links.prepare_article_page(root, article, [article])
            self.assertIn(links.BYLINE_HTML, html)
            self.assertIn(links.HOW_MADE_OTHER, html)
            self.assertIn('<meta name="author" content="Ryan Moalemi">', html)
            node = links._article_node(_ld_nodes(html)[0])
            self.assertEqual(node['author'], AUTHOR)
            self.assertEqual(node['publisher']['name'], 'Full Court Buckets')
            again = links.ensure_byline(links.ensure_author_meta(html))
            self.assertEqual(again.count('class="byline"'), 1)
            self.assertEqual(again.count('name="author"'), 1)
            page = links.render_author_page([article])
            self.assertIn('<h1>Ryan Moalemi</h1>', page)
            self.assertIn('href="/news/future-recap/"', page)
            self.assertIn('since 2001', page)
            self.assertIn(links.AUTHOR_TIKTOK_HTML, page)
            self.assertNotIn('sameAs', links.author_person())
            self.assertNotIn('\u2014', page)
