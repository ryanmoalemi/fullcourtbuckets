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
        ordered = sorted(_articles(), key=lambda article: article.get('date') or '', reverse=True)
        on_home = {article['slug'] for article in ordered[:1 + links.MORE_STORY_LIMIT]}
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
            for label, page in (('hub', hub), ('author', author)):
                self.assertIn(article['image'], page, f'{slug} {label}')
            if slug in on_home:
                if slug == '2026-wnba-finals-ratings-tracker':
                    card = '/images/articles/2026-wnba-finals-ratings-tracker/matchup-1200.webp'
                    self.assertIn(card, home, slug)
                    featured = home.split('id="featured-story"', 1)[1].split('</a>', 1)[0]
                    self.assertIn('class="article-visual"', featured)
                    if '2026-wnba-finals-ratings-tracker' in featured:
                        self.assertIn('matchup-1200.webp', featured)
                    self.assertNotIn('ratings-sheet.webp', featured)
                    self.assertNotIn('social-card.webp', featured)
                else:
                    self.assertIn(article['image'], home, f'{slug} home')
            story = (ROOT / 'news' / slug / 'index.html').read_text(encoding='utf-8')
            if slug == '2026-wnba-finals-ratings-tracker':
                social = '/images/articles/2026-wnba-finals-ratings-tracker/matchup-og.webp'
                page_image = '/images/articles/2026-wnba-finals-ratings-tracker/matchup-1200.webp'
                self.assertEqual(article.get('image'), page_image)
                self.assertEqual((article.get('imageWidth'), article.get('imageHeight')), (1200, 675))
                self.assertEqual(article.get('imageOg'), social)
                self.assertEqual((article.get('imageOgWidth'), article.get('imageOgHeight')), (1200, 630))
                self.assertIn(links.BASE + social, story)
                body = story.split('<article', 1)[1].split('</article>', 1)[0]
                self.assertNotIn('matchup-1200.webp', body)
                self.assertNotIn('tracker-matchup', body)
                self.assertNotIn('social-card.webp', body)
                self.assertNotIn('og-1200.webp', story)
                self.assertNotIn('lead-photo', body)
                continue
            self.assertIn(token, story, slug)
            og = str(article.get('imageOg') or '')
            self.assertTrue(og.endswith(('og-1200.jpg', 'og.jpg')), slug)
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
