"""Ryan's Angel Reese cards stay a generated personal page, not a news article."""
import json
import unittest
from decimal import Decimal
from pathlib import Path

import build_reese_cards as cards
import site_nav

ROOT = Path(__file__).resolve().parents[1]
ROUTE = '/authors/ryan-moalemi/ryans-angel-reese-cards/'
PAGE = ROOT / 'authors' / 'ryan-moalemi' / 'ryans-angel-reese-cards' / 'index.html'


class ReeseCardMathTests(unittest.TestCase):
    def test_unknown_card_is_left_out_of_the_money_totals(self):
        data = cards.load_collection(ROOT)
        summary = cards.summarize(data)
        self.assertEqual(summary['count'], 7)
        self.assertEqual(summary['valued_count'], 6)
        self.assertEqual(summary['up'], 0)
        self.assertEqual(summary['down'], 6)
        self.assertEqual(summary['paid'], Decimal('3668.56'))
        self.assertEqual(summary['current'], Decimal('2209.25'))
        self.assertEqual(summary['change'], Decimal('-1459.31'))
        self.assertEqual(summary['percent'], Decimal('-39.8'))
        unknown = summary['unknown']
        self.assertEqual(len(unknown), 1)
        self.assertEqual(unknown[0]['id'], 'reese-2023-bowman-u-now-blue-auto')
        self.assertEqual(cards.paid_amount(unknown[0]), Decimal('243.11'))
        tiger = next(card for card in data['cards'] if card['id'] == 'reese-2024-prizm-dp-tiger-38')
        self.assertEqual(cards.card_change(tiger), Decimal('-24.44'))
        self.assertEqual(cards.card_percent(tiger), Decimal('-9.8'))
        self.assertEqual(cards.value_as_of(ROOT), '2026-10-01')
        self.assertEqual(cards.short_date('2026-10-01'), 'Oct 1, 2026')


