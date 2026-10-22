#!/usr/bin/env python3
"""Live Finals play-by-play fetch. Game, ids and paths come from data/live-pbp.json.

Writes data/games/<date>-<away>-<home>.json in the feed's side order (the name game_stats.py uses) with status 'live' (or 'pre'), the running
score rebuilt from scoring plays, and period/clock. On Final it leaves the full
import to game_stats.py (box score) and exits 10 so the workflow switches to final
mode. Prints no secrets. No feed is named on the page.
"""
import datetime as dt, json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import wnba_sync as sync  # noqa: E402
from game_stats import normalize_plays  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / 'data/live-pbp.json').read_text())
OUT = ROOT / CFG['game_json']
FEED_ID, SITE_ID = CFG.get('feed_id'), CFG['site_id']
FINAL = {'final', 'post', 'complete', 'completed', 'status_final'}


def abbr(t):
    return (t or {}).get('abbreviation') if isinstance(t, dict) else None


def main():
    client = sync.Client(os.environ.get('BALLDONTLIE_API_KEY', ''))
    games = client.all('games', {'dates[]': CFG['feed_dates']})
    want = set(CFG['teams'])
    game = next((g for g in games if (FEED_ID and g.get('id') == FEED_ID) or (not FEED_ID and {abbr(g.get('visitor_team')), abbr(g.get('home_team'))} == want)), None)
    if not game:
        print('game not found'); return 1
    status = str(game.get('status') or '').lower(); state = str(game.get('status_state') or '').lower()
    is_final = status in FINAL or state in FINAL or 'final' in status
    feed_id = game['id']
    plays = normalize_plays(client.all('plays', {'game_id': feed_id}))
    away_t, home_t = abbr(game.get('visitor_team')), abbr(game.get('home_team'))
    # Keep the feed's sides and name the file the way game_stats.py will (date-away-home), so the
    # final import overwrites this same file and pbp-games.json never points at a stale live copy.
    out = ROOT / f"data/games/{CFG['date']}-{away_t.lower()}-{home_t.lower()}.json"
    if out != OUT:
        print(f'WARNING: config game_json {CFG["game_json"]} != feed order {out.relative_to(ROOT)}; using feed order')
    path_file = os.environ.get('LIVE_PBP_PATH_FILE')
    if path_file: Path(path_file).write_text(out.relative_to(ROOT).as_posix())
    away_feed, home_feed = game.get('away_score'), game.get('home_score')
    a = h = 0; per = {}
    for p in plays:
        side = 'away' if p['team'] == away_t else 'home'
        q = per.setdefault(p['period'] or 1, {'period': p['period'] or 1, 'away': 0, 'home': 0})
        if p.get('scoring_play'):
            if side == 'away': a += p['score_value'] or 0
            else: h += p['score_value'] or 0
            q[side] += p['score_value'] or 0
    last = plays[-1] if plays else {}
    doc = {
        'schema_version': 1, 'status': 'final' if is_final else ('live' if plays else 'pre'),
        'live': not is_final, 'espn_game_id': SITE_ID, 'balldontlie_game_id': feed_id, 'date': CFG['date'],
        'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
        'period': game.get('period') or last.get('period'), 'clock': game.get('time') or last.get('clock'),
        'last_play_period': last.get('period'), 'last_play_clock': last.get('clock'),
        'away': {'abbreviation': away_t, 'score': a, 'feed_score': away_feed},
        'home': {'abbreviation': home_t, 'score': h, 'feed_score': home_feed},
        'periods': [per[k] for k in sorted(per)], 'players': [], 'plays': plays,
    }
    print(f"status={doc['status']} plays={len(plays)} rebuilt={a}-{h} feed={game.get('away_score')}-{game.get('home_score')} last={last.get('period')} {last.get('clock')} teams={away_t}@{home_t}")
    if is_final:
        return 10  # workflow runs the full final import + score check
    if plays and (a, h) != (away_feed, home_feed):
        print('SANITY: game score != sum of scoring plays; not publishing this run'); return 3
    old = json.loads(out.read_text()) if out.exists() else {}
    # Commit only when the play count (or the score) moves; clock-only changes wait for the next play.
    if len(old.get('plays') or []) == len(plays) and old.get('status') == doc['status'] and \
            (old.get('away', {}).get('score'), old.get('home', {}).get('score')) == (a, h):
        print('no change'); return 4
    out.write_text(json.dumps(doc, indent=1) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
