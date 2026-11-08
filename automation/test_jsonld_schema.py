"""NewsArticle, Dataset, and BreadcrumbList checks for published pages."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import breadcrumbs
import jsonld_schema
import site_nav

ROOT = Path(__file__).resolve().parents[1]
JSONLD_RE = re.compile(r'<script\b[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
NOINDEX_RE = re.compile(r'name="robots"[^>]+content="[^"]*noindex', re.I)
CSV_RE = re.compile(r'href="([^"]+\.csv)"', re.I)


def _nodes(html: str):
    found = []

    def walk(node):
        if isinstance(node, dict):
            kind = node.get('@type')
            kinds = kind if isinstance(kind, list) else [kind]
            for name in kinds:
                if isinstance(name, str):
                    found.append((name, node))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for raw in JSONLD_RE.findall(html):
        walk(json.loads(raw))
    return found


class NewsArticleTests(unittest.TestCase):
    def test_every_news_page_names_ryan_and_both_dates(self):
        missing = []
        for path in sorted((ROOT / 'news').glob('*/index.html')):
            html = path.read_text(encoding='utf-8')
            if NOINDEX_RE.search(html) or 'http-equiv="refresh"' in html:
                continue
            articles = [node for kind, node in _nodes(html) if kind == 'NewsArticle']
            if not articles:
                missing.append(path.parent.name + ' missing NewsArticle')
                continue
            node = articles[0]
            author = node.get('author') or {}
            if isinstance(author, list):
                author = author[0] if author else {}
            if not node.get('datePublished') or not node.get('dateModified'):
                missing.append(path.parent.name + ' missing a date')
            if isinstance(author, dict) and author.get('name') != 'Ryan Moalemi':
                missing.append(path.parent.name + ' author ' + str(author.get('name')))
        self.assertEqual(missing, [])

    def test_date_modified_falls_back_to_date_published(self):
        html = '<script type="application/ld+json">{"@type":"NewsArticle","datePublished":"2026-10-21"}</script>'
        updated = jsonld_schema.fill_newsarticle_dates(html)
        self.assertIn('"dateModified": "2026-10-21"', updated)


class DatasetTests(unittest.TestCase):
    def test_csv_pages_publish_dataset_downloads(self):
        missing = []
        for path in ROOT.rglob('index.html'):
            rel = path.relative_to(ROOT).as_posix()
            if rel.startswith(('automation/', 'portrait')):
                continue
            html = path.read_text(encoding='utf-8', errors='replace')
            if NOINDEX_RE.search(html) or not CSV_RE.search(html):
                continue
            datasets = [node for kind, node in _nodes(html) if kind == 'Dataset']
            if not datasets:
                missing.append(rel)
                continue
            distribution = datasets[0].get('distribution')
            rows = distribution if isinstance(distribution, list) else [distribution]
            urls = [str((row or {}).get('contentUrl') or '') for row in rows if isinstance(row, dict)]
            if not any(url.endswith('.csv') for url in urls):
                missing.append(rel + ' distribution')
        self.assertEqual(missing, [])


class BreadcrumbTests(unittest.TestCase):
    def test_team_player_and_news_pages_have_breadcrumb_lists(self):
        samples = [
            ROOT / 'wnba' / 'teams' / 'atlanta-dream' / 'index.html',
            ROOT / 'wnba' / 'aja-wilson' / 'index.html',
            ROOT / 'news' / 'dream-valkyries-finals-game-7-recap' / 'index.html',
        ]
        for path in samples:
            kinds = {kind for kind, _node in _nodes(path.read_text(encoding='utf-8'))}
            self.assertIn('BreadcrumbList', kinds, path)


class MobileTableTests(unittest.TestCase):
    def test_phone_tables_scroll_with_a_hint_and_a_sticky_first_column(self):
        css = (ROOT / 'assets' / 'site-nav.css').read_text(encoding='utf-8')
        js = (ROOT / 'assets' / 'site-nav.js').read_text(encoding='utf-8')
        self.assertIn('.table-scroll', js)
        self.assertIn('table-scroll-hint', js)
        phone = css.split('Phone data tables', 1)[1][:700]
        self.assertIn('position:sticky', phone)
        self.assertIn('.article .table-wrap th:first-child', phone)
        before = css.split('Phone data tables', 1)[0]
        self.assertNotIn('.article .table-wrap th:first-child{position:sticky', before)
        self.assertEqual(css, site_nav.CSS_TEXT)
        self.assertIn('@media (max-width:640px)', css)
        self.assertIn('td.is-balance', css)
        self.assertIn('content:" shortfall"', css)
        self.assertIn('data-label', js)
        self.assertIn('roster-face', js)


class MethodsPageTests(unittest.TestCase):
    def test_methods_page_is_linked_and_does_not_invent_a_dash(self):
        page = (ROOT / 'methods' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('<h1>How we calculate</h1>', page)
        self.assertIn('729 points in 43 games is 17.0', page)
        self.assertIn('https://www.wnba.com/standings', page)
        self.assertIn('CUUR0000SA0', page)
        self.assertNotIn('\u2014', page)
        self.assertIn('BreadcrumbList', page)
        self.assertIn('href="/methods/"', site_nav.FOOTER_HTML)
        menu = site_nav.render(site_nav.build_menu(ROOT), '/__none__')
        self.assertIn('href="/methods/"', menu)
        self.assertIn('https://fullcourtbuckets.com/methods/', (ROOT / 'pages-sitemap.xml').read_text(encoding='utf-8'))
        self.assertIn('href="/methods/"', (ROOT / 'sitemap' / 'index.html').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
