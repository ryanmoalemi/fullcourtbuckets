"""Built pages must not send readers to raw API or JSON endpoints."""
import html
import re
import unittest
from pathlib import Path
from urllib.parse import unquote, urlparse

from link_graph import iter_html

ROOT = Path(__file__).resolve().parents[1]
ANCHOR = re.compile(r'<a\b[^>]*>', re.I)
HREF = re.compile(r"""href\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
PLAYER_DATA = re.compile(r'^/data/wnba/players/[a-z0-9-]+\.json$')
OWN_HOSTS = {'fullcourtbuckets.com', 'www.fullcourtbuckets.com'}


def is_api_or_json_href(href: str) -> bool:
    """True for machine endpoints such as site.api.espn.com or a remote .json URL.

    The published player-data download at /data/wnba/players/<slug>.json is a
    first-party file labeled "View player data", so it is not treated as an API link.
    """
    value = html.unescape(href or '').strip()
    if not value or value.startswith(('#', 'mailto:', 'tel:', 'javascript:')):
        return False
    parsed = urlparse(value)
    host = (parsed.hostname or '').lower()
    path = unquote(parsed.path or '')
    if host in OWN_HOSTS:
        path_only = path if path.startswith('/') else f'/{path}'
        if PLAYER_DATA.match(path_only):
            return False
    elif not host and PLAYER_DATA.match(path):
        return False
    labels = host.split('.') if host else []
    if 'api' in labels:
        return True
    parts = [part for part in path.lower().split('/') if part]
    if 'api' in parts or 'apis' in parts:
        return True
    if path.lower().split('?', 1)[0].endswith('.json'):
        return True
    query = (parsed.query or '').lower()
    if 'format=json' in query or query.endswith('.json'):
        return True
    return False


class NoApiHrefTests(unittest.TestCase):
    def test_detector_flags_api_and_json_endpoints(self):
        self.assertTrue(is_api_or_json_href(
            'https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/summary?event=401918022'
        ))
        self.assertTrue(is_api_or_json_href('https://api.example.com/v1/games'))
        self.assertTrue(is_api_or_json_href('https://example.com/feeds/scores.json'))
        self.assertTrue(is_api_or_json_href('/api/wnba-standings'))
        self.assertFalse(is_api_or_json_href('https://www.espn.com/wnba/boxscore/_/gameId/401918015'))
        self.assertFalse(is_api_or_json_href('https://www.espn.com/wnba/playbyplay/_/gameId/401918022'))
        self.assertFalse(is_api_or_json_href('https://www.espn.com/wnba/game/_/gameId/401918022'))
        self.assertFalse(is_api_or_json_href('/data/wnba/players/caitlin-clark.json'))
        self.assertFalse(is_api_or_json_href('/wnba/caitlin-clark/'))

    def test_built_pages_do_not_link_to_api_or_json_endpoints(self):
        offenders = []
        for path in iter_html(ROOT):
            text = path.read_text(encoding='utf-8')
            for tag in ANCHOR.finditer(text):
                match = HREF.search(tag.group(0))
                if not match:
                    continue
                href = match.group(1) if match.group(1) is not None else match.group(2)
                if is_api_or_json_href(href):
                    offenders.append(f'{path.relative_to(ROOT)} -> {html.unescape(href)}')
        self.assertEqual(offenders, [])

    def test_series_breakdown_sources_are_human_espn_pages(self):
        page = (ROOT / 'news/aces-fever-series-breakdown/index.html').read_text(encoding='utf-8')
        self.assertNotIn('site.api.espn.com', page)
        expected = {
            'ESPN play-by-play': 'https://www.espn.com/wnba/playbyplay/_/gameId/401918022',
            'Game 1 box': 'https://www.espn.com/wnba/boxscore/_/gameId/401918015',
            'Game 2 box': 'https://www.espn.com/wnba/boxscore/_/gameId/401918018',
            'Game 3 box': 'https://www.espn.com/wnba/boxscore/_/gameId/401918022',
            'ESPN box': 'https://www.espn.com/wnba/boxscore/_/gameId/401918022',
            'G1': 'https://www.espn.com/wnba/boxscore/_/gameId/401918015',
            'G2': 'https://www.espn.com/wnba/boxscore/_/gameId/401918018',
            'G3': 'https://www.espn.com/wnba/boxscore/_/gameId/401918022',
        }
        for label, url in expected.items():
            self.assertIn(
                f'<a href="{url}" target="_blank" rel="noopener">{label}</a>',
                page,
                label,
            )
        self.assertEqual(page.count('ESPN play-by-play'), 2)
        self.assertEqual(page.count('>ESPN box</a>'), 2)
