"""The New bar matches the newest published article on every page."""
import re
import unittest
from pathlib import Path

import internal_links as links
import site_nav
from link_graph import file_for_url, iter_html

ROOT = Path(__file__).resolve().parents[1]
GAME7 = 'Game 7 recap: Valkyries 68, Dream 63 at Chase Center'


def _exists(url: str) -> bool:
    path = url.split('#', 1)[0]
    return path.startswith('/') and file_for_url(ROOT, path) is not None


class NowBarTests(unittest.TestCase):
    def test_shared_value_is_the_newest_published_article(self):
        articles = links.load_articles(ROOT)
        item = links.latest_published_article(articles, ROOT)
        self.assertIsNotNone(item)
        data = site_nav.load_now()
        self.assertEqual(data['url'], item['url'])
        self.assertEqual(data['text'], item['text'])
        self.assertEqual(data['date'], item['date'])
        self.assertNotIn('tonight', data['text'].lower())
        self.assertNotIn('\u2014', data['text'])
        self.assertNotIn(GAME7, data['text'])
        self.assertTrue(_exists(data['url']), data['url'])
        self.assertIn(item['title'], data['text'])
        if item['description'] and item['description'].casefold() not in item['title'].casefold():
            self.assertIn(item['description'], data['text'])
        bar = site_nav.now_bar_html()
        self.assertNotIn('data-expires', bar)
        self.assertNotIn('data-fallback', bar)
        self.assertIn(f'href="{item["url"]}"', bar)
        news = (ROOT / 'news' / 'index.html').read_text(encoding='utf-8')
        first = re.search(r'<a class="news-item" href="([^"]+)"', news)
        self.assertIsNotNone(first)
        self.assertEqual(first.group(1), item['url'])

    def test_same_day_clock_time_beats_a_date_only_value(self):
        articles = [
            {'slug': 'morning', 'title': 'Morning story', 'description': 'Early dek.', 'date': '2026-11-07'},
            {
                'slug': 'evening',
                'title': 'Evening story',
                'description': 'Late dek.',
                'date': '2026-11-07T22:05:38-08:00',
            },
        ]
        item = links.latest_published_article(articles)
        self.assertEqual(item['slug'], 'evening')
        self.assertEqual(item['text'], 'Evening story. Late dek.')

    def test_equal_publish_instants_prefer_the_later_edit_then_catalog_order(self):
        articles = [
            {'slug': 'first-merged', 'title': 'First merged', 'description': 'Kept.', 'date': '2026-11-01'},
            {
                'slug': 'edited',
                'title': 'Edited later',
                'description': 'Updated dek.',
                'date': '2026-11-01',
                'dateModified': '2026-11-02T15:00:00-08:00',
            },
            {'slug': 'also-plain', 'title': 'Also plain', 'description': 'Later row.', 'date': '2026-11-01'},
        ]
        self.assertEqual(links.latest_published_article(articles)['slug'], 'edited')
        plain = [articles[0], articles[2]]
        # The publisher inserts a new equal-date story first, so the earlier row wins.
        self.assertEqual(links.latest_published_article(plain)['slug'], 'first-merged')

    def test_drafts_unpublished_and_noindex_are_skipped(self):
        articles = [
            {'slug': 'secret-draft', 'title': 'Secret draft', 'description': 'Hidden.', 'date': '2026-11-09', 'draft': True},
            {'slug': 'held', 'title': 'Held back', 'description': 'Hidden.', 'date': '2026-11-08', 'status': 'unpublished'},
            {'slug': 'quiet', 'title': 'Quiet page', 'description': 'Hidden.', 'date': '2026-11-08', 'robots': 'noindex'},
            {'slug': 'live', 'title': 'Live story', 'description': 'Shown.', 'date': '2026-11-01'},
        ]
        self.assertEqual(links.latest_published_article(articles)['slug'], 'live')

    def test_missing_or_noindex_pages_are_skipped_when_the_site_is_checked(self):
        articles = [
            {'slug': 'not-a-real-published-story', 'title': 'Missing page', 'description': 'No file.', 'date': '2026-11-09'},
            {'slug': 'kelsey-mitchell-2027-free-agency-cap', 'title': 'Real story', 'description': 'On the site.', 'date': '2026-11-01'},
        ]
        item = links.latest_published_article(articles, ROOT)
        self.assertEqual(item['slug'], 'kelsey-mitchell-2027-free-agency-cap')

    def test_every_page_has_the_shared_bar(self):
        expected = site_nav.now_bar_html()
        self.assertIn(site_nav.load_now()['url'], expected)
        bad = []
        leftover = []
        for path in iter_html(ROOT):
            html = path.read_text(encoding='utf-8', errors='ignore')
            if GAME7 in html:
                leftover.append(str(path.relative_to(ROOT)))
            if 'site-header' not in html:
                continue
            bars = site_nav.NOW_RE.findall(html)
            if bars != [expected]:
                bad.append(str(path.relative_to(ROOT)))
                continue
            href = re.search(r'<a href="([^"]+)"', bars[0])
            if not href or not _exists(href.group(1)):
                bad.append(str(path.relative_to(ROOT)) + ' (link)')
        self.assertEqual(leftover, [])
        self.assertEqual(bad, [])


if __name__ == '__main__':
    unittest.main()
