"""The 2027 draft lottery page enumerates the Oct. 28, 2026 rules."""
from __future__ import annotations

import csv
import json
import shutil
import subprocess
import unittest
from fractions import Fraction
from pathlib import Path

import build_draft_lottery_2027 as lottery
import build_players
from test_data_table_first import gap_between_byline_and_table

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / 'wnba' / 'draft-lottery-2027' / 'index.html'
CSV_PATH = ROOT / 'data' / 'wnba-draft-lottery-2027-odds.csv'
RESULTS = ROOT / 'data' / 'wnba-draft-lottery-2027-results.json'


class LotteryMath(unittest.TestCase):
    def setUp(self):
        self.table = lottery.pick_probabilities()

    def test_chances_and_columns_sum(self):
        self.assertEqual(sum(lottery.CHANCES.values()), 1000)
        for slot, probs in self.table.items():
            self.assertEqual(sum(probs), 1)
            self.assertEqual(probs[0], Fraction(lottery.CHANCES[slot], 1000))
        for index in range(7):
            self.assertEqual(sum(probs[index] for probs in self.table.values()), 1)

    def test_tiebreak_limits(self):
        self.assertEqual(sum(self.table['HOU'][3:]), 0)
        self.assertGreater(self.table['HOU'][2], 0)
        self.assertEqual(sum(self.table['TOR'][4:]), 0)
        self.assertGreater(self.table['TOR'][3], 0)
        self.assertEqual(self.table['SEA'][2], 0)
        self.assertGreater(self.table['LAL-PHX'][6], Fraction(9, 10))

    def test_csv_matches_the_enumeration(self):
        with CSV_PATH.open(encoding='utf-8') as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual([row['slot_id'] for row in rows], lottery.ORDER)
        for row in rows:
            for index in range(7):
                shown = Fraction(row[f'pick_{index + 1}_fraction'])
                self.assertEqual(shown, self.table[row['slot_id']][index])
        self.assertEqual(rows[0]['method'], 'exact enumeration of 42 ordered pairs')


