"""Play-by-play pages: score check gates publishing; placeholder has no plays."""
import copy, json, unittest
from pathlib import Path
import build_pbp
ROOT = Path(__file__).resolve().parents[1]
G1 = ROOT / 'data/games/2026-10-17-atl-gs.json'


def build_unplayed(game_id):
    """Build a game as the pre-tip placeholder (its box score dropped from a temp copy of the config)."""
    import json as _j, tempfile as _t
    from pathlib import Path as _P
    conf = _j.loads(build_pbp.CONF.read_text()); conf['games'][game_id].pop('game_json', None)
    conf['games'][game_id].pop('recap', None)
    tmp = _P(_t.mkdtemp()) / 'pbp-games.json'; tmp.write_text(_j.dumps(conf))
    saved, build_pbp.CONF = build_pbp.CONF, tmp
    try:
        return build_pbp.build(game_id)
    finally:
        build_pbp.CONF = saved


class BuildPbp(unittest.TestCase):
    def test_game1_builds_and_matches_box(self):
        path, out = build_pbp.build('401918305')
        self.assertEqual(path, '/wnba/finals/2026/game-1/play-by-play/')
        self.assertIn('data-fcb-data-table', out)
        self.assertIn('Final: Valkyries 68, Dream 64', out)
        self.assertNotRegex(out.lower(), r'espn|balldontlie')
        d = json.loads(G1.read_text()); plays, roster = build_pbp.derive(d)
        pc, _ = build_pbp.player_counts(plays, roster)
        for r in roster:
            m = pc[r['name']]
            self.assertEqual((m['pts'], m['3pa'], m['2pa'] + m['3pa']), (r['pts'], r['fg3a'], r['fga']), r['name'])

    def test_placeholder_has_no_plays(self):
        # Game 5 as it looked before tip-off (series 2-2): the placeholder has no plays.
        _, out = build_unplayed('401918309')
        self.assertIn('Live: updates every 30 seconds.', out)
        self.assertIn('Series tied 2-2', out)
        self.assertIn('TV: USA Network (simulcast on CNBC). Streaming: Peacock.', out)
        self.assertNotIn('id="play-', out)

    def test_bad_score_refuses(self):
        d = json.loads(G1.read_text()); d = copy.deepcopy(d)
        for p in d['plays']:
            if p['scoring_play']: p['home_score'] += 1; break
        with self.assertRaises(build_pbp.ScoreCheckError):
            build_pbp.derive(d)

    def test_pages_are_current(self):
        for gid in ('401918305', '401918306', '401918307', '401918308', '401918309'):
            path, out = build_pbp.build(gid)
            self.assertEqual((ROOT / path.strip('/') / 'index.html').read_text(), out, f'{path} is stale: rerun build_pbp.py')


if __name__ == '__main__':
    unittest.main()
