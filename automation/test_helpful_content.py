"""Disclosures for the helpful-content update, plus the removed duplicate recap."""
import json
import re
import unittest
from pathlib import Path

import build_players as builder
import internal_links as links
import site_nav

ROOT = Path(__file__).resolve().parents[1]
HOW = '/how-we-make-full-court-buckets/'
TAGLINE = 'Independent WNBA news and analysis'
OLD_TAGLINE = 'Built by the WNBA community, for the WNBA community'
PROFILE_NOTE = (
    'Built by Full Court Buckets from ESPN and WNBA data. '
    'Profile text and FAQs drafted with AI tools and checked against the stats on this page.'
)
PORTRAIT_LINE = 'Portrait is an AI illustration.'
KEPT = '/news/liberty-lynx-game-1-full-recap/'
REMOVED = 'liberty-lynx-game-1-ionescu-stewart'


class HelpfulContentTests(unittest.TestCase):
    def test_how_we_make_page_is_linked_from_footer_not_the_menu(self):
        page = (ROOT / 'how-we-make-full-court-buckets' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('<h1>How we make Full Court Buckets</h1>', page)
        self.assertIn('He comes up with the story ideas, picks the stats and angles that matter', page)
        self.assertIn('Opinion and analysis pieces are his own take.', page)
        self.assertIn('Ryan reads every story before it goes live and makes the final edit.', page)
        self.assertIn('No invented quotes, no guessed stats.', page)
        self.assertIn('hello@fullcourtbuckets.com', page)
        self.assertNotIn('\u2014', page)
        self.assertNotIn(OLD_TAGLINE, page)
        menu = site_nav.render(site_nav.build_menu(ROOT), '/__none__')
        self.assertNotIn(HOW, menu)
        self.assertIn(f'href="{HOW}"', site_nav.FOOTER_HTML)
        self.assertIn(site_nav.FOOTER_HTML, page)
        for name in ('sitemap.xml', 'pages-sitemap.xml'):
            text = (ROOT / name).read_text(encoding='utf-8')
            self.assertIn('https://fullcourtbuckets.com' + HOW, text)
        self.assertNotIn(HOW, (ROOT / 'player-sitemap.xml').read_text(encoding='utf-8'))

    def test_about_and_author_explain_the_editing(self):
        about = (ROOT / 'about' / 'index.html').read_text(encoding='utf-8')
        self.assertIn(
            'Ryan Moalemi</a> runs Full Court Buckets. He comes up with the stories, edits every one, and uses AI tools to help draft them.',
            about,
        )
        self.assertIn(f'href="{HOW}">Here\'s how that works.</a>', about)
        self.assertNotIn('writes the news and game recaps.', about)
        author = (ROOT / 'authors' / 'ryan-moalemi' / 'index.html').read_text(encoding='utf-8')
        self.assertIn(f'href="{HOW}"', author)
        self.assertIn('alt="Ryan Moalemi"', author)
        self.assertIn(links.AUTHOR_IMAGE, author)
        self.assertIn(links.AUTHOR_IMAGE_URL, author)

    def test_every_story_says_how_it_was_made(self):
        articles = json.loads((ROOT / 'articles.json').read_text(encoding='utf-8'))
        slugs = {article['slug'] for article in articles}
        self.assertNotIn(REMOVED, slugs)
        self.assertIn('liberty-lynx-game-1-full-recap', slugs)
        for article in articles:
            html = (ROOT / 'news' / article['slug'] / 'index.html').read_text(encoding='utf-8')
            self.assertIn(links.HOW_MADE_LINK, html, article['slug'])
            links.assert_disclosure_matches_sources(html)
            expected = links.how_made_sentence(html, article)
            self.assertIn(expected, html, article['slug'])
            if 'sources linked above' in expected:
                self.assertTrue(links.outbound_source_links(html), article['slug'])
            if links.story_uses_box_score(html, article):
                self.assertLess(html.find('class="box-score"'), html.find('class="how-made"'), article['slug'])
            self.assertIn(links.BYLINE_HTML, html, article['slug'])
            self.assertIn('By Ryan Moalemi', html, article['slug'])

    def test_fiba_story_does_not_invent_sources_and_names_its_figures(self):
        slug = 'fiba-womens-basketball-world-cup-2026'
        html = (ROOT / 'news' / slug / 'index.html').read_text(encoding='utf-8')
        articles = json.loads((ROOT / 'articles.json').read_text(encoding='utf-8'))
        article = next(item for item in articles if item['slug'] == slug)
        self.assertEqual(links.outbound_source_links(html), [])
        self.assertIn(links.HOW_MADE_OTHER_UNLINKED, html)
        self.assertNotIn('sources linked above', html)
        self.assertNotIn('official FIBA', html)
        self.assertNotIn('USA Basketball announcements', html)
        links.assert_disclosure_matches_sources(html)
        self.assertIn('2026 FIBA Women\'s Basketball World Cup logo', html)
        self.assertIn('2026 USA Women\'s National Team roster', html)
        self.assertIn('coaching staff: head coach Kara Lawson', html)
        self.assertIn('September 4 versus China', html)
        self.assertNotIn('alt="World Cup hero image"', html)
        self.assertNotIn('alt="Team USA roster image"', html)
        node = None
        for match in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html):
            data = json.loads(match)
            node = links._article_node(data)
            if node is not None:
                break
        self.assertEqual(node['datePublished'], '2026-08-30')
        self.assertEqual(node['dateModified'], article['dateModified'])
        self.assertEqual(node['dateModified'], '2026-10-04')
        bare = '<article><p>No links here.</p><p class="how-made">How this story was made: drafted with AI tools from the sources linked above, then reviewed and edited by Ryan Moalemi.</p></article>'
        with self.assertRaises(links.DisclosureError):
            links.assert_disclosure_matches_sources(bare)

    def test_college_collecting_story_credits_ryan_as_the_writer(self):
        slug = 'top-10-womens-college-basketball-cards-to-collect-2026'
        html = (ROOT / 'news' / slug / 'index.html').read_text(encoding='utf-8')
        articles = json.loads((ROOT / 'articles.json').read_text(encoding='utf-8'))
        article = next(item for item in articles if item['slug'] == slug)
        self.assertTrue(article.get('authorWrote'))
        self.assertEqual(article['date'], '2026-10-04')
        self.assertEqual(article['dateModified'], '2026-10-04')
        self.assertIn(links.HOW_MADE_RYAN, html)
        self.assertNotIn('drafted with AI tools', html)
        self.assertIn('Published October 4, 2026', html)
        self.assertIn('SEC Sixth Woman of the Year', html)
        self.assertIn('By Ryan Moalemi', html)
        self.assertNotIn('\u2014', html)
        self.assertLess(len(article['description']), 160)
        node = None
        for match in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html):
            data = json.loads(match)
            node = links._article_node(data)
            if node is not None:
                break
        self.assertEqual(node['datePublished'], '2026-10-04')
        self.assertEqual(node['dateModified'], '2026-10-04')
        self.assertEqual(node['author']['url'], links.AUTHOR_URL)

    def test_duplicate_game_one_redirects_to_the_full_recap(self):
        kept = (ROOT / 'news' / 'liberty-lynx-game-1-full-recap' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('Ionescu assisted Stewart five times', kept)
        self.assertIn('11 defensive', kept)
        self.assertIn('2024 WNBA Finals', kept)
        self.assertNotIn(REMOVED, kept)
        self.assertNotIn('\u2014', kept)
        target = 'https://fullcourtbuckets.com' + KEPT
        for relative in (
            f'news/{REMOVED}/index.html',
            f'{REMOVED}/index.html',
        ):
            stub = (ROOT / relative).read_text(encoding='utf-8')
            self.assertEqual(stub, links.permanent_redirect(target))
        for name in ('sitemap.xml', 'pages-sitemap.xml', 'index.html', 'news/index.html'):
            text = (ROOT / name).read_text(encoding='utf-8')
            self.assertNotIn(REMOVED, text, name)
        game_2 = (ROOT / 'news' / 'liberty-lynx-game-2-recap' / 'index.html').read_text(encoding='utf-8')
        self.assertNotIn(REMOVED, game_2)

    def test_tagline_and_player_profile_note(self):
        offenders = []
        noted = 0
        for path in ROOT.rglob('*.html'):
            if '.git' in path.parts:
                continue
            text = path.read_text(encoding='utf-8', errors='replace')
            if OLD_TAGLINE in text:
                offenders.append(path.relative_to(ROOT).as_posix())
            if 'class="ai-note"' in text and PROFILE_NOTE not in text:
                offenders.append('missing profile note ' + path.relative_to(ROOT).as_posix())
            if 'has-player-portrait' in text and PORTRAIT_LINE not in text:
                offenders.append('missing portrait line ' + path.relative_to(ROOT).as_posix())
            if 'has-player-portrait' not in text and PORTRAIT_LINE in text and 'wnba/' in path.as_posix():
                offenders.append('portrait line without a portrait ' + path.relative_to(ROOT).as_posix())
            if PROFILE_NOTE in text:
                noted += 1
                sources = text.split('id="sources"', 1)
                if len(sources) > 1 and 'drafted with AI tools' in sources[1].split('</details>', 1)[0]:
                    offenders.append('ai note still inside sources ' + path.relative_to(ROOT).as_posix())
        self.assertEqual(offenders, [])
        self.assertGreater(noted, 10)
        self.assertIn(TAGLINE, (ROOT / 'index.html').read_text(encoding='utf-8'))
        self.assertIn(TAGLINE, builder.header('/'))
