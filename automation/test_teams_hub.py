"""The /wnba/teams/ hub lists current clubs from data already in the repo."""
import json
import unittest
from pathlib import Path

import team_hub
import build_players as builder
import internal_links as links

ROOT = Path(__file__).resolve().parents[1]


class TeamsHubTests(unittest.TestCase):
    def test_hub_uses_repo_facts_and_real_team_pages(self):
        index = json.loads((ROOT / 'data' / 'wnba' / 'players-index.json').read_text(encoding='utf-8'))
        linking = links.catalog_from_index(index)
        extras = team_hub.expansion_facts(ROOT)
        records, when = team_hub.standings_index(ROOT)
        self.assertEqual(extras['portland-fire']['conference'], 'West')
        self.assertEqual(extras['toronto-tempo']['conference'], 'East')
        self.assertIn('17-27', extras['portland-fire']['record'])
        self.assertIn('11-33', extras['toronto-tempo']['record'])
        self.assertEqual(records['Minnesota Lynx'], '33-11')
        self.assertEqual(records['Atlanta Dream'], '30-14')
        self.assertRegex(when, r'^[A-Z][a-z]+ \d{1,2}, \d{4}$')
        self.assertNotIn('Los Angeles Sparks', {name for name, record in records.items() if record == '10-30'})

        body, structured, title, description = team_hub.hub_parts(ROOT, linking)
        self.assertEqual(title, 'WNBA Teams | Full Court Buckets')
        self.assertIn('Portland Fire', description)
        self.assertIn('Toronto Tempo', description)
        self.assertNotIn('\u2014', body)
        self.assertIn('aria-label="Breadcrumb"', body)
        self.assertIn('<a href="/">Home</a>', body)
        self.assertNotIn('<a href="/wnba/">WNBA</a>', body)
        self.assertIn('<span>Teams</span>', body)
        nav = body[body.find('<nav class="breadcrumbs"'):body.find('</nav>')]
        self.assertNotIn('target="_blank"', nav)
        self.assertIn('<h2>Eastern Conference</h2>', body)
        self.assertIn('<h2>Western Conference</h2>', body)
        self.assertEqual(body.count('class="team-card-link"'), 15)
        self.assertEqual(body.count('class="team-card-link" href="'), 15)
        self.assertEqual(body.count('<a class="team-card-link" href="'), body.count('class="team-card-link" href="'))
        opening = body[body.find('<a class="team-card-link"'):body.find('>', body.find('<a class="team-card-link"')) + 1]
        self.assertNotIn('target=', opening)
        cards = body.split('<li class="team-card">')[1:]
        self.assertEqual(len(cards), 15)
        for card in cards:
            link = card.split('</a>', 1)[0]
            self.assertNotIn('team-card-credit', link)
            self.assertEqual(link.count('<a '), 1)
            credit = card.split('class="team-card-credit"', 1)[1].split('</p>', 1)[0]
            self.assertEqual(credit.count('<a '), 2)
            self.assertEqual(credit.count('target="_blank" rel="noopener"'), 2)
            self.assertIn('Wikimedia Commons', credit)
        css = (ROOT / 'automation' / 'players.css').read_text(encoding='utf-8')
        self.assertIn('.team-card-credit{position:absolute', css)
        self.assertIn('pointer-events:none', css)
        self.assertIn('font-size:11px', css)
        self.assertIn('.team-card-credit a:hover,.team-card-credit a:focus-visible{text-decoration:underline', css)
        self.assertNotIn('.team-card-credit a{text-decoration:underline}', css)
        for slot in linking['by_id'].values():
            href = links.team_href(slot)
            self.assertIn(f'href="{href}"', body)
            self.assertTrue((ROOT / 'wnba' / 'teams' / slot['slug'] / 'index.html').is_file(), href)
            spec = team_hub.VISUALS[slot['slug']]
            self.assertTrue((ROOT / spec['src'].lstrip('/')).is_file(), spec['src'])
            self.assertIn(spec['src'], body)
        self.assertIn('Portland', body)
        self.assertIn('Toronto', body)
        self.assertIn('2026 record: 17-27, 5th in the West.', body)
        self.assertIn('2026 record: 11-33, 6th in the East.', body)
        self.assertIn(f'33-11 as of {when}.', body)
        self.assertNotIn('10-30', body)
        self.assertNotIn('9-31', body)
        graph = {node['@type']: node for node in structured['@graph']}
        crumbs = graph['BreadcrumbList']['itemListElement']
        self.assertEqual([crumb['name'] for crumb in crumbs], ['Home', 'Teams'])
        self.assertEqual(crumbs[1]['item'], 'https://fullcourtbuckets.com/wnba/teams/')
        self.assertEqual(graph['ItemList']['numberOfItems'], 15)
        names = [item['name'] for item in graph['ItemList']['itemListElement']]
        self.assertIn('Portland Fire', names)
        self.assertIn('Toronto Tempo', names)
        self.assertEqual(len(names), 15)

    def test_team_page_teams_crumb_points_at_the_hub(self):
        slot = {
            'id': 1,
            'full_name': 'Example Team',
            'name': 'Example',
            'slug': 'example-team',
            'conference': 'Western Conference',
            'players': [{'id': 1, 'slug': 'example-player', 'name': 'Example Player'}],
        }
        page = builder.team_page(slot, include_standings=False, menu=[])
        self.assertIn('<a href="/wnba/teams/">Teams</a>', page)
        self.assertIn('"name": "Teams"', page)
        self.assertIn('https://fullcourtbuckets.com/wnba/teams/', page)
        self.assertIn('G-ZJK92LK3XT', page)
        self.assertIn('ca-pub-6621195315204235', page)
        crumb = page[page.find('class="breadcrumbs"'):page.find('</div>', page.find('class="breadcrumbs"'))]
        self.assertNotIn('target="_blank"', crumb)
        self.assertIn('class="inline-link" href="/wnba/teams/"', page)
        self.assertNotIn('href="/wnba/teams/" target="_blank"', page)


if __name__ == '__main__':
    unittest.main()
