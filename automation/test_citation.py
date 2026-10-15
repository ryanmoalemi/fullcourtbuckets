"""Citation tools on the five link-magnet pages, plus the updater slug fix."""
import html
import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

import internal_links as links

ROOT = Path(__file__).resolve().parents[1]
MEDIA = (
    'Media, data citations &amp; editorial: '
    '<a href="mailto:ryan@fullcourtbuckets.com">ryan@fullcourtbuckets.com</a>'
    ' | General: '
    '<a href="mailto:hello@fullcourtbuckets.com">hello@fullcourtbuckets.com</a>'
)


def page(relative: str) -> str:
    return (ROOT / relative).read_text(encoding='utf-8')


class JsonLdExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self._on = False
        self._buf = []

    def handle_starttag(self, tag, attrs):
        attr = {key.lower(): (value or '') for key, value in attrs}
        if tag == 'script' and 'ld+json' in attr.get('type', ''):
            self._on = True
            self._buf = []

    def handle_endtag(self, tag):
        if tag == 'script' and self._on:
            self._on = False
            self.blocks.append(json.loads(''.join(self._buf)))

    def handle_data(self, data):
        if self._on:
            self._buf.append(data)


def json_ld(html: str) -> list:
    parser = JsonLdExtractor()
    parser.feed(html)
    return parser.blocks


def walk_types(node, found):
    if isinstance(node, dict):
        kind = node.get('@type')
        if isinstance(kind, str):
            found.append(node)
        elif isinstance(kind, list):
            found.append(node)
        for value in node.values():
            walk_types(value, found)
    elif isinstance(node, list):
        for value in node:
            walk_types(value, found)


def typed(html: str, name: str) -> list:
    found = []
    for block in json_ld(html):
        nodes = []
        walk_types(block, nodes)
        for node in nodes:
            kind = node.get('@type')
            kinds = kind if isinstance(kind, list) else [kind]
            if name in kinds:
                found.append(node)
    return found


def duplicate_ids(html: str) -> list:
    ids = re.findall(r'\bid="([^"]+)"', html)
    return sorted({item for item in ids if ids.count(item) > 1})


