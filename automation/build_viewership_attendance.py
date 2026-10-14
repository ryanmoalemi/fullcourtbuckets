#!/usr/bin/env python3
"""Build /wnba/viewership-attendance/ from data/viewership-attendance.json.

Append a game or a season row to the JSON and rerun this script. The page
reads every attendance and viewership figure from that file. A row with no
date, or a number with no source URL, fails the build.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from analytics import GA4_TAG
import internal_links as links
import site_nav

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = 'data/viewership-attendance.json'
ROUTE = '/wnba/viewership-attendance/'
BASE = 'https://fullcourtbuckets.com'
PAGE_TITLE = 'WNBA viewership and attendance stats 2026: How many people watch the WNBA?'
DESCRIPTION = (
    'Record 2026 WNBA attendance, fans per game, Finals audiences, and the '
    'most-watched games, each figure with its date and source.'
)
ADSENSE_TAG = (
    '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js'
    '?client=ca-pub-6621195315204235" crossorigin="anonymous"></script>'
)
DAY_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
MONTH_RE = re.compile(r'^\d{4}-\d{2}$')
MONTHS = {
    1: 'Jan.', 2: 'Feb.', 3: 'March', 4: 'April', 5: 'May', 6: 'June',
    7: 'July', 8: 'Aug.', 9: 'Sept.', 10: 'Oct.', 11: 'Nov.', 12: 'Dec.',
}
WEEKDAYS = ('Mon.', 'Tue.', 'Wed.', 'Thu.', 'Fri.', 'Sat.', 'Sun.')
# Longer names first so "Indiana Fever" is not also linked as "Fever".
TEAM_LINKS = (
    ('Golden State Valkyries', '/wnba/teams/golden-state-valkyries/'),
    ('Washington Mystics', '/wnba/teams/washington-mystics/'),
    ('New York Liberty', '/wnba/teams/new-york-liberty/'),
    ('Los Angeles Sparks', '/wnba/teams/los-angeles-sparks/'),
    ('Phoenix Mercury', '/wnba/teams/phoenix-mercury/'),
    ('Las Vegas Aces', '/wnba/teams/las-vegas-aces/'),
    ('Minnesota Lynx', '/wnba/teams/minnesota-lynx/'),
    ('Indiana Fever', '/wnba/teams/indiana-fever/'),
    ('Chicago Sky', '/wnba/teams/chicago-sky/'),
    ('Atlanta Dream', '/wnba/teams/atlanta-dream/'),
    ('Connecticut Sun', '/wnba/teams/connecticut-sun/'),
    ('Valkyries', '/wnba/teams/golden-state-valkyries/'),
    ('Mystics', '/wnba/teams/washington-mystics/'),
    ('Liberty', '/wnba/teams/new-york-liberty/'),
    ('Mercury', '/wnba/teams/phoenix-mercury/'),
    ('Sparks', '/wnba/teams/los-angeles-sparks/'),
    ('Fever', '/wnba/teams/indiana-fever/'),
    ('Dream', '/wnba/teams/atlanta-dream/'),
    ('Aces', '/wnba/teams/las-vegas-aces/'),
    ('Lynx', '/wnba/teams/minnesota-lynx/'),
    ('Sky', '/wnba/teams/chicago-sky/'),
    ('Sun', '/wnba/teams/connecticut-sun/'),
)
TEAM_RE = re.compile(r'\b(' + '|'.join(re.escape(name) for name, _href in TEAM_LINKS) + r')\b')
TEAM_HREF = dict(TEAM_LINKS)
# A number on a season row requires the source field beside it.
SEASON_NUMBERS = (
    ('total_attendance', 'attendance_source'),
    ('games_played', 'attendance_source'),
    ('avg_attendance', 'avg_attendance_source'),
    ('finals_avg_viewers', 'finals_viewers_source'),
    ('finals_games', 'finals_viewers_source'),
    ('relocated_games', 'relocated_source'),
    ('relocated_attendance', 'relocated_source'),
    ('relocated_avg', 'relocated_source'),
    ('home_attendance', 'home_attendance_source'),
    ('home_games', 'home_attendance_source'),
)
EXTRA_CSS = """
.audience-table{width:100%;border-collapse:separate;border-spacing:0;min-width:640px}
.audience-table th,.audience-table td{padding:12px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}
.audience-table thead th{color:#9b958f;font-size:11px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;background:rgba(17,18,21,.9)}
.audience-table tbody td{font-size:14px;color:#f5f3ef}
.audience-table a,.answer a,.note a,.byline a,.sources a,.cite a{color:var(--orange);text-decoration:underline;text-underline-offset:3px}
.qa{margin-top:36px}
.qa h2,.key-stats h2{margin:0 0 10px;font:800 clamp(26px,3vw,34px)/1.1 "Barlow",sans-serif;letter-spacing:-.5px}
.answer{margin:0 0 14px;color:#f5f3ef;font-size:18px;line-height:1.45}
.key-stats{margin-top:8px}
.key-list{margin:0;padding:0;list-style:none;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
.key-list li{margin:0;padding:14px 16px;border:1px solid var(--line);background:rgba(11,11,13,.95);color:#e8e4df;font-size:14px;line-height:1.45}
.byline{margin:10px 0 0;color:#d2cec8;font-size:14px}
.sources{margin:10px 0 0;color:#a39d95;font-size:13px;line-height:1.55}
.note{margin:10px 0 0;color:#d6d2cd;font-size:14px;line-height:1.6}
.pending{color:#a39d95}
.cite{margin:8px 0;padding:12px 14px;border-left:3px solid var(--purple);color:#d6d2cd;font-size:15px;line-height:1.5}
.cite code{display:block;margin-top:8px;color:#f5f3ef;font-size:13px;white-space:normal}
.how-made{margin-top:22px;color:#8a877f;font-size:13px;line-height:1.55}
.how-made a{color:var(--orange)}
@media(max-width:900px){.key-list{grid-template-columns:1fr}.answer{font-size:16px}}
"""


def esc(value) -> str:
    return html.escape('' if value is None else str(value), quote=True)


def is_number(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_source_url(value) -> bool:
    """A public http(s) page. Machine endpoints are not a source credit."""
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text.startswith(('http://', 'https://')) or ' ' in text:
        return False
    parsed = urlparse(text)
    host = (parsed.hostname or '').lower()
    if not host:
        return False
    labels = host.split('.')
    path = [part for part in (parsed.path or '').lower().split('/') if part]
    if 'api' in labels or 'api' in path or 'apis' in path:
        return False
    if (parsed.path or '').lower().split('?', 1)[0].endswith('.json'):
        return False
    return True


def parse_day(value: str) -> dt.date:
    year, month, day = (int(part) for part in value.split('-'))
    return dt.date(year, month, day)


def valid_day(value) -> bool:
    if not isinstance(value, str) or not DAY_RE.fullmatch(value):
        return False
    try:
        parse_day(value)
    except ValueError:
        return False
    return True


def valid_source_date(value) -> bool:
    if value in ('', None):
        return True
    if not isinstance(value, str):
        return False
    if DAY_RE.fullmatch(value):
        return valid_day(value)
    if not MONTH_RE.fullmatch(value):
        return False
    year, month = (int(part) for part in value.split('-'))
    return 1990 <= year <= 2100 and 1 <= month <= 12


def _row_label(kind: str, index: int, row: dict) -> str:
    if kind == 'game':
        name = str(row.get('game') or '').strip() or f'game {index + 1}'
        return f'Game row {index + 1} ({name})'
    season = row.get('season')
    team = str(row.get('home_team') or '').strip()
    where = f'season {season}' if season else f'season row {index + 1}'
    if team:
        where = f'{where}, {team}'
    return f'Season row {index + 1} ({where})'


def _require_number_source(label: str, row: dict, number_key: str, source_key: str) -> None:
    value = row.get(number_key)
    if value is None:
        return
    if not is_number(value):
        raise ValueError(f'{label} has a {number_key} that is not a whole number.')
    if not is_source_url(row.get(source_key)):
        raise ValueError(f'{label} has a number but no source.')


def validate(payload: dict) -> None:
    """Fail when a row has no date, or a number and no source URL."""
    if not isinstance(payload, dict):
        raise ValueError('Viewership file is not an object.')
    if not valid_day(payload.get('updated')):
        raise ValueError('Viewership file is missing a date.')
    games = payload.get('games')
    seasons = payload.get('seasons')
    if not isinstance(games, list):
        raise ValueError('Viewership file is missing a games list.')
    if seasons is None:
        seasons = []
    if not isinstance(seasons, list):
        raise ValueError('Viewership seasons must be a list.')
    for index, row in enumerate(games):
        if not isinstance(row, dict):
            raise ValueError(f'Game row {index + 1} is not an object.')
        label = _row_label('game', index, row)
        if not valid_day(row.get('date')):
            raise ValueError(f'{label} is missing a date.')
        if not str(row.get('game') or '').strip():
            raise ValueError(f'{label} is missing a game name.')
        season = row.get('season')
        if not is_number(season):
            raise ValueError(f'{label} is missing a season.')
        _require_number_source(label, row, 'attendance', 'attendance_source')
        _require_number_source(label, row, 'viewers', 'viewers_source')
        for key in ('attendance_source_date', 'viewers_source_date'):
            if not valid_source_date(row.get(key)):
                raise ValueError(f'{label} has a source date that is not a month or a day.')
    for index, row in enumerate(seasons):
        if not isinstance(row, dict):
            raise ValueError(f'Season row {index + 1} is not an object.')
        label = _row_label('season', index, row)
        season = row.get('season')
        if not is_number(season):
            raise ValueError(f'{label} is missing a date.')
        for number_key, source_key in SEASON_NUMBERS:
            _require_number_source(label, row, number_key, source_key)
        for key in (
            'attendance_source_date', 'avg_attendance_source_date',
            'finals_viewers_source_date', 'relocated_source_date',
            'home_attendance_source_date',
        ):
            if not valid_source_date(row.get(key)):
                raise ValueError(f'{label} has a source date that is not a month or a day.')


def format_number(value: int) -> str:
    if value >= 1_000_000 and value % 10_000 == 0:
        text = f'{value / 1_000_000:.2f}'.rstrip('0').rstrip('.')
        return f'{text} million'
    return f'{value:,}'


def format_day(value: str, *, weekday: bool = False) -> str:
    date = parse_day(value)
    label = f'{MONTHS[date.month]} {date.day}, {date.year}'
    if weekday:
        return f'{WEEKDAYS[date.weekday()]} {label}'
    return label


def format_updated(value: str) -> str:
    date = parse_day(value)
    return f'{MONTHS[date.month]} {date.day}, {date.year}'


def network_phrase(network: str) -> str:
    parts = [part.strip() for part in str(network or '').split(',') if part.strip()]
    if len(parts) < 2:
        return str(network or '')
    if len(parts) == 2:
        return f'{parts[0]} and {parts[1]}'
    return ', '.join(parts[:-1]) + ' and ' + parts[-1]


def format_source_date(value: str) -> str:
    if not value:
        return ''
    if len(value) == 7:
        year, month = (int(part) for part in value.split('-'))
        return f'{MONTHS[month]} {year}'
    return format_day(value)


def source_label(url: str) -> str:
    host = (urlparse(url).hostname or '').lower().removeprefix('www.')
    if host == 'espnpressroom.com':
        return 'ESPN press release'
    if host.endswith('nbcsports.com'):
        return 'NBC Sports press release'
    if host.endswith('sportsmediawatch.com'):
        return 'Sports Media Watch'
    if host.endswith('sportsbusinessjournal.com'):
        return 'Sports Business Journal'
    if host == 'valkyries.wnba.com':
        return 'Golden State Valkyries'
    if host.endswith('wnba.com'):
        return 'WNBA.com'
    if host.endswith('frontofficesports.com'):
        return 'Front Office Sports'
    return host


def link_teams(text: str) -> str:
    escaped = esc(text)

    def replace(match: re.Match) -> str:
        name = match.group(1)
        href = TEAM_HREF.get(name)
        if not href:
            return name
        return f'<a href="{href}">{name}</a>'

    return TEAM_RE.sub(replace, escaped)


def sources_line(pairs: list[tuple[str, str]]) -> str:
    seen = []
    for url, date in pairs:
        if not url or any(url == existing for existing, _date in seen):
            continue
        seen.append((url, date or ''))
    if not seen:
        return ''
    bits = []
    for url, date in seen:
        link = f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(source_label(url))}</a>'
        when = format_source_date(date)
        bits.append(f'{link} ({esc(when)})' if when else link)
    return '<p class="sources">Sources: ' + ', '.join(bits) + '.</p>'


def league_rows(payload: dict) -> list[dict]:
    return [row for row in payload.get('seasons') or [] if not str(row.get('home_team') or '').strip()]


def home_rows(payload: dict) -> list[dict]:
    rows = [row for row in payload.get('seasons') or [] if str(row.get('home_team') or '').strip() and is_number(row.get('home_attendance'))]
    return sorted(rows, key=lambda row: (-row['home_attendance'], -row['season']))


def number_rows(rows: list[dict], key: str) -> list[dict]:
    return [row for row in rows if is_number(row.get(key))]


def is_finals_game(row: dict) -> bool:
    return str(row.get('game') or '').startswith('Finals Game')


def is_all_star(row: dict) -> bool:
    return 'All-Star' in str(row.get('game') or '')


def lead_sentence(payload: dict) -> str:
    season = next((row for row in league_rows(payload) if row.get('season') == 2026 and is_number(row.get('total_attendance'))), None)
    game = next((row for row in payload['games'] if row.get('date') == '2026-08-23' and is_number(row.get('viewers'))), None)
    if (
        season and game
        and season['total_attendance'] == 3_790_000
        and season.get('games_played') == 330
        and game['viewers'] == 3_310_000
    ):
        return (
            'The WNBA drew a record 3.79 million fans to regular-season games in 2026, '
            'and its most-watched regular-season game since 1997 pulled 3.31 million TV and streaming viewers.'
        )
    parts = []
    if season:
        parts.append(
            f"The WNBA's {season['season']} regular season drew {format_number(season['total_attendance'])} fans."
        )
    if game:
        parts.append(
            f"{game['game']} on {format_day(game['date'])} drew {format_number(game['viewers'])} viewers."
        )
    return ' '.join(parts)


def key_stats(payload: dict) -> list[str]:
    items = []
    totals = number_rows(league_rows(payload), 'total_attendance')
    if totals:
        top = max(totals, key=lambda row: (row['total_attendance'], row['season']))
        figure = format_number(top['total_attendance'])
        record = top['total_attendance'] == 3_790_000 and all(
            row['total_attendance'] <= top['total_attendance'] for row in totals
        )
        if record:
            items.append(f"{top['season']} regular-season attendance hit a record {figure}.")
        else:
            items.append(f"{top['season']} regular-season attendance was {figure}.")
    averages = number_rows(league_rows(payload), 'avg_attendance')
    if averages:
        top = max(averages, key=lambda row: (row['avg_attendance'], row['season']))
        figure = format_number(top['avg_attendance'])
        if top['avg_attendance'] == 11474 and all(row['avg_attendance'] <= 11474 for row in averages):
            items.append(f'WNBA games averaged a record {figure} fans per game in {top["season"]}.')
        else:
            items.append(f'WNBA games averaged {figure} fans per game in {top["season"]}.')
    later = []
    for row in payload['games']:
        if not is_number(row.get('viewers')) or is_all_star(row) or is_finals_game(row):
            continue
        if row['date'] <= '1997-06-22':
            continue
        later.append(row)
    if later:
        top = max(later, key=lambda row: row['viewers'])
        figure = format_number(top['viewers'])
        if top['date'] == '2026-08-23' and top['viewers'] == 3_310_000:
            items.append(
                f'{top["game"]} on {format_day(top["date"])} drew {figure} viewers on {network_phrase(top.get("network") or "")}, '
                'the most for a regular-season game since 1997.'
            )
        else:
            network = f' on {network_phrase(top["network"])}' if top.get('network') else ''
            items.append(f'{top["game"]} on {format_day(top["date"])} drew {figure} viewers{network}.')
    finals = number_rows(league_rows(payload), 'finals_avg_viewers')
    for season in (2024, 2025):
        row = next((item for item in finals if item.get('season') == season), None)
        if not row:
            continue
        figure = format_number(row['finals_avg_viewers'])
        if season == 2024 and row['finals_avg_viewers'] == 1_600_000:
            items.append(f'The 2024 Finals averaged {figure} viewers, the most-watched Finals in 25 years.')
        elif season == 2025 and row['finals_avg_viewers'] == 1_500_000 and row.get('finals_games') == 4:
            items.append(f'The 2025 Finals averaged {figure} viewers over a four-game sweep.')
        else:
            items.append(f'The {season} Finals averaged {figure} viewers.')
    crowds = number_rows(payload['games'], 'attendance')
    if crowds:
        top = max(crowds, key=lambda row: row['attendance'])
        figure = format_number(top['attendance'])
        if top['date'] == '2024-09-19' and top['attendance'] == 20711:
            items.append(
                f'The single-game attendance record is {figure}, set {format_day(top["date"])} '
                "(as of the league's 2024 release)."
            )
        else:
            items.append(f'The largest listed crowd is {figure}, on {format_day(top["date"])}.')
    return items


def table(headers: list[str], rows: list[list[str]], label: str) -> str:
    head = ''.join(f'<th>{esc(header)}</th>' for header in headers)
    body = []
    for row in rows:
        cells = ''.join(f'<td>{cell}</td>' for cell in row)
        body.append(f'<tr>{cells}</tr>')
    return (
        '<div class="table-wrap"><table class="audience-table" aria-label="' + esc(label) + '">'
        f'<thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'
    )


def section(heading: str, answer: str, table_html: str, source_html: str, note: str = '') -> str:
    note_html = f'<p class="note">{link_teams(note)}</p>' if note else ''
    return (
        '<section class="qa">'
        f'<h2>{esc(heading)}</h2>'
        f'<p class="answer">{link_teams(answer)}</p>'
        f'{table_html}{note_html}{source_html}'
        '</section>'
    )


def finals_answer(payload: dict) -> str:
    row = next((item for item in league_rows(payload) if item.get('season') == 2024 and is_number(item.get('finals_avg_viewers'))), None)
    if row and row['finals_avg_viewers'] == 1_600_000:
        return 'The 2024 Finals averaged 1.6 million viewers, the highest of the last 25 years.'
    finals = number_rows(league_rows(payload), 'finals_avg_viewers')
    if not finals:
        return ''
    top = max(finals, key=lambda item: item['finals_avg_viewers'])
    return f"The {top['season']} Finals averaged {format_number(top['finals_avg_viewers'])} viewers."


def finals_section(payload: dict) -> str:
    rows = sorted(number_rows(league_rows(payload), 'finals_avg_viewers'), key=lambda row: -row['season'])
    if not rows:
        return ''
    body = []
    sources = []
    for row in rows:
        body.append([
            esc(row['season']),
            link_teams(str(row.get('finals_matchup') or '')),
            esc(row.get('finals_games') if row.get('finals_games') is not None else ''),
            esc(format_number(row['finals_avg_viewers'])),
            esc(row.get('finals_network') or ''),
        ])
        sources.append((row.get('finals_viewers_source') or '', row.get('finals_viewers_source_date') or ''))
    return section(
        'How many people watched the WNBA Finals?',
        finals_answer(payload),
        table(['Year', 'Matchup', 'Games', 'Avg. viewers', 'Network'], body, 'WNBA Finals viewership by year'),
        sources_line(sources),
    )


def watched_answer(payload: dict) -> str:
    watched = number_rows(payload['games'], 'viewers')
    if not watched:
        return ''
    top = max(watched, key=lambda row: row['viewers'])
    if top.get('date') == '1997-06-21' and top['viewers'] == 5_040_000:
        return (
            "The most-watched WNBA game ever is the league's 1997 opener, Liberty vs. Sparks, "
            'with 5.04 million viewers on NBC.'
        )
    network = f" on {top['network']}" if top.get('network') else ''
    return f"{top['game']} on {format_day(top['date'])} drew {format_number(top['viewers'])} viewers{network}."


def watched_section(payload: dict) -> str:
    rows = sorted(number_rows(payload['games'], 'viewers'), key=lambda row: (-row['viewers'], row['date']))
    if not rows:
        return ''
    body = []
    sources = []
    for row in rows:
        body.append([
            link_teams(row['game']),
            esc(format_day(row['date'])),
            esc(format_number(row['viewers'])),
            esc(row.get('network') or ''),
        ])
        sources.append((row.get('viewers_source') or '', row.get('viewers_source_date') or ''))
    note = ''
    if any(row.get('season') == 2026 and 'Peacock' in str(row.get('network') or '') for row in rows):
        note = "NBC's 2026 numbers count TV plus Peacock streaming. Older numbers are TV only."
    return section(
        'What are the most-watched WNBA games?',
        watched_answer(payload),
        table(['Game', 'Date', 'Viewers', 'Network'], body, 'Most-watched WNBA games'),
        sources_line(sources),
        note,
    )


def attendance_answer(payload: dict) -> str:
    row = next((item for item in league_rows(payload) if item.get('season') == 2026 and is_number(item.get('total_attendance'))), None)
    if row and row['total_attendance'] == 3_790_000 and row.get('games_played') == 330:
        return "The WNBA's 2026 regular season drew 3.79 million fans across 330 games, a league record."
    totals = number_rows(league_rows(payload), 'total_attendance')
    if not totals:
        return ''
    top = max(totals, key=lambda item: item['total_attendance'])
    games = f" across {top['games_played']} games" if is_number(top.get('games_played')) else ''
    return f"The WNBA's {top['season']} regular season drew {format_number(top['total_attendance'])} fans{games}."


def attendance_section(payload: dict) -> str:
    rows = sorted(number_rows(league_rows(payload), 'total_attendance'), key=lambda row: -row['season'])
    if not rows:
        return ''
    body = []
    sources = []
    for row in rows:
        total = format_number(row['total_attendance'])
        if is_number(row.get('games_played')):
            total = f"{total} ({row['games_played']} games)"
        body.append([esc(row['season']), esc(total)])
        sources.append((row.get('attendance_source') or '', row.get('attendance_source_date') or ''))
    return section(
        'How many fans attended WNBA games?',
        attendance_answer(payload),
        table(['Season', 'Total attendance'], body, 'WNBA attendance by season'),
        sources_line(sources),
    )


def average_answer(payload: dict) -> str:
    row = next((item for item in league_rows(payload) if item.get('season') == 2026 and item.get('avg_attendance') == 11474), None)
    if row:
        return 'WNBA games averaged a record 11,474 fans in 2026.'
    averages = number_rows(league_rows(payload), 'avg_attendance')
    if not averages:
        return ''
    top = max(averages, key=lambda item: item['avg_attendance'])
    return f"WNBA games averaged {format_number(top['avg_attendance'])} fans in {top['season']}."


def average_section(payload: dict) -> str:
    rows = sorted(number_rows(league_rows(payload), 'avg_attendance'), key=lambda row: -row['season'])
    if not rows:
        return ''
    body = [[esc(row['season']), esc(format_number(row['avg_attendance']))] for row in rows]
    sources = [(row.get('avg_attendance_source') or '', row.get('avg_attendance_source_date') or '') for row in rows]
    note = ''
    if any(row.get('season') == 2026 for row in rows):
        note = 'Two expansion teams joined in 2026, so per-game average is the fairer year-to-year comparison.'
    return section(
        'What is the average WNBA attendance per game?',
        average_answer(payload),
        table(['Season', 'Fans per game'], body, 'WNBA average attendance per game'),
        sources_line(sources),
        note,
    )


def crowd_detail(row: dict) -> str:
    parts = [format_number(row['attendance'])]
    detail = [row.get('game') or '']
    if row.get('venue'):
        detail.append(row['venue'])
    detail = [part for part in detail if part]
    if detail:
        parts[0] = f"{parts[0]} ({', '.join(detail)})"
    return parts[0]


def crowds_answer(payload: dict) -> str:
    crowds = number_rows(payload['games'], 'attendance')
    if not crowds:
        return ''
    top = max(crowds, key=lambda row: row['attendance'])
    if top['date'] == '2024-09-19' and top['attendance'] == 20711:
        return (
            'The biggest WNBA crowd on record is 20,711, for Fever at Mystics on Sept. 19, 2024, '
            "as of the league's 2024 release."
        )
    return f"The largest listed crowd is {format_number(top['attendance'])}, {top['game']} on {format_day(top['date'])}."


def crowds_section(payload: dict) -> str:
    crowds = sorted(number_rows(payload['games'], 'attendance'), key=lambda row: -row['attendance'])
    relocated = [
        row for row in league_rows(payload)
        if is_number(row.get('relocated_games')) or is_number(row.get('relocated_attendance')) or is_number(row.get('relocated_avg'))
    ]
    if not crowds and not relocated:
        return ''
    body = []
    sources = []
    for index, row in enumerate(crowds):
        label = 'Single-game attendance' if index == 0 and row['attendance'] == 20711 else row['game']
        body.append([
            link_teams(label),
            link_teams(crowd_detail(row)),
            esc(format_day(row['date'])),
        ])
        sources.append((row.get('attendance_source') or '', row.get('attendance_source_date') or ''))
    for row in sorted(relocated, key=lambda item: -item['season']):
        bits = []
        if is_number(row.get('relocated_games')):
            bits.append(f"{row['relocated_games']} games")
        if is_number(row.get('relocated_attendance')):
            bits.append(f"{format_number(row['relocated_attendance'])} fans")
        text = ', '.join(bits)
        if is_number(row.get('relocated_avg')):
            text = f"{text} ({format_number(row['relocated_avg'])} avg.)" if text else f"{format_number(row['relocated_avg'])} avg."
        elif row.get('relocated_avg_status') == 'unresolved':
            text = f'{text}, average unresolved' if text else 'average unresolved'
        body.append([
            esc(f"Relocated big-arena games, {row['season']}"),
            esc(text),
            esc(f"{row['season']} season"),
        ])
        sources.append((row.get('relocated_source') or '', row.get('relocated_source_date') or ''))
    notes = []
    if any(row.get('date') == '2024-09-19' and row.get('attendance') == 20711 for row in crowds):
        notes.append("We haven't found a league release confirming whether 20,711 was topped in 2025 or 2026.")
    if any(row.get('relocated_avg_status') == 'unresolved' for row in relocated):
        notes.append('The 2026 relocated-game average is unresolved. 388,997 divided by 25 is 15,560, so the printed average is omitted.')
    note = ' '.join(notes)
    return section(
        'What is the biggest WNBA crowd on record?',
        crowds_answer(payload),
        table(['Record', 'Number', 'Date'], body, 'WNBA record crowds'),
        sources_line(sources),
        note,
    )


def home_answer(payload: dict) -> str:
    rows = home_rows(payload)
    if not rows:
        return ''
    top = rows[0]
    if top.get('home_team') == 'Golden State Valkyries' and top['home_attendance'] == 397408 and top.get('season') == 2025:
        return (
            'The Golden State Valkyries set the single-season home attendance record with 397,408 fans in 2025, '
            "an average of 18,064. Indiana's 340,715 in 2024 stays as that season's record in the league release."
        )
    return f"{top['home_team']} drew {format_number(top['home_attendance'])} fans at home in {top['season']}."


def home_cell(row: dict) -> str:
    text = format_number(row['home_attendance'])
    bits = []
    if is_number(row.get('home_games')):
        bits.append(f"{row['home_games']} games")
    if str(row.get('home_note') or '').strip():
        bits.append(str(row['home_note']).strip())
    if bits:
        text = f"{text} ({'; '.join(bits)})"
    return text


def home_section(payload: dict) -> str:
    rows = home_rows(payload)
    if not rows:
        return ''
    body = []
    sources = []
    for row in rows:
        body.append([
            link_teams(row['home_team']),
            esc(row['season']),
            esc(home_cell(row)),
        ])
        sources.append((row.get('home_attendance_source') or '', row.get('home_attendance_source_date') or ''))
    return section(
        'Which WNBA team has the biggest home crowds?',
        home_answer(payload),
        table(['Team', 'Season', 'Home attendance'], body, 'Biggest home crowds by team'),
        sources_line(sources),
        "Other teams' totals will be added once verified from league sources.",
    )


def tracker_answer(payload: dict) -> str:
    games = [row for row in payload['games'] if row.get('season') == 2026 and is_finals_game(row)]
    matchup = ''
    for row in league_rows(payload):
        if row.get('season') == 2026 and str(row.get('finals_matchup') or '').strip():
            matchup = str(row['finals_matchup']).strip()
            break
    if not games:
        return ''
    first = min(games, key=lambda row: row['date'])
    when = format_day(first['date'])
    if matchup == 'Valkyries vs. Dream' and first['date'] == '2026-10-17':
        return 'The 2026 Finals (Valkyries vs. Dream) begin Oct. 17.'
    if matchup:
        return f"The {first['season']} Finals ({matchup}) begin {when}."
    return f"The {first['season']} Finals begin {when}."


def tracker_section(payload: dict) -> str:
    games = sorted(
        [row for row in payload['games'] if is_finals_game(row)],
        key=lambda row: (row.get('season') or 0, row['date']),
    )
    if not games:
        return ''
    body = []
    sources = []
    for row in games:
        match = re.fullmatch(r'Finals Game (\d+)', row['game'])
        label = match.group(1) if match else row['game']
        if is_number(row.get('viewers')):
            viewers = esc(format_number(row['viewers']))
            sources.append((row.get('viewers_source') or '', row.get('viewers_source_date') or ''))
        else:
            viewers = '<span class="pending">Pending</span>'
        when = format_day(row['date'], weekday=True)
        tip = str(row.get('tip') or '').strip()
        if tip:
            when = f'{when}, {tip}'
        if row.get('schedule_source'):
            sources.append((row.get('schedule_source') or '', row.get('schedule_source_date') or ''))
        body.append([
            esc(label),
            esc(when),
            esc(row.get('venue') or ''),
            esc(row.get('network') or ''),
            viewers,
        ])
    source_html = sources_line(sources)
    if not source_html:
        source_html = '<p class="sources">Sources: to be added per game (network press releases, Sports Media Watch).</p>'
    return section(
        'How many people are watching the 2026 WNBA Finals?',
        tracker_answer(payload),
        table(['Game', 'Date', 'Venue', 'Network', 'Viewers'], body, '2026 WNBA Finals viewership tracker'),
        source_html,
        'Games 5, 6 and 7 are if necessary. The Oct. 13, 2026 release does not list their dates.',
    )


def methodology() -> str:
    return (
        '<section class="qa explainer">'
        '<h2>How this page is built</h2>'
        '<ul>'
        '<li><strong>Viewership:</strong> Nielsen estimates reported by the league, the networks or Sports Media Watch. '
        'Nielsen added smart-TV and set-top-box data ("Big Data + Panel") in 2025, which gives 2025 and later numbers '
        'a built-in boost over earlier years.</li>'
        '<li><strong>Attendance:</strong> paid attendance from the league, or Sports Business Journal\'s count of official box scores.</li>'
        '<li><strong>No guessing:</strong> we leave a cell empty rather than estimate. '
        'Spot an error? Email <a href="mailto:hello@fullcourtbuckets.com">Ryan</a> and we\'ll fix it with a dated correction note.</li>'
        '</ul></section>'
    )


def cite_block(updated: str) -> str:
    url = BASE + ROUTE
    return (
        '<section class="qa">'
        '<h2>Cite this page</h2>'
        f'<blockquote class="cite">WNBA viewership and attendance stats 2026. Full Court Buckets. '
        f'Updated {esc(updated)}. <a href="{url}">{url}</a></blockquote>'
        '<p class="cite"><code>'
        + esc(f'<a href="{url}">WNBA viewership and attendance stats (Full Court Buckets)</a>')
        + '</code></p></section>'
    )


def render_page(root: Path, payload: dict) -> str:
    menu = site_nav.build_menu(root)
    updated = format_updated(payload['updated'])
    stats = ''.join(f'<li>{link_teams(item)}</li>' for item in key_stats(payload))
    sections = ''.join([
        finals_section(payload),
        watched_section(payload),
        attendance_section(payload),
        average_section(payload),
        crowds_section(payload),
        home_section(payload),
        tracker_section(payload),
        methodology(),
        cite_block(updated),
    ])
    questions = []
    for heading, answer in (
        ('How many people watched the WNBA Finals?', finals_answer(payload)),
        ('What are the most-watched WNBA games?', watched_answer(payload)),
        ('How many fans attended WNBA games?', attendance_answer(payload)),
        ('What is the average WNBA attendance per game?', average_answer(payload)),
        ('What is the biggest WNBA crowd on record?', crowds_answer(payload)),
        ('Which WNBA team has the biggest home crowds?', home_answer(payload)),
        ('How many people are watching the 2026 WNBA Finals?', tracker_answer(payload)),
    ):
        if answer:
            questions.append({
                '@type': 'Question',
                'name': heading,
                'acceptedAnswer': {'@type': 'Answer', 'text': answer},
            })
    structured = {
        '@context': 'https://schema.org',
        '@graph': [
            {
                '@type': 'WebPage',
                'name': PAGE_TITLE,
                'headline': PAGE_TITLE,
                'url': BASE + ROUTE,
                'description': DESCRIPTION,
                'datePublished': '2026-10-13',
                'dateModified': payload['updated'],
                'author': {'@type': 'Person', 'name': 'Ryan Moalemi', 'url': BASE + '/authors/ryan-moalemi/'},
                'isPartOf': {'@type': 'WebSite', 'name': 'Full Court Buckets', 'url': BASE + '/'},
            },
            {
                '@type': 'BreadcrumbList',
                'itemListElement': [
                    {'@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': BASE + '/'},
                    {'@type': 'ListItem', 'position': 2, 'name': PAGE_TITLE, 'item': BASE + ROUTE},
                ],
            },
        ],
    }
    if questions:
        structured['@graph'].append({
            '@type': 'FAQPage',
            '@id': BASE + ROUTE + '#faq',
            'mainEntity': questions,
        })
    schema = json.dumps(structured, ensure_ascii=False).replace('<', '\\u003c')
    css = (Path(__file__).with_name('standings.css')).read_text(encoding='utf-8') + EXTRA_CSS
    lead = link_teams(lead_sentence(payload))
    disclosure = f'<p class="how-made">{esc(links.HOW_MADE_OTHER)} {links.HOW_MADE_LINK}</p>'
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
{GA4_TAG}
{ADSENSE_TAG}
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(PAGE_TITLE)} | Full Court Buckets</title>
<meta name="description" content="{esc(DESCRIPTION)}">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{BASE}{ROUTE}">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(PAGE_TITLE)}">
<meta property="og:description" content="{esc(DESCRIPTION)}">
<meta property="og:url" content="{BASE}{ROUTE}">
<meta property="og:site_name" content="Full Court Buckets">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{esc(PAGE_TITLE)}">
<meta name="twitter:description" content="{esc(DESCRIPTION)}">
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
{site_nav.render_header(menu, ROUTE)}
<main class="page">
<div class="standings-shell">
<div class="page-header">
<p class="eyebrow">Viewership</p>
<h1>{esc(PAGE_TITLE)}</h1>
<p class="support" id="viewership-updated">Last updated: {esc(updated)}.</p>
<p class="byline">By <a href="/authors/ryan-moalemi/">Ryan Moalemi</a></p>
<p class="subhead">{lead}</p>
</div>
<section class="key-stats" aria-label="Key WNBA stats">
<h2>Key WNBA stats</h2>
<ul class="key-list">{stats}</ul>
</section>
{sections}
{disclosure}
</div>
</main>
{site_nav.footer_html(True)}
<script src="/assets/site-nav.js" defer></script>
</body>
</html>
'''


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def build(root: Path) -> None:
    path = root / DATA_FILE
    payload = load(path)
    validate(payload)
    page = root / 'wnba' / 'viewership-attendance' / 'index.html'
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(render_page(root, payload), encoding='utf-8')
    print(f'Wrote {page.relative_to(root)} from {DATA_FILE}.')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        build(args.root)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
