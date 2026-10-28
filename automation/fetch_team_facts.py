#!/usr/bin/env python3
"""Snapshot official team facts from each club's WNBA.com team page.

Writes data/wnba/team-facts.json. Run by hand (network); the site build only
reads the snapshot. Every field is copied from WNBA.com as published. A field
WNBA.com leaves empty stays empty (null) and the page leaves it blank.

    python3 automation/fetch_team_facts.py [--html-dir DIR]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'wnba' / 'team-facts.json'
IDS = [1611661313, 1611661317, 1611661319, 1611661320, 1611661321, 1611661322,
       1611661323, 1611661324, 1611661325, 1611661327, 1611661328, 1611661329,
       1611661330, 1611661331, 1611661332, 1611661333]


def _clean(value):
    if value in (None, '', 'None', [], {}):
        return None
    return value


def parse(text: str, team_id: int) -> dict | None:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', text, re.S)
    if not m:
        return None
    page = json.loads(m.group(1))['props']['pageProps']
    team = page.get('team') or {}
    if not team.get('city'):
        return None
    bg = team.get('background') or {}
    head = [c.get('displayName') for c in team.get('coaches') or [] if c.get('type') == 'Head Coach']
    leaders = team.get('franchiseLeaders') or {}
    full = f"{team['city']} {team['name']}"
    return {
        'wnba_team_id': team_id,
        'full_name': full,
        'source': f'https://www.wnba.com/team/{team_id}',
        'founded': _clean(bg.get('YEARFOUNDED') or team.get('seasonDebut')),
        'arena': _clean(bg.get('ARENA') or team.get('arena')),
        'arena_capacity': _clean(bg.get('ARENACAPACITY')),
        'owner': _clean(team.get('owner') or bg.get('OWNER')),
        'general_manager': _clean(team.get('generalManager') or bg.get('GENERALMANAGER')),
        'head_coach': _clean(head[0] if head else bg.get('HEADCOACH')),
        'official_site': _clean((team.get('links') or {}).get('team')),
        'ranks': {
            key: {'value': _clean(team.get(key)), 'rank': _clean(team.get(key + 'Rank'))}
            for key in ('ppg', 'rpg', 'apg', 'oppg')
        },
        'championships': [
            {'year': a.get('YEARAWARDED'), 'opponent': _clean(a.get('OPPOSITETEAM'))}
            for a in (team.get('awards') or {}).get('champ') or []
        ],
        'commissioners_cup': [a.get('YEARAWARDED') for a in (team.get('awards') or {}).get('commCupChamp') or []],
        'hall_of_fame': [
            {'player': h.get('PLAYER'), 'position': _clean(h.get('POSITION')),
             'seasons': _clean(h.get('SEASONSWITHTEAM')), 'inducted': _clean(h.get('YEAR'))}
            for h in team.get('hof') or []
        ],
        'franchise_leaders': {
            label: {'player': _clean(leaders.get(key + '_PLAYER')), 'total': _clean(leaders.get(key))}
            for key, label in (('PTS', 'points'), ('REB', 'rebounds'), ('AST', 'assists'), ('STL', 'steals'), ('BLK', 'blocks'))
            if _clean(leaders.get(key + '_PLAYER'))
        },
        'roster': {
            r['displayName']: {
                'number': _clean(r.get('number')),
                'height': _clean(r.get('height')),
                'age': _clean(r.get('age')),
                'experience': r.get('experience') if r.get('experience') not in (None, '', 'None') else None,
                'country': _clean(r.get('country')),
                'school': _clean(r.get('school')),
                'developmental': bool(r.get('supplementalStatus')) if r.get('supplementalStatus') not in (None, 'None') else False,
            }
            for r in team.get('roster') or [] if r.get('displayName')
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--html-dir')
    args = ap.parse_args()
    teams = {}
    for tid in IDS:
        if args.html_dir:
            path = Path(args.html_dir) / f'{tid}.html'
            text = path.read_text(encoding='utf-8') if path.is_file() else ''
        else:
            req = urllib.request.Request(f'https://www.wnba.com/team/{tid}', headers={'User-Agent': 'Mozilla/5.0'})
            text = urllib.request.urlopen(req, timeout=30).read().decode('utf-8')
        facts = parse(text, tid)
        if facts:
            teams[facts['full_name']] = facts
    OUT.write_text(json.dumps({
        'source': 'WNBA.com team pages (official league site)',
        'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
        'note': 'Copied as published. Empty fields stay null and are left blank on the site.',
        'teams': teams,
    }, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'{len(teams)} teams -> {OUT.relative_to(ROOT)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
