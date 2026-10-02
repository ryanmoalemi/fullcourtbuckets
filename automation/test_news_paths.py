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

    def test_featured_story_has_a_lead_image(self):
        articles = sorted(_articles(), key=lambda article: article.get('date') or '', reverse=True)
        featured = articles[0]
        image = str(featured.get('image') or '').strip()
        alt = str(featured.get('imageAlt') or '').strip()
        self.assertTrue(image.startswith('/images/'), featured.get('slug'))
        self.assertTrue(alt, featured.get('slug'))
        photo = ROOT / image.lstrip('/')
        self.assertTrue(photo.is_file(), image)
        self.assertGreater(photo.stat().st_size, 1000, image)
        home = (ROOT / 'index.html').read_text(encoding='utf-8')
        hero = home.split('id="featured-story"', 1)[1].split('</a>', 1)[0]
        self.assertIn('id="featured-image"', hero)
        self.assertIn(f'src="{image}"', hero)
        self.assertIn(f'alt="{html.escape(alt, quote=True)}"', hero)
        self.assertIn('id="featured-credit"', hero)
        for article in articles:
            lead = str(article.get('image') or '').strip()
            self.assertTrue(lead.startswith('/images/'), article.get('slug'))
            self.assertTrue((ROOT / lead.lstrip('/')).is_file(), article.get('slug'))
        older = home.split('id="older-stories"', 1)[1].split('<!-- fcb-stories:end -->', 1)[0]
        for article in articles[1:]:
            card = older.split(f'href="{links.article_href(article)}"', 1)[1].split('</a>', 1)[0]
            self.assertIn(f'src="{article["image"]}"', card, article['slug'])
        bare = dict(featured)
        bare['image'] = ''
        bare['imageAlt'] = ''
        rendered = links._apply_featured_media(
            '<a class="feature feature-link" id="featured-story" href="/news/example/"><div class="feature-content"></div></a>',
            bare,
        )
        self.assertNotIn('id="featured-image"', rendered)

    def test_game_3_recap_is_linked_from_fever_and_aces(self):
        for slug in ('indiana-fever', 'las-vegas-aces'):
            page = (ROOT / 'wnba' / 'teams' / slug / 'index.html').read_text(encoding='utf-8')
            self.assertIn('href="/news/fever-aces-game-3-recap/"', page)
            self.assertNotIn('href="/news/fever-aces-game-3-recap/" target="_blank"', page)
        recap = (ROOT / 'news' / 'fever-aces-game-3-recap' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('https://www.espn.com/wnba/game/_/gameId/401918022', recap)
        self.assertIn('href="/wnba/aja-wilson/" target="_blank" rel="noopener"', recap)
        self.assertIn('href="/wnba/teams/las-vegas-aces/" target="_blank" rel="noopener"', recap)
        self.assertNotIn('\u2014', recap)

    def test_expansion_story_is_linked_from_both_team_pages(self):
        for slug in ('portland-fire', 'toronto-tempo'):
            page = (ROOT / 'wnba' / 'teams' / slug / 'index.html').read_text(encoding='utf-8')
            self.assertIn('href="/news/wnba-expansion-teams/"', page)
            self.assertNotIn('href="/news/wnba-expansion-teams/" target="_blank"', page)
        html_text = links.team_news_html(ROOT, 'portland-fire')
        self.assertIn('href="/news/wnba-expansion-teams/"', html_text)
        self.assertNotIn('target="_blank"', html_text)
        fever = links.team_news_html(ROOT, 'indiana-fever')
        self.assertIn('Latest stories', fever)
        self.assertIn('href="/news/fever-aces-game-2-recap/"', fever)
        self.assertNotIn('target="_blank"', fever)

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
