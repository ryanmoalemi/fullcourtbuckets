"""The couples page stays inside the verified list and the shared nav."""
import unittest
from pathlib import Path
import re

import build_couples

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / 'wnba' / 'couples' / 'index.html'


def main_text():
    html = PAGE.read_text(encoding='utf-8')
    return html.split('<main', 1)[1].split('</main>', 1)[0]


class CouplesPageTests(unittest.TestCase):
    def test_page_uses_only_confirmed_couples(self):
        html = PAGE.read_text(encoding='utf-8')
        body = main_text()
        self.assertEqual(body.count('class="couple-card"'), 15)
        self.assertEqual(body.count('<h1>'), 1)
        self.assertIn('Last checked September 29, 2026', body)
        self.assertIn('Both WNBA', body)
        self.assertLess(body.find('Both WNBA'), body.find('A&#x27;ja Wilson'))
        for kind in ('Article', 'ItemList', 'BreadcrumbList', 'FAQPage'):
            self.assertIn(f'"@type": "{kind}"', html)
        self.assertNotIn('\u2014', html)
        for phrase in (
            'Megan Rapinoe', 'Sue Bird', 'Cherelle', 'Wendell Carter', 'Jana',
            'Airr', 'Lailaa', 'USA Basketball', 'WNBA bubble', 'permission to marry',
        ):
            self.assertNotIn(phrase, body, phrase)
        for block in re.findall(r'<ul class="chips">(.*?)</ul>', body):
            self.assertIn('href="http', block)
            self.assertNotIn('href=""', block)

    def test_player_note_links_to_the_card(self):
        note = build_couples.note_for_slug(ROOT, 'breanna-stewart')
        self.assertIn('/wnba/couples/#breanna-stewart-marta-xargay-casademont', note)
        self.assertIn('Married to', note)
        self.assertEqual(build_couples.note_for_slug(ROOT, 'angel-reese'), '')
        page = (ROOT / 'wnba' / 'breanna-stewart' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('class="relationship-note"', page)
        self.assertLessEqual(page.count('class="inline-link"'), 8)

    def test_sitemap_and_hub_link(self):
        pages = (ROOT / 'pages-sitemap.xml').read_text(encoding='utf-8')
        index = (ROOT / 'sitemap.xml').read_text(encoding='utf-8')
        self.assertIn('https://fullcourtbuckets.com/wnba/couples/', pages)
        self.assertNotIn('https://fullcourtbuckets.com/wnba/couples/', index)
        self.assertIn('https://fullcourtbuckets.com/pages-sitemap.xml', index)
        allowed = {'news/index.html', 'sitemap/index.html'}
        found = []
        for path in ROOT.rglob('*.html'):
            if '.git' in path.parts:
                continue
            text = path.read_text(encoding='utf-8', errors='replace')
            if 'href="/wnba/couples/"' not in text:
                continue
            found.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(sorted(found), sorted(allowed))
        hub = (ROOT / 'wnba' / 'index.html').read_text(encoding='utf-8')
        main = hub.split('<main', 1)[1].split('</main>', 1)[0]
        self.assertNotIn('href="/wnba/couples/"', main)
        self.assertNotIn('Confirmed WNBA relationships', main)
        self.assertLess(hub.find('id="player-search"'), hub.find('class="player-grid"'))
        self.assertLess(hub.find('class="player-grid"'), hub.find('id="teams"'))
        news = (ROOT / 'news' / 'index.html').read_text(encoding='utf-8')
        list_end = news.find('</ol>')
        main_end = news.find('</main>', list_end)
        feature = news[list_end:main_end]
        self.assertLess(news.find('<ol class="news-list">'), list_end)
        self.assertIn('class="couples-feature"', feature)
        self.assertIn('href="/wnba/couples/"', feature)
        self.assertIn('WNBA couples', feature)
        crumb = main_text().split('<section', 1)[0]
        self.assertIn('<a href="/wnba/">Players</a>', crumb)
        self.assertNotIn('href="/news/"', crumb)
        self.assertIn('"name": "Players", "item": "https://fullcourtbuckets.com/wnba/"', PAGE.read_text(encoding='utf-8'))
        self.assertNotIn('"name": "News", "item": "https://fullcourtbuckets.com/news/"', PAGE.read_text(encoding='utf-8'))

    def test_patch_hub_moves_couples_link_to_news(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            page = root / 'wnba' / 'index.html'
            page.parent.mkdir(parents=True)
            page.write_text(
                '<p>2 profiles. Available statistics from 2008 onward.</p>'
                '<div class="directory-filters js-only"><input id="player-search"></div>'
                '<div class="player-grid"></div>'
                '<p id="no-players" hidden>No players match your search.</p>'
                '<section class="section hub-links" id="teams"><h2>Teams</h2>'
                '<ul class="team-index"></ul>'
                '<p><a class="inline-link" href="/wnba/teams/">All teams</a></p></section>'
                '<p><a class="inline-link" href="/wnba/couples/">Confirmed WNBA relationships</a></p>',
                encoding='utf-8',
            )
            news = root / 'news' / 'index.html'
            news.parent.mkdir(parents=True)
            news.write_text(
                '<style></style><main><ol class="news-list"><li>story</li></ol></main>',
                encoding='utf-8',
            )
            build_couples.patch_hub(root)
            text = page.read_text(encoding='utf-8')
            self.assertNotIn('/wnba/couples/', text)
            self.assertNotIn('Confirmed WNBA relationships', text)
            self.assertLess(text.find('id="player-search"'), text.find('id="teams"'))
            news_text = news.read_text(encoding='utf-8')
            self.assertLess(news_text.find('</ol>'), news_text.find('href="/wnba/couples/"'))
            self.assertLess(news_text.find('href="/wnba/couples/"'), news_text.find('</main>'))
            self.assertEqual(news_text.count('href="/wnba/couples/"'), 1)
            build_couples.patch_hub(root)
            self.assertEqual(news.read_text(encoding='utf-8').count('href="/wnba/couples/"'), 1)
