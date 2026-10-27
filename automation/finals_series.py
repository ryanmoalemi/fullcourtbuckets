"""WNBA Finals series state, built from the final box scores in data/games.

The post-game flow (fcb-game-stats.yml) commits each final to data/games and
dispatches fcb-wnba.yml, which rebuilds the standings page. So the series
record, links and champion here move forward after every final on their own.
Only the not-yet-played schedule lives in data/finals-schedule.json.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, json.JSONDecodeError):
        return None


def schedule(root: Path = ROOT) -> dict:
    return _load(Path(root) / 'data' / 'finals-schedule.json') or {}


def series(root: Path = ROOT) -> dict | None:
    """The current (or just-finished) Finals series, or None outside the Finals."""
    root = Path(root)
    sched = schedule(root)
    season = sched.get('season')
    best_of = int(sched.get('best_of') or 7)
    games = []
    for path in sorted((root / 'data' / 'games').glob('*.json')):
        data = _load(path)
        if not isinstance(data, dict) or data.get('status') != 'final' or not data.get('postseason'):
            continue
        if season and data.get('season') != season:
            continue
        games.append(data)
    if not games:
        return None
    games.sort(key=lambda g: str(g.get('date') or ''))
    last = games[-1]
    pair = {last['away']['abbreviation'], last['home']['abbreviation']}
    finals = [g for g in games if {g['away']['abbreviation'], g['home']['abbreviation']} == pair]
    teams = {}
    played = []
    for number, game in enumerate(finals, 1):
        away, home = game['away'], game['home']
        for side in (away, home):
            teams.setdefault(side['abbreviation'], {'abbreviation': side['abbreviation'], 'name': side.get('name') or side['abbreviation'], 'full_name': side.get('full_name') or side['abbreviation'], 'wins': 0})
        winner = away if away['score'] > home['score'] else home
        teams[winner['abbreviation']]['wins'] += 1
        played.append({'game': number, 'date': game.get('date'), 'winner': winner['abbreviation'], 'espn_game_id': game.get('espn_game_id')})
    # Only call it the Finals once the schedule file names this pair (it is written for the Finals).
    sched_homes = {g.get('home') for g in sched.get('games') or []}
    if sched_homes and not sched_homes <= pair:
        return None
    need = best_of // 2 + 1
    ordered = sorted(teams.values(), key=lambda t: -t['wins'])
    champion = ordered[0] if ordered[0]['wins'] >= need else None
    upcoming = [g for g in sched.get('games') or [] if int(g.get('game') or 0) > len(played)] if not champion else []
    return {
        'season': season or last.get('season'),
        'teams': ordered,
        'games': played,
        'champion': champion,
        'upcoming': upcoming,
        'last_day': str(last.get('date') or ''),
        'best_of': best_of,
    }


def latest_day(root: Path = ROOT) -> str:
    current = series(root)
    return current['last_day'] if current else ''
