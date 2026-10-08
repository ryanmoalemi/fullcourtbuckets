"""Ryan's Angel Reese cards stay a generated personal page, not a news article."""
import html as html_lib
import json
import re
import threading
import unittest
from decimal import Decimal
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
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
        self.assertEqual(summary['count'], 11)
        self.assertEqual(summary['valued_count'], 10)
        self.assertEqual(summary['up'], 0)
        self.assertEqual(summary['down'], 10)
        self.assertEqual(summary['paid'], Decimal('8634.03'))
        self.assertEqual(summary['current'], Decimal('5175.25'))
        self.assertEqual(summary['change'], Decimal('-3458.78'))
        self.assertEqual(summary['percent'], Decimal('-40.1'))
        unknown = summary['unknown']
        self.assertEqual(len(unknown), 1)
        bowman = next(card for card in unknown if card['id'] == 'reese-2023-bowman-u-now-blue-auto')
        flawless = next(card for card in data['cards'] if card['id'] == 'reese-2024-25-flawless-royalty-rpa-ar-gold')
        self.assertEqual(cards.paid_amount(bowman), Decimal('243.11'))
        self.assertEqual(cards.paid_amount(flawless), Decimal('1084.55'))
        self.assertEqual(flawless['serial_number'], '01/10')
        self.assertEqual(cards.card_change(flawless), Decimal('-159.55'))
        self.assertEqual(cards.card_percent(flawless), Decimal('-14.7'))
        self.assertEqual(cards.direction(flawless), 'down')
        self.assertEqual(summary['fully_excluded'][0]['id'], bowman['id'])
        self.assertEqual(summary['paid_unpriced'], [])
        self.assertEqual(cards.value_amount(flawless), Decimal('925.00'))
        tiger = next(card for card in data['cards'] if card['id'] == 'reese-2024-prizm-dp-tiger-38')
        self.assertEqual(cards.card_change(tiger), Decimal('-24.44'))
        self.assertEqual(cards.card_percent(tiger), Decimal('-9.8'))
        self.assertEqual(cards.value_as_of(ROOT), '2026-10-03')
        self.assertEqual(cards.short_date('2026-10-01'), 'Oct 1, 2026')
        self.assertEqual(cards.short_date('2026-10-03'), 'Oct 3, 2026')
        self.assertEqual(cards.long_date('2026-09-24'), 'September 24, 2026')
        self.assertEqual(cards.long_date('2026-09-26'), 'September 26, 2026')
        self.assertEqual(cards.long_date('2026-09-19'), 'September 19, 2026')
        kept = {
            'reese-2024-25-flawless-royalty-rpa-ar-gold': ('2026-10-02', '2026-10-03'),
            'reese-2024-prizm-dp-tiger-38': ('2026-09-04', '2026-10-01'),
            'reese-2024-prizm-dp-black-color-blast-11': ('2026-08-24', '2026-10-01'),
            'reese-2024-prizm-dp-color-blast-7': ('2026-08-24', '2026-10-01'),
            'reese-2024-rookie-royalty-kaboom-5': ('2026-08-24', '2026-10-01'),
            'reese-2024-select-dss-red-auto': ('2026-08-25', '2026-10-01'),
            'reese-2023-bowman-u-chrome-lava-auto': ('2026-08-24', '2026-10-01'),
            'reese-2023-bowman-u-now-blue-auto': ('2026-08-24', '2026-10-01'),
        }
        for card in data['cards']:
            if card['id'] not in kept:
                continue
            bought, checked = kept[card['id']]
            self.assertEqual(card['purchase_date'], bought)
            self.assertEqual(card['value_checked'], checked)
            self.assertNotIn('fees', card)
            self.assertNotIn('hammer', card)


