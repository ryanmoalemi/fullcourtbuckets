#!/usr/bin/env python3
"""Rebuild standings/index.html from the stats feed stored for this site.

The regular-season table comes from the standings endpoint (or the snapshot
the workflow saved from it). Playoff series come from data/games, with player
logs filling boxes that have not been written yet. A second feed is only a
cross-check. If the two disagree, the last good page stays on disk and the
command exits non-zero. The page does not name or link either feed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from analytics import GA4_TAG
import internal_links as links
import playoff_board
import site_nav
import team_names
import wnba_sync

FEED_URL = 'https://site.api.espn.com/apis/v2/sports/basketball/wnba/standings'
SCOREBOARD_URL = 'https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard'
BASE = 'https://fullcourtbuckets.com'
ROUTE = '/standings/'
ADSENSE_TAG = '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-6621195315204235" crossorigin="anonymous"></script>'
EXPECTED_TEAMS = 15
PLAYOFF_SPOTS = 8
WNBA_STANDINGS_PAGE = 'https://www.wnba.com/standings'
WNBA_POSTSEASON_FAQ = 'https://www.wnba.com/news/2026-wnba-postseason-faq'


def esc(value) -> str:
    return html.escape('' if value is None else str(value), quote=True)


def _stats(entry: dict) -> dict:
    found = {}
    for stat in entry.get('stats') or []:
        if not isinstance(stat, dict):
            continue
        for key in (stat.get('name'), stat.get('type'), stat.get('abbreviation')):
            text = str(key or '').strip().casefold()
            if text:
                found[text] = stat
    return found


def _display(stats: dict, *keys: str) -> str:
    for key in keys:
        stat = stats.get(key.casefold())
        if not stat:
            continue
        text = str(stat.get('displayValue') or '').strip()
        if text:
            return text
    return ''


def _int_stat(stats: dict, key: str):
    stat = stats.get(key.casefold()) or {}
    value = stat.get('value')
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        text = str(stat.get('displayValue') or '').strip()
        if text.isdigit():
            return int(text)
        return None
    return int(value)


def _float_stat(stats: dict, key: str):
    stat = stats.get(key.casefold()) or {}
    value = stat.get('value')
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _games_back(display: str) -> str:
    text = (display or '').strip()
    if text in ('', '-', '—', '–'):
        return '0'
    return text


def _league_games_back(leader: dict, team: dict) -> str:
    gap = ((leader['wins'] - team['wins']) + (team['losses'] - leader['losses'])) / 2
    if gap <= 0:
        return '0'
    if abs(gap - round(gap)) < 1e-9:
        return str(int(round(gap)))
    return f'{gap:.1f}'


def parse_standings(payload: dict, updated_at: str) -> dict:
    """Turn the ESPN v2 payload into one record per team, plus league seeds."""
    if not isinstance(payload, dict):
        raise ValueError('Standings payload is not an object.')
    children = payload.get('children') or []
    if not isinstance(children, list) or not children:
        raise ValueError('Standings payload has no conferences.')
    raw = []
    feed_index = 0
    for child in children:
        if not isinstance(child, dict):
            continue
        label = str(child.get('name') or '').strip()
        conference = 'Eastern' if 'east' in label.casefold() else 'Western' if 'west' in label.casefold() else ''
        if not conference:
            raise ValueError(f'Unrecognized conference name: {label}')
        entries = ((child.get('standings') or {}).get('entries')) or []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            team = entry.get('team') or {}
            name = team_names.public_name(str(team.get('displayName') or team.get('name') or '').strip())
            stats = _stats(entry)
            wins, losses = _int_stat(stats, 'wins'), _int_stat(stats, 'losses')
            if not name or wins is None or losses is None:
                continue
            raw.append({
                'name': name,
                'abbreviation': str(team.get('abbreviation') or name.split()[-1][:3]).upper(),
                'wins': wins,
                'losses': losses,
                'pct': _float_stat(stats, 'winpercent'),
                'conference': conference,
                'conferenceRank': 0,
                'conferenceGamesBack': _games_back(_display(stats, 'gamesbehind', 'gb')),
                'home': _display(stats, 'home'),
                'road': _display(stats, 'road'),
                'streak': _display(stats, 'streak'),
                'last10': _display(stats, 'last ten games', 'lasttengames'),
                'feed_index': feed_index,
            })
            feed_index += 1
    # The feed lists each conference best to worst. A repeated name is a bad row.
    seen = set()
    unique = []
    for team in raw:
        if team['name'] in seen:
            continue
        seen.add(team['name'])
        unique.append(team)
    if len(unique) != EXPECTED_TEAMS:
        raise ValueError(f'Expected {EXPECTED_TEAMS} teams, found {len(unique)}.')
    for conference in ('Eastern', 'Western'):
        rank = 0
        for team in unique:
            if team['conference'] != conference:
                continue
            rank += 1
            team['conferenceRank'] = rank
    ordered = sorted(unique, key=lambda team: (-team['wins'], team['losses'], team['feed_index']))
    leader = ordered[0]
    season = payload.get('season') or {}
    year = season.get('year') if isinstance(season, dict) else None
    teams = []
    for index, team in enumerate(ordered, start=1):
        teams.append({
            'rank': index,
            'playoffSeed': index if index <= PLAYOFF_SPOTS else None,
            'name': team['name'],
            'abbreviation': team['abbreviation'],
            'wins': team['wins'],
            'losses': team['losses'],
            'pct': team['pct'] if team['pct'] is not None else (team['wins'] / (team['wins'] + team['losses'])),
            'gamesBack': _league_games_back(leader, team),
            'conferenceGamesBack': team['conferenceGamesBack'],
            'home': team['home'],
            'road': team['road'],
            'streak': team['streak'],
            'last10': team['last10'],
            'conference': team['conference'],
            'conferenceRank': team['conferenceRank'],
        })
    return {
        'updatedAt': updated_at,
        'season': year,
        'teams': teams,
    }


def _conference_name(value) -> str:
    text = str(value or '')
    if 'east' in text.casefold():
        return 'Eastern'
    if 'west' in text.casefold():
        return 'Western'
    return ''


def _record_text(value) -> str:
    return str(value or '').strip().replace('–', '-').replace('—', '-')


def _whole(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value == int(value):
        return int(value)
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    return None


def table_from_provider(rows, updated_at: str, season=None, previous=None) -> dict:
    """One row per team from standings-endpoint rows. League seeds follow the record."""
    if isinstance(rows, dict):
        season = season or rows.get('season')
        rows = rows.get('teams') or rows.get('data') or []
    if not isinstance(rows, list):
        raise ValueError('Standings rows are not a list.')
    raw = []
    previous_rank = {}
    previous_extra = {}
    if isinstance(previous, dict):
        for team in previous.get('teams') or []:
            if not isinstance(team, dict):
                continue
            if isinstance(team.get('rank'), int):
                previous_rank[team.get('name')] = team['rank']
            previous_extra[team.get('name')] = team
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        team = row.get('team') if isinstance(row.get('team'), dict) else {}
        name = team_names.public_name(str(team.get('full_name') or row.get('full_name') or team.get('name') or '').strip())
        wins, losses = _whole(row.get('wins')), _whole(row.get('losses'))
        conference = _conference_name(row.get('conference') or team.get('conference'))
        if not name or wins is None or losses is None or not conference:
            continue
        if season is None:
            season = _whole(row.get('season'))
        prior = previous_extra.get(name) or {}
        same_record = prior.get('wins') == wins and prior.get('losses') == losses
        raw.append({
            'name': name,
            'abbreviation': str(team.get('abbreviation') or row.get('abbreviation') or name.split()[-1][:3]).upper(),
            'wins': wins,
            'losses': losses,
            'pct': row.get('win_percentage') if isinstance(row.get('win_percentage'), (int, float)) and not isinstance(row.get('win_percentage'), bool) else None,
            'conference': conference,
            'conferenceRank': 0,
            'conferenceGamesBack': '',
            'home': _record_text(row.get('home_record') or row.get('home')),
            'road': _record_text(row.get('away_record') or row.get('road')),
            'streak': prior.get('streak') if same_record else '',
            'last10': prior.get('last10') if same_record else '',
            'feed_index': index,
        })
    seen = set()
    unique = []
    for team in raw:
        if team['name'] in seen:
            continue
        seen.add(team['name'])
        unique.append(team)
    if len(unique) != EXPECTED_TEAMS:
        raise ValueError(f'Expected {EXPECTED_TEAMS} teams, found {len(unique)}.')
    for conference in ('Eastern', 'Western'):
        group = [team for team in unique if team['conference'] == conference]
        group.sort(key=lambda team: (-team['wins'], team['losses'], previous_rank.get(team['name'], 99), team['feed_index']))
        if not group:
            continue
        leader_row = group[0]
        for rank, team in enumerate(group, start=1):
            team['conferenceRank'] = rank
            team['conferenceGamesBack'] = _league_games_back(leader_row, team)
    ordered = sorted(
        unique,
        key=lambda team: (-team['wins'], team['losses'], previous_rank.get(team['name'], 99), team['feed_index']),
    )
    leader = ordered[0]
    year = season
    teams = []
    for index, team in enumerate(ordered, start=1):
        played = team['wins'] + team['losses']
        teams.append({
            'rank': index,
            'playoffSeed': index if index <= PLAYOFF_SPOTS else None,
            'name': team['name'],
            'abbreviation': team['abbreviation'],
            'wins': team['wins'],
            'losses': team['losses'],
            'pct': team['pct'] if team['pct'] is not None else (team['wins'] / played if played else 0),
            'gamesBack': _league_games_back(leader, team),
            'conferenceGamesBack': team['conferenceGamesBack'],
            'home': team['home'],
            'road': team['road'],
            'streak': team['streak'],
            'last10': team['last10'],
            'conference': team['conference'],
            'conferenceRank': team['conferenceRank'],
        })
    return {
        'updatedAt': updated_at,
        'season': year,
        'teams': teams,
    }


def stamp_is_fresh(stamp: str, now: dt.datetime, hours: int = 36) -> bool:
    """True when a playoff refresh stamp is within the daily window."""
    text = str(stamp or '').strip()
    if not text:
        return False
    try:
        moment = dt.datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        return False
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo('America/Los_Angeles'))
    age = now - moment
    return dt.timedelta(0) <= age <= dt.timedelta(hours=hours)


def standings_hash(table: dict) -> str:
    """Hash of the table a reader sees. The updatedAt stamp is not part of the data."""
    payload = {'season': table.get('season'), 'teams': table.get('teams')}
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def keep_updated_at(previous, table: dict, proposed: str) -> str:
    """Keep the stored date when the standings hash is unchanged."""
    if isinstance(previous, dict) and standings_hash(previous) == standings_hash(table):
        kept = previous.get('updatedAt')
        if isinstance(kept, str) and kept.strip():
            return kept
    return proposed


def fetch_standings(url: str = FEED_URL) -> dict:
    request = Request(url, headers={'User-Agent': 'FullCourtBuckets/1.0'})
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode('utf-8'))
    return payload


def _streak_html(value: str) -> str:
    text = esc(value or '-')
    if str(value or '').startswith('W'):
        return f'<span class="winning">{text}</span>'
    if str(value or '').startswith('L'):
        return f'<span class="losing">{text}</span>'
    return f'<span class="secondary">{text}</span>'


def _pct_html(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ''
    text = f'{number:.3f}'
    if number < 1:
        text = text.replace('0.', '.', 1)
    return text


def _team_cell(team: dict, href: str) -> str:
    name = esc(team['name'])
    badge = esc(team.get('abbreviation') or '')
    label = f'<a class="team-name" href="{esc(href)}">{name}</a>' if href else f'<span class="team-name">{name}</span>'
    return f'<td><div class="team-cell"><span class="team-badge">{badge}</span>{label}</div></td>'


def _row(team: dict, href: str, wide: bool) -> str:
    rank = team['rank'] if wide else team.get('conferenceRank')
    games_back = team.get('gamesBack') if wide else team.get('conferenceGamesBack')
    cells = (
        f'<td><span class="rank">{esc(rank)}</span></td>'
        + _team_cell(team, href)
        + f'<td>{esc(team.get("wins"))}</td><td>{esc(team.get("losses"))}</td>'
        + f'<td class="percent">{esc(_pct_html(team.get("pct")))}</td><td>{esc(games_back)}</td>'
    )
    if wide:
        cells += (
            f'<td>{esc(team.get("home") or "-")}</td><td>{esc(team.get("road") or "-")}</td>'
            f'<td>{_streak_html(team.get("streak") or "")}</td><td>{esc(team.get("last10") or "-")}</td>'
        )
    playoff = wide and isinstance(team.get('rank'), int) and team['rank'] <= PLAYOFF_SPOTS
    klass = ' class="playoff-row"' if playoff else ''
    row = f'<tr{klass}>{cells}</tr>'
    if wide and team.get('rank') == PLAYOFF_SPOTS:
        row += '<tr class="playoff-line"><td colspan="10">Playoff Line</td></tr>'
    return row


def standings_refresh_clock() -> tuple[str, str]:
    """Clock time from the workflow that rebuilds this page, plus a note when it is not 6:45 AM PT."""
    workflow = Path(__file__).resolve().parents[1] / '.github' / 'workflows' / 'fcb-wnba.yml'
    text = workflow.read_text(encoding='utf-8') if workflow.is_file() else ''
    match = re.search(
        r"cron:\s*'(\d+)\s+(\d+)\s+\*\s+\*\s\*'\s*\n\s*timezone:\s*America/Los_Angeles",
        text,
    )
    if not match:
        return '', (
            'Standings refresh time: .github/workflows/fcb-wnba.yml has no America/Los_Angeles cron, '
            'so "standings refresh daily at 6:45 AM PT" was not published.'
        )
    minute, hour = int(match.group(1)), int(match.group(2))
    suffix = 'AM' if hour < 12 else 'PM'
    shown = hour % 12 or 12
    clock = f'{shown}:{minute:02d} {suffix} PT'
    note = ''
    if clock != '6:45 AM PT':
        note = (
            'Standings refresh time: the approved line "standings refresh daily at 6:45 AM PT" was not published. '
            f'.github/workflows/fcb-wnba.yml rebuilds standings at {clock} '
            f'(cron {minute} {hour} * * * America/Los_Angeles). '
            'The 6:45 AM PT job is the FAQ consistency check, and it does not rebuild standings.'
        )
    return clock, note


def season_length_answer(table: dict) -> tuple[str, str]:
    """Games played from the standings file. Remaining games only when every team has finished the same schedule."""
    teams = [team for team in (table.get('teams') or []) if isinstance(team, dict)]
    played = []
    for team in teams:
        wins, losses = team.get('wins'), team.get('losses')
        if isinstance(wins, bool) or isinstance(losses, bool) or not isinstance(wins, int) or not isinstance(losses, int):
            return '', 'Season length: a standings row is missing a win or loss total, so games remaining were not stated.'
        played.append(wins + losses)
    if not played:
        return '', 'Season length: the standings file has no team rows, so games remaining were not stated.'
    year = table.get('season') or 'This'
    if len(set(played)) == 1 and links.regular_season_is_final(table):
        games = played[0]
        sentence = (
            f'The {year} regular season on this page is {games} games. '
            f'Every team has played {games}, so no regular-season games are left.'
        )
        if table.get('champion'):
            sentence += f" The playoffs on this page are over. {table['champion']} won the title."
        elif table.get('showPlayoffs'):
            sentence += ' The playoffs are listed on this page and continue until a champion is decided.'
        return sentence, ''
    if len(set(played)) == 1:
        games = played[0]
        return (
            f'Teams on this page have each played {games} games in {year}. '
            'Games remaining are not a separate field in the standings file.',
            'Season length: every team has the same games played, but the schedule is not marked final, so games remaining were not invented.',
        )
    return (
        f'{year} games played on this page run from {min(played)} to {max(played)}. '
        'Games remaining are not a separate field in the standings file.',
        'Season length: teams do not show the same games played, and the file has no games-remaining field.',
    )


def standings_faq(table: dict) -> tuple[str, dict | None, list[str]]:
    """FAQ block, FAQPage node, and notes for facts that were not published."""
    notes = []
    tie_plain = (
        'The WNBA standings page lists this order for playoff eligibility and home-court advantage '
        f'({WNBA_STANDINGS_PAGE}). '
        'Step 1: better record in head-to-head games. '
        'Step 2: better winning percentage against teams that are .500 or better at the end of the season. '
        'Step 3: better point differential in the head-to-head games, points scored minus points allowed. '
        'Step 4: better point differential against all opponents, points scored minus points allowed. '
        'If more than two teams are tied, as many teams as possible are dropped at that step. '
        'As soon as one or more teams are separated, start again at step 1 with the teams that are still tied.'
    )
    tie_html = tie_plain.replace(
        f'({WNBA_STANDINGS_PAGE})',
        f'(<a href="{esc(WNBA_STANDINGS_PAGE)}" target="_blank" rel="noopener">WNBA standings</a>)',
    )
    format_plain = (
        'The WNBA says the 2026 playoffs take the top eight teams by regular-season record, regardless of conference '
        f'({WNBA_POSTSEASON_FAQ}). '
        'The first round is a best-of-three, played 1-1-1. '
        'The semifinals are a best-of-five, played 2-2-1. '
        'The Finals are a best-of-seven, played 2-2-1-1-1.'
    )
    format_html = format_plain.replace(
        f'({WNBA_POSTSEASON_FAQ})',
        f'(<a href="{esc(WNBA_POSTSEASON_FAQ)}" target="_blank" rel="noopener">WNBA postseason FAQ</a>)',
    )
    length_plain, length_note = season_length_answer(table)
    if length_note:
        notes.append(length_note)
    clock, clock_note = standings_refresh_clock()
    if clock_note:
        notes.append(clock_note)
    pairs = [
        ('How do WNBA playoff tiebreakers work?', tie_plain, tie_html),
        ('What is the 2026 WNBA playoff format by round?', format_plain, format_html),
    ]
    if length_plain:
        pairs.append(('How long is the WNBA season, and how many games are left?', length_plain, length_plain))
    if clock:
        if table.get('playoffsActive'):
            refresh = (
                f'Full Court Buckets refreshes these standings and the playoff series daily at {clock} '
                'until the Finals are over.'
            )
        else:
            refresh = f'Full Court Buckets refreshes these standings daily at {clock}.'
        pairs.append(('When do these standings refresh?', refresh, refresh))
    items = ''.join(
        f'<div class="faq-item"><h3>{esc(question)}</h3><p>{html_answer}</p></div>'
        for question, _plain, html_answer in pairs
    )
    block = (
        '<section class="section" id="faq">'
        '<p class="eyebrow">Standings FAQ</p>'
        '<h2>Frequently asked questions</h2>'
        f'{items}'
        '</section>'
    )
    entity = {
        '@type': 'FAQPage',
        '@id': BASE + ROUTE + '#faq',
        'mainEntity': [
            {
                '@type': 'Question',
                'name': question,
                'acceptedAnswer': {'@type': 'Answer', 'text': plain},
            }
            for question, plain, _html in pairs
        ],
    }
    return block, entity, notes


def team_hrefs(root: Path) -> dict[str, str]:
    path = root / 'data' / 'wnba' / 'players-index.json'
    if not path.is_file():
        return {}
    index = json.loads(path.read_text(encoding='utf-8'))
    linking = links.catalog_from_index(index)
    found = {}
    for slot in linking['by_id'].values():
        href = links.team_href(slot)
        found[slot['full_name']] = href
        nick = slot.get('name') or ''
        if nick:
            found.setdefault(nick, href)
    return found


def attach_playoffs(root: Path, table: dict) -> dict:
    """Series from stored games. The score has to match those games or the page is not written."""
    season = table.get('season')
    year = season if isinstance(season, int) and not isinstance(season, bool) else None
    board = playoff_board.build_board(
        playoff_board.load_results(root, year),
        playoff_board.load_schedule(root, year),
        table.get('teams') or [],
    )
    playoff_board.verify_board(board)
    table['showPlayoffs'] = bool(board.get('show'))
    table['playoffsActive'] = bool(board.get('active'))
    table['champion'] = board.get('champion') or ''
    table['playoffDigest'] = playoff_board.section_text(board)
    return board


def render_page(root: Path, table: dict) -> str:
    hrefs = team_hrefs(root)
    board = table.get('_board')
    if not isinstance(board, dict):
        board = attach_playoffs(root, table)
    menu = site_nav.build_menu(root)
    nav = site_nav.render(menu, ROUTE)
    teams = table['teams']
    when = links.updated_label(table.get('updatedAt'), with_time=bool(table.get('playoffsActive')))
    sentence = links.standings_sentence(table)
    support = f'{sentence} Updated {when}.' if when else sentence
    year = table.get('season') or ''
    heading = links.standings_title(table)
    if table.get('showPlayoffs'):
        subhead = 'Playoff series are listed above the final regular-season table.'
    elif links.regular_season_is_final(table):
        subhead = heading
    else:
        subhead = f'{year} Regular Season'
    if links.regular_season_is_final(table):
        table_heading = f'Final {year} regular-season standings' if year else 'Final regular-season standings'
    else:
        table_heading = f'{year} WNBA Standings'.strip()
    page_name = f'{year} WNBA Playoffs' if table.get('showPlayoffs') else f'{year} WNBA Standings'
    modified = links._iso_day(table.get('updatedAt'))
    playoff_html = playoff_board.render_html(board, hrefs)
    def by_conference(name):
        rows = [team for team in teams if team['conference'] == name]
        return sorted(rows, key=lambda team: team.get('conferenceRank') or 99)

    body_rows = ''.join(_row(team, hrefs.get(team['name'], ''), True) for team in teams)
    east = ''.join(_row(team, hrefs.get(team['name'], ''), False) for team in by_conference('Eastern'))
    west = ''.join(_row(team, hrefs.get(team['name'], ''), False) for team in by_conference('Western'))
    css = (Path(__file__).with_name('standings.css')).read_text(encoding='utf-8')
    if table.get('showPlayoffs'):
        description = (
            f'{year} WNBA playoff series, game results, and the final regular-season standings '
            f'for all {len(teams)} teams.'
        )
    else:
        description = (
            f'{year} WNBA standings for all {len(teams)} teams: wins, losses, winning percentage, '
            'games back, home and road records, and playoff seeds.'
        )
    structured = {
        '@context': 'https://schema.org',
        '@graph': [
            {
                '@type': 'WebPage',
                'name': page_name,
                'url': BASE + ROUTE,
                'description': description,
                'dateModified': modified,
                'isPartOf': {'@type': 'WebSite', 'name': 'Full Court Buckets', 'url': BASE + '/'},
            },
            {
                '@type': 'BreadcrumbList',
                'itemListElement': [
                    {'@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': BASE + '/'},
                    {'@type': 'ListItem', 'position': 2, 'name': 'Standings', 'item': BASE + ROUTE},
                ],
            },
        ],
    }
    faq_html, faq_entity, _notes = standings_faq(table)
    if faq_entity:
        structured['@graph'].append(faq_entity)
    schema = json.dumps(structured, ensure_ascii=False).replace('<', '\\u003c')
    conf_head = '<tr><th>RK</th><th>TEAM</th><th>W</th><th>L</th><th>PCT</th><th>GB</th></tr>'
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
{GA4_TAG}
{ADSENSE_TAG}
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(page_name)} | Full Court Buckets</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{BASE}{ROUTE}">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(page_name)} | Full Court Buckets">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{BASE}{ROUTE}">
<meta property="og:site_name" content="Full Court Buckets">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@500;600;700;800&amp;family=Inter:wght@400;500;600;700&amp;display=swap" rel="stylesheet">
<style>
{css}
</style>
<link rel="stylesheet" href="/assets/site-nav.css">
<script type="application/ld+json">{schema}</script>
</head>
<body>
<div class="utility"><div class="shell"><div class="utility-tag">WNBA News • Analysis • Commentary</div><div class="utility-note">Independent WNBA news and analysis</div></div></div>
<header><div class="shell nav"><a class="brand" href="/"><img src="/logo.png" alt="Full Court Buckets"></a>{nav}<a class="watch-btn nav-watch" href="/#latest">Latest Stories</a></div></header>
<main class="page">
<div class="standings-shell">
<div class="page-header">
<div class="eyebrow">League</div>
<h1>{esc(heading)}</h1>
<p class="subhead">{esc(subhead)}</p>
<p class="support" id="standings-updated">{esc(support)}</p>
</div>
{playoff_html}
<section class="panel">
<div class="panel-head">
<h2>{esc(table_heading)}</h2>
<div class="last-updated"><span class="dot"></span><span id="updatedAt">Updated: {esc(when)}</span></div>
</div>
<div class="table-wrap">
<table class="standings-table" aria-label="{esc(year)} WNBA Standings">
<thead>
<tr>
<th>RK</th><th>TEAM</th><th>W</th><th>L</th><th>PCT</th><th>GB</th><th>HOME</th><th>ROAD</th><th>STREAK</th><th>L10</th>
</tr>
</thead>
<tbody id="standingsBody">{body_rows}</tbody>
</table>
</div>
</section>
<div class="conference-wrap">
<section class="conf-card">
<div class="conf-header"><h3>Eastern Conference</h3></div>
<div class="table-wrap">
<table class="conf-table" aria-label="Eastern Conference Standings">
<thead>{conf_head}</thead>
<tbody id="eastStandings">{east}</tbody>
</table>
</div>
</section>
<section class="conf-card">
<div class="conf-header"><h3>Western Conference</h3></div>
<div class="table-wrap">
<table class="conf-table" aria-label="Western Conference Standings">
<thead>{conf_head}</thead>
<tbody id="westStandings">{west}</tbody>
</table>
</div>
</section>
</div>
<!-- fcb-rosters:start --><!-- fcb-rosters:end -->
<div class="info-grid">
<div class="info-card"><span class="info-label">Playoff Field</span><p>Top 8 teams qualify</p></div>
<div class="info-card"><span class="info-label">Regular Season</span><p>League standings determine playoff seeding</p></div>
<div class="info-card"><span class="info-label">Tiebreakers</span><p>Head-to-head record is the first tiebreaker</p></div>
</div>
<section class="explainer">
<h3>How WNBA Standings Work</h3>
<p>The eight teams with the best regular-season records qualify for the WNBA Playoffs. Playoff seeding is based on regular-season record rather than conference.</p>
<p>If teams finish with identical records, WNBA tiebreak procedures are used to determine playoff qualification and seeding. When records match, this page keeps the order already published.</p>
<p><strong>Tiebreakers</strong></p>
<ul>
<li>Better head-to-head record</li>
<li>Better winning percentage against teams that finish .500 or better</li>
<li>Better head-to-head point differential</li>
<li>Better point differential against all opponents</li>
</ul>
</section>
{faq_html}
</div>
</main>
{site_nav.footer_html(True)}
<script src="/assets/site-nav.js" defer></script>
</body>
</html>
'''


def fetch_json(url: str) -> dict:
    request = Request(url, headers={'User-Agent': 'FullCourtBuckets/1.0'})
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode('utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('Cross-check feed did not return an object.')
    return payload


def season_year(previous, now: dt.datetime) -> int:
    if isinstance(previous, dict):
        year = previous.get('season')
        if isinstance(year, int) and not isinstance(year, bool):
            return year
    if now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo('America/Los_Angeles'))
    return now.astimezone(ZoneInfo('America/Los_Angeles')).year


def fetch_provider_rows(season: int) -> list:
    """Standings endpoint. The key stays in the environment and is never written."""
    key = os.environ.get('BALLDONTLIE_API_KEY', '').strip()
    if not key:
        raise playoff_board.CheckError('Standings need the stats feed key. The last good page was kept.')
    rows = wnba_sync.Client(key).all('standings', {'season': season})
    if key in json.dumps(rows):
        raise playoff_board.CheckError('Standings response contained the API key. The last good page was kept.')
    return rows


def write_provider_snapshot(root: Path, rows: list, season: int, checked_at: str) -> None:
    path = root / 'data' / 'wnba' / 'standings.json'
    payload = {'checked_at': checked_at, 'season': season, 'teams': rows}
    text = json.dumps(payload, indent=2) + '\n'
    key = os.environ.get('BALLDONTLIE_API_KEY', '').strip()
    if key and key in text:
        raise playoff_board.CheckError('Refusing to write a standings file that contains the API key.')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _load_json(path: Path):
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, json.JSONDecodeError):
        return None


def cross_check_days(root: Path, table: dict, now: dt.datetime) -> list[dt.date]:
    season = table.get('season')
    year = season if isinstance(season, int) and not isinstance(season, bool) else None
    days = set()
    for game in playoff_board.load_results(root, year):
        days.add(game['day'])
    for game in playoff_board.load_schedule(root, year):
        days.add(game['day'])
    if now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo('America/Los_Angeles'))
    today = now.astimezone(ZoneInfo('America/Los_Angeles')).date()
    for offset in range(-1, 3):
        days.add(today + dt.timedelta(days=offset))
    return sorted(days)


def run_cross_check(root: Path, table: dict, board: dict, now: dt.datetime, cross_check=None, events=None) -> None:
    """Compare the table and every playoff series. Disagreement raises CheckError."""
    if cross_check is None and events is None and os.environ.get('FCB_SKIP_STANDINGS_CROSS_CHECK') == '1':
        raise playoff_board.CheckError('Cross-check was skipped. The last good page was kept.')
    if cross_check is None:
        cross_check = fetch_standings()
    if isinstance(cross_check, dict) and cross_check.get('children'):
        other = parse_standings(cross_check, table.get('updatedAt') or '')
    elif isinstance(cross_check, dict) and cross_check.get('teams'):
        other = cross_check
    else:
        raise playoff_board.CheckError('Cross-check standings could not be read. The last good page was kept.')
    playoff_board.cross_check_table(table, other)
    if not board.get('show'):
        return
    parsed = []
    if events is None:
        events = []
        for day in cross_check_days(root, table, now):
            try:
                events.append(fetch_json(SCOREBOARD_URL + '?dates=' + day.strftime('%Y%m%d')))
            except Exception as exc:
                raise playoff_board.CheckError(
                    f'Cross-check scoreboard for {day.isoformat()} failed ({exc}). The last good page was kept.'
                ) from None
    for item in events:
        if isinstance(item, dict) and item.get('events') is not None and 'pair' not in item:
            parsed.extend(playoff_board.espn_events(item))
        elif isinstance(item, dict):
            parsed.append(item)
    playoff_board.cross_check_board(board, parsed)


def build(root: Path, payload=None, updated_at: str | None = None, cross_check=None, events=None) -> bool:
    """Write the standings page. A failed check leaves the last good page on disk."""
    page = root / 'standings' / 'index.html'
    data_path = root / 'api' / 'wnba-standings'
    try:
        previous = _load_json(data_path)
        now = dt.datetime.now(ZoneInfo('America/Los_Angeles'))
        if not updated_at:
            updated_at = now.isoformat(timespec='seconds')
        if payload is None:
            year = season_year(previous, now)
            payload = fetch_provider_rows(year)
            write_provider_snapshot(root, payload, year, updated_at)
        table = table_from_provider(payload, updated_at, previous=previous)
        board = attach_playoffs(root, table)
        table['_board'] = board
        if table.get('playoffsActive'):
            table['updatedAt'] = updated_at
        else:
            table['updatedAt'] = keep_updated_at(previous, table, updated_at)
        # Fixture builds pass both sides in. A real run always fetches the cross-check.
        if payload is not None and cross_check is None and events is None:
            pass
        else:
            run_cross_check(root, table, board, now, cross_check=cross_check, events=events)
        names = [team['name'] for team in table['teams']]
        if len(names) != EXPECTED_TEAMS or len(set(names)) != EXPECTED_TEAMS:
            raise playoff_board.CheckError('Standings did not contain 15 unique teams. The last good page was kept.')
        html_text = render_page(root, table)
        index_path = root / 'data' / 'wnba' / 'players-index.json'
        if index_path.is_file():
            index = json.loads(index_path.read_text(encoding='utf-8'))
            linking = links.catalog_from_index(index)
            html_text = links.apply_standings(html_text, linking, table)
            html_text = site_nav.install(html_text, ROUTE, site_nav.build_menu(root))
        if 'espn.com' in html_text.lower() or 'balldontlie' in html_text.lower():
            raise playoff_board.CheckError('The standings page named a data feed. The last good page was kept.')
        published = {key: value for key, value in table.items() if key != '_board'}
    except Exception as exc:
        print(f'Standings check failed ({exc}). Keeping the last good page.')
        return False
    page.parent.mkdir(parents=True, exist_ok=True)
    data_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = page.with_suffix('.html.tmp')
    temporary.write_text(html_text, encoding='utf-8')
    temporary.replace(page)
    data_path.write_text(json.dumps(published, indent=2) + '\n', encoding='utf-8')
    label = links.updated_label(published.get('updatedAt'), with_time=bool(published.get('playoffsActive')))
    print(f'Wrote standings for {len(names)} teams. Updated {label}.')
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    sys.exit(0 if build(args.root) else 1)
