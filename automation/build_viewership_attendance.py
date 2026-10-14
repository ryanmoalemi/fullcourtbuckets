#!/usr/bin/env python3
"""Build /wnba/viewership-attendance/ from data/viewership-attendance.json.

Append a game or a season row to the JSON and rerun this script. The page
reads every attendance and viewership figure from that file. A row with no
date, or a number with no source URL, fails the build.

Optional ``sources`` entries enrich the source register (publisher, covers,
checked_at) for a URL already cited on a row. Optional ``metrics`` rows are
appended to the CSV for a later data drop, such as a growth split. Each
metric needs metric_id, period, value, unit, scope, source_url, source_date,
checked_at and notes. The CSV of figures already on the page is written
either way.
"""
from __future__ import annotations

import argparse
import csv
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
PAGE_TITLE = 'WNBA Viewership & Attendance Statistics 2026'
QUESTION = 'How many people watch the WNBA?'
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
CSV_NAME = 'viewership-attendance.csv'
CSV_FIELDS = (
    'metric_id', 'period', 'value', 'unit', 'scope', 'source_url',
    'source_date', 'checked_at', 'notes',
)
OG_IMAGE = ROUTE + 'share-11474-landscape.png'
OG_ALT = '11,474 fans per regular-season game. 2026 WNBA attendance. Full Court Buckets.'
SHARE_LANDSCAPE = 'share-11474-landscape.png'
SHARE_PORTRAIT = 'share-11474-portrait.png'
NAV_LINKS = (
    ('viewership', 'Viewership'),
    ('attendance', 'Attendance'),
    ('teams', 'Teams'),
    ('finals', 'Finals'),
    ('sources', 'Sources'),
)
EXTRA_CSS = """
html{scroll-padding-top:120px}
.page-header h1{max-width:16em;font-size:clamp(32px,4vw,48px);line-height:1.12;letter-spacing:-.6px}
.answer,.note,.correction,.subhead,.explainer li,.how-made,.sources,.stat-label{max-width:65ch}
.answer{margin:0 0 14px;color:#f5f3ef;font-size:17px;line-height:1.6}
.subhead{max-width:65ch;font-size:17px;line-height:1.6;font-weight:500}
.qa{margin-top:56px}
.qa h2{margin:0 0 12px;font:800 clamp(26px,3vw,32px)/1.15 "Barlow",sans-serif;letter-spacing:-.4px}
.qa h3{margin:18px 0 8px;font:700 20px/1.3 "Barlow",sans-serif}
.audience-table{width:100%;border-collapse:separate;border-spacing:0}
.audience-table.fit{min-width:0}
.audience-table.wide{min-width:720px}
.audience-table caption{caption-side:bottom;padding:8px 2px 0;color:#b4bbc7;font-size:13px;font-weight:600;text-align:left}
.audience-table th,.audience-table td{padding:12px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}
.audience-table thead th{color:#b4bbc7;font-size:13px;font-weight:700;letter-spacing:0;text-transform:none;background:#141820}
.audience-table tbody td{font-size:15px;color:#f5f3ef;background:#10141a}
.audience-table .num{text-align:right;font-variant-numeric:tabular-nums}
.audience-table tr.latest td{background:#1c1814}
.latest-tag{margin-left:6px;color:var(--orange);font-size:12px;font-weight:700}
.audience-table.wide th:first-child,.audience-table.wide td:first-child{position:sticky;left:0;z-index:1}
.audience-table.wide thead th:first-child{z-index:2;background:#141820}
.audience-table.wide tbody td:first-child{background:#10141a}
.audience-table.wide tr.latest td:first-child{background:#1c1814}
.audience-table a,.answer a,.note a,.sources a,.cite a,.contents-rail a,.correction a,.stat-meta a,.chart-download{color:var(--orange);text-decoration:underline;text-underline-offset:3px}
.key-stats{margin-top:22px}
.key-list{margin:0;padding:0;list-style:none;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
.stat-card{display:flex;flex-direction:column;gap:6px;margin:0;padding:18px 16px;border:1px solid var(--line);background:#141820;min-height:176px}
.stat-value{margin:0;color:#f5f3ef;font:800 clamp(36px,4vw,44px)/1 "Barlow",sans-serif;letter-spacing:-.8px;font-variant-numeric:tabular-nums}
.stat-label{margin:0;color:#f5f3ef;font-size:15px;line-height:1.35;font-weight:650}
.stat-period{margin:0;color:#b4bbc7;font-size:13px;line-height:1.4}
.stat-meta{margin:8px 0 0;color:#b4bbc7;font-size:13px;line-height:1.4}
.byline-row{display:flex;align-items:center;gap:10px 12px;margin:14px 0 0;flex-wrap:nowrap}
.byline-sep{color:#6f6a64}
.byline-row .article-date{color:#b4bbc7;font:600 14px/1.3 Inter,system-ui,sans-serif}
.data-layout{margin-top:8px}
.contents-rail{display:none}
.contents-label{margin:0 0 10px;color:#b4bbc7;font:800 12px/1 "Barlow",sans-serif;letter-spacing:.12em;text-transform:uppercase}
.contents-rail ul,.on-page-mobile{margin:0;padding:0;list-style:none}
.contents-rail li{margin:0 0 8px}
.contents-rail a{display:inline-flex;align-items:center;min-height:36px;font-weight:700;text-decoration:none}
.contents-rail a[aria-current="true"]{color:var(--orange)}
.data-actions{display:flex;flex-direction:column;align-items:flex-start;gap:8px;margin-top:16px}
.btn{display:inline-flex;align-items:center;justify-content:center;box-sizing:border-box;min-height:44px;padding:0 14px;border:1px solid var(--orange);border-radius:3px;background:transparent;color:var(--orange);font:700 14px/1 Inter,system-ui,sans-serif;text-decoration:none;cursor:pointer}
.btn.primary{background:var(--orange);border-color:var(--orange);color:#1a1006}
.btn:focus-visible,a:focus-visible,select:focus-visible,summary:focus-visible,textarea:focus-visible{outline:2px solid var(--orange);outline-offset:3px}
.on-page-mobile{margin:20px 0 0}
.on-page-mobile label{display:block;color:#b4bbc7;font-size:14px;font-weight:700}
.on-page-mobile select{display:block;width:100%;min-height:44px;margin-top:6px;padding:0 10px;border:1px solid var(--line);background:#141820;color:#f5f3ef;font:600 16px/1.2 Inter,system-ui,sans-serif}
.chart-figure{margin:0 0 14px;max-width:720px}
.chart-panels{display:grid;grid-template-columns:1fr;gap:18px;margin:0 0 16px}
.chart-panel h3{margin:0 0 8px;font:700 18px/1.3 "Barlow",sans-serif}
.chart{display:block;width:100%;height:auto;max-height:220px;background:#141820}
.provisional{display:inline-block;margin:0 0 8px;padding:2px 8px;border:1px solid var(--orange);color:var(--orange);font:800 12px/1.4 "Barlow",sans-serif;letter-spacing:.08em;text-transform:uppercase}
.byline-row .byline{margin:0;text-decoration:none}
@media(min-width:800px){.chart-panels.two{grid-template-columns:1fr 1fr}}
.chart-download{font-size:14px;font-weight:700}
.scroll-hint{display:none;margin:0 0 6px;color:#b4bbc7;font-size:14px}
.sources{margin:10px 0 0;color:#b4bbc7;font-size:14px;line-height:1.55}
.note{margin:10px 0 0;color:#d6d2cd;font-size:14px;line-height:1.6}
.correction{margin:14px 0 0;padding:10px 12px;border-left:3px solid var(--orange);color:#d6d2cd;font-size:14px;line-height:1.55}
.pending{color:#b4bbc7}
.cite{margin:8px 0;padding:12px 14px;border-left:3px solid var(--purple);color:#d6d2cd;font-size:16px;line-height:1.5}
.embed{margin-top:12px}
.embed summary{min-height:44px;color:var(--orange);font-weight:700;cursor:pointer}
.embed textarea{display:block;width:min(100%,640px);min-height:72px;margin-top:8px;padding:8px;border:1px solid var(--line);background:#10141a;color:#f5f3ef;font:13px/1.45 ui-monospace,monospace}
.how-made{margin-top:28px;color:#8a877f;font-size:14px;line-height:1.55}
.how-made a{color:var(--orange)}
.explainer ul{margin:0;padding-left:18px}
.explainer li{margin:0 0 8px;color:#d6d2cd;font-size:16px;line-height:1.6}
@media(max-width:1099px){.key-list{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:900px){
.qa{margin-top:36px}
.page-header h1{font-size:32px}
.byline-row{flex-wrap:wrap}
.byline-sep{display:none}
.scroll-hint{display:block}
.table-wrap.wide{overflow-x:auto;-webkit-overflow-scrolling:touch;mask-image:linear-gradient(to right,#000 0,#000 calc(100% - 28px),transparent)}
.table-wrap.fit{overflow-x:visible;mask-image:none}
}
@media(max-width:420px){.key-list{grid-template-columns:1fr}}
@media(min-width:1100px){
.data-layout{display:grid;grid-template-columns:180px minmax(0,1fr);column-gap:32px;align-items:start}
.contents-rail{display:block;position:sticky;top:110px}
.on-page-mobile{display:none}
}
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
        for key in ('attendance_source_date', 'viewers_source_date', 'schedule_source_date'):
            if not valid_source_date(row.get(key)):
                raise ValueError(f'{label} has a source date that is not a month or a day.')
        if str(row.get('tip_et') or '').strip() or str(row.get('status') or '').strip():
            if not is_source_url(row.get('schedule_source')) or not str(row.get('schedule_source_date') or '').strip():
                raise ValueError(f'{label} has a schedule detail but no source.')
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
        _check_relocated_average(label, row)
    _validate_register(payload.get('sources'))
    _validate_metrics(payload.get('metrics'))
    _validate_broadcasts(payload.get('broadcasts'))


def _check_relocated_average(label: str, row: dict) -> None:
    """A relocated average that does not match the total and the game count stays off the page."""
    games = row.get('relocated_games')
    total = row.get('relocated_attendance')
    average = row.get('relocated_avg')
    status = str(row.get('relocated_avg_status') or '').strip()
    if status == 'unresolved':
        if is_number(average):
            raise ValueError(f'{label} leaves an unresolved relocated average in the data.')
        return
    if not (is_number(games) and games and is_number(total) and is_number(average)):
        return
    if average != round(total / games):
        raise ValueError(f'{label} relocated average does not reconcile.')


def _validate_register(sources) -> None:
    if sources is None:
        return
    if not isinstance(sources, list):
        raise ValueError('Source register must be a list.')
    for index, row in enumerate(sources):
        if not isinstance(row, dict) or not is_source_url(row.get('url')):
            raise ValueError(f'Source register row {index + 1} needs a page URL.')
        if not str(row.get('publisher') or '').strip():
            raise ValueError(f'Source register row {index + 1} needs a publisher.')
        if not valid_source_date(row.get('source_date')) or not str(row.get('source_date') or '').strip():
            raise ValueError(f'Source register row {index + 1} needs a source date.')
        if not valid_day(row.get('checked_at')):
            raise ValueError(f'Source register row {index + 1} needs a checked date.')


def _validate_metrics(metrics) -> None:
    if metrics is None:
        return
    if not isinstance(metrics, list):
        raise ValueError('Metrics must be a list.')
    for index, row in enumerate(metrics):
        if not isinstance(row, dict):
            raise ValueError(f'Metric row {index + 1} is not an object.')
        missing = [key for key in CSV_FIELDS if key not in row]
        if missing:
            raise ValueError(f'Metric row {index + 1} is missing {missing[0]}.')
        if not is_number(row.get('value')):
            raise ValueError(f'Metric row {index + 1} needs a whole-number value.')
        if not is_source_url(row.get('source_url')):
            raise ValueError(f'Metric row {index + 1} has a number but no source.')
        if not valid_source_date(row.get('source_date')) or not str(row.get('source_date') or '').strip():
            raise ValueError(f'Metric row {index + 1} needs a source date.')
        if not valid_day(row.get('checked_at')):
            raise ValueError(f'Metric row {index + 1} needs a checked date.')


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
    if host.startswith('valkyries.') and host.endswith('wnba.com'):
        return 'Golden State Valkyries'
    if host.endswith('valkyries.com'):
        return 'Golden State Valkyries'
    if host.endswith('wnba.com'):
        return 'WNBA.com'
    if host.endswith('frontofficesports.com'):
        return 'Front Office Sports'
    if host.endswith('oursportscentral.com'):
        return 'OurSports Central'
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



def _validate_broadcasts(rows) -> None:
    if rows is None:
        return
    if not isinstance(rows, list):
        raise ValueError('Broadcasts must be a list.')
    for index, row in enumerate(rows):
        label = f'Broadcast row {index + 1}'
        if not isinstance(row, dict):
            raise ValueError(f'{label} is not an object.')
        if not is_number(row.get('season')) or not str(row.get('network') or '').strip():
            raise ValueError(f'{label} is missing a season.')
        if not is_number(row.get('avg_viewers')) or not is_source_url(row.get('source')):
            raise ValueError(f'{label} has a number but no source.')
        if row.get('games') is not None and not is_number(row.get('games')):
            raise ValueError(f'{label} has a game count that is not a whole number.')
        if not valid_source_date(row.get('source_date')) or not str(row.get('source_date') or '').strip():
            raise ValueError(f'{label} needs a source date.')


def growth_split(prior: dict, current: dict) -> dict | None:
    from viewership_render import growth_split as split
    return split(prior, current)


def render_page(root: Path, payload: dict) -> str:
    from viewership_render import render_page as render
    return render(root, payload)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def build(root: Path) -> None:
    from viewership_render import csv_rows, write_csv, write_downloads
    path = root / DATA_FILE
    payload = load(path)
    validate(payload)
    page = root / 'wnba' / 'viewership-attendance' / 'index.html'
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(render_page(root, payload), encoding='utf-8')
    write_csv(page.parent / CSV_NAME, csv_rows(payload))
    write_downloads(page.parent, payload)
    stale = page.parent / 'og.jpg'
    if stale.exists():
        stale.unlink()
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
