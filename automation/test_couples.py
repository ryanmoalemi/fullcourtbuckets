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
        for name in ('sitemap.xml', 'pages-sitemap.xml'):
            self.assertIn('https://fullcourtbuckets.com/wnba/couples/', (ROOT / name).read_text(encoding='utf-8'))
        hub = (ROOT / 'wnba' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('href="/wnba/couples/"', hub)
        self.assertIn('Confirmed WNBA relationships', hub)
