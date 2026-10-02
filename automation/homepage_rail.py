#!/usr/bin/env python3
"""Homepage rail: playoff series and latest scores, or final standings in the offseason.

The daily player build calls load_rail(). Rendering is pure so tests never hit the network.
If the scoreboard request fails, load_rail() returns None and the last rail stays in place.
"""
from __future__ import annotations

import datetime as dt
import gzip
import html
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

PT = ZoneInfo('America/Los_Angeles')
SCOREBOARD = 'https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard'
RECENT = dt.timedelta(days=14)
LATEST_LIMIT = 4
USER_AGENT = 'FullCourtBuckets/1.0'
RAIL_PATTERN = re.compile(
    r'<!-- fcb-rail:start -->.*?<!-- fcb-rail:end -->|<aside class="rail"[^>]*>.*?</aside>',
    re.S,
)
SLOGANS = (
    'WNBA News. Given to You Straight.',
    'What Happened and Why',
    'Facts First',
    'WNBA Coverage Every Day',
)


def esc(value) -> str:
    return html.escape('' if value is None else str(value), quote=True)


def espn_game_url(game_id: str) -> str:
    return f'https://www.espn.com/wnba/game/_/gameId/{game_id}'


def _parse_when(raw) -> dt.datetime | None:
    text = str(raw or '').strip()
    if not text:
        return None
    try:
        moment = dt.datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.timezone.utc)
    return moment


def _nick(team: dict) -> str:
    nick = str(team.get('shortDisplayName') or team.get('nickname') or '').strip()
    if nick:
        return nick
    display = str(team.get('displayName') or team.get('name') or '').strip()
    return display.split()[-1] if display else ''


def _int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_event(event: dict) -> dict | None:
    """One scoreboard event, or None when the payload has no two-team game."""
    competitions = event.get('competitions') or []
    if not competitions or not isinstance(competitions[0], dict):
        return None
    comp = competitions[0]
    status = ((comp.get('status') or {}).get('type') or {})
    teams = []
    for row in comp.get('competitors') or []:
        if not isinstance(row, dict):
            continue
        team = row.get('team') or {}
        teams.append({
            'id': _int(team.get('id'), 0),
            'nick': _nick(team),
            'abbr': str(team.get('abbreviation') or ''),
            'score': _int(row.get('score'), 0),
            'home': row.get('homeAway') == 'home',
        })
    if len(teams) < 2:
        return None
    series = comp.get('series') or {}
    wins = {}
    for row in series.get('competitors') or []:
        if isinstance(row, dict):
            wins[_int(row.get('id'), 0)] = _int(row.get('wins'), 0)
    season = event.get('season') if isinstance(event.get('season'), dict) else {}
    series_type = str(series.get('type') or '')
    if not series_type and season.get('type') == 3:
        series_type = 'playoff'
    detail = str(status.get('detail') or '')
    short = str(status.get('shortDetail') or '')
    description = str(status.get('description') or '')
    clock_text = f'{short} {detail} {description}'
    return {
        'id': str(event.get('id') or ''),
        'when': _parse_when(event.get('date')),
        'state': str(status.get('state') or ''),
        'detail': detail,
        'short': short,
        'tbd': 'TBD' in clock_text.upper(),
        'ot': bool(re.search(r'\bOT\b', clock_text)),
        'teams': teams[:2],
        'series_type': series_type,
        'series_completed': bool(series.get('completed')),
        'wins': wins,
    }


def _named(teams: list) -> bool:
    for team in teams:
        nick = team['nick'].casefold()
        if team['id'] <= 0 or nick in ('', 'tbd') or team['abbr'].upper() == 'TBD':
            return False
    return True


def _series_key(teams: list) -> tuple:
    return tuple(sorted(team['id'] for team in teams))