class ReeseCardPageTests(unittest.TestCase):
    def setUp(self):
        self.html = PAGE.read_text(encoding='utf-8')

    def test_page_is_generated_from_the_json_and_not_an_article(self):
        articles = json.loads((ROOT / 'articles.json').read_text(encoding='utf-8'))
        self.assertFalse(any(item.get('slug') == 'ryans-angel-reese-cards' for item in articles))
        self.assertIn('rel="canonical" href="https://fullcourtbuckets.com/authors/ryan-moalemi/ryans-angel-reese-cards/"', self.html)
        self.assertIn('Ryan&#x27;s Angel Reese card collection | Full Court Buckets', self.html)
        self.assertIn('og:title" content="Ryan&#x27;s Angel Reese card collection | Full Court Buckets"', self.html)
        self.assertNotIn('Ryan&#x27;s Angel Reese cards |', self.html)
        self.assertIn('<h1 id="collection-title"><span class="owner-word">Ryan&#x27;s</span> <span>Angel Reese</span> <span class="cards-word">cards</span></h1>', self.html)
        heading = self.html.split('id="collection-title">', 1)[1].split('</h1>', 1)[0]
        visible = re.sub(r'<[^>]+>', '', heading)
        self.assertEqual(html_lib.unescape(visible), "Ryan's Angel Reese cards")
        self.assertIn('Ryan&#x27;s Angel Reese card collection | Full Court Buckets', self.html.split('</title>', 1)[0])
        self.assertIn("Ryan's collection of Angel Reese cards", self.html)
        self.assertLessEqual(len(cards.PAGE_DESCRIPTION), 155)
        self.assertGreaterEqual(len(cards.PAGE_DESCRIPTION), 110)
        self.assertIn('Values as of Oct 3, 2026', self.html)
        self.assertNotIn('Values as of Oct 4, 2026', self.html)
        self.assertIn('$8,634.03', self.html)
        self.assertIn('$1,084.55', self.html)
        self.assertIn('$5,175.25', self.html)
        self.assertIn('-$3,458.78', self.html)
        self.assertIn('-40.1%', self.html)
        self.assertIn('Value unknown*', self.html)
        self.assertIn('left out of paid, value, and change', self.html)
        self.assertNotIn('not enough sales to price it yet', self.html)
        flawless = self.html.split('data-id="reese-2024-25-flawless-royalty-rpa-ar-gold"', 1)[1].split('</button>', 1)[0]
        self.assertIn('Value <b>$925.00</b>', flawless)
        self.assertIn('badge down">-$159.55 (-14.7%)', flawless)
        self.assertNotIn('not enough sales', flawless)
        self.assertNotIn('badge unknown', flawless)
        self.assertIn('#RPA-AR Gold / 01/10', flawless)
        self.assertNotIn('#RPA-AR Gold /10', flawless)
        self.assertIn('>Raw<', flawless)
        panel = self.html.split('data-detail="reese-2024-25-flawless-royalty-rpa-ar-gold"', 1)[1].split('</article>', 1)[0]
        self.assertIn('>$925.00</b>', panel)
        self.assertIn('badge down">-$159.55 (-14.7%)', panel)
        self.assertIn('last eBay sale, $925 best offer', panel)
        self.assertIn('Date unknown', panel)
        self.assertIn('$995', panel)
        self.assertNotIn('not enough sales', panel)
        self.assertNotIn('left out of value and change', panel)
        self.assertIn('Photo: eBay seller listing of this card', panel)
        self.assertIn('Rookie card, first on print, autograph, patch.', panel)
        self.assertIn('Serial 01/10', panel)
        self.assertIn('serial 01/10', panel)
        self.assertNotIn('exact serial is not shown', panel)
        self.assertNotIn('numbered /10', panel)
        self.assertNotIn('psacard.com/cert/', panel)
        self.assertNotIn('badge up', panel)
        self.assertEqual(panel.count('<img '), 2)
        self.assertNotIn('\u2014', self.html)
        intro = self.html.split('<section class="intro">', 1)[1].split('</section>', 1)[0]
        for paragraph in cards.INTRO_PARAGRAPHS:
            self.assertIn(f'<p>{paragraph}</p>', intro)
        self.assertEqual(intro.count('<p>'), 4)
        self.assertIn('href="/wnba/angel-reese/"', intro)
        self.assertNotIn('transcendent talent', self.html)
        self.assertNotIn('got into sports writing', self.html)
        self.assertIn('height:min(72vh,calc(100svh - 13.25rem))', self.html)
        self.assertIn('max-height:75vh', self.html)
        self.assertIn('object-fit:cover', self.html)
        self.assertIn('object-position:center top', self.html)
        self.assertNotIn('min-height:100svh', self.html)
        self.assertNotIn('min-height:78vh', self.html)
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
        self.assertIn('August 24 to October 2, 2026', self.html)
        self.assertIn('How the numbers work', self.html)
        main = self.html.split('<main class="shell" id="content">', 1)[1].split('</main>', 1)[0]
        order = [
            '<section class="intro">',
            'id="collection"',
            'id="bidding"',
            'id="summary"',
            'id="movers"',
            'id="paid-vs-value"',
            'id="timeline"',
            'id="method"',
            'id="faq"',
        ]
        bidding = main.split('id="bidding"', 1)[1].split('id="summary"', 1)[0]
        self.assertIn('Cards I&#x27;m bidding on', bidding)
        self.assertIn('https://goldin.co/item/2024-panini-prizm-wnba-gold-vinyl-prizm-147-angel-reese-rookie-card-1e2x5r', bidding)
        self.assertIn('https://alt.xyz/itm/19c74115-a39e-4896-927d-a075a4b60a54', bidding)
        self.assertIn('status-live">Live', bidding)
        self.assertIn('>TBA<', bidding)
        self.assertIn('datetime="2026-10-17T19:00:00-07:00"', bidding)
        self.assertIn('Oct 17, 2026, 7:00 p.m. PT', bidding)
        self.assertIn('$2,750', bidding)
        self.assertIn('$3,355', bidding)
        self.assertIn('$982', bidding)
        self.assertIn('$2,750 to $6,000', bidding)
        self.assertIn('$1,000 to $6,900', bidding)
        self.assertIn('Comparable sales', bidding)
        self.assertIn('No graded Gold /10 sale found', bidding)
        self.assertIn('two base Kabooms in gem mint', bidding)
        self.assertNotIn('<p class="bid-meta">Cert', bidding)
        self.assertEqual(bidding.count('>146338722<'), 1)
        self.assertEqual(bidding.count('>139024135<'), 1)
        self.assertIn('loading="eager"', bidding)
        self.assertNotIn('Two live auctions', bidding)
        self.assertNotIn('/news/angel-reese-game-2-stats-liberty-dream-semis/', bidding)
        self.assertIn('Bids as of 1:20 a.m. PT, Oct 8, 2026</p>\n<div class="bids">', bidding)
        goldin = 'https://goldin.co/item/2024-panini-prizm-wnba-gold-vinyl-prizm-147-angel-reese-rookie-card-1e2x5r'
        alt = 'https://alt.xyz/itm/19c74115-a39e-4896-927d-a075a4b60a54'
        self.assertIn(f'<a class="bid-photo-link" href="{goldin}" target="_blank" rel="noopener nofollow"><img ', bidding)
        self.assertIn(f'<a class="bid-photo-link" href="{alt}" target="_blank" rel="noopener nofollow"><img ', bidding)
        self.assertIn(f'Image: <a href="{goldin}" target="_blank" rel="noopener nofollow">Goldin</a>', bidding)
        self.assertIn(f'Image: <a href="{alt}" target="_blank" rel="noopener nofollow">Alt</a>', bidding)
        self.assertEqual(bidding.count('<p class="bid-take">I&#x27;m bidding on'), 2)
        self.assertIn('Image: <a href="https://goldin.co/', bidding)
        self.assertIn('Image: <a href="https://alt.xyz/', bidding)
        self.assertNotIn('\u2014', bidding)
        for name in (
            'bid-goldin-prizm-gold-vinyl-147-psa8.webp',
            'bid-alt-kaboom-gold-5-psa10.webp',
        ):
            photo = ROOT / 'images' / 'reese-cards' / name
            self.assertTrue(photo.is_file(), name)
            self.assertLess(photo.stat().st_size, 200_000, name)
        positions = [main.index(marker) for marker in order]
        self.assertEqual(positions, sorted(positions))
        cards_block = main.split('id="collection"', 1)[1].split('id="summary"', 1)[0]
        self.assertLess(cards_block.index('data-sort="date"'), cards_block.index('id="card-grid"'))
        self.assertLess(cards_block.index('id="card-filter"'), cards_block.index('id="card-grid"'))
        self.assertIn('https://www.psacard.com/cert/112951750', self.html)
        self.assertIn('target="_blank" rel="noopener"', self.html)
        self.assertIn('only 1 PSA 10 sale', self.html)
        self.assertIn('Auto grade could not be checked', self.html)
        self.assertIn('treat this as a ceiling', self.html)
        menu = site_nav.render(site_nav.build_menu(ROOT), '/__none__')
        self.assertNotIn(ROUTE, menu)
        self.assertIn('href="https://www.tiktok.com/@fullcourtbuckets" target="_blank" rel="noopener me"', self.html)
        self.assertIn('<footer class="site-footer">', self.html)

    def test_three_fanatics_psa10s_match_the_other_cards(self):
        self.assertIn('Photo: Fanatics Collect vault scan', self.html)
        self.assertIn('https://www.psacard.com/cert/139009502', self.html)
        self.assertIn('https://www.psacard.com/cert/139128313', self.html)
        self.assertIn('https://www.psacard.com/cert/117017224', self.html)
        self.assertIn('"numberOfItems": 11', self.html)
        gold = self.html.split('data-id="reese-2024-rookie-royalty-contenders-season-ticket-gold-2"', 1)[1].split('</button>', 1)[0]
        self.assertIn('Photo: Fanatics Collect vault scan', gold)
        self.assertIn('#2 Gold / 07/10', gold)
        self.assertIn('Paid <b>$1,688.85</b>', gold)
        self.assertIn('Value <b>$720.00</b>', gold)
        self.assertIn('badge down">-$968.85 (-57.4%)', gold)
        gold_panel = self.html.split('data-detail="reese-2024-rookie-royalty-contenders-season-ticket-gold-2"', 1)[1].split('</article>', 1)[0]
        self.assertIn('Serial 07/10', gold_panel)
        self.assertIn('Low confidence: only 1 PSA 10 sale found, and it is this same slab', gold_panel)
        self.assertIn('Bought September 24, 2026 on Fanatics Collect.', gold_panel)
        self.assertIn('Value on Oct 3, 2026', gold_panel)
        self.assertIn('<dt>Item</dt><dd>$1,500.00</dd>', gold_panel)
        self.assertIn('<dt>Shipping</dt><dd>$25.00</dd>', gold_panel)
        self.assertIn('<dt>Tax</dt><dd>$116.25</dd>', gold_panel)
        self.assertIn('<dt>Fees</dt><dd>$47.60</dd>', gold_panel)
        self.assertIn('<dt>Total paid</dt><dd>$1,688.85</dd>', gold_panel)
        self.assertNotIn('Hammer', gold_panel)
        self.assertIn('PSA cert <a href="https://www.psacard.com/cert/139009502"', gold_panel)
        kaboom = self.html.split('data-id="reese-2024-rookie-royalty-kaboom-5-2"', 1)[1].split('</button>', 1)[0]
        self.assertIn('#5 Kaboom! (second copy)', kaboom)
        self.assertIn('Paid <b>$1,688.85</b>', kaboom)
        self.assertIn('Value <b>$975.00</b>', kaboom)
        self.assertIn('badge down">-$713.85 (-42.3%)', kaboom)
        kaboom_panel = self.html.split('data-detail="reese-2024-rookie-royalty-kaboom-5-2"', 1)[1].split('</article>', 1)[0]
        self.assertIn('Kaboom! (second copy)', kaboom_panel)
        self.assertIn('Second copy of the Kaboom! #5.', kaboom_panel)
        self.assertIn('Bought September 26, 2026 on Fanatics Collect.', kaboom_panel)
        self.assertIn('Value on Oct 1, 2026', kaboom_panel)
        self.assertIn('<dt>Item</dt><dd>$1,500.00</dd>', kaboom_panel)
        self.assertIn('<dt>Shipping</dt><dd>$25.00</dd>', kaboom_panel)
        self.assertIn('<dt>Tax</dt><dd>$116.25</dd>', kaboom_panel)
        self.assertIn('<dt>Fees</dt><dd>$47.60</dd>', kaboom_panel)
        self.assertIn('<dt>Total paid</dt><dd>$1,688.85</dd>', kaboom_panel)
        self.assertNotIn('sale at $1,500 is this slab', kaboom_panel)
        self.assertIn('PSA cert <a href="https://www.psacard.com/cert/139128313"', kaboom_panel)
        mojo = self.html.split('data-id="reese-2024-prizm-throwback-mojo-tb-ar"', 1)[1].split('</button>', 1)[0]
        self.assertIn('#TB-AR Mojo /25', mojo)
        self.assertIn('Paid <b>$503.22</b>', mojo)
        self.assertIn('Value <b>$346.00</b>', mojo)
        self.assertIn('badge down">-$157.22 (-31.2%)', mojo)
        mojo_panel = self.html.split('data-detail="reese-2024-prizm-throwback-mojo-tb-ar"', 1)[1].split('</article>', 1)[0]
        self.assertIn('Numbered /25', mojo_panel)
        self.assertIn('Exact serial is unknown. Still in the Fanatics vault, waiting to ship.', mojo_panel)
        self.assertIn('Bought September 19, 2026 on Fanatics Collect.', mojo_panel)
        self.assertIn('Value on Oct 3, 2026', mojo_panel)
        self.assertIn('<dt>Hammer</dt><dd>$390.00</dd>', mojo_panel)
        self.assertIn('<dt>Buyer&#x27;s premium</dt><dd>$78.00</dd>', mojo_panel)
        self.assertIn('<dt>Shipping</dt><dd>$7.00</dd>', mojo_panel)
        self.assertIn('<dt>Tax</dt><dd>$0.00</dd>', mojo_panel)
        self.assertIn('<dt>Fees</dt><dd>$28.22<span class="fee-note">Card fee plus vault retrieval.</span></dd>', mojo_panel)
        self.assertIn('<dt>Total paid</dt><dd>$503.22</dd>', mojo_panel)
        self.assertNotIn('$4.99', mojo_panel)
        self.assertNotIn('$30.23', mojo_panel)
        self.assertNotIn('$468.00', mojo_panel)
        self.assertNotIn('<dt>Item</dt>', mojo_panel)
        self.assertIn('Median of the 3 most recent PSA 10 sales on SportsCardsPro', mojo_panel)
        self.assertIn('PSA cert <a href="https://www.psacard.com/cert/117017224"', mojo_panel)

    def test_black_color_blast_has_no_back_and_breadcrumbs_stay_in_page(self):
        panel = self.html.split('data-detail="reese-2024-prizm-dp-black-color-blast-11"', 1)[1].split('</article>', 1)[0]
        self.assertEqual(panel.count('<img '), 1)
        self.assertNotIn('-back.webp', panel)
        crumbs = self.html.split('aria-label="Breadcrumb"', 1)[1].split('</nav>', 1)[0]
        self.assertIn('>Home</a>', crumbs)
        self.assertIn('href="/authors/ryan-moalemi/">Ryan Moalemi</a>', crumbs)
        self.assertIn('Ryan&#x27;s Angel Reese card collection', crumbs)
        self.assertNotIn('Ryan&#x27;s Angel Reese cards', crumbs)
        self.assertNotIn('>Angel Reese Cards<', crumbs)
        self.assertNotIn('target="_blank"', crumbs)
        self.assertIn('"name": "Home"', self.html)
        self.assertIn('"name": "Ryan Moalemi"', self.html)
        self.assertIn('"name": "Ryan\'s Angel Reese card collection"', self.html)

    def test_author_and_player_pages_link_here(self):
        author = (ROOT / 'authors' / 'ryan-moalemi' / 'index.html').read_text(encoding='utf-8')
        self.assertIn(f'href="{ROUTE}"', author)
        self.assertNotIn(f'href="{ROUTE}" target="_blank"', author)
        self.assertIn("<b>Ryan&#x27;s Angel Reese card collection</b>", author)
        self.assertNotIn("<b>Ryan&#x27;s Angel Reese cards</b>", author)
        self.assertNotIn('<b>Angel Reese cards</b>', author)
        player = (ROOT / 'wnba' / 'angel-reese' / 'index.html').read_text(encoding='utf-8')
        self.assertIn(cards.PLAYER_CALLOUT, player)
        self.assertNotIn("See Ryan's Angel Reese cards", player)
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
        self.assertIn(cards.PLAYER_CALLOUT, rebuilt)
        self.assertNotIn("See Ryan's Angel Reese cards", rebuilt)
        self.assertLessEqual(build_players.contextual_link_count(rebuilt), internal_links.MAX_PLAYER_LINKS)
        pages = (ROOT / 'pages-sitemap.xml').read_text(encoding='utf-8')
        index = (ROOT / 'sitemap.xml').read_text(encoding='utf-8')
        self.assertIn('https://fullcourtbuckets.com/authors/ryan-moalemi/ryans-angel-reese-cards/', pages)
        self.assertIn('https://fullcourtbuckets.com/pages-sitemap.xml', index)
        self.assertNotIn('https://fullcourtbuckets.com/authors/ryan-moalemi/ryans-angel-reese-cards/', index)
        players = (ROOT / 'player-sitemap.xml').read_text(encoding='utf-8')
        self.assertNotIn(ROUTE, players)
        hero = ROOT / 'images' / 'reese-cards' / 'angel-reese-hero.webp'
        self.assertTrue(hero.is_file())
        self.assertLess(hero.stat().st_size, 250_000)
        for name in (
            'reese-2024-prizm-dp-black-color-blast-11-front.webp',
            'reese-2024-rookie-royalty-kaboom-5-back.webp',
            'reese-2024-25-flawless-royalty-rpa-ar-gold-front.webp',
            'reese-2024-25-flawless-royalty-rpa-ar-gold-back.webp',
            'reese-2024-rookie-royalty-contenders-gold-2-front.webp',
            'reese-2024-rookie-royalty-contenders-gold-2-back.webp',
            'reese-2024-rookie-royalty-kaboom-5-copy-2-front.webp',
            'reese-2024-rookie-royalty-kaboom-5-copy-2-back.webp',
            'reese-2024-prizm-throwback-mojo-tb-ar-front.webp',
            'reese-2024-prizm-throwback-mojo-tb-ar-back.webp',
        ):
            photo = ROOT / 'images' / 'reese-cards' / name
            self.assertTrue(photo.is_file(), name)
            self.assertLess(photo.stat().st_size, 200_000, name)


