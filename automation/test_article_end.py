"""Related links at the end of a news story are generated with the page."""
import json
import unittest
from pathlib import Path

import internal_links as links
import build_standings

ROOT = Path(__file__).resolve().parents[1]


def _articles():
    return json.loads((ROOT / 'articles.json').read_text(encoding='utf-8'))


class ArticleEndTests(unittest.TestCase):
    def test_series_preview_links_both_matchups_and_latest_news(self):
        articles = _articles()
        preview = next(article for article in articles if article['slug'] == 'semis-game-3-preview')
        series = links.series_articles(preview, articles)
        slugs = {article['slug'] for article in series}
        self.assertTrue(any('liberty' in slug or 'dream' in slug for slug in slugs))
        self.assertTrue(any('aces' in slug or 'valkyries' in slug for slug in slugs))
        self.assertNotIn('fever-aces-game-3-recap', slugs)
        page = (ROOT / 'news' / 'semis-game-3-preview' / 'index.html').read_text(encoding='utf-8')
        block = links.article_end_html(page, ROOT, preview, articles)
        self.assertIn('More from this series', block)
        self.assertIn('Latest news', block)
        latest = block.split('<section class="article-latest">', 1)[1].split('</section>', 1)[0]
        self.assertEqual(latest.count('<li>'), 3)
        players = block.split('<section class="article-players">', 1)[1]
        self.assertIn('target="_blank" rel="noopener"', players)
        self.assertNotIn('href="/news/', players)
        again = links.ensure_article_end(page + block, ROOT, preview, articles)
        self.assertEqual(again.count('class="article-end"'), 1)

    def test_a_one_off_story_skips_the_series_block(self):
        articles = _articles()
        story = next(article for article in articles if article['slug'] == 'wnba-expansion-teams')
        self.assertEqual(links.series_articles(story, articles), [])
        html_text = (ROOT / 'news' / 'wnba-expansion-teams' / 'index.html').read_text(encoding='utf-8')
        block = links.article_end_html(html_text, ROOT, story, articles)
        self.assertNotIn('More from this series', block)
        self.assertIn('<h2>Latest news</h2>', block)

    def test_couples_preloads_the_condensed_face(self):
        page = (ROOT / 'wnba' / 'couples' / 'index.html').read_text(encoding='utf-8')
        css = (ROOT / 'automation' / 'players.css').read_text(encoding='utf-8')
        self.assertIn('rel="preload" href="/assets/fonts/barlow-condensed-800.woff2"', page)
        self.assertIn('size-adjust:72%', css)
        self.assertIn('Barlow Condensed Fallback', css)
        self.assertTrue((ROOT / 'assets' / 'fonts' / 'barlow-condensed-800.woff2').is_file())

    def test_standings_has_one_heading_one_updated_line_and_a_series_box(self):
        box = build_standings.series_coverage_html(ROOT)
        self.assertIn('href="/news/semis-game-3-preview/"', box)
        self.assertIn('>Read the series coverage</a>', box)
        css = (ROOT / 'automation' / 'standings.css').read_text(encoding='utf-8')
        self.assertIn('width:min(1240px,calc(100% - 32px))', css)
        self.assertIn('nth-child(2){position:sticky;left:48px', css)
        table = (ROOT / 'automation' / 'players.css').read_text(encoding='utf-8')
        self.assertIn('border-collapse:separate', table)
        self.assertIn('mask-image:linear-gradient(to right,#000 0,#000 calc(100% - 32px),transparent)', table)


if __name__ == '__main__':
    unittest.main()