def _status_line(teams: list, wins: dict, completed: bool) -> str:
    rows = [(team['nick'], wins.get(team['id'], 0), team) for team in teams]
    by_wins = sorted(rows, key=lambda row: -row[1])
    leader, leader_wins, _leader = by_wins[0]
    trailer, trailer_wins, _trailer = by_wins[1]
    if completed and leader_wins != trailer_wins:
        return f'{leader} beat {trailer} {leader_wins}-{trailer_wins}'
    if leader_wins == trailer_wins == 0:
        away = next((team for team in teams if not team['home']), teams[0])
        home = next((team for team in teams if team['home']), teams[1])
        return f'{away["nick"]} at {home["nick"]}'
    if leader_wins == trailer_wins:
        return f'{rows[0][0]} and {rows[1][0]} tied {leader_wins}-{trailer_wins}'
    return f'{leader} lead {trailer} {leader_wins}-{trailer_wins}'


def _next_label(event: dict) -> str:
    if event['state'] == 'in':
        return 'In progress'
    if event['tbd']:
        match = re.search(r'(\d{1,2})/(\d{1,2})', f"{event['short']} {event['detail']}")
        if match:
            month = int(match.group(1))
            day = int(match.group(2))
            if 1 <= month <= 12:
                return f'Next: {dt.date(2000, month, 1).strftime("%b")} {day}, time TBD'
        if event['when']:
            local = event['when'].astimezone(PT)
            return f'Next: {local.strftime("%b")} {local.day}, time TBD'
        return 'Next: time TBD'
    if not event['when']:
        return 'Next: time TBD'
    local = event['when'].astimezone(PT)
    hour = local.strftime('%I').lstrip('0') or '12'
    ampm = 'a.m.' if local.hour < 12 else 'p.m.'
    return f'Next: {local.strftime("%a")}, {local.strftime("%b")} {local.day}, {hour}:{local.strftime("%M")} {ampm} PT'


def _score_line(event: dict) -> str:
    ordered = sorted(event['teams'], key=lambda team: (-team['score'], 0 if team['home'] else 1))
    line = f'{ordered[0]["nick"]} {ordered[0]["score"]}, {ordered[1]["nick"]} {ordered[1]["score"]}'
    if event['ot']:
        line += ' OT'
    return line


def _date_label(event: dict) -> str:
    if not event['when']:
        return ''
    local = event['when'].astimezone(PT)
    return f'{local.strftime("%b")} {local.day}'