FOLD_VIEWPORTS = (
    (1280, 720),
    (1366, 768),
    (1024, 760),
    (1440, 900),
    (390, 844),
    (360, 740),
)
FOLD_MEASURE = """() => {
  const hero = document.querySelector('.hero');
  const name = document.querySelector('#collection-title span:not(.owner-word):not(.cards-word)');
  const word = document.querySelector('#collection-title .cards-word');
  const line = document.querySelector('.hero-line');
  const photo = document.querySelector('.hero-photo');
  const box = (el) => {
    const r = el.getBoundingClientRect();
    return {top: r.top, bottom: r.bottom, height: r.height, width: r.width};
  };
  const photoStyle = getComputedStyle(photo);
  return {
    scrollY: window.scrollY,
    vh: window.innerHeight,
    hero: box(hero),
    name: box(name),
    cards: box(word),
    line: box(line),
    photo: box(photo),
    fit: photoStyle.objectFit,
    position: photoStyle.objectPosition,
  };
}"""


class ReeseHeroFoldTests(unittest.TestCase):
    """ANGEL REESE, CARDS, and the subtitle stay above the fold."""

    def test_title_block_is_above_the_fold(self):
        from playwright.sync_api import sync_playwright

        server = ThreadingHTTPServer(('127.0.0.1', 0), _QuietHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f'http://127.0.0.1:{server.server_address[1]}'
        failures = []
        try:
            with sync_playwright() as playwright:
                browser = _launch(playwright)
                try:
                    for width, height in FOLD_VIEWPORTS:
                        page = browser.new_page(viewport={'width': width, 'height': height})
                        page.goto(origin + ROUTE, wait_until='domcontentloaded')
                        page.evaluate("() => document.fonts.ready")
                        measured = page.evaluate(FOLD_MEASURE)
                        failures.extend(_fold_problems(width, height, measured))
                        page.close()
                finally:
                    browser.close()
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(failures, [])


class _QuietHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, format, *args):
        return


