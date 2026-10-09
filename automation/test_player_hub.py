"""Player hub layout and the profile count that the sitemap already uses."""
import html
import json
from pathlib import Path
import re
import unittest

import build_players as b

ROOT = Path(__file__).resolve().parents[1]
THIN = (
    'deja-kelly',
    'elena-buenavida',
    'elizabeth-balogun',
    'kamila-borkowska',
    'maria-gakdeng',
    'matilde-villa-270867',
)


def _faq_pairs(html_text: str):
    block = html_text.split('id="faq"', 1)[1].split('</section>', 1)[0]
    questions = [html.unescape(re.sub(r'<[^>]+>', '', q)) for q in re.findall(r'<h3>(.*?)</h3>', block, re.S)]
    answers = []
    for paragraph in re.findall(r'<p>(.*?)</p>', block, re.S):
        answers.append(html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', paragraph)).strip()))
    payload = re.search(r'<script type="application/ld\+json">(.*?)</script>', html_text, re.S)
    data = json.loads(payload.group(1))
    entity = next(node for node in data['@graph'] if node.get('@type') == 'FAQPage')
    schema = [
        (item['name'], re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', item['acceptedAnswer']['text'])).strip())
        for item in entity['mainEntity']
    ]
    visible = list(zip(questions, answers))
    return visible, schema


class PlayerHubTests(unittest.TestCase):
    def test_hub_lists_the_same_players_as_the_sitemap(self):
        hub = (ROOT / 'wnba' / 'index.html').read_text(encoding='utf-8')
        sitemap = (ROOT / 'player-sitemap.xml').read_text(encoding='utf-8')
        hub_hrefs = set(re.findall(r'class="player-row" href="(/wnba/[^"]+/)"', hub))
        locs = set(re.findall(r'<loc>https://fullcourtbuckets.com(/wnba/[^<]+)</loc>', sitemap))
        self.assertEqual(hub_hrefs, locs)
        self.assertIn(f'{len(locs)} profiles. Available statistics from 2008 onward.', hub)
        self.assertNotIn('Historical player records', hub)
        for slug in THIN:
            self.assertNotIn(f'href="/wnba/{slug}/"', hub)
            self.assertNotIn(f'https://fullcourtbuckets.com/wnba/{slug}/', sitemap)
            page = (ROOT / 'wnba' / slug / 'index.html').read_text(encoding='utf-8')
            self.assertIn('noindex', page)
            profile = json.loads((ROOT / 'data' / 'wnba' / 'players' / f'{slug}.json').read_text(encoding='utf-8'))
            self.assertFalse(b.player_has_records(profile))

    def test_active_stars_lead_and_inactive_stays_collapsed(self):
        hub = (ROOT / 'wnba' / 'index.html').read_text(encoding='utf-8')
        rows = re.findall(r'class="player-row" href="(/wnba/[^"]+/)"', hub)
        self.assertEqual(rows[:6], [
            '/wnba/aja-wilson/',
            '/wnba/caitlin-clark/',
            '/wnba/angel-reese/',
            '/wnba/paige-bueckers/',
            '/wnba/breanna-stewart/',
            '/wnba/sabrina-ionescu/',
        ])
        self.assertLess(hub.find('id="featured-players"'), hub.find('id="players-a"'))
        self.assertIn('class="az-jump"', hub)
        self.assertIn('href="#players-a"', hub)
        self.assertIn('<details class="inactive-players" id="inactive-players">', hub)
        self.assertNotIn('id="inactive-players" open', hub)
        self.assertIn('value="true" selected', hub)
        self.assertIn('A&#x27;ja Wilson · Las Vegas Aces · ', hub)
        self.assertRegex(hub, r'Inactive players \(\d+\)')

    def test_quick_answers_match_the_visible_questions(self):
        clark = (ROOT / 'wnba' / 'caitlin-clark' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('<h2>Frequently asked questions</h2>', clark)
        self.assertNotIn('<h2>Quick answers</h2>', clark)
        self.assertNotIn('Related searches', clark)
        visible, schema = _faq_pairs(clark)
        self.assertTrue(visible)
        self.assertEqual(visible, schema)
        gray = (ROOT / 'wnba' / 'chelsea-gray' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('<h2>Frequently asked questions</h2>', gray)
        self.assertNotIn('<h2>Quick answers</h2>', gray)
        self.assertNotIn('Related searches', gray)
        visible, schema = _faq_pairs(gray)
        self.assertTrue(visible)
        self.assertEqual(visible, schema)
        aja = (ROOT / 'wnba' / 'aja-wilson' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('<h2>Frequently asked questions</h2>', aja)
        self.assertNotIn('<h2>Quick answers</h2>', aja)
        visible, schema = _faq_pairs(aja)
        self.assertEqual(visible, schema)