class ReeseCardPageTests(unittest.TestCase):
    def setUp(self):
        self.html = PAGE.read_text(encoding='utf-8')

    def test_page_is_generated_from_the_json_and_not_an_article(self):
        articles = json.loads((ROOT / 'articles.json').read_text(encoding='utf-8'))
        self.assertFalse(any(item.get('slug') == 'ryans-angel-reese-cards' for item in articles))
        self.assertIn('rel="canonical" href="https://fullcourtbuckets.com/authors/ryan-moalemi/ryans-angel-reese-cards/"', self.html)
        self.assertIn('Ryan&#x27;s Angel Reese Cards | Full Court Buckets', self.html)
        self.assertLessEqual(len(cards.PAGE_DESCRIPTION), 155)
        self.assertGreaterEqual(len(cards.PAGE_DESCRIPTION), 110)
        self.assertIn('Values as of Oct 1, 2026', self.html)
        self.assertIn('$3,668.56', self.html)
        self.assertIn('$2,209.25', self.html)
        self.assertIn('-$1,459.31', self.html)
        self.assertIn('-39.8%', self.html)
        self.assertIn('Value unknown*', self.html)
        self.assertIn('left out of paid, value, and change', self.html)
        self.assertNotIn('\u2014', self.html)
        self.assertIn('transcendent talent', self.html)
        self.assertIn('positive impact she is having on women', self.html)
        self.assertIn('young girls look up to her', self.html)
        self.assertIn('got into sports writing after watching her play', self.html)
        self.assertIn('Photo: eBay seller listing of this card', self.html)
        self.assertIn('John McClellan', self.html)
        self.assertIn('CC BY-SA 2.0', self.html)
        self.assertIn('https://creativecommons.org/licenses/by-sa/2.0/', self.html)
        self.assertIn('Wikimedia Commons', self.html)
        self.assertIn('data-sort="date"', self.html)
        self.assertIn('data-sort="gain"', self.html)
        self.assertIn('data-sort="value"', self.html)
        self.assertIn('data-sort="paid"', self.html)
        self.assertIn('Purchase timeline', self.html)
        self.assertIn('August 24 to September 4, 2026', self.html)
        self.assertIn('How the numbers work', self.html)
        self.assertIn('https://www.psacard.com/cert/112951750', self.html)
        self.assertIn('target="_blank" rel="noopener"', self.html)
        self.assertIn('only 1 PSA 10 sale', self.html)
        self.assertIn('Auto grade could not be checked', self.html)
        self.assertIn('treat this as a ceiling', self.html)
        menu = site_nav.render(site_nav.build_menu(ROOT), '/__none__')
        self.assertNotIn(ROUTE, menu)
        self.assertIn('href="https://www.tiktok.com/@fullcourtbuckets" target="_blank" rel="noopener me"', self.html)
        self.assertIn('<footer class="site-footer">', self.html)

    def test_black_color_blast_has_no_back_and_breadcrumbs_stay_in_page(self):
        panel = self.html.split('data-detail="reese-2024-prizm-dp-black-color-blast-11"', 1)[1].split('</article>', 1)[0]
        self.assertEqual(panel.count('<img '), 1)
        self.assertNotIn('-back.webp', panel)
        crumbs = self.html.split('aria-label="Breadcrumb"', 1)[1].split('</nav>', 1)[0]
        self.assertIn('>Home</a>', crumbs)
        self.assertIn('href="/authors/ryan-moalemi/">Ryan Moalemi</a>', crumbs)
        self.assertIn('Angel Reese Cards', crumbs)
        self.assertNotIn('target="_blank"', crumbs)
        self.assertIn('"name": "Home"', self.html)
        self.assertIn('"name": "Ryan Moalemi"', self.html)
        self.assertIn('"name": "Angel Reese Cards"', self.html)

    def test_author_and_player_pages_link_here(self):
        author = (ROOT / 'authors' / 'ryan-moalemi' / 'index.html').read_text(encoding='utf-8')
        self.assertIn(f'href="{ROUTE}"', author)
        self.assertNotIn(f'href="{ROUTE}" target="_blank"', author)
        self.assertIn('Angel Reese cards', author)
        player = (ROOT / 'wnba' / 'angel-reese' / 'index.html').read_text(encoding='utf-8')
        self.assertIn("See Ryan's Angel Reese cards", player)
        self.assertIn(f'href="{ROUTE}"', player)
        self.assertNotIn(f'href="{ROUTE}" target="_blank"', player)
        import build_players
        import internal_links
        self.assertLessEqual(build_players.contextual_link_count(player), internal_links.MAX_PLAYER_LINKS)
        index = json.loads((ROOT / 'data' / 'wnba' / 'players-index.json').read_text(encoding='utf-8'))
        published = [row for row in index['players'] if row.get('id') not in build_players.DUPLICATE_PLAYER_IDS]
        linking = internal_links.catalog_from_index({**index, 'players': published})
        profile = json.loads((ROOT / 'data' / 'wnba' / 'players' / 'angel-reese.json').read_text(encoding='utf-8'))
        rebuilt = build_players.profile_page(profile, ROOT, linking, None)
        self.assertIn("See Ryan's Angel Reese cards", rebuilt)
        self.assertLessEqual(build_players.contextual_link_count(rebuilt), internal_links.MAX_PLAYER_LINKS)
        for name in ('sitemap.xml', 'pages-sitemap.xml'):
            sitemap = (ROOT / name).read_text(encoding='utf-8')
            self.assertIn('https://fullcourtbuckets.com/authors/ryan-moalemi/ryans-angel-reese-cards/', sitemap)
        players = (ROOT / 'player-sitemap.xml').read_text(encoding='utf-8')
        self.assertNotIn(ROUTE, players)
        hero = ROOT / 'images' / 'reese-cards' / 'angel-reese-hero.webp'
        self.assertTrue(hero.is_file())
        self.assertLess(hero.stat().st_size, 250_000)
        for name in (
            'reese-2024-prizm-dp-black-color-blast-11-front.webp',
            'reese-2024-rookie-royalty-kaboom-5-back.webp',
        ):
            photo = ROOT / 'images' / 'reese-cards' / name
            self.assertTrue(photo.is_file(), name)
            self.assertLess(photo.stat().st_size, 200_000, name)


if __name__ == '__main__':
    unittest.main()