def _launch(playwright):
    args = ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
    try:
        return playwright.chromium.launch(args=args)
    except Exception:
        return playwright.chromium.launch(channel='chrome', args=args)


def _fold_problems(width, height, measured):
    problems = []
    label = f'{width}x{height}'
    if measured['scrollY'] != 0:
        problems.append(f'{label} scrolled')
    if measured['fit'] != 'cover':
        problems.append(f'{label} object-fit is {measured["fit"]}')
    position = measured['position']
    if 'top' not in position and not position.endswith('0%'):
        problems.append(f'{label} object-position is {position}')
    hero = measured['hero']
    photo = measured['photo']
    if hero['bottom'] > measured['vh'] + 1:
        problems.append(f'{label} hero bottom {hero["bottom"]:.1f} past {measured["vh"]}')
    if abs(photo['width'] - hero['width']) > 2 or abs(photo['height'] - hero['height']) > 2:
        problems.append(f'{label} photo does not cover the hero')
    for name in ('name', 'cards', 'line'):
        box = measured[name]
        if box['height'] < 8:
            problems.append(f'{label} {name} has no height')
        if box['top'] < -1:
            problems.append(f'{label} {name} starts above the viewport ({box["top"]:.1f})')
        if box['bottom'] > measured['vh'] + 1:
            problems.append(f'{label} {name} ends below the fold ({box["bottom"]:.1f} > {measured["vh"]})')
        if box['bottom'] > hero['bottom'] + 1:
            problems.append(f'{label} {name} is clipped by the hero')
    return problems


if __name__ == '__main__':
    unittest.main()
