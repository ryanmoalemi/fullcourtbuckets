"""Ryan's Angel Reese cards stay a generated personal page, not a news article."""
import json
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
        self.assertIn('Ryan&#x27;s Angel Reese cards | Full Court Buckets', self.html)
        self.assertIn('<h1 id="collection-title"><span class="owner-word">Ryan&#x27;s</span><span>Angel Reese</span><span class="cards-word">cards</span></h1>', self.html)
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
        self.assertIn('Ryan&#x27;s Angel Reese cards', crumbs)
        self.assertNotIn('>Angel Reese Cards<', crumbs)
        self.assertNotIn('target="_blank"', crumbs)
        self.assertIn('"name": "Home"', self.html)
        self.assertIn('"name": "Ryan Moalemi"', self.html)
        self.assertIn('"name": "Ryan\'s Angel Reese cards"', self.html)

    def test_author_and_player_pages_link_here(self):
        author = (ROOT / 'authors' / 'ryan-moalemi' / 'index.html').read_text(encoding='utf-8')
        self.assertIn(f'href="{ROUTE}"', author)
        self.assertNotIn(f'href="{ROUTE}" target="_blank"', author)
        self.assertIn("<b>Ryan&#x27;s Angel Reese cards</b>", author)
        self.assertNotIn('<b>Angel Reese cards</b>', author)
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
