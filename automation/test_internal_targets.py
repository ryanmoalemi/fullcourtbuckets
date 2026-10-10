"""Every internal link on a published page must resolve to a file in the site."""
import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

from link_graph import SITEMAP_NAMES, file_for_url, iter_html, normalize_href, page_url

ROOT = Path(__file__).resolve().parents[1]


class LinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.refs = []
        self._ld = False
        self._buf = []

    def handle_starttag(self, tag, attrs):
        self._start(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, attrs)

    def _start(self, tag, attrs):
        attr = {key.lower(): (value or '') for key, value in attrs}
        if tag == 'script' and 'ld+json' in attr.get('type', ''):
            self._ld = True
            self._buf = []
        if tag == 'a' and attr.get('href'):
            self.refs.append(attr['href'])
        if tag == 'link' and attr.get('href') and 'canonical' in attr.get('rel', '').lower():
            self.refs.append(attr['href'])
        if tag == 'meta' and attr.get('property', '').lower() == 'og:url' and attr.get('content'):
            self.refs.append(attr['content'])
        if tag == 'meta' and attr.get('http-equiv', '').lower() == 'refresh':
            match = re.search(r'url=([^;\"\'\s]+)', attr.get('content', ''), re.I)
            if match:
                self.refs.append(match.group(1))

    def handle_endtag(self, tag):
        if tag == 'script' and self._ld:
            self._ld = False
            raw = ''.join(self._buf).strip()
            if not raw:
                return
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                self.refs.append('__invalid_jsonld__')
                return
            self._walk(data)

    def handle_data(self, data):
        if self._ld:
            self._buf.append(data)

    def _walk(self, node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ('url', '@id', 'item', 'contentUrl') and isinstance(value, str):
                    self.refs.append(value)
                else:
                    self._walk(value)
        elif isinstance(node, list):
            for value in node:
                self._walk(value)


class InternalTargetTests(unittest.TestCase):
    def test_internal_links_resolve(self):
        broken = []
        for path in iter_html(ROOT):
            page = page_url(path.relative_to(ROOT))
            parser = LinkExtractor()
            parser.feed(path.read_text(encoding='utf-8', errors='replace'))
            rel = path.relative_to(ROOT).as_posix()
            for href in parser.refs:
                if href == '__invalid_jsonld__':
                    broken.append(f'{rel} has JSON-LD that is not valid JSON')
                    continue
                target = normalize_href(href, page)
                if not target:
                    continue
                if file_for_url(ROOT, target) is None:
                    broken.append(f'{rel} -> {target}')
        for name in SITEMAP_NAMES:
            sitemap = ROOT / name
            if not sitemap.is_file():
                continue
            for loc in re.findall(r'<loc>\s*([^<]+?)\s*</loc>', sitemap.read_text(encoding='utf-8')):
                target = normalize_href(loc.strip(), '/')
                if target and file_for_url(ROOT, target) is None:
                    broken.append(f'{name} -> {target}')
        self.assertEqual(broken, [])

    def test_old_player_urls_redirect_to_wnba_profiles(self):
        import internal_links as links
        index = json.loads((ROOT / 'data' / 'wnba' / 'players-index.json').read_text(encoding='utf-8'))
        published = {entry['slug'] for entry in index['players']}
        published |= links.wnba_player_slugs(ROOT)
        expected = links.legacy_player_redirect_files(published)
        self.assertIn('players/index.html', expected)
        self.assertIn('/wnba/', expected['players/index.html'])
        for slug in ('nia-brodie', 'stephanie-white'):
            stub = expected[f'players/{slug}/index.html']
            self.assertIn('https://fullcourtbuckets.com/wnba/"', stub)
            self.assertNotIn(f'/wnba/{slug}/', stub)
        for relative, content in expected.items():
            path = ROOT / relative
            self.assertTrue(path.is_file(), relative)
            self.assertEqual(path.read_text(encoding='utf-8'), content)
            self.assertNotIn('G-ZJK92LK3XT', content)
        linked = []
        for path in iter_html(ROOT):
            rel = path.relative_to(ROOT).as_posix()
            if rel.startswith('players/'):
                continue
            text = path.read_text(encoding='utf-8', errors='replace')
            if 'href="/players/' in text or 'href="/players"' in text:
                linked.append(rel)
        self.assertEqual(linked, [])

    def test_every_wnba_player_has_players_redirect(self):
        self.assertEqual(self._missing_player_redirects(), [])

    @staticmethod
    def _missing_player_redirects():
        import internal_links as links
        missing = []
        for slug in sorted(links.wnba_player_slugs(ROOT)):
            path = ROOT / 'players' / slug / 'index.html'
            expected = links.permanent_redirect(f'{links.BASE}/wnba/{slug}/')
            if not path.is_file() or path.read_text(encoding='utf-8') != expected:
                missing.append(slug)
        return missing
