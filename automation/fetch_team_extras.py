#!/usr/bin/env python3
"""Snapshot draft slots, franchise history and the 2026 schedule from WNBA.com.

Writes, all from the official league site:
  data/wnba/player-draft.json   draft year/round/pick per rostered player (wnba.com/player/<id>)
  data/wnba/team-history.json   season-by-season W-L, finish and playoff result per franchise
  data/wnba/schedule-2026.json  every 2026 regular-season, Commissioner's Cup and playoff game

Sources: wnba.com/team/<id> (roster ids), wnba.com/player/<id>, wnba.com/api/schedule?season=YYYY
(the feed behind wnba.com/schedule) and wnba.com/standings?season=YYYY (published for 2010 on).
Run by hand (network); the site build only reads the snapshots. Nothing is filled from
aggregators; a value WNBA.com does not publish stays null and the page leaves it blank.

    python3 automation/fetch_team_extras.py [--first 1997] [--cache DIR]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'wnba'
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) Chrome/130 Safari/537.36'}
TEAM_IDS = [1611661313, 1611661317, 1611661319, 1611661320, 1611661321, 1611661322,
            1611661323, 1611661324, 1611661325, 1611661327, 1611661328, 1611661329,
            1611661330, 1611661331, 1611661332, 1611661333]
SEASON = 2026
STANDINGS_FIRST = 2010  # wnba.com/standings redirects to the current season before 2010


def get(url: str, cache: Path | None = None, name: str = '') -> str:
    if cache and name and (cache / name).is_file():
        return (cache / name).read_text(encoding='utf-8')
    for attempt in range(3):
        try:
            text = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read().decode('utf-8')
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)
    if cache and name:
        cache.mkdir(parents=True, exist_ok=True)
        (cache / name).write_text(text, encoding='utf-8')
    return text


def next_data(text: str) -> dict:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', text, re.S)
    return json.loads(m.group(1))['props']['pageProps'] if m else {}


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def draft_for(person_id, cache) -> dict:
    url = f'https://www.wnba.com/player/{person_id}'
    page = next_data(get(url, cache, f'player-{person_id}.html'))
    p = page.get('player') or {}
    info = p.get('info') or p.get('playerInfo') or {}
    if isinstance(info, list):
        info = info[0] if info else {}
    year = _int(p.get('draftYear') or info.get('DRAFT_YEAR'))
    rnd = _int(p.get('draftRound') or info.get('DRAFT_ROUND'))
    pick = _int(p.get('draftNumber') or info.get('DRAFT_NUMBER'))
    raw = ' '.join(str(x) for x in (p.get('draftYear'), info.get('DRAFT_YEAR')) if x)
    undrafted = 'undrafted' in raw.casefold() or (year is None and rnd is None and pick is None and bool(p))
    return {'year': year, 'round': rnd, 'pick': pick, 'undrafted': bool(undrafted and year is None),
            'source': url}


def schedule(year: int, cache) -> list[dict]:
    text = get(f'https://www.wnba.com/api/schedule?season={year}&regionId=1', cache, f'schedule-{year}.json')
    games = []
    for day in json.loads(text)['leagueSchedule']['gameDates']:
        games.extend(day.get('games') or [])
    return games


def standings(year: int, cache) -> dict:
    url = f'https://www.wnba.com/standings?season={year}'
    rows = next_data(get(url, cache, f'standings-{year}.html')).get('standingsRowsData') or []
    if not rows or str(rows[0].get('SeasonID', ''))[-4:] != str(year):
        return {}
    league_wide = len({r.get('PlayoffRank') for r in rows}) == len(rows)
    out = {}
    for r in rows:
        rank = _int(r.get('PlayoffRank'))
        if rank:
            finish = (f'{ordinal(rank)} of {len(rows)} in the league' if league_wide
                      else f'{ordinal(rank)} in the {r.get("Conference")}')
        else:
            finish = None
        out[r['TeamID']] = {'wins': _int(r.get('WINS')), 'losses': _int(r.get('LOSSES')),
                            'finish': finish, 'conference': r.get('Conference'), 'source': url}
    return out


def ordinal(n: int) -> str:
    suf = 'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return f'{n}{suf}'


ROUNDS = {'WNBA Finals': 'WNBA Finals', 'Semi-Finals': 'Semifinals', 'Second Round': 'Second Round',
          'First Round': 'First Round', 'Playoffs': 'Playoffs', 'Conference Finals': 'Conference Finals'}


def playoff_results(games: list[dict]) -> dict:
    """Last series each team played and whether it won it, from the league's seriesText."""
    po = [g for g in games if g.get('seasonType') == 'Playoffs' and g.get('gameStatus') == 3]
    if not po:
        return {}
    final_pair = {po[-1]['homeTeam']['teamId'], po[-1]['awayTeam']['teamId']}
    last = {}
    for g in po:
        pair = {g['homeTeam']['teamId'], g['awayTeam']['teamId']}
        label = ROUNDS.get(g.get('gameLabel') or '', g.get('gameLabel') or 'Playoffs')
        if label == 'WNBA Finals' and pair != final_pair:
            label = 'Semifinals'  # 1997 feed labels every single-game round as the Finals
        m = re.match(r'([A-Z]{2,3}) wins', g.get('seriesText') or '')
        winner = None
        if m:
            winner = next((t['teamId'] for t in (g['homeTeam'], g['awayTeam']) if t['teamTricode'] == m.group(1)), None)
        for side in ('homeTeam', 'awayTeam'):
            tid = side and g[side]['teamId']
            last[tid] = {'round': label, 'won': (winner == tid) if winner else None}
    out = {}
    for tid, r in last.items():
        if r['round'] == 'WNBA Finals':
            out[tid] = 'Won WNBA Finals' if r['won'] else 'Lost in WNBA Finals'
        elif r['won'] is False:
            out[tid] = f'Lost in {r["round"]}'
        else:
            out[tid] = f'Reached {r["round"]}'
    return out


