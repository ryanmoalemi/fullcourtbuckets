"""RSS full text and Basketball-Reference player links.

The linker tests use a tiny map so they do not touch the network.
The mapping test checks the checked-in file, which was built from the
Basketball-Reference index and kept only after each URL returned HTTP 200.
"""
import json
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import bref_player_links
import rss_feed

ROOT = Path(__file__).resolve().parents[1]
GABBY = 'https://www.basketball-reference.com/wnba/players/w/williga01w.html'
COURTNEY = 'https://www.basketball-reference.com/wnba/players/w/willico01w.html'
AJA = 'https://www.basketball-reference.com/wnba/players/w/wilsoa01w.html'
PLAYERS = {
    'Gabby Williams': GABBY,
    'Courtney Williams': COURTNEY,
    "A'ja Wilson": AJA,
}
CONTENT = '{http://purl.org/rss/1.0/modules/content/}'
URL_RE = re.compile(
    r'https://www\.basketball-reference\.com/wnba/players/[a-z]/[a-z0-9]+\.html\Z'
)


class PlayerLinkTests(unittest.TestCase):
    def test_first_plain_mention_is_linked_once(self):
        html = '<p>Gabby Williams scored. Gabby Williams scored again.</p>'
        out = bref_player_links.link_html(html, PLAYERS)
        self.assertEqual(out.count(GABBY), 1)
        self.assertTrue(out.startswith(
            f'<p><a class="inline-link" href="{GABBY}" target="_blank" rel="noopener">Gabby Williams</a> scored.'
        ))
        self.assertEqual(bref_player_links.link_html(out, PLAYERS), out)
        self.assertNotIn('\u2014', out)

    def test_headings_tables_existing_links_and_asides_are_skipped(self):
        html = (
            '<h2>Gabby Williams</h2>'
            '<table><tr><td>Gabby Williams</td></tr></table>'
            '<aside class="article-end"><p>Gabby Williams</p></aside>'
            '<p><a class="inline-link" href="/wnba/gabby-williams/">Gabby Williams</a> scored. '
            'Gabby Williams added a steal.</p>'
        )
        out = bref_player_links.link_html(html, PLAYERS)
        self.assertIn('<h2>Gabby Williams</h2>', out)
        self.assertIn('<td>Gabby Williams</td>', out)
        self.assertIn('<aside class="article-end"><p>Gabby Williams</p></aside>', out)
        self.assertIn(
            '<a class="inline-link" href="/wnba/gabby-williams/">Gabby Williams</a>',
            out,
        )
        self.assertEqual(out.count(GABBY), 1)
        self.assertIn(f'href="{GABBY}"', out)
        self.assertNotIn('<a class="inline-link" href="/wnba/gabby-williams/"><a', out)

    def test_unknown_names_and_urls_are_not_invented(self):
        html = '<p>Gabby Williams and Not A Real Person. Courtney Williams too.</p>'
        out = bref_player_links.link_html(html, PLAYERS)
        self.assertIn('Not A Real Person', out)
        self.assertNotIn('Not A Real Person</a>', out)
        self.assertIn(GABBY, out)
        self.assertIn(COURTNEY, out)
        self.assertEqual(out.count('basketball-reference.com'), 2)
        for url in bref_player_links.BREF_HREF_RE.findall(out):
            self.assertIn(url, PLAYERS.values())

    def test_apostrophe_entity_and_possessive(self):
        html = "<p>A&#x27;ja Wilson's line, then A'ja Wilson again.</p>"
        out = bref_player_links.link_html(html, PLAYERS)
        self.assertEqual(out.count(AJA), 1)
        self.assertIn("A&#x27;ja Wilson</a>'s", out)
        self.assertIn("then A'ja Wilson again.", out)

    def test_document_links_only_inside_the_article(self):
        html = (
            '<p>Gabby Williams outside.</p>'
            '<article class="article"><p>Gabby Williams inside.</p></article>'
        )
        out = bref_player_links.link_document(html, PLAYERS)
        self.assertIn('<p>Gabby Williams outside.</p>', out)
        self.assertEqual(out.count(GABBY), 1)

    def test_checked_in_mapping_uses_confirmed_player_urls(self):
        data = json.loads((ROOT / 'data/wnba/bref-player-urls.json').read_text(encoding='utf-8'))
        players = data['players']
        self.assertEqual(players["A'ja Wilson"], AJA)
        self.assertEqual(players['Gabby Williams'], GABBY)
        self.assertGreater(len(players), 1000)
        for name in data.get('ambiguous_names') or []:
            self.assertNotIn(name, players)
        for name, url in players.items():
            self.assertRegex(url, URL_RE)
            self.assertIn(' ', name)
            self.assertNotIn('\u2014', name)
            self.assertNotIn('\u2014', url)


