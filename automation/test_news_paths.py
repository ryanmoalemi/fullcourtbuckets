"""Posts live at /news/<slug>/. Root post URLs are redirect stubs, not links."""
import hashlib
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


def _section(page: str, section_id: str) -> str:
    match = re.search(rf'<section\b[^>]*\bid="{section_id}"[^>]*>.*?</section>', page, re.S)
    if match is None:
        raise AssertionError(f'missing section {section_id}')
    return match.group(0)


def _is_lead_image(image: str) -> bool:
    """Shared story photos live in /images/. This collecting story keeps its cards beside the article."""
    return image.startswith('/images/') or image.startswith('/news/')


# Ryan decided to keep both listing photos. They are the same bytes
# (sha256 9a25b2a9...), so the cards and article["image"] paths show one photo
# twice:
#   images/articles/aces-valkyries-semis-game-2-recap/veronica-burton-valkyries.webp
#   images/articles/wings-valkyries-game-3-recap/veronica-burton-valkyries-2025.webp
# Do not swap either photo or change either article's copy. The in-article lead
# crops (each story's hero-1200.webp) are different files and are not part of
# this exception. Any other shared file still fails.
KNOWN_DUPLICATE_PHOTO_PAIRS = {
    frozenset({'aces-valkyries-semis-game-2-recap', 'wings-valkyries-game-3-recap'}),
}


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
        sitemap = (ROOT / 'pages-sitemap.xml').read_text(encoding='utf-8')
        index = (ROOT / 'sitemap.xml').read_text(encoding='utf-8')
        self.assertIn('https://fullcourtbuckets.com/pages-sitemap.xml', index)
        self.assertNotIn('<urlset', index)
        self.assertRegex(sitemap, r'<loc>\s*https://fullcourtbuckets\.com/news/\s*</loc>')
        for article in ordered:
            loc = 'https://fullcourtbuckets.com' + links.article_href(article)
            self.assertIn(loc, sitemap)
            self.assertNotIn(loc, index)
        positions = []
        for article in ordered:
            href = links.article_href(article)
            self.assertIn(f'href="{href}"', hub)
            visible_hub = html.unescape(re.sub(r'<[^>]+>', '', hub))
            self.assertIn(article['title'].replace('\u2019', "'"), visible_hub.replace('\u2019', "'"))
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
        self.assertTrue(_is_lead_image(image), featured.get('slug'))
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
            self.assertTrue(_is_lead_image(lead), article.get('slug'))
            self.assertTrue((ROOT / lead.lstrip('/')).is_file(), article.get('slug'))
        older = home.split('id="older-stories"', 1)[1].split('<!-- fcb-stories:end -->', 1)[0]
        shown = articles[1:1 + links.MORE_STORY_LIMIT]
        self.assertIn('class="all-news" href="/news/">All news</a>', home)
        self.assertLess(home.find('id="site-hubs"'), home.find('id="more-stories"'))
        self.assertGreaterEqual(older.count('article-card is-compact'), 1)
        for article in shown:
            card = older.split(f'href="{links.article_href(article)}"', 1)[1].split('</a>', 1)[0]
            self.assertIn(f'src="{article["image"]}"', card, article['slug'])
        for article in articles[1 + links.MORE_STORY_LIMIT:]:
            self.assertNotIn(f'href="{links.article_href(article)}"', older, article['slug'])
        bare = dict(featured)
        bare['image'] = ''
        bare['imageAlt'] = ''
        rendered = links._apply_featured_media(
            '<a class="feature feature-link" id="featured-story" href="/news/example/"><div class="feature-content"></div></a>',
            bare,
        )
        self.assertNotIn('id="featured-image"', rendered)

    def test_articles_do_not_share_a_lead_image(self):
        articles = _articles()
        paths = {}
        hashes = {}
        for article in articles:
            image = str(article.get('image') or '').strip()
            slug = article.get('slug')
            self.assertTrue(_is_lead_image(image), slug)
            self.assertNotIn(image, paths, f'{slug} reuses the lead path from {paths.get(image)}')
            paths[image] = slug
            photo = ROOT / image.lstrip('/')
            digest = hashlib.sha256(photo.read_bytes()).hexdigest()
            prior = hashes.get(digest)
            if prior is not None and frozenset({slug, prior}) in KNOWN_DUPLICATE_PHOTO_PAIRS:
                continue
            self.assertNotIn(digest, hashes, f'{slug} reuses the photo file from {prior}')
            hashes[digest] = slug
        by_slug = {article['slug']: article for article in articles}
        game_1_article = by_slug['liberty-lynx-game-1-full-recap']
        game_1 = game_1_article['image']
        sweep = by_slug['liberty-lynx-game-2-recap']['image']
        self.assertIn('breanna-stewart', game_1)
        self.assertIn('marine-johannes', sweep)
        self.assertNotEqual(game_1, sweep)
        # The listing image stays the original Stewart file. The article lead is the 16:9 crop of it.
        self.assertEqual(game_1_article.get('imageSource'), game_1)
        page = (ROOT / 'news' / 'liberty-lynx-game-1-full-recap' / 'index.html').read_text(encoding='utf-8')
        self.assertIn(game_1_article['imageHero'], page)
        self.assertIn('CC BY-SA 4.0', page)
        self.assertNotIn('\u2014', page)

    def test_game_3_recap_is_linked_from_fever_and_aces(self):
        for slug in ('indiana-fever', 'las-vegas-aces'):
            page = (ROOT / 'wnba' / 'teams' / slug / 'index.html').read_text(encoding='utf-8')
            self.assertIn('href="/news/fever-aces-game-3-recap/"', page)
            news = _section(page, 'team-news')
            self.assertIn('href="/news/fever-aces-game-3-recap/"', news)
            self.assertNotIn('target="_blank"', news)
        recap = (ROOT / 'news' / 'fever-aces-game-3-recap' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('https://www.espn.com/wnba/game/_/gameId/401918022', recap)
        self.assertIn('href="/wnba/aja-wilson/" target="_blank" rel="noopener"', recap)
        self.assertIn('href="/wnba/teams/las-vegas-aces/" target="_blank" rel="noopener"', recap)
        self.assertNotIn('\u2014', recap)

    def test_expansion_story_is_linked_from_both_team_pages(self):
        for slug in ('portland-fire', 'toronto-tempo'):
            page = (ROOT / 'wnba' / 'teams' / slug / 'index.html').read_text(encoding='utf-8')
            self.assertIn('href="/news/wnba-expansion-teams/"', page)
            news = _section(page, 'team-news')
            self.assertIn('href="/news/wnba-expansion-teams/"', news)
            self.assertNotIn('target="_blank"', news)
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

    def test_duplicate_liberty_lynx_game_1_redirects_to_the_full_recap(self):
        kept = (ROOT / 'news' / 'liberty-lynx-game-1-full-recap' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('Ionescu assisted Stewart five times', kept)
        self.assertIn('2024 WNBA Finals', kept)
        self.assertNotIn('liberty-lynx-game-1-ionescu-stewart', kept)
        target = 'https://fullcourtbuckets.com/news/liberty-lynx-game-1-full-recap/'
        for relative in (
            'news/liberty-lynx-game-1-ionescu-stewart/index.html',
            'liberty-lynx-game-1-ionescu-stewart/index.html',
        ):
            stub = (ROOT / relative).read_text(encoding='utf-8')
            self.assertIn(f'rel="canonical" href="{target}"', stub)
            self.assertIn('http-equiv="refresh" content="0; url=' + target + '"', stub)
            self.assertNotIn('site-footer', stub)
        root_stub = (ROOT / 'liberty-lynx-game-1-ionescu-stewart' / 'index.html').read_text(encoding='utf-8')
        self.assertNotIn('/news/liberty-lynx-game-1-ionescu-stewart/', root_stub)
        for name in ('sitemap.xml', 'pages-sitemap.xml', 'articles.json'):
            text = (ROOT / name).read_text(encoding='utf-8')
            self.assertNotIn('liberty-lynx-game-1-ionescu-stewart', text)