def season_rows(year: int, games: list[dict], cache) -> dict:
    stand = standings(year, cache) if year >= STANDINGS_FIRST else {}
    rec = {}
    names = {}
    for g in games:
        if g.get('seasonType') not in ('Regular Season', 'Comm Cup') and not (
                g.get('seasonType') == 'Regular Season'):
            continue
        if g.get('seasonType') != 'Regular Season' or g.get('gameStatus') != 3:
            continue
        h, a = g['homeTeam'], g['awayTeam']
        for t in (h, a):
            names[t['teamId']] = f'{t.get("teamCity") or ""} {t.get("teamName") or ""}'.strip()
            rec.setdefault(t['teamId'], [0, 0, 0])
        if not (h.get('score') or a.get('score')):
            rec[h['teamId']][2] += 1
            rec[a['teamId']][2] += 1
            continue
        win, lose = (h, a) if h['score'] > a['score'] else (a, h)
        rec[win['teamId']][0] += 1
        rec[lose['teamId']][1] += 1
    po = playoff_results(games)
    sched = f'https://www.wnba.com/api/schedule?season={year}&regionId=1'
    out = {}
    for tid in set(rec) | set(stand):
        s = stand.get(tid)
        w, l, unscored = rec.get(tid, [None, None, 0])
        row = {'season': year, 'team_name': names.get(tid)}
        if s and s['wins'] is not None:
            row.update(wins=s['wins'], losses=s['losses'], finish=s['finish'], record_source=s['source'])
        elif unscored:
            # A final with no score (2018 forfeit): the W-L cannot be read from scores alone.
            row.update(wins=None, losses=None, finish=None, record_source=None)
        else:
            row.update(wins=w, losses=l, finish=None, record_source=sched)
        if year == SEASON and not any(g.get('seasonType') == 'Playoffs' and g.get('gameStatus') != 3 for g in games):
            pass
        row['playoffs'] = po.get(tid) or ('Missed playoffs' if po else None)
        row['playoffs_source'] = sched
        out[tid] = row
    return out


def schedule_2026(games: list[dict]) -> dict:
    keep = []
    for g in games:
        if g.get('seasonType') not in ('Regular Season', 'Comm Cup', 'Playoffs'):
            continue
        h, a = g['homeTeam'], g['awayTeam']
        keep.append({
            'game_id': g.get('gameId'), 'date': (g.get('gameDateEst') or '')[:10],
            'time_utc': g.get('gameDateTimeUTC'), 'type': g.get('seasonType'),
            'label': ' '.join(x for x in (g.get('gameLabel'), g.get('gameSubLabel')) if x) or None,
            'status': g.get('gameStatus'), 'arena': g.get('arenaName'),
            'home': {'id': h['teamId'], 'tricode': h.get('teamTricode'), 'score': h.get('score') if g.get('gameStatus') == 3 else None},
            'away': {'id': a['teamId'], 'tricode': a.get('teamTricode'), 'score': a.get('score') if g.get('gameStatus') == 3 else None},
            'series': g.get('seriesText') or None,
        })
    return keep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--first', type=int, default=1997)
    ap.add_argument('--cache')
    args = ap.parse_args()
    cache = Path(args.cache) if args.cache else None
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')

    players = {}
    names = {}
    for tid in TEAM_IDS:
        try:
            team = next_data(get(f'https://www.wnba.com/team/{tid}', cache, f'team-{tid}.html')).get('team') or {}
        except urllib.error.HTTPError:
            continue
        if not team.get('city'):
            continue
        full = f"{team['city']} {team['name']}"
        names[tid] = full
        for r in team.get('roster') or []:
            if not r.get('id') or not r.get('displayName'):
                continue
            row = draft_for(r['id'], cache)
            row.update(player=r['displayName'], team=full, person_id=r['id'])
            players[str(r['id'])] = row
            time.sleep(0.3)
    (DATA / 'player-draft.json').write_text(json.dumps({
        'source': 'WNBA.com player pages (official league site)', 'checked_at': now,
        'note': 'Draft year, round and overall pick as published on each player page. WNBA.com does not '
                'publish the drafting team there, so it is not recorded.',
        'players': players}, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

    history = {name: [] for name in names.values()}
    sched26 = []
    for year in range(args.first, SEASON + 1):
        games = schedule(year, cache)
        if year == SEASON:
            sched26 = schedule_2026(games)
        for tid, row in season_rows(year, games, cache).items():
            if tid in names:
                history[names[tid]].append(row)
    for rows in history.values():
        rows.sort(key=lambda r: -r['season'])
    (DATA / 'team-history.json').write_text(json.dumps({
        'source': 'WNBA.com standings (2010 on) and the WNBA.com schedule feed (every season)', 'checked_at': now,
        'note': 'W-L and finish from wnba.com/standings when published (2010 on); before 2010 the W-L is '
                'counted from final regular-season scores in the league schedule feed and the finish is left blank. '
                'Playoff result from the series line in the same feed.',
        'teams': history}, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    (DATA / 'schedule-2026.json').write_text(json.dumps({
        'source': f'https://www.wnba.com/api/schedule?season={SEASON}&regionId=1', 'checked_at': now,
        'teams': {str(k): v for k, v in names.items()}, 'games': sched26}, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(len(players), 'players;', sum(map(len, history.values())), 'team-seasons;', len(sched26), 'games')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