class PublishedPageTests(unittest.TestCase):
    def test_linker_is_stable_on_published_stories(self):
        players = bref_player_links.load_players()
        self.assertGreater(len(players), 100)
        for path in sorted((ROOT / 'news').glob('*/index.html')):
            text = path.read_text(encoding='utf-8')
            once = bref_player_links.link_document(text, players)
            twice = bref_player_links.link_document(once, players)
            self.assertEqual(twice, once, path.parent.name)

    def test_repository_feed_carries_full_news_text(self):
        document = (ROOT / 'feed.xml').read_text(encoding='utf-8')
        self.assertNotIn('\u2014', document)
        parsed = ET.fromstring(document)
        items = parsed.findall('channel/item')
        self.assertGreaterEqual(len(items), 10)
        for item in items:
            link = item.find('link').text or ''
            encoded = item.find(CONTENT + 'encoded')
            description = item.find('description')
            self.assertIsNotNone(description, link)
            if not link.startswith('https://fullcourtbuckets.com/news/'):
                continue
            self.assertIsNotNone(encoded, link)
            self.assertIn('<p', encoded.text or '')
            self.assertGreater(len(encoded.text or ''), len(description.text or ''), link)


class FeedTests(unittest.TestCase):
    def test_news_item_carries_full_article_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            slug = 'example-recap'
            news = root / 'news' / slug
            news.mkdir(parents=True)
            sentence = 'Caitlin Clark scored 30 in a sentence that is the full story, not the card summary.'
            page = (
                '<html><article class="article">'
                f'<h1>Title</h1><p class="lead"><a href="/wnba/caitlin-clark/">{sentence}</a></p>'
                '<p>Texas A&amp;M stayed linked.</p>'
                '<aside class="article-end"><p>Related headline only.</p></aside>'
                '</article></html>'
            )
            (news / 'index.html').write_text(page, encoding='utf-8')
            articles = [{
                'slug': slug,
                'url': f'/news/{slug}/',
                'title': 'Title',
                'date': '2026-11-01',
                'description': 'Short summary only.',
                'category': 'news',
            }]
            (root / 'articles.json').write_text(json.dumps(articles), encoding='utf-8')
            document = rss_feed.feed_document(root)
            self.assertNotIn('\u2014', document)
            parsed = ET.fromstring(document)
            item = parsed.find('channel/item')
            description = item.find('description').text
            encoded = item.find(CONTENT + 'encoded').text
            self.assertEqual(description, 'Short summary only.')
            self.assertIn(sentence, encoded)
            self.assertIn('<p class="lead">', encoded)
            self.assertIn('href="https://fullcourtbuckets.com/wnba/caitlin-clark/"', encoded)
            self.assertNotIn('href="/wnba/', encoded)
            self.assertIn('Texas A&amp;M', encoded)
            self.assertNotIn('Related headline only.', encoded)
            self.assertIn('xmlns:content="http://purl.org/rss/1.0/modules/content/"', document)


if __name__ == '__main__':
    unittest.main()
