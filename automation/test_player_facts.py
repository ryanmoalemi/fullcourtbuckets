"""Sourced notes on thin active player pages stay under the stats table."""
import json
import unittest
from pathlib import Path

import build_players as players

ROOT = Path(__file__).resolve().parents[1]


class PlayerFactTests(unittest.TestCase):
    def test_thin_active_notes_are_sourced_and_sit_below_the_table(self):
        data = json.loads((ROOT / 'data/wnba/player-facts.json').read_text(encoding='utf-8'))
        slugs = [key for key in data if not key.startswith('_')]
        self.assertEqual(len(slugs), 20)
        seen = {}
        for slug in slugs:
            rows = players.player_facts(ROOT, slug)
            self.assertGreaterEqual(len(rows), 2, slug)
            self.assertLessEqual(len(rows), 3, slug)
            html = players.player_facts_html(ROOT, slug)
            self.assertIn('class="career-notes"', html, slug)
            page = (ROOT / 'wnba' / slug / 'index.html').read_text(encoding='utf-8')
            self.assertIn(html, page, slug)
            stats_at = page.find('id="stats"')
            notes_at = page.find('class="career-notes"')
            self.assertGreater(stats_at, 0, slug)
            self.assertGreater(notes_at, stats_at, slug)
            for row in rows:
                self.assertNotIn('\u2014', row['text'], slug)
                self.assertNotIn('espn', row['text'].casefold(), slug)
                self.assertNotIn('espn', row['href'].casefold(), slug)
                self.assertTrue(
                    row['href'].startswith('/') or row['href'].startswith('https://'),
                    slug,
                )
                seen.setdefault(row['text'], []).append(slug)
        dupes = {text: slugs for text, slugs in seen.items() if len(slugs) > 1}
        self.assertEqual(dupes, {})
