#!/usr/bin/env python3
"""Live play-by-play guards (used by automation/live_pbp_loop.sh).

  pbp_guard.py resolve <site_id>          print the final game JSON for this game (status final, matching id)
  pbp_guard.py check <page_html> <json>   exit 2 if the page says 'not started' / has an empty score while plays exist
"""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def resolve(site_id):
    hits = []
    for p in sorted((ROOT / 'data/games').glob('*.json')):
        if p.name in ('index.json', 'balldontlie-endpoints.json'): continue
        try: d = json.loads(p.read_text())
        except (OSError, ValueError): continue
        if str(d.get('espn_game_id')) == str(site_id) and d.get('status') == 'final' and d.get('plays'):
            hits.append(p)
    if len(hits) != 1:
        print(f'expected one final file for {site_id}, found {[h.name for h in hits]}', file=sys.stderr); return None
    return hits[0].relative_to(ROOT).as_posix()


def check(page, game_json):
    html = (ROOT / page).read_text(encoding='utf-8')
    d = json.loads((ROOT / game_json).read_text()) if (ROOT / game_json).exists() else {}
    plays = d.get('plays') or []
    if not plays: return []
    bad = []
    if 'has not started' in html or 'NOT STARTED' in html: bad.append("page says 'has not started'")
    sc = re.search(r'<div class="sb"><div class="tm">[^<]*<b>([^<]*)</b>.*?<b>([^<]*)</b>', html, re.S)
    if not sc or not all(x.strip().isdigit() for x in sc.groups()): bad.append(f'empty scoreboard {sc.groups() if sc else None}')
    if 'id="play-' not in html: bad.append('no play rows')
    if d.get('status') == 'final' and 'Final:' not in html: bad.append('final data but page is not final')
    return bad


if __name__ == '__main__':
    if sys.argv[1] == 'resolve':
        r = resolve(sys.argv[2]); print(r or ''); sys.exit(0 if r else 1)
    bad = check(sys.argv[2], sys.argv[3])
    for b in bad: print('GUARD:', b, file=sys.stderr)
    sys.exit(2 if bad else 0)
