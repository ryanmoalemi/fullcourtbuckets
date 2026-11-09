"""The shared team and player card is on every page stylesheet."""
import unittest
from pathlib import Path

import fcb_card
import site_nav

ROOT = Path(__file__).resolve().parents[1]


class FcbCardTests(unittest.TestCase):
    def test_shared_css_defines_the_card(self):
        css = (ROOT / 'assets' / 'site-nav.css').read_text(encoding='utf-8')
        self.assertEqual(css, site_nav.CSS_TEXT)
        for selector in ('.fcb-card', '.stat-tiles', '.stat-tile', '.card-credit', '.section-note'):
            self.assertIn(selector, css)

    def test_helper_emits_the_shared_classes(self):
        html = (
            fcb_card.card_open('prospect')
            + fcb_card.stat_tiles(fcb_card.stat_tile('8/8', 'Mocks'))
            + fcb_card.card_credit('Photo: Example')
            + fcb_card.card_close()
            + fcb_card.section_note('Methods sit here once.')
        )
        self.assertIn('class="fcb-card prospect"', html)
        self.assertNotIn('</article>', html)
        self.assertIn('class="stat-tiles"', html)
        self.assertIn('class="stat-tile"', html)
        self.assertIn('class="card-credit"', html)
        self.assertIn('class="section-note table-note"', html)

    def test_stat_paragraph_becomes_a_card_without_dropping_the_claim(self):
        sample = (
            '<p><a class="inline-link" href="/wnba/awak-kuier/" target="_blank" rel="noopener">Awak Kuier</a> '
            'played 41 games at 6.3 points, 3.9 rebounds and 1.1 assists per game '
            '(18.6 minutes, 50.8% from the field, 39.0% from three). '
            'The file has 4 regular seasons with at least one game (2021, 2022, 2023, 2026).</p>'
        )
        html = fcb_card.wrap_player_stat_cards(sample)
        self.assertIn('class="fcb-card"', html)
        self.assertIn('>6.3</b>', html)
        self.assertIn('>3.9</b>', html)
        self.assertIn('>1.1</b>', html)
        self.assertIn('>41</b>', html)
        self.assertIn('18.6 minutes, 50.8% from the field, 39.0% from three.', html)
        self.assertIn('The file has 4 regular seasons with at least one game (2021, 2022, 2023, 2026).', html)

    def test_lottery_page_uses_the_card(self):
        page = (ROOT / 'wnba' / 'draft-lottery-2027' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('class="fcb-card need-card"', page)
        self.assertIn('class="stat-tiles need-tiles"', page)
        self.assertIn('class="section-note table-note"', page)

    def test_data_posts_keep_their_numbers_on_cards(self):
        reese = (ROOT / 'news/angel-reese-always-this-good-data/index.html').read_text(encoding='utf-8')
        self.assertIn('>16.4</b>', reese)
        self.assertIn('>12.1</b>', reese)
        self.assertIn('521 rebounds', reese)
        mitchell = (ROOT / 'news/kelsey-mitchell-2027-free-agency-cap/index.html').read_text(encoding='utf-8')
        self.assertIn('>$45,672</b>', mitchell)
        self.assertIn('>-$1,010,600</b>', mitchell)
        self.assertIn('averaged 24.7 points', mitchell)
        self.assertIn('id="cap-table"', mitchell)
        cards = (ROOT / 'news/top-10-womens-college-basketball-cards-to-collect-2026/index.html').read_text(encoding='utf-8')
        self.assertIn('>$24,404</b>', cards)
        self.assertIn('id="juju-watkins"', cards)
        self.assertIn('$20,003', cards)

    def test_card_line_uses_the_shared_classes(self):
        import publish_articles
        md = (
            'Lead.\n\n'
            '!card: Sarah Strong | Junior forward | 39=PTS | 15-26=FG | 10=REB | '
            'Career high on the [official box](https://uconnhuskies.com/). | '
            'Box: UConn, Nov. 8, 2026. | \n'
            '!note: Tiles are the official final box. One note for the section.\n'
        )
        html = publish_articles.body_html(md)
        self.assertIn('class="fcb-card"', html)
        self.assertIn('class="stat-tiles"', html)
        self.assertIn('>39</b><span>PTS</span>', html)
        self.assertIn('class="av"', html)
        self.assertIn('class="card-credit"', html)
        self.assertIn('class="section-note table-note"', html)
        self.assertNotIn('<article', html)
        self.assertNotIn('</article>', html)

    def test_story_cards_do_not_close_the_article(self):
        import publish_articles
        page = (
            '<article class="article"><p>Old.</p>'
            '<article class="fcb-card"><p>Card</p></article>'
            '<p>Still the story.</p></article><footer>Keep</footer>'
        )
        fresh = '<article class="article"><div class="fcb-card"><p>New</p></div></article>'
        updated = publish_articles.replace_article(page, fresh)
        self.assertEqual(updated, fresh + '<footer>Keep</footer>')
        for rel in (
            'news/wnba-free-agents-2027/index.html',
            'news/kelsey-mitchell-2027-free-agency-cap/index.html',
            'news/angel-reese-always-this-good-data/index.html',
        ):
            html = (ROOT / rel).read_text(encoding='utf-8')
            self.assertEqual(html.count('<article'), 1, rel)
            self.assertEqual(html.count('</article>'), 1, rel)
            self.assertNotIn('<article class="fcb-card"', html, rel)