def games_active(events: list, now: dt.datetime) -> bool:
    """True when a game is scheduled, in progress, or a final is still recent."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=PT)
    for event in events:
        if event['state'] in ('pre', 'in'):
            return True
        if event['series_type'] == 'playoff' and not event['series_completed']:
            return True
        when = event['when']
        if event['state'] == 'post' and when and now - when <= RECENT:
            return True
    return False


def _recaps(articles: list) -> dict:
    best = {}
    for article in articles or []:
        if not isinstance(article, dict):
            continue
        game_id = str(article.get('espnGameId') or '').strip()
        slug = str(article.get('slug') or '').strip()
        if not game_id or not slug:
            continue
        href = str(article.get('url') or f'/news/{slug}/')
        if not href.startswith('/'):
            href = f'/news/{slug}/'
        date = str(article.get('date') or '')
        current = best.get(game_id)
        if current is None or date > current[0]:
            best[game_id] = (date, href)
    return {game_id: href for game_id, (_date, href) in best.items()}


def playoff_series(events: list) -> list:
    """Incomplete series first, then completed series, newest last game first."""
    groups: dict[tuple, list] = {}
    for event in events:
        if event['series_type'] != 'playoff' or not _named(event['teams']):
            continue
        groups.setdefault(_series_key(event['teams']), []).append(event)
    rows = []
    for grouped in groups.values():
        grouped.sort(key=lambda event: event['when'] or dt.datetime.min.replace(tzinfo=dt.timezone.utc))
        latest = grouped[-1]
        completed = latest['series_completed']
        upcoming = [event for event in grouped if event['state'] in ('pre', 'in')]
        upcoming.sort(key=lambda event: event['when'] or dt.datetime.max.replace(tzinfo=dt.timezone.utc))
        nxt = upcoming[0] if upcoming and not completed else None
        # An unstarted series has no wins yet. Use the next game for home and away.
        status_teams = nxt['teams'] if nxt and not any(latest['wins'].values()) else latest['teams']
        rows.append({
            'status': _status_line(status_teams, latest['wins'], completed),
            'completed': completed,
            'next_label': _next_label(nxt) if nxt else '',
            'next_url': espn_game_url(nxt['id']) if nxt and nxt['id'] else '',
            'next_when': nxt['when'] if nxt else None,
            'last_when': latest['when'],
        })
    def sort_key(row):
        if row['next_when']:
            return (0, row['next_when'].timestamp())
        if not row['completed']:
            return (1, 0)
        stamp = row['last_when'].timestamp() if row['last_when'] else 0
        return (2, -stamp)
    rows.sort(key=sort_key)
    return rows


def latest_finals(events: list, articles: list, limit: int = LATEST_LIMIT) -> list:
    finals = [event for event in events if event['state'] == 'post' and _named(event['teams'])]
    finals.sort(key=lambda event: event['when'] or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True)
    recaps = _recaps(articles)
    rows = []
    for event in finals[:limit]:
        rows.append({
            'line': _score_line(event),
            'when_label': _date_label(event),
            'recap': recaps.get(event['id'], ''),
            'espn': espn_game_url(event['id']) if event['id'] else '',
        })
    return rows


def _standings_nick(name: str) -> str:
    parts = str(name or '').split()
    return parts[-1] if parts else ''


def render_standings(standings: dict | None) -> str:
    teams = [team for team in (standings or {}).get('teams') or [] if isinstance(team, dict)]
    groups: dict[str, list] = {}
    for team in teams:
        conference = str(team.get('conference') or '').replace(' Conference', '').strip() or 'League'
        groups.setdefault(conference, []).append(team)
    order = [name for name in ('Eastern', 'Western') if name in groups]
    order += sorted(name for name in groups if name not in order)
    parts = ['<section class="rail-box" id="final-standings"><h2>Final standings</h2>']
    for conference in order:
        ranked = sorted(
            groups[conference],
            key=lambda team: (_int(team.get('conferenceRank'), 99), -_int(team.get('wins'), 0)),
        )[:4]
        parts.append(f'<h3 class="rail-conf">{esc(conference)}</h3><ul class="rail-list">')
        for team in ranked:
            rank = team.get('conferenceRank')
            nick = _standings_nick(str(team.get('name') or ''))
            line = f'{rank}. {nick} {team.get("wins")}-{team.get("losses")}'
            parts.append(f'<li><a href="/standings/">{esc(line)}</a></li>')
        parts.append('</ul>')
    parts.append('<p class="rail-more"><a href="/standings/">Full standings</a></p></section>')
    return ''.join(parts)


def render_series(rows: list) -> str:
    if not rows:
        return ''
    items = []
    for row in rows:
        nxt = ''
        if row['next_label'] and row['next_url']:
            nxt = (
                f'<a class="rail-next" href="{esc(row["next_url"])}" target="_blank" rel="noopener">'
                f'{esc(row["next_label"])}</a>'
            )
        items.append(f'<li><p class="rail-status">{esc(row["status"])}</p>{nxt}</li>')
    return (
        '<section class="rail-box" id="playoff-series"><h2>Playoff series</h2>'
        f'<ul class="rail-list">{"".join(items)}</ul></section>'
    )


def render_scores(rows: list) -> str:
    if not rows:
        return ''
    items = []
    for row in rows:
        if row['recap']:
            link = f'<a href="{esc(row["recap"])}">{esc(row["line"])}</a>'
        elif row['espn']:
            link = f'<a href="{esc(row["espn"])}" target="_blank" rel="noopener">{esc(row["line"])}</a>'
        else:
            link = esc(row['line'])
        meta = f'<p class="rail-meta">{esc(row["when_label"])}</p>' if row['when_label'] else ''
        items.append(f'<li>{link}{meta}</li>')
    return (
        '<section class="rail-box" id="latest-scores"><h2>Latest scores</h2>'
        f'<ul class="rail-list">{"".join(items)}</ul></section>'
    )


def render_rail(events: list, articles: list, standings: dict | None, now: dt.datetime | None = None) -> str:
    """Static rail HTML. Offseason (no active or recent games) is final standings."""
    moment = now or dt.datetime.now(PT)
    if not games_active(events, moment):
        inner = render_standings(standings)
    else:
        inner = render_series(playoff_series(events)) + render_scores(latest_finals(events, articles))
        if not inner.strip():
            inner = render_standings(standings)
    html_text = f'<aside class="rail" id="home-rail">{inner}</aside>'
    for slogan in SLOGANS:
        if slogan in html_text:
            raise ValueError('Homepage rail included a slogan.')
    if '\u2014' in html_text or '\u2013' in html_text:
        raise ValueError('Homepage rail included a dash that is not a hyphen.')
    return html_text


def apply_rail(text: str, rail_html: str) -> str:
    """Replace the homepage rail. Leaves pages that have no rail block unchanged."""
    if not rail_html:
        return text
    block = f'<!-- fcb-rail:start -->{rail_html}<!-- fcb-rail:end -->'
    if RAIL_PATTERN.search(text):
        return RAIL_PATTERN.sub(lambda _match: block, text, count=1)
    return text


def _get_json(url: str) -> dict:
    request = Request(url, headers={
        'User-Agent': USER_AGENT,
        'Accept': 'application/json',
        'Accept-Encoding': 'gzip',
    })
    with urlopen(request, timeout=30) as response:
        raw = response.read()
    if raw[:2] == b'\x1f\x8b':
        raw = gzip.decompress(raw)
    payload = json.loads(raw.decode('utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('Scoreboard payload was not an object.')
    return payload


def fetch_events(today: dt.date | None = None, days_back: int = 14, days_forward: int = 14) -> list:
    """Scoreboard events across a window. Raises if too many days fail."""
    day = today or dt.datetime.now(PT).date()
    events = []
    seen = set()
    failures = 0
    for offset in range(-days_back, days_forward + 1):
        stamp = (day + dt.timedelta(days=offset)).strftime('%Y%m%d')
        try:
            payload = _get_json(f'{SCOREBOARD}?dates={stamp}')
        except Exception:
            failures += 1
            if failures > 2:
                raise
            continue
        for event in payload.get('events') or []:
            if not isinstance(event, dict):
                continue
            parsed = parse_event(event)
            if not parsed or not parsed['id'] or parsed['id'] in seen:
                continue
            seen.add(parsed['id'])
            events.append(parsed)
    if failures and not events:
        raise RuntimeError('Scoreboard returned no events.')
    return events


def build_rail_html(root: Path, today: dt.date | None = None, now: dt.datetime | None = None) -> str:
    events = fetch_events(today)
    articles_path = root / 'articles.json'
    articles = json.loads(articles_path.read_text(encoding='utf-8')) if articles_path.is_file() else []
    standings_path = root / 'api' / 'wnba-standings'
    standings = json.loads(standings_path.read_text(encoding='utf-8')) if standings_path.is_file() else {}
    return render_rail(events, articles, standings, now=now or dt.datetime.now(PT))


def load_rail(root: Path, homepage_text: str) -> str | None:
    """Fresh rail HTML, or None so the caller can keep the last good column."""
    if 'id="latest"' not in homepage_text:
        return None
    try:
        return build_rail_html(root)
    except Exception as exc:
        print(f'Homepage scoreboard failed ({exc}). Keeping the last rail.')
        return None
