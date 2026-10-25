"""Live updater: same file through Final, feed side order, guards, lead changes. Offline replay of Game 3."""
import copy, json, tempfile, unittest
from pathlib import Path
import build_pbp, live_pbp, pbp_guard
ROOT = Path(__file__).resolve().parents[1]
G3 = json.loads((ROOT / 'data/games/2026-10-21-gs-atl.json').read_text())


class FakeClient:
    def __init__(self, n, final=False): self.n, self.final = n, final
    def all(self, ep, params):
        if ep == 'games':
            pl = [p for p in G3['plays'][:self.n] if p['scoring_play']]
            last = G3['plays'][self.n - 1]
            return [{'id': G3['balldontlie_game_id'], 'status': 'Final' if self.final else '3rd Qtr', 'period': last['period'], 'time': last['clock'],
                     'visitor_team': {'abbreviation': 'GS'}, 'home_team': {'abbreviation': 'ATL'},
                     'away_score': pl[-1]['away_score'], 'home_score': pl[-1]['home_score']}]
        return [dict(p, team={'abbreviation': p['team']}) for p in G3['plays'][:self.n]]


class LivePbp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); (self.tmp / 'data/games').mkdir(parents=True)
        self.saved = (live_pbp.ROOT, live_pbp.OUT, live_pbp.CFG, live_pbp.SITE_ID, live_pbp.FEED_ID, live_pbp.sync.Client)
        cfg = {'date': '2026-10-21', 'feed_dates': ['2026-10-21'], 'teams': ['ATL', 'GS'], 'feed_id': None, 'site_id': '401918307', 'game_json': 'data/games/2026-10-21-gs-atl.json'}
        live_pbp.ROOT, live_pbp.CFG, live_pbp.SITE_ID, live_pbp.FEED_ID = self.tmp, cfg, '401918307', None
        live_pbp.OUT = self.tmp / cfg['game_json']

    def tearDown(self):
        live_pbp.ROOT, live_pbp.OUT, live_pbp.CFG, live_pbp.SITE_ID, live_pbp.FEED_ID, live_pbp.sync.Client = self.saved

    def run_feed(self, n, final=False):
        live_pbp.sync.Client = lambda key: FakeClient(n, final)
        return live_pbp.main()

    def test_live_writes_feed_order_file_and_builds(self):
        self.assertEqual(self.run_feed(200), 0)
        f = self.tmp / 'data/games/2026-10-21-gs-atl.json'   # the name game_stats.py gives the final file
        d = json.loads(f.read_text())
        self.assertEqual((d['away']['abbreviation'], d['home']['abbreviation'], d['status'], len(d['plays'])), ('GS', 'ATL', 'live', 200))
        _, out = build_pbp.build('401918307', str(f), live=True)
        self.assertIn('LIVE', out); self.assertNotIn('has not started', out)
        page = self.tmp / 'p.html'; page.write_text(out)
        self.assertEqual(pbp_guard.check(str(page), str(f)), [])
        self.assertEqual(self.run_feed(200), 4)          # same play count: no commit
        self.assertEqual(self.run_feed(201), 0)          # one new play: commit
        self.assertEqual(self.run_feed(len(G3['plays']), final=True), 10)

    def test_never_placeholder_once_plays_exist(self):
        self.run_feed(200); f = self.tmp / 'data/games/2026-10-21-gs-atl.json'
        with self.assertRaises(build_pbp.ScoreCheckError):
            build_pbp.build('401918307', str(f))         # the Game 3 bug: final build pointed at a live file
        _, ph = build_pbp.build('401918309')         # Game 5: still a placeholder (Game 4 is final)
        page = self.tmp / 'p.html'; page.write_text(ph)
        self.assertTrue(pbp_guard.check(str(page), str(f)))

    def test_resolve_final_file(self):
        self.assertEqual(pbp_guard.resolve('401918307'), 'data/games/2026-10-21-gs-atl.json')

    def test_game3_lead_changes_and_ties(self):
        d = copy.deepcopy(G3); d['away'], d['home'] = d['home'], d['away']
        for p in d['plays']: p['away_score'], p['home_score'] = p['home_score'], p['away_score']
        plays, _ = build_pbp.derive(d)
        self.assertEqual((sum(p['flag'] == 'lead change' for p in plays), sum(p['flag'] == 'tie' for p in plays)), (0, 2))
        self.assertIn('0 lead changes, 2 ties', build_pbp.build('401918307')[1])

    def test_lead_change_through_tie_counts(self):
        mk = lambda o, t, v, a, h: {'order': o, 'period': 1, 'clock': '9:00', 'type': 'x', 'text': 'x', 'scoring_play': True, 'score_value': v, 'team': t, 'away_score': a, 'home_score': h}
        d = {'away': {'abbreviation': 'ATL', 'score': 4}, 'home': {'abbreviation': 'GS', 'score': 5}, 'players': [],
             'plays': [mk(1, 'ATL', 2, 2, 0), mk(2, 'GS', 2, 2, 2), mk(3, 'GS', 3, 2, 5), mk(4, 'ATL', 2, 4, 5)]}
        flags = [p['flag'] for p in build_pbp.derive(d)[0]]
        self.assertEqual(flags, ['', 'tie', 'lead change', ''])


if __name__ == '__main__':
    unittest.main()