class LotteryPage(unittest.TestCase):
    def setUp(self):
        self.html = PAGE.read_text(encoding='utf-8')

    def test_seo_copy_and_schema(self):
        self.assertEqual(self.html.count('<h1'), 1)
        self.assertIn(f'<title>{lottery.TITLE}</title>', self.html)
        self.assertIn(lottery.DESCRIPTION, self.html)
        self.assertGreaterEqual(len(lottery.DESCRIPTION), 140)
        self.assertLessEqual(len(lottery.DESCRIPTION), 160)
        self.assertIn('rel="canonical" href="https://fullcourtbuckets.com/wnba/draft-lottery-2027/"', self.html)
        self.assertIn('"@type": "FAQPage"', self.html)
        self.assertIn('"@type": "Dataset"', self.html)
        self.assertIn('"@type": "BreadcrumbList"', self.html)
        self.assertIn('/data/wnba-draft-lottery-2027-odds.csv', self.html)
        self.assertIn('Free to use and republish (CC0)', self.html)
        self.assertNotIn('\u2014', self.html)
        self.assertNotIn('guaranteed', self.html.lower())
        self.assertNotIn('espn.com', self.html.lower())
        self.assertIn('class="byline"', self.html)
        self.assertLess(self.html.index('<h1'), self.html.index('class="byline"'))
        self.assertLess(self.html.index('class="breadcrumbs"'), self.html.index('<h1'))
        self.assertEqual(gap_between_byline_and_table(self.html, news=True), '')
        self.assertIn('class="meta-row"', self.html)
        self.assertIn('class="lead-photo"', self.html)
        self.assertIn('class="button primary"', self.html)
        self.assertIn('class="shell article-wrap"', self.html)
        self.assertNotIn('background:#2a1458', self.html)
        self.assertIn('draft-lottery-2027', build_players.SKIP_PLAYER_DIRS)

    def test_rules_and_sources_are_on_the_page(self):
        for needle in (
            'April 12, 2027',
            'April 3, 2026',
            '4:30 to 5:00 p.m. PT',
            '7:30 to 8:00 p.m. ET',
            'Bethany Donaphin',
            'Ernst &amp; Young',
            'State Street Investment Management SPY',
            '329',
            'Ariel Atkins',
            'Kelsey Plum',
            'connecticut-sun/',
            'JuJu Watkins',
            'to be confirmed',
            'seed 20261115',
            'https://www.wnba.com/news/wnba-draft-lottery-2027-sunday-november-15',
            'https://www.sports-reference.com/cbb/players/juju-watkins-1.html',
        ):
            self.assertIn(needle, self.html)
        self.assertNotIn('href="/wnba/teams/houston', self.html)

    def test_results_file_can_lock_the_simulator(self):
        data = json.loads(RESULTS.read_text(encoding='utf-8'))
        self.assertEqual(data['status'], 'pending')
        self.assertEqual([pick['pick'] for pick in data['picks']], list(range(1, 16)))
        self.assertTrue(all(pick['label'] == 'to be confirmed' for pick in data['picks'] if pick['pick'] > 7))
        self.assertIn('status !== \'final\'', self.html)

    def test_seeded_draws_match_javascript(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node not installed')
        slots = [
            {'id': slot['id'], 'chances': slot['chances']}
            for slot in lottery.SLOTS
        ]
        script = r'''
const fs = require('fs');
const SLOTS = JSON.parse(fs.readFileSync('/tmp/lottery-slots.json','utf8'));
const ORDER = SLOTS.map(s => s.id);
function lcg(seed){ let state = seed >>> 0; return function(){ state = (Math.imul(1664525, state) + 1013904223) >>> 0; return state; }; }
function below(next, n){ const limit = Math.floor(0x100000000 / n) * n; let x; do { x = next(); } while (x >= limit); return x % n; }
function pick(next, items){ let total=0; for (const it of items) total += it.chances; let r=below(next,total), acc=0; for (const it of items){ acc += it.chances; if (r < acc) return it; } return items[items.length-1]; }
function draw(next){ let pool=SLOTS.slice(); const first=pick(next,pool); pool=pool.filter(s=>s.id!==first.id); const second=pick(next,pool); const used={}; used[first.id]=1; used[second.id]=1; const rest=[]; for (const id of ORDER) if(!used[id]) rest.push(id); return [first.id, second.id].concat(rest); }
const next=lcg(20261115);
const out=[];
for (let i=0;i<25;i++) out.push(draw(next).join(','));
process.stdout.write(out.join('\n'));
'''
        path = Path('/tmp/lottery-slots.json')
        path.write_text(json.dumps(slots), encoding='utf-8')
        js = subprocess.check_output([node, '-e', script], text=True).splitlines()
        mask = 0xFFFFFFFF

        def make(seed):
            state = seed & mask

            def nxt():
                nonlocal state
                state = (1664525 * state + 1013904223) & mask
                return state
            return nxt

        def below(nxt, n):
            limit = (0x100000000 // n) * n
            while True:
                value = nxt()
                if value < limit:
                    return value % n

        def pick(nxt, items):
            total = sum(item['chances'] for item in items)
            roll = below(nxt, total)
            acc = 0
            for item in items:
                acc += item['chances']
                if roll < acc:
                    return item
            return items[-1]

        order = [slot['id'] for slot in slots]
        nxt = make(20261115)
        py = []
        for _ in range(25):
            pool = list(slots)
            first = pick(nxt, pool)
            pool = [item for item in pool if item['id'] != first['id']]
            second = pick(nxt, pool)
            used = {first['id'], second['id']}
            rest = [slot_id for slot_id in order if slot_id not in used]
            py.append(','.join([first['id'], second['id'], *rest]))
        self.assertEqual(py, js)

    def test_sitemap_search_and_free_agency_link(self):
        self.assertIn(
            'https://fullcourtbuckets.com/wnba/draft-lottery-2027/',
            (ROOT / 'pages-sitemap.xml').read_text(encoding='utf-8'),
        )
        self.assertIn('href="/wnba/draft-lottery-2027/"', (ROOT / 'sitemap' / 'index.html').read_text(encoding='utf-8'))
        index = json.loads((ROOT / 'search-index.json').read_text(encoding='utf-8'))
        self.assertIn('/wnba/draft-lottery-2027/', {item['u'] for item in index['items']})
        article = (ROOT / 'news' / 'wnba-free-agents-2027' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('href="/wnba/draft-lottery-2027/"', article)
        self.assertIn('/wnba/draft-lottery-2027/', (ROOT / 'content' / 'articles' / 'wnba-free-agents-2027' / 'article.md').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
