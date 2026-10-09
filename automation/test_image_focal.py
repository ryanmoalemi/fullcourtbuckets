"""Every story crop has a focal point, or the top-biased default."""
import json
import re
import unittest
from pathlib import Path

import internal_links as links
import news_heroes as heroes

ROOT = Path(__file__).resolve().parents[1]


def _articles():
    return json.loads((ROOT / 'articles.json').read_text(encoding='utf-8'))


class ImageFocalTests(unittest.TestCase):
    def test_default_favors_the_top(self):
        self.assertEqual(links.DEFAULT_IMAGE_FOCAL, 'center 20%')
        self.assertEqual(heroes.DEFAULT_FOCAL, 'center 20%')
        self.assertEqual(links.lead_focal({}), 'center 20%')
        self.assertNotEqual(links.lead_focal({}), 'center')
        self.assertEqual(heroes.parse_focal(None), (0.5, 0.20))

    def test_every_article_has_a_focal_point_or_the_default(self):
        home = (ROOT / 'index.html').read_text(encoding='utf-8')
        hub = (ROOT / 'news' / 'index.html').read_text(encoding='utf-8')
        author = (ROOT / 'authors' / 'ryan-moalemi' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('object-position:center 20%', home)
        self.assertIn('object-position:center 20%', hub)
        self.assertIn('object-position:center 20%', author)
        for article in _articles():
            slug = article['slug']
            raw = str(article.get('imageFocal') or '').strip()
            if raw:
                self.assertRegex(raw, heroes.FOCAL_RE, slug)
                focal = heroes.focal_for(article)
                self.assertEqual(focal, raw.lower(), slug)
            else:
                focal = heroes.focal_for(article)
                self.assertEqual(focal, heroes.DEFAULT_FOCAL, slug)
            token = f'object-position:{focal}'
            for label, page in (('hub', hub), ('home', home), ('author', author)):
                self.assertIn(article['image'], page, f'{slug} {label}')
            story = (ROOT / 'news' / slug / 'index.html').read_text(encoding='utf-8')
            self.assertIn(token, story, slug)
            og = str(article.get('imageOg') or '')
            self.assertTrue(og.endswith(('og-1200.webp', 'og.webp')), slug)
            self.assertIn(links.BASE + og, story, slug)
            self.assertTrue((ROOT / og.lstrip('/')).is_file(), slug)
            width = int(article['imageOgWidth'])
            height = int(article['imageOgHeight'])
            self.assertAlmostEqual(width / height, heroes.OG_ASPECT, places=2, msg=slug)

    def test_listing_cards_use_the_focal_point(self):
        article = {
            'slug': 'future-photo',
            'url': '/news/future-photo/',
            'title': 'Future',
            'description': 'Later.',
            'category': 'WNBA',
            'date': '2026-10-02',
            'image': '/images/articles/future.webp',
            'imageAlt': 'A player',
            'imageFocal': 'center 8%',
        }
        card = links._story_card(article)
        self.assertIn('style="object-position:center 8%"', card)
        item = links._news_list_item(article)
        self.assertIn('style="object-position:center 8%"', item)
        photo = links._featured_photo(article)
        self.assertIn('style="object-position:center 8%"', photo)
        bare = dict(article)
        bare.pop('imageFocal')
        self.assertIn('style="object-position:center 20%"', links._story_card(bare))

    def test_blank_photo_falls_back_without_a_face(self):
        from PIL import Image

        image = Image.new('RGB', (400, 600), (30, 30, 30))
        self.assertEqual(heroes.suggest_focal(image), 'center 20%')

    def test_team_news_thumbnail_uses_the_focal_point(self):
        html_text = links.team_news_html(ROOT, 'atlanta-dream')
        self.assertIn('class="team-news-item"', html_text)
        self.assertIn('object-position:', html_text)
        self.assertNotIn('target="_blank"', html_text)
        self.assertIn('href="/news/angel-reese-game-2-stats-liberty-dream-semis/"', html_text)
