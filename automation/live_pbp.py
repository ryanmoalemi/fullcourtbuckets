#!/usr/bin/env python3
"""Live Finals play-by-play fetch. Game, ids and paths come from data/live-pbp.json.

Writes the configured game JSON with status 'live' (or 'pre'), the running
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
    away_t, home_t = abbr(game.get('visitor_team')) or 'ATL', abbr(game.get('home_team')) or 'GS'
    # File keeps ATL as 'away' for the whole series; map feed scores by team, not by side.
    atl_feed, gs_feed = (game.get('away_score'), game.get('home_score')) if away_t == 'ATL' else (game.get('home_score'), game.get('away_score'))
    a = h = 0; per = {}
    for p in plays:
        if p.get('scoring_play'):
            if p['team'] == 'ATL': a += p['score_value'] or 0
            else: h += p['score_value'] or 0
        q = per.setdefault(p['period'] or 1, {'period': p['period'] or 1, 'away': 0, 'home': 0})
        if p.get('scoring_play'):
            q['away' if p['team'] == 'ATL' else 'home'] += p['score_value'] or 0
    last = plays[-1] if plays else {}
    doc = {
        'schema_version': 1, 'status': 'final' if is_final else ('live' if plays else 'pre'),
        'live': not is_final, 'espn_game_id': SITE_ID, 'balldontlie_game_id': feed_id, 'date': CFG['date'],
        'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
        'period': game.get('period') or last.get('period'), 'clock': game.get('time') or last.get('clock'),
        'last_play_period': last.get('period'), 'last_play_clock': last.get('clock'),
        'away': {'abbreviation': 'ATL', 'score': a, 'feed_score': atl_feed},
        'home': {'abbreviation': 'GS', 'score': h, 'feed_score': gs_feed},
        'periods': [per[k] for k in sorted(per)], 'players': [], 'plays': plays,
    }
    print(f"status={doc['status']} plays={len(plays)} rebuilt={a}-{h} feed={game.get('away_score')}-{game.get('home_score')} last={last.get('period')} {last.get('clock')} teams={away_t}@{home_t}")
    if is_final:
        return 10  # workflow runs the full final import + score check
    if plays and (a, h) != (atl_feed, gs_feed):
        print('SANITY: game score != sum of scoring plays; not publishing this run'); return 3
    new = json.dumps({k: v for k, v in doc.items() if k != 'checked_at'}, sort_keys=True)
    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    if json.dumps({k: v for k, v in old.items() if k != 'checked_at'}, sort_keys=True) == new:
        print('no change'); return 4
    OUT.write_text(json.dumps(doc, indent=1) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
