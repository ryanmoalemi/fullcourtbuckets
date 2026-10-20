"""Site search: index covers every page type; engine handles stems, typos and ranking."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import search_index  # noqa: E402
import site_nav  # noqa: E402

NODE = shutil.which('node')


def run_queries(root: Path, *queries: str) -> dict:
    out = subprocess.run([NODE, str(HERE / 'search_harness.js'), str(root), *queries],
                         check=True, capture_output=True, text=True, timeout=60).stdout
    return {r['q']: r for r in json.loads(out)}


PAGE = ('<!doctype html><html><head><title>{title} | Full Court Buckets</title>'
        '<meta name="description" content="{desc}"><meta name="robots" content="index,follow"></head>'
        '<body><header>nav</header><main><h1>{title}</h1><h2>{h2}</h2><p>{body}</p></main></body></html>')


class SearchIndexTest(unittest.TestCase):
    def test_index_on_disk_is_current_and_covers_types(self):
        on_disk = json.loads((ROOT / 'search-index.json').read_text(encoding='utf-8'))
        self.assertEqual(on_disk, search_index.build(ROOT))
        kinds = {item['k'] for item in on_disk['items']}
        self.assertTrue({'Article', 'Player', 'Team', 'Tracker', 'Data', 'Couple', 'Game'} <= kinds, kinds)
        urls = {item['u'] for item in on_disk['items']}
        for url in ('/standings/', '/wnba/couples/', '/wnba/aja-wilson/', '/wnba/teams/atlanta-dream/'):
            self.assertIn(url, urls)
        self.assertNotIn('/search/', urls)
        for item in on_disk['items']:
            if item.get('i'):
                self.assertTrue((ROOT / item['i'].lstrip('/')).is_file(), item['i'])
        aja = next(i for i in on_disk['items'] if i['u'] == '/wnba/aja-wilson/')
        self.assertEqual(aja.get('c'), 1)
        self.assertLess((ROOT / 'search-index.json').stat().st_size, 900_000)

    def test_every_page_uses_new_search_markup(self):
        self.assertNotIn(site_nav.OLD_SEARCH_HTML, site_nav.upgrade_search_markup(site_nav.OLD_SEARCH_HTML))
        for rel, path in search_index.iter_pages(ROOT):
            html = path.read_text(encoding='utf-8')
            self.assertNotIn(site_nav.OLD_SEARCH_HTML, html, rel)
        self.assertTrue((ROOT / 'search' / 'index.html').is_file())
        self.assertIn('id="search-page"', (ROOT / 'search' / 'index.html').read_text(encoding='utf-8'))


@unittest.skipUnless(NODE, 'node not installed')
class SearchEngineTest(unittest.TestCase):
    def test_live_index_queries(self):
        r = run_queries(ROOT, 'aja wilsn', 'aja wilson', 'rhyne howrd', 'standings', 'atlanta dream')
        self.assertEqual(r['aja wilsn']['suggestion'], "A'ja Wilson")
        self.assertEqual(r['aja wilsn']['top'][0]['u'], '/wnba/aja-wilson/')
        self.assertEqual(r['aja wilson']['top'][0]['u'], '/wnba/aja-wilson/')
        self.assertEqual(r['rhyne howrd']['suggestion'], 'Rhyne Howard')
        self.assertEqual(r['standings']['top'][0]['u'], '/standings/')
        self.assertEqual(r['atlanta dream']['top'][0]['u'], '/wnba/teams/atlanta-dream/')
        if (ROOT / 'wnba' / 'owners' / 'index.html').is_file():
            r = run_queries(ROOT, 'wnba owner')
            self.assertTrue(r['wnba owner']['top'][0]['u'].startswith('/wnba/owners/'))

    def test_owner_stem_and_type_on_fixture_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pages = {
                'wnba/owners/index.html': ('WNBA owners: who owns every team', 'Every WNBA team owner and price paid.', 'Ownership groups', 'Owners list'),
                'news/some-story/index.html': ('Valkyries beat Aces', 'Game story.', 'Recap', 'The owner sat courtside.'),
                'wnba/aja-wilson/index.html': ("A'ja Wilson", 'Profile.', 'Stats', 'Las Vegas Aces center.'),
            }
            for rel, (title, desc, h2, body) in pages.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(PAGE.format(title=title, desc=desc, h2=h2, body=body), encoding='utf-8')
            search_index.write(root)
            items = json.loads((root / 'search-index.json').read_text())['items']
            self.assertEqual({i['u']: i['k'] for i in items}['/wnba/owners/'], 'Owner')
            r = run_queries(root, 'wnba owner', 'owners', 'aja wilsn')
            self.assertEqual(r['wnba owner']['top'][0]['u'], '/wnba/owners/')
            self.assertEqual(r['owners']['top'][0]['u'], '/wnba/owners/')
            self.assertEqual(r['aja wilsn']['suggestion'], "A'ja Wilson")


if __name__ == '__main__':
    unittest.main()