class CitationPageTests(unittest.TestCase):
    def test_shared_controls_and_unique_ids(self):
        pages = {
            'news/wnba-finals-2026-audience-growth-dream-valkyries/index.html': [
                'verified-viewership-table',
                'finals-tv-schedule',
                'search-demand-estimates',
                'finals-ratings-hub',
                'finals-ratings-tracker',
            ],
            'news/2026-wnba-finals-ratings-tracker/index.html': [
                'finals-ratings-tracker',
                'finals-benchmarks',
                'october-search-interest',
                'finals-average-viewers',
                'figures-left-off',
            ],
            'news/top-10-womens-college-basketball-cards-to-collect-2026/index.html': [
                'card-sales-comparison-table',
                'juju-watkins',
                'sarah-strong',
                'hannah-hidalgo',
                'madison-booker',
                'mikayla-blakes',
                'joyce-edwards',
                'milaysia-fulwiley',
                'mikaylah-williams',
                'audi-crooks',
                'jaloni-cambridge',
            ],
            'news/wnba-expansion-teams/index.html': [
                'year-1-expansion-comparison',
                'expansion-draft-coin-toss',
                'future-expansion-timeline',
                'expansion-fee-table',
                'sources',
                'source-17',
            ],
            'news/liberty-offseason-five-gm-moves/index.html': [
                'sweep-stat-breakdown',
                'semifinal-totals',
                'liberty-2027-contracts',
                'gm-move-1',
                'gm-move-2',
                'gm-move-3',
                'gm-move-4',
                'gm-move-5',
            ],
            'standings/index.html': [
                'final-2026-standings',
                'wnba-tiebreaker-rules',
                'standings-faq',
                'standings-tie-log',
            ],
        }
        for relative, ids in pages.items():
            html = page(relative)
            self.assertIn('class="fcb-quick-cite"', html, relative)
            self.assertIn('Copy Citation &amp; Link', html, relative)
            self.assertIn('fcb-embed-toggle', html, relative)
            self.assertIn('Copy Embed Code', html, relative)
            self.assertIn('CC BY 4.0', html, relative)
            self.assertIn('/assets/citation.css', html, relative)
            self.assertIn('/assets/citation.js', html, relative)
            self.assertEqual(duplicate_ids(html), [], relative)
            for ident in ids:
                self.assertIn(f'id="{ident}"', html, f'{relative} #{ident}')
            json_ld(html)

    def test_dataset_pages_and_faq_match(self):
        for relative in (
            'news/wnba-finals-2026-audience-growth-dream-valkyries/index.html',
            'news/2026-wnba-finals-ratings-tracker/index.html',
            'news/top-10-womens-college-basketball-cards-to-collect-2026/index.html',
            'standings/index.html',
        ):
            html = page(relative)
            datasets = typed(html, 'Dataset')
            self.assertEqual(len(datasets), 1, relative)
            self.assertEqual(datasets[0]['license'], 'https://creativecommons.org/licenses/by/4.0/')
            self.assertTrue(datasets[0]['distribution']['contentUrl'].endswith('.csv'))
            self.assertIn('Full Court Buckets gathers and verifies its own data', datasets[0]['description'])
        standings = page('standings/index.html')
        faqs = typed(standings, 'FAQPage')
        self.assertEqual(len(faqs), 1)
        self.assertTrue(faqs[0]['@id'].endswith('#standings-faq'))
        names = [item['name'] for item in faqs[0]['mainEntity']]
        visible = []
        for inner in re.findall(r'<h3\b[^>]*>(.*?)</h3>', standings, re.S):
            inner = re.sub(r'<a class="fcb-anchor"[^>]*>.*?</a>', '', inner, flags=re.S)
            visible.append(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', inner)).strip())
        for name in names:
            self.assertIn(name, visible)
        self.assertIn('Not in the standings file', standings)
        self.assertIn('href="https://www.espn.com/wnba/standings" target="_blank" rel="noopener"', standings)
        self.assertNotIn('\u2014', standings)

    def test_finals_tracker_uses_the_oct_13_release(self):
        html = page('news/2026-wnba-finals-ratings-tracker/index.html')
        tracker = html.split('id="finals-ratings-tracker"', 1)[1].split('id="finals-average-viewers"', 1)[0]
        self.assertIn('Wed, Oct. 21, 2026', tracker)
        self.assertIn('State Farm Arena', tracker)
        self.assertIn('10:00 a.m. PT', tracker)
        self.assertIn('Pending tip-off', tracker)
        self.assertEqual(tracker.count('>Not listed<'), 6)
        self.assertNotIn('Oct. 26', tracker)
        self.assertNotIn('168%', html)
        self.assertNotIn('ESPN networks', html)
        self.assertIn('about 2.7 times', html)
        self.assertIn('984,000', html)
        self.assertIn('https://fullcourtbuckets.com/news/2026-wnba-finals-ratings-tracker/#finals-ratings-tracker', html)
        self.assertIn('href="/news/wnba-finals-2026-audience-growth-dream-valkyries/"', html)
        self.assertIn('href="/wnba/viewership-attendance/"', html)
        self.assertIn('"@type": "Dataset"', html)
        history = html.split('id="finals-average-viewers"', 1)[1].split('id="figures-left-off"', 1)[0]
        self.assertIn('534,000', history)
        self.assertIn('728,000', history)
        self.assertIn('1,600,000', history)
        self.assertIn('1,500,000', history)
        self.assertIn('Not in the Full Court Buckets viewership file', history)
        audience = page('news/wnba-finals-2026-audience-growth-dream-valkyries/index.html')
        self.assertIn('href="/news/2026-wnba-finals-ratings-tracker/#finals-ratings-tracker"', audience)
        self.assertIn('id="finals-ratings-tracker"', audience)
        self.assertIn('id="finals-ratings-hub"', audience)
        self.assertNotIn('embed-finals-tv-schedule', audience)
        schedule = audience.split('id="finals-tv-schedule"', 1)[1].split('</table>', 1)[0]
        self.assertIn('Wed. Oct. 21, 2026', schedule)
        self.assertIn('State Farm Arena', schedule)
        self.assertIn('1:00 p.m. ET / 10:00 a.m. PT', schedule)
        self.assertIn('Not listed', schedule)
        self.assertNotIn('Thu. Oct. 22', schedule)
        self.assertNotIn('Oct. 26', schedule)
        preview = page('news/finals-game-1-preview-dream-valkyries/index.html')
        listed = preview.split('Full Finals schedule', 1)[1].split('Injury report', 1)[0]
        self.assertIn('Wednesday, Oct. 21', listed)
        self.assertIn('State Farm Arena', listed)
        self.assertIn('1:00 p.m. ET / 10:00 a.m. PT', listed)
        self.assertIn('Not listed', listed)
        self.assertNotIn('Thursday, Oct. 22', listed)
        self.assertNotIn('Oct. 26', listed)
        data = page('wnba/viewership-attendance/index.html')
        self.assertIn('href="/news/2026-wnba-finals-ratings-tracker/"', data)

    def test_cards_table_keeps_selected_sales(self):
        html = page('news/top-10-womens-college-basketball-cards-to-collect-2026/index.html')
        table = html.split('id="card-sales-comparison-table"', 1)[1].split('id="juju-watkins"', 1)[0]
        self.assertIn('Sale selected for this guide', table)
        self.assertIn('$24,404', table)
        self.assertIn('Sep 26, 2026 PT', table)
        self.assertNotIn('Sept 27', table)
        self.assertNotIn('highest recorded', table.lower())
        self.assertIn('true shooting percentage are not in this guide', table.lower())
        self.assertNotIn('>TS%<', table)
        self.assertIn('Verified Auction Records: Goldin, Fanatics Collect &amp; SportsCardsPro (Updated Oct 2026)', table)

    def test_expansion_and_liberty_omit_unverified_columns(self):
        expansion = page('news/wnba-expansion-teams/index.html')
        self.assertNotIn('-211', expansion)
        self.assertNotIn('-383', expansion)
        self.assertIn('$250 million', expansion)
        self.assertIn('Arena not stated on this page.', expansion)
        self.assertIn('[7]', expansion)
        self.assertIn('[17]', expansion)
        liberty = page('news/liberty-offseason-five-gm-moves/index.html')
        self.assertIn('47.1%', liberty)
        self.assertIn('42.0%', liberty)
        self.assertIn('-18', liberty)
        self.assertNotIn('eFG', liberty)
        self.assertIn('$1,190,000', liberty)
        self.assertIn('$288,600', liberty)
        self.assertIn('not a published dollar figure', liberty)

    def test_embed_and_cite_anchors_resolve(self):
        pages = (
            'news/wnba-finals-2026-audience-growth-dream-valkyries/index.html',
            'news/2026-wnba-finals-ratings-tracker/index.html',
            'news/top-10-womens-college-basketball-cards-to-collect-2026/index.html',
            'news/wnba-expansion-teams/index.html',
            'news/liberty-offseason-five-gm-moves/index.html',
            'standings/index.html',
        )
        loaded = {relative: page(relative) for relative in pages}
        found = 0
        for relative, markup in loaded.items():
            h1 = markup.find('</h1>')
            cite = markup.find('class="fcb-quick-cite"')
            byline = markup.find('class="byline"')
            figure = re.search(r'<figure\b[^>]*\blead-photo\b', markup)
            self.assertLess(h1, cite, relative)
            if byline > h1:
                self.assertLess(h1, byline, relative)
            if figure:
                self.assertLess(figure.end(), cite, relative)
                if byline > h1:
                    self.assertLess(byline, figure.start(), relative)
            for raw in re.findall(r'<textarea\b[^>]*>(.*?)</textarea>', markup, re.S):
                text = html.unescape(re.sub(r'\s+', ' ', raw))
                for url, anchor in re.findall(
                    r'(https://fullcourtbuckets\.com[^#\s"<>]*)#([A-Za-z0-9_-]+)',
                    text,
                ):
                    found += 1
                    path = url.split('https://fullcourtbuckets.com', 1)[1]
                    if not path.endswith('/'):
                        path += '/'
                    target = 'index.html' if path == '/' else path.lstrip('/') + 'index.html'
                    target_html = page(target)
                    self.assertIn(f'id="{anchor}"', target_html, f'{relative} -> {url}#{anchor}')
        self.assertGreaterEqual(found, 6)

    def test_author_and_contact_lines(self):
        for relative in ('authors/ryan-moalemi/index.html', 'contact/index.html'):
            self.assertIn(MEDIA, page(relative))
        author = page('authors/ryan-moalemi/index.html')
        self.assertIn('href="/assets/citation.css"', author)
        self.assertIn('src="/assets/citation.js"', author)
        self.assertEqual(author.count('class="media-contact"'), 1)

    def test_author_generator_keeps_contact_line_through_nav_install(self):
        """The nightly updater renders this page, then installs the site nav."""
        import site_nav
        articles = json.loads((ROOT / 'articles.json').read_text(encoding='utf-8'))
        html = links.render_author_page(articles, ROOT)
        self.assertIn(MEDIA, html)
        self.assertIn('href="/assets/citation.css"', html)
        self.assertIn('src="/assets/citation.js"', html)
        installed = site_nav.install(html, '/authors/ryan-moalemi/', site_nav.build_menu(ROOT))
        self.assertIn(MEDIA, installed)
        self.assertIn('href="/assets/citation.css"', installed)
        self.assertIn('src="/assets/citation.js"', installed)
        self.assertEqual(installed.count('class="media-contact"'), 1)
        self.assertEqual(installed.count('href="/assets/citation.css"'), 1)
        self.assertEqual(installed.count('src="/assets/citation.js"'), 1)

    def test_viewership_hub_embed_stays_one_click(self):
        html = page('wnba/viewership-attendance/index.html')
        self.assertIn('class="btn copy-embed"', html)
        self.assertNotIn('fcb-embed-toggle', html)
        self.assertNotIn('<textarea', html)
        self.assertIn('href="/how-we-make-full-court-buckets/">How we make Full Court Buckets</a>', html)
        self.assertNotIn('href="/how-we-make-full-court-buckets/" target="_blank"', html)
        self.assertIn('viewership-attendance', links.WNBA_NON_PLAYER_DIRS)
        self.assertTrue((ROOT / 'assets' / 'fonts' / 'Inter-Bold.ttf').is_file())
        self.assertTrue((ROOT / 'assets' / 'fonts' / 'Inter-Medium.ttf').is_file())


if __name__ == '__main__':
    unittest.main()
