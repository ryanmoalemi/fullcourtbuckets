"""Render the viewership page, its inline charts, and the download files.

Charts read the validated JSON. A missing year stays a gap. Example numbers
from the visual brief are not data and are not drawn here.
"""
from __future__ import annotations

import csv
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import build_viewership_attendance as core

FONT_BOLD = '/usr/share/fonts/truetype/macos/Inter-Bold.ttf'
FONT_MED = '/usr/share/fonts/truetype/macos/Inter-Medium.ttf'
BG = (20, 24, 32)
INK = (245, 243, 239)
MUTED = (180, 187, 199)
ORANGE = (255, 152, 0)
PURPLE = (125, 53, 255)
GRID = (42, 46, 54)
SHARE_BG = (9, 11, 16)


def growth_split(prior: dict, current: dict) -> dict | None:
    """Accounting split of a total-attendance change. None until both years are sourced."""
    if prior is None or current is None:
        return None
    if prior.get('avg_attendance_status') == 'calculated':
        return _fraction_growth(prior, current)
    for row in (prior, current):
        for number_key, source_key in (
            ('games_played', 'attendance_source'),
            ('avg_attendance', 'avg_attendance_source'),
        ):
            if not core.is_number(row.get(number_key)) or not core.is_source_url(row.get(source_key)):
                return None
    games_prior = prior['games_played']
    average_prior = prior['avg_attendance']
    games_current = current['games_played']
    average_current = current['avg_attendance']
    extra_games = (games_current - games_prior) * average_prior
    average_crowd = games_current * (average_current - average_prior)
    return {
        'prior_season': prior.get('season'),
        'current_season': current.get('season'),
        'games_prior': games_prior,
        'avg_prior': average_prior,
        'games_current': games_current,
        'avg_current': average_current,
        'extra_games': extra_games,
        'average_crowd': average_crowd,
        'prior_total': games_prior * average_prior,
        'current_total': games_current * average_current,
    }


def _fraction_growth(prior: dict, current: dict) -> dict | None:
    """Split a rounded prior total so the pieces add back to games times the new average."""
    if not (
        core.is_number(prior.get('total_attendance'))
        and core.is_number(prior.get('games_played'))
        and prior['games_played']
        and core.is_number(current.get('games_played'))
        and core.is_number(current.get('avg_attendance'))
        and core.is_source_url(prior.get('attendance_source'))
        and core.is_source_url(current.get('avg_attendance_source'))
    ):
        return None
    games_prior = prior['games_played']
    games_current = current['games_played']
    total_prior = prior['total_attendance']
    average_current = current['avg_attendance']
    extra = (games_current - games_prior) * total_prior / games_prior
    current_total = games_current * average_current
    change = current_total - total_prior
    extra_games = int(Decimal(str(extra)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    average_crowd = int(change) - extra_games
    share_games = round(100 * extra_games / change) if change else 0
    return {
        'prior_season': prior.get('season'),
        'current_season': current.get('season'),
        'games_prior': games_prior,
        'avg_prior': round(total_prior / games_prior),
        'games_current': games_current,
        'avg_current': average_current,
        'extra_games': extra_games,
        'average_crowd': average_crowd,
        'prior_total': total_prior,
        'current_total': current_total,
        'method': 'fraction',
        'share_games': share_games,
        'share_crowd': 100 - share_games,
        'printed_avg': prior.get('avg_attendance_printed'),
    }


def _rounded_total_note(payload: dict, split: dict) -> str:
    row = league_season(payload, split['current_season'])
    if not row or not core.is_number(row.get('total_attendance')):
        return ''
    if row['total_attendance'] == split['current_total']:
        return ''
    return (
        f" {core.source_label(row.get('attendance_source') or '')} rounds the "
        f"{split['current_season']} total to {core.format_number(row['total_attendance'])}, "
        'which is a separate rounded figure.'
    )


def league_season(payload: dict, season: int) -> dict | None:
    return next((row for row in core.league_rows(payload) if row.get('season') == season), None)


def compact_millions(value: int) -> str:
    if value >= 1_000_000 and value % 10_000 == 0:
        text = f'{value / 1_000_000:.2f}'.rstrip('0').rstrip('.')
        return f'{text}M'
    return f'{value:,}'


def _broadcasts(payload: dict) -> list[dict]:
    rows = []
    for row in payload.get('broadcasts') or []:
        if core.is_number(row.get('avg_viewers')) and core.is_source_url(row.get('source')):
            rows.append(row)
    return rows


def same_season_broadcasts(payload: dict) -> tuple[list[dict], int | None]:
    grouped: dict[int, list[dict]] = {}
    for row in _broadcasts(payload):
        if not core.is_number(row.get('games')) or row['games'] <= 0:
            continue
        grouped.setdefault(row['season'], []).append(row)
    multi = {
        season: rows for season, rows in grouped.items()
        if len({row.get('network') for row in rows}) >= 2
    }
    if not multi:
        return [], None
    season = max(multi)
    rows = sorted(multi[season], key=lambda row: -row['avg_viewers'])
    return rows, season


def espn_regular_season(payload: dict) -> list[dict]:
    rows = [
        row for row in _broadcasts(payload)
        if str(row.get('network') or '').startswith('ESPN') and core.is_number(row.get('games'))
    ]
    return sorted(rows, key=lambda row: row['season'])


def attendance_points(payload: dict, key: str) -> list[tuple[int, int | None]]:
    rows = {
        row['season']: row[key]
        for row in core.league_rows(payload)
        if core.is_number(row.get('season')) and core.is_number(row.get(key))
    }
    if not rows:
        return []
    start, end = min(rows), max(rows)
    return [(year, rows.get(year)) for year in range(start, end + 1)]


def complete_team_rank(payload: dict):
    flagged = [
        item.get('season') for item in payload.get('home_rankings') or []
        if item.get('complete') and core.is_number(item.get('season'))
    ]
    if not flagged:
        return None
    season = max(flagged)
    ranked = []
    for row in core.home_rows(payload):
        if row.get('season') != season:
            continue
        games = row.get('home_games')
        total = row.get('home_attendance')
        if not (core.is_number(games) and games and core.is_number(total)):
            return None
        if not core.is_source_url(row.get('home_attendance_source')):
            return None
        average = total / games
        ranked.append({
            'team': row['home_team'],
            'average': average,
            'label': f'{round(average):,}',
            'total': total,
            'games': games,
            'source': row.get('home_attendance_source') or '',
            'source_date': row.get('home_attendance_source_date') or '',
        })
    if len(ranked) < 2:
        return None
    ranked.sort(key=lambda item: -item['average'])
    return season, ranked


def _svg_text(x, y, text, *, size=12, fill='#b4bbc7', anchor='middle', weight=600) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" fill="{fill}" font-size="{size}" '
        f'font-family="Inter,system-ui,sans-serif" font-weight="{weight}" '
        f'text-anchor="{anchor}">{core.esc(text)}</text>'
    )


def _chart(aria: str, body: str, *, width=640, height=196) -> str:
    return (
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{core.esc(aria)}" '
        f'xmlns="http://www.w3.org/2000/svg">{body}</svg>'
    )


def _axis_label(value: float) -> str:
    if value >= 1_000_000:
        text = f'{value / 1_000_000:.2f}'.rstrip('0').rstrip('.')
        return f'{text}M'
    if value >= 1000:
        return f'{round(value):,}'
    return str(int(round(value)))


def _grid(plot, y_max: float, ticks: int = 4) -> str:
    left, top, right, bottom = plot
    parts = []
    for step in range(ticks + 1):
        value = y_max * step / ticks
        y = bottom - (bottom - top) * (value / y_max if y_max else 0)
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" stroke="#2a2e36" stroke-width="1"/>'
        )
        parts.append(_svg_text(left - 8, y + 4, _axis_label(value), size=11, anchor='end'))
    parts.append(
        f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#6f6a64" stroke-width="1.5"/>'
    )
    return ''.join(parts)


def line_chart_svg(points, *, y_max: float, unit: str, aria: str, label) -> str:
    width, height = 640, 188
    plot = (72, 28, 590, 148)
    left, top, right, bottom = plot
    count = max(len(points), 1)
    parts = [f'<rect width="{width}" height="{height}" fill="#141820"/>', _grid(plot, y_max)]
    parts.append(_svg_text(left, 16, unit, size=11, anchor='start'))

    def x_at(index: int) -> float:
        if count == 1:
            return (left + right) / 2
        return left + (right - left) * index / (count - 1)

    def y_at(value: float) -> float:
        return bottom - (bottom - top) * (value / y_max)

    segment = []
    dots = []
    drawn = []
    for index, point in enumerate(points):
        name, value = point[0], point[1]
        marker = point[2] if len(point) > 2 else ''
        x = x_at(index)
        parts.append(_svg_text(x, bottom + 20, str(name), size=12, fill='#f5f3ef', weight=700))
        if value is None:
            if len(segment) >= 2:
                drawn.append(segment)
            segment = []
            parts.append(_svg_text(x, bottom - 12, 'Not reported', size=10))
            continue
        y = y_at(value)
        segment.append((x, y))
        dots.append((x, y, marker))
        parts.append(_svg_text(x, max(14, y - 10), label(value), size=12, fill='#f5f3ef', weight=700))
        if marker:
            parts.append(_svg_text(x, min(bottom - 4, y + 16), marker, size=10))
    if len(segment) >= 2:
        drawn.append(segment)
    for segment in drawn:
        coords = ' '.join(f'{x:.1f},{y:.1f}' for x, y in segment)
        parts.append(f'<polyline points="{coords}" fill="none" stroke="#ff9800" stroke-width="2.5"/>')
    for x, y, marker in dots:
        if marker:
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="#141820" stroke="#ff9800" stroke-width="2"/>')
        else:
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#ff9800"/>')
    return _chart(aria, ''.join(parts), width=width, height=height)


def column_chart_svg(points, *, y_max: float, unit: str, aria: str, label, fill='#ff9800') -> str:
    width, height = 640, 200
    plot = (72, 26, 590, 150)
    left, top, right, bottom = plot
    count = max(len(points), 1)
    slot = (right - left) / count
    bar_width = min(46, slot * 0.42)
    parts = [f'<rect width="{width}" height="{height}" fill="#141820"/>', _grid(plot, y_max)]
    parts.append(_svg_text(left, 14, unit, size=11, anchor='start'))
    for index, point in enumerate(points):
        name, value = point[0], point[1]
        sub = point[2] if len(point) > 2 else ''
        center = left + slot * (index + 0.5)
        parts.append(_svg_text(center, bottom + 18, str(name), size=12, fill='#f5f3ef', weight=700))
        if sub:
            parts.append(_svg_text(center, bottom + 32, sub, size=10))
        if value is None:
            parts.append(_svg_text(center, bottom - 10, 'Not reported', size=10))
            continue
        y = bottom - (bottom - top) * (value / y_max)
        parts.append(
            f'<rect x="{center - bar_width / 2:.1f}" y="{y:.1f}" width="{bar_width:.1f}" '
            f'height="{bottom - y:.1f}" fill="{fill}"/>'
        )
        parts.append(_svg_text(center, max(14, y - 8), label(value), size=12, fill='#f5f3ef', weight=700))
    return _chart(aria, ''.join(parts), width=width, height=height)


def horizontal_chart_svg(rows, *, aria: str) -> str:
    width = 640
    row_height = 32
    height = 28 + len(rows) * row_height
    peak = max(row['average'] for row in rows) or 1
    left, right = 132, 560
    parts = [f'<rect width="{width}" height="{height}" fill="#141820"/>']
    parts.append(f'<line x1="{left}" y1="16" x2="{left}" y2="{height - 10}" stroke="#6f6a64" stroke-width="1.5"/>')
    for index, row in enumerate(rows):
        y = 22 + index * row_height
        bar = (right - left) * (row['average'] / peak)
        parts.append(_svg_text(left - 8, y + 12, row['team'], size=12, fill='#f5f3ef', anchor='end', weight=700))
        parts.append(f'<rect x="{left}" y="{y}" width="{bar:.1f}" height="16" fill="#ff9800"/>')
        parts.append(_svg_text(left + bar + 8, y + 13, row['label'], size=12, fill='#f5f3ef', anchor='start', weight=700))
    return _chart(aria, ''.join(parts), width=width, height=height)


def waterfall_svg(split: dict) -> str:
    width, height = 640, 200
    plot = (64, 28, 620, 150)
    left, top, right, bottom = plot
    steps = [
        (f"{split['prior_season']} total", split['prior_total'], 'total'),
        ('Extra games', split['extra_games'], 'delta'),
        ('Average crowd', split['average_crowd'], 'delta'),
        (f"{split['current_season']} total", split['current_total'], 'total'),
    ]
    peak = max(split['prior_total'], split['current_total'], 1)
    running = split['prior_total']
    levels = [split['prior_total']]
    for _name, value, kind in steps[1:-1]:
        running += value
        levels.append(running)
    levels.append(split['current_total'])
    peak = max(peak, max(levels), 1)
    parts = [f'<rect width="{width}" height="{height}" fill="#141820"/>', _grid(plot, peak)]
    parts.append(_svg_text(left, 16, 'Provisional fans', size=11, anchor='start', fill='#ff9800'))
    slot = (right - left) / len(steps)
    bar_width = min(54, slot * 0.45)
    running = 0
    for index, (name, value, kind) in enumerate(steps):
        center = left + slot * (index + 0.5)
        if kind == 'total':
            base, end = 0, value
            color = '#ff9800'
        else:
            base = running
            end = running + value
            color = '#7d35ff' if value >= 0 else '#ff5b5b'
        running = end if kind == 'delta' else value
        y0 = bottom - (bottom - top) * (max(base, end) / peak)
        y1 = bottom - (bottom - top) * (min(base, end) / peak)
        parts.append(
            f'<rect x="{center - bar_width / 2:.1f}" y="{y0:.1f}" width="{bar_width:.1f}" '
            f'height="{max(y1 - y0, 1):.1f}" fill="{color}"/>'
        )
        prefix = ''
        if kind == 'delta':
            prefix = '+' if value > 0 else ''
        parts.append(_svg_text(center, max(16, y0 - 8), prefix + compact_millions(int(value)) if abs(value) >= 1_000_000 else prefix + f'{int(value):,}', size=11, fill='#f5f3ef', weight=700))
        parts.append(_svg_text(center, bottom + 18, name, size=11, fill='#f5f3ef', weight=700))
    return _chart(
        f"Provisional attendance split from {split['prior_season']} to {split['current_season']}.",
        ''.join(parts),
        width=width,
        height=height,
    )


def chart_figure(svg: str, filename: str) -> str:
    return (
        '<figure class="chart-figure">'
        f'{svg}'
        f'<figcaption><a class="chart-download" href="{core.esc(filename)}" download>Download chart</a></figcaption>'
        '</figure>'
    )


def source_cell(url: str) -> str:
    if not url:
        return ''
    return (
        f'<a href="{core.esc(url)}" target="_blank" rel="noopener">{core.esc(core.source_label(url))}</a>'
    )


def table(headers, rows, label, *, caption='', numeric=None, wide=None, mark_latest=False) -> str:
    if wide is None:
        wide = len(headers) > 3
    numeric = set(numeric or [])
    kind = 'wide' if wide else 'fit'
    head = ''.join(f'<th scope="col">{core.esc(header)}</th>' for header in headers)
    body = []
    for index, row in enumerate(rows):
        latest = mark_latest and index == 0
        cells = []
        for column, cell in enumerate(row):
            classes = ['num'] if column in numeric else []
            attr = f' class="{" ".join(classes)}"' if classes else ''
            text = f'{cell}<span class="latest-tag">Latest</span>' if latest and column == 0 else cell
            cells.append(f'<td{attr}>{text}</td>')
        body.append(f'<tr{" class=\"latest\"" if latest else ""}>{"".join(cells)}</tr>')
    cap = f'<caption>{core.esc(caption)}</caption>' if caption else ''
    hint = '<p class="scroll-hint">Swipe to see more.</p>' if wide else ''
    return (
        f'{hint}<div class="table-wrap {kind}"><table class="audience-table {kind}" aria-label="{core.esc(label)}">'
        f'{cap}<thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'
    )


def event_type(row: dict) -> str:
    if core.is_finals_game(row):
        return 'Finals'
    if core.is_all_star(row):
        return 'All-Star'
    return 'Regular season'


def stat_cards(payload: dict) -> list[dict]:
    cards = []
    season = league_season(payload, 2026)
    if season and season.get('total_attendance') == 3_790_000 and core.is_source_url(season.get('attendance_source')):
        cards.append({
            'value': '3.79M', 'metric': 'Total attendance', 'period': '2026 regular season',
            'scope': 'Reported, rounded', 'url': season['attendance_source'],
            'date': season.get('attendance_source_date') or '',
        })
    if season and season.get('avg_attendance') == 11474 and core.is_source_url(season.get('avg_attendance_source')):
        cards.append({
            'value': '11,474', 'metric': 'Average crowd', 'period': '2026 regular season',
            'scope': 'Fans per game', 'url': season['avg_attendance_source'],
            'date': season.get('avg_attendance_source_date') or '',
        })
    espn = next((
        row for row in _broadcasts(payload)
        if row.get('season') == 2025 and row.get('avg_viewers') == 1_300_000 and row.get('games') == 25
    ), None)
    if espn:
        cards.append({
            'value': '1.3M', 'metric': 'Average ESPN audience', 'period': '2025 regular season',
            'scope': '25 games, Big Data + Panel', 'url': espn['source'],
            'date': espn.get('source_date') or '',
        })
    finals = league_season(payload, 2025)
    if (
        finals and finals.get('finals_avg_viewers') == 1_500_000 and finals.get('finals_games') == 4
        and core.is_source_url(finals.get('finals_viewers_source'))
    ):
        cards.append({
            'value': '1.5M', 'metric': 'Average Finals audience', 'period': '2025 completed series',
            'scope': '4 games, ABC and ESPN', 'url': finals['finals_viewers_source'],
            'date': finals.get('finals_viewers_source_date') or '',
        })
    return cards


def render_cards(cards: list[dict]) -> str:
    items = []
    for card in cards:
        when = core.format_source_date(card['date'])
        source = source_cell(card['url'])
        if when:
            source = f'{source}, {core.esc(when)}'
        items.append(
            '<li class="stat-card">'
            f'<p class="stat-value">{core.esc(card["value"])}</p>'
            f'<p class="stat-label">{core.esc(card["metric"])}</p>'
            f'<p class="stat-period">{core.esc(card["period"])}</p>'
            f'<p class="stat-meta">{core.esc(card["scope"])} | {source}</p>'
            '</li>'
        )
    return f'<ul class="key-list">{"".join(items)}</ul>'


def finals_answer(payload: dict) -> str:
    rows = {row['season']: row for row in core.number_rows(core.league_rows(payload), 'finals_avg_viewers')}
    year_2025 = rows.get(2025)
    year_2024 = rows.get(2024)
    if (
        year_2025 and year_2025.get('finals_avg_viewers') == 1_500_000 and year_2025.get('finals_games') == 4
        and year_2024 and year_2024.get('finals_avg_viewers') == 1_600_000
    ):
        return (
            'The 2025 Finals averaged 1.5 million viewers across four games. '
            'The 2024 Finals averaged 1.6 million viewers, the highest of the last 25 years.'
        )
    if not rows:
        return ''
    top = max(rows.values(), key=lambda item: item['finals_avg_viewers'])
    return f"The {top['season']} Finals averaged {core.format_number(top['finals_avg_viewers'])} viewers."


def home_answer(payload: dict) -> str:
    rows = core.home_rows(payload)
    if not rows:
        return ''
    valkyries = {
        row.get('season') for row in rows
        if row.get('home_team') == 'Golden State Valkyries' and row.get('home_attendance') == 397408
    }
    if 2025 in valkyries and 2026 in valkyries:
        return (
            'The Golden State Valkyries hold the single-season home attendance record with 397,408 fans, '
            'set in 2025 and matched in 2026. Indiana drew 340,715 in 2024.'
        )
    top = rows[0]
    if top.get('home_team') == 'Indiana Fever' and top.get('home_attendance') == 340715 and top.get('season') == 2024:
        return 'The Indiana Fever hold the single-season home attendance record with 340,715 fans in 2024.'
    return f"{top['home_team']} drew {core.format_number(top['home_attendance'])} fans at home in {top['season']}."


def watched_answer(payload: dict) -> str:
    watched = [
        row for row in core.number_rows(payload['games'], 'viewers')
        if not core.is_finals_game(row)
    ]
    if not watched:
        return ''
    top = max(watched, key=lambda row: row['viewers'])
    if top.get('date') == '1997-06-21' and top['viewers'] == 5_040_000:
        return (
            "The most-watched WNBA game on this list is the league's 1997 opener, Liberty vs. Sparks, "
            'with 5.04 million viewers on NBC.'
        )
    network = f" on {top['network']}" if top.get('network') else ''
    return f"{top['game']} on {core.format_day(top['date'])} drew {core.format_number(top['viewers'])} viewers{network}."


def attendance_answer(payload: dict) -> str:
    row = league_season(payload, 2026)
    if row and row.get('total_attendance') == 3_790_000 and row.get('games_played') == 330:
        return "The WNBA's 2026 regular season drew 3.79 million fans across 330 games, a league record."
    totals = core.number_rows(core.league_rows(payload), 'total_attendance')
    if not totals:
        return ''
    top = max(totals, key=lambda item: item['total_attendance'])
    games = f" across {top['games_played']} games" if core.is_number(top.get('games_played')) else ''
    return f"The WNBA's {top['season']} regular season drew {core.format_number(top['total_attendance'])} fans{games}."


def average_answer(payload: dict) -> str:
    row = league_season(payload, 2026)
    prior = league_season(payload, 2024)
    if row and row.get('avg_attendance') == 11474:
        if prior and prior.get('avg_attendance') == 9807:
            return (
                'WNBA games averaged 11,474 fans in 2026. The 2024 average was 9,807. '
                'The 2025 average is not in this file.'
            )
        return 'WNBA games averaged 11,474 fans in 2026.'
    averages = core.number_rows(core.league_rows(payload), 'avg_attendance')
    if not averages:
        return ''
    top = max(averages, key=lambda item: item['avg_attendance'])
    return f"WNBA games averaged {core.format_number(top['avg_attendance'])} fans in {top['season']}."


def crowds_answer(payload: dict) -> str:
    crowds = core.number_rows(payload['games'], 'attendance')
    if not crowds:
        return ''
    top = max(crowds, key=lambda row: row['attendance'])
    if top['date'] == '2024-09-19' and top['attendance'] == 20711:
        return (
            'The biggest WNBA crowd on record is 20,711, for Fever at Mystics on Sept. 19, 2024, '
            "as of the league's 2024 release."
        )
    return (
        f"The largest listed crowd is {core.format_number(top['attendance'])}, "
        f"{top['game']} on {core.format_day(top['date'])}."
    )


def _other_broadcast_table(payload: dict, season: int, sources: list) -> str:
    rows = [
        row for row in _broadcasts(payload)
        if row.get('season') == season and row.get('chart') is False
    ]
    if not rows:
        return ''
    rows = sorted(rows, key=lambda row: -row['avg_viewers'])
    body = []
    for row in rows:
        games = str(row['games']) if core.is_number(row.get('games')) else ''
        body.append([
            core.esc(row['network']),
            core.esc(row['season']),
            core.esc(games),
            core.esc(core.format_number(row['avg_viewers'])),
            core.esc(row.get('scope') or ''),
            source_cell(row.get('source') or ''),
        ])
        sources.append((row.get('source') or '', row.get('source_date') or ''))
    return (
        '<h3>Other 2026 partner averages</h3>'
        '<p class="answer">These averages stay off the bars. The source did not give a full-season game count, '
        'the figure is only part of the season, or the number is a split or a subset of a larger average.</p>'
        + table(
            ['Network', 'Season', 'Games', 'Average viewers', 'Scope', 'Source'],
            body,
            f'{season} partner averages without a comparable game count',
            caption=f'{season} partner averages that are not on the bar chart. Blank game counts were not stated.',
            numeric={2, 3},
        )
    )


def _peak_table(payload: dict, sources: list) -> str:
    rows = [row for row in payload.get('games') or [] if core.is_number(row.get('peak_viewers'))]
    if not rows:
        return ''
    rows = sorted(rows, key=lambda row: -row['peak_viewers'])
    body = []
    for row in rows:
        body.append([
            core.link_teams(row['game']),
            core.esc(core.format_day(row['date'])),
            core.esc(core.format_number(row['peak_viewers'])),
            core.esc(core.format_number(row['viewers']) if core.is_number(row.get('viewers')) else ''),
            source_cell(row.get('peak_viewers_source') or ''),
        ])
        sources.append((row.get('peak_viewers_source') or '', row.get('peak_viewers_source_date') or ''))
    return (
        '<h3>Peak minute audiences</h3>'
        '<p class="answer">A peak is the highest minute, not the average audience for the game.</p>'
        + table(
            ['Game', 'Date', 'Peak viewers', 'Average viewers', 'Source'],
            body,
            'Peak minute audiences',
            caption='Peak minute audiences. Not comparable to average audiences.',
            numeric={2, 3},
        )
    )


def tracker_answer(payload: dict) -> str:
    games = [row for row in payload['games'] if row.get('season') == 2026 and core.is_finals_game(row)]
    matchup = ''
    for row in core.league_rows(payload):
        if row.get('season') == 2026 and str(row.get('finals_matchup') or '').strip():
            matchup = str(row['finals_matchup']).strip()
            break
    if not games:
        return ''
    first = min(games, key=lambda row: row['date'])
    when = core.format_day(first['date'])
    if matchup == 'Valkyries vs. Dream' and first['date'] == '2026-10-17':
        return 'The 2026 Finals (Valkyries vs. Dream) begin Oct. 17. Audiences are awaiting release.'
    if matchup:
        return f"The {first['season']} Finals ({matchup}) begin {when}."
    return f"The {first['season']} Finals begin {when}."


def _round_max(values, *, floor: float) -> float:
    peak = max([value for value in values if value], default=0)
    if peak <= 0:
        return floor
    return max(floor, peak * 1.25)


def viewership_section(payload: dict) -> str:
    rows = sorted(
        [row for row in core.number_rows(payload['games'], 'viewers') if not core.is_finals_game(row)],
        key=lambda row: (-row['viewers'], row['date']),
    )
    body = []
    sources = []
    for row in rows:
        body.append([
            core.link_teams(row['game']),
            core.esc(core.format_day(row['date'])),
            core.esc(event_type(row)),
            core.esc(core.format_number(row['viewers'])),
            core.esc(row.get('network') or ''),
            source_cell(row.get('viewers_source') or ''),
        ])
        sources.append((row.get('viewers_source') or '', row.get('viewers_source_date') or ''))
    note = ''
    if any(row.get('season') == 2026 and 'Peacock' in str(row.get('network') or '') for row in rows):
        note = "NBC's 2026 numbers count TV plus Peacock streaming. Older numbers are TV only. This is a selected list, not a complete ranking."
    games_table = table(
        ['Game', 'Date', 'Event', 'Viewers', 'Network', 'Source'],
        body,
        'Selected major WNBA audiences',
        caption='Selected major audiences. Not a verified complete ranking.',
        numeric={3},
    )
    network_rows, season = same_season_broadcasts(payload)
    network_html = ''
    if network_rows and season:
        points = [(row['network'], row['avg_viewers'], f"{row['games']} games") for row in network_rows]
        aria = (
            f"{season} regular-season averages for networks that published a game count: "
            + '; '.join(f"{row['network']} {core.format_number(row['avg_viewers'])} across {row['games']} games" for row in network_rows)
            + '. Schedules differ.'
        )
        svg = column_chart_svg(
            points,
            y_max=_round_max([row['avg_viewers'] for row in network_rows], floor=1),
            unit='Average viewers',
            aria=aria,
            label=compact_millions,
        )
        table_rows = []
        for row in network_rows:
            table_rows.append([
                core.esc(row['network']),
                core.esc(row['season']),
                core.esc(f"{row['games']}"),
                core.esc(core.format_number(row['avg_viewers'])),
                core.esc(row.get('scope') or ''),
                source_cell(row.get('source') or ''),
            ])
            sources.append((row.get('source') or '', row.get('source_date') or ''))
        network_html = (
            '<h3>What audience did each broadcaster report?</h3>'
            f'<p class="answer">In {season}, these networks published both a regular-season average and a game count. '
            'The schedules are different sizes, so the bars compare reported audiences. They do not rank the broadcasters.</p>'
            f'{chart_figure(svg, "network-2026.png")}'
            + table(
                ['Network', 'Season', 'Games', 'Average viewers', 'Scope', 'Source'],
                table_rows,
                f'{season} regular-season TV audiences',
                caption=f'{season} regular season. Each row is that network\'s own schedule.',
                numeric={2, 3},
            )
            + _other_broadcast_table(payload, season, sources)
        )
    espn_rows = espn_regular_season(payload)
    espn_html = ''
    if len(espn_rows) >= 2:
        points = [(str(row['season']), row['avg_viewers'], f"{row['games']} games") for row in espn_rows]
        aria = (
            'ESPN regular-season average: '
            + ' and '.join(
                f"{core.format_number(row['avg_viewers'])} in {row['season']} across {row['games']} games"
                for row in espn_rows
            )
            + '. Measurement methods differ. This is not a percent change.'
        )
        svg = column_chart_svg(
            points,
            y_max=_round_max([row['avg_viewers'] for row in espn_rows], floor=1),
            unit='Average viewers',
            aria=aria,
            label=compact_millions,
            fill='#7d35ff',
        )
        table_rows = []
        for row in espn_rows:
            measure = row.get('measurement') or 'Series average in the linked release'
            table_rows.append([
                core.esc(row['network']),
                core.esc(row['season']),
                core.esc(str(row['games'])),
                core.esc(core.format_number(row['avg_viewers'])),
                core.esc(measure),
                source_cell(row.get('source') or ''),
            ])
            sources.append((row.get('source') or '', row.get('source_date') or ''))
        detail = ' and '.join(
            f"a {core.format_number(row['avg_viewers'])} average across {row['games']} regular-season games in {row['season']}"
            for row in espn_rows
        )
        espn_html = (
            '<h3>ESPN regular-season average, 2024 and 2025</h3>'
            f'<p class="answer">ESPN reported {detail}. The 2025 figure uses Nielsen Big Data + Panel. '
            'The bars are separate reports, not a percent change in fan interest.</p>'
            f'{chart_figure(svg, "espn-regular-season.png")}'
            + table(
                ['Network', 'Season', 'Games', 'Average viewers', 'Measurement', 'Source'],
                table_rows,
                'ESPN regular-season averages',
                caption='ESPN only. 2024 and 2025 used different measurement.',
                numeric={2, 3},
            )
        )
    note_html = f'<p class="note">{core.esc(note)}</p>' if note else ''
    return (
        '<section class="qa" id="viewership">'
        f'<h2>{core.esc(core.QUESTION)}</h2>'
        f'<p class="answer">{core.link_teams(watched_answer(payload))}</p>'
        '<h3>What are the most-watched WNBA games?</h3>'
        f'{games_table}{note_html}{_peak_table(payload, sources)}'
        f'{network_html}{espn_html}'
        f'{core.sources_line(sources)}'
        '</section>'
    )


def _chart_points(payload: dict, points, key: str):
    marked = []
    for year, value in points:
        row = league_season(payload, year) or {}
        marker = ''
        if key == 'avg_attendance' and row.get('avg_attendance_status') == 'calculated':
            marker = 'calculated'
        elif key == 'total_attendance' and row.get('total_attendance_rounded'):
            marker = 'rounded'
        marked.append((str(year), value, marker) if marker else (str(year), value))
    return marked


def _average_chart(payload: dict) -> str:
    points = attendance_points(payload, 'avg_attendance')
    if len([value for _year, value in points if value is not None]) < 2:
        return ''
    aria_bits = []
    for year, value in points:
        row = league_season(payload, year) or {}
        if value is None:
            aria_bits.append(f'{year} not reported')
        elif row.get('avg_attendance_status') == 'calculated':
            aria_bits.append(f'{year} {value:,} fans per game, calculated')
        else:
            aria_bits.append(f'{year} {value:,} fans per game')
    svg = line_chart_svg(
        _chart_points(payload, points, 'avg_attendance'),
        y_max=_round_max([value or 0 for _year, value in points], floor=1),
        unit='Fans per game',
        aria='Regular-season attendance per game. ' + '; '.join(aria_bits) + '. Missing years are not zero. A calculated point is an open circle.',
        label=lambda value: f'{value:,}',
    )
    return (
        '<div class="chart-panel">'
        '<h3>Are average crowds growing?</h3>'
        '<p class="answer">Reported averages are shown for each season in the file. '
        'A calculated average is an open circle. A missing year stays a gap. It is not drawn as zero, and the line does not connect across it.</p>'
        f'{chart_figure(svg, "attendance-average.png")}'
        '</div>'
    )


def _total_chart(payload: dict) -> str:
    points = attendance_points(payload, 'total_attendance')
    if not points:
        return ''
    # Keep the same span as the average series when that series is wider.
    average_years = [year for year, _value in attendance_points(payload, 'avg_attendance')]
    if average_years:
        start, end = min(average_years), max(average_years)
        known = dict(points)
        points = [(year, known.get(year)) for year in range(start, end + 1)]
    aria_bits = []
    for year, value in points:
        aria_bits.append(f'{year} not reported' if value is None else f'{year} {core.format_number(value)}')
    svg = column_chart_svg(
        _chart_points(payload, points, 'total_attendance'),
        y_max=_round_max([value or 0 for _year, value in points], floor=1),
        unit='Total fans',
        aria='Regular-season total attendance. ' + '; '.join(aria_bits) + '. Blank years are not zero. Rounded totals are labeled.',
        label=compact_millions,
    )
    return (
        '<div class="chart-panel">'
        '<h3>Total attendance</h3>'
        '<p class="answer">Totals use a separate panel because a bigger schedule and a bigger crowd answer different questions. '
        'Years without a sourced total are left blank.</p>'
        f'{chart_figure(svg, "attendance-total.png")}'
        '</div>'
    )


def growth_section(payload: dict) -> str:
    split = growth_split(league_season(payload, 2025), league_season(payload, 2026))
    if split is None:
        return (
            '<h3>How much of the total comes from games versus average crowds?</h3>'
            '<p class="answer">A provisional waterfall splits a change in total attendance into extra games, '
            f'(games in the new season minus games in the old season) times the old average, and the average-crowd piece, '
            'new games times the change in average. '
            'The 2025 league game count and average attendance are not in this file, so the chart is not drawn.</p>'
        )
    if split.get('method') == 'fraction':
        formula = (
            f"Extra games: {split['games_current'] - split['games_prior']} x "
            f"({split['prior_total']:,} / {split['games_prior']}) = {split['extra_games']:,} "
            f"({split['share_games']}%). "
            f"Average crowd: {split['games_current']} x "
            f"({split['avg_current']:,} - {split['prior_total']:,} / {split['games_prior']}) "
            f"= {split['average_crowd']:,} ({split['share_crowd']}%). "
            f"Together that is {split['current_total']:,} minus {split['prior_total']:,}, "
            f"or {split['extra_games'] + split['average_crowd']:,}. "
            f"{split['games_current']} times {split['avg_current']:,} is {split['current_total']:,}."
            + _rounded_total_note(payload, split)
        )
    else:
        formula = (
            f"Extra games: ({split['games_current']} - {split['games_prior']}) x {split['avg_prior']:,} "
            f"= {split['extra_games']:,}. "
            f"Average crowd: {split['games_current']} x ({split['avg_current']:,} - {split['avg_prior']:,}) "
            f"= {split['average_crowd']:,}."
        )
    return (
        '<h3>How much of the total comes from games versus average crowds?</h3>'
        '<p class="provisional">Provisional</p>'
        '<p class="answer">This is an accounting split of the change in total attendance. '
        'It is not a cause of demand. The 2025 game count is calculated, and the 2025 average used here is calculated from the rounded total.</p>'
        f'{chart_figure(waterfall_svg(split), "attendance-growth.png")}'
        f'<p class="note">{core.esc(formula)}</p>'
    )


def attendance_section(payload: dict) -> str:
    averages = sorted(core.number_rows(core.league_rows(payload), 'avg_attendance'), key=lambda row: -row['season'])
    totals = sorted(core.number_rows(core.league_rows(payload), 'total_attendance'), key=lambda row: -row['season'])
    average_body = []
    total_body = []
    sources = []
    for row in averages:
        status = 'Calculated' if row.get('avg_attendance_status') == 'calculated' else 'Printed'
        average_body.append([
            core.esc(row['season']),
            core.esc(core.format_number(row['avg_attendance'])),
            core.esc(status),
            source_cell(row.get('avg_attendance_source') or ''),
        ])
        sources.append((row.get('avg_attendance_source') or '', row.get('avg_attendance_source_date') or ''))
        if core.is_number(row.get('avg_attendance_printed')):
            average_body.append([
                core.esc(row['season']),
                core.esc(core.format_number(row['avg_attendance_printed'])),
                'Printed, does not reconcile',
                source_cell(row.get('avg_attendance_source') or ''),
            ])
    for row in totals:
        games = str(row['games_played']) if core.is_number(row.get('games_played')) else ''
        if games and row.get('games_calculated'):
            games = f'{games}, calculated'
        total_body.append([
            core.esc(row['season']),
            core.esc(core.format_number(row['total_attendance'])),
            core.esc(games),
            source_cell(row.get('attendance_source') or ''),
        ])
        sources.append((row.get('attendance_source') or '', row.get('attendance_source_date') or ''))
        if row.get('games_source'):
            sources.append((row.get('games_source') or '', row.get('games_source_date') or ''))
    share = ''
    if any(row.get('avg_attendance') == 11474 and row.get('season') == 2026 for row in averages):
        share = (
            '<div class="data-actions">'
            f'<a class="btn primary" href="{core.SHARE_LANDSCAPE}" download>Download share graphic</a>'
            f'<a class="btn" href="{core.SHARE_PORTRAIT}" download>Download portrait graphic</a>'
            '</div>'
            '<p class="note">The share graphic states one fact: 11,474 fans per regular-season game, 2026 WNBA attendance. '
            'Source: Front Office Sports, Sept. 25, 2026.</p>'
        )
    relocated = _relocated_block(payload)
    return (
        '<section class="qa" id="attendance">'
        '<h2>How many fans attended WNBA games?</h2>'
        f'<p class="answer">{core.link_teams(attendance_answer(payload))}</p>'
        f'<div class="chart-panels two">{_average_chart(payload)}{_total_chart(payload)}</div>'
        f'{growth_section(payload)}'
        '<h3>What is the average WNBA attendance per game?</h3>'
        f'<p class="answer">{core.esc(average_answer(payload))}</p>'
        + table(
            ['Season', 'Fans per game', 'Status', 'Source'],
            average_body,
            'WNBA average attendance per game',
            caption='Regular-season average attendance. A calculated average is the reported total divided by the game count.',
            numeric={1},
            mark_latest=True,
        )
        + _attendance_notes(averages + totals)
        + share
        + '<h3>Season totals</h3>'
        + table(
            ['Season', 'Total attendance', 'Games', 'Source'],
            total_body,
            'WNBA attendance by season',
            caption='Regular-season total attendance.',
            numeric={1, 2},
            mark_latest=True,
        )
        + relocated
        + _crowds_block(payload)
        + core.sources_line(sources)
        + '</section>'
    )


def _attendance_notes(rows: list[dict]) -> str:
    seen = []
    for row in rows:
        for key in ('avg_attendance_note', 'attendance_note', 'games_note'):
            note = str(row.get(key) or '').strip()
            if note and note not in seen:
                seen.append(note)
    return ''.join(f'<p class="note">{core.esc(note)}</p>' for note in seen)


def _relocated_block(payload: dict) -> str:
    rows = [
        row for row in core.league_rows(payload)
        if core.is_number(row.get('relocated_games')) or core.is_number(row.get('relocated_attendance'))
    ]
    if not rows:
        return ''
    body = []
    for row in sorted(rows, key=lambda item: -item['season']):
        average = 'Unresolved' if row.get('relocated_avg_status') == 'unresolved' or not core.is_number(row.get('relocated_avg')) else core.format_number(row['relocated_avg'])
        body.append([
            core.esc(row['season']),
            core.esc(row.get('relocated_games') if row.get('relocated_games') is not None else ''),
            core.esc(core.format_number(row['relocated_attendance']) if core.is_number(row.get('relocated_attendance')) else ''),
            core.esc(average),
            source_cell(row.get('relocated_source') or ''),
        ])
    notes = [str(row.get('relocated_note') or '').strip() for row in rows if str(row.get('relocated_note') or '').strip()]
    note_html = ''.join(f'<p class="note">{core.esc(note)}</p>' for note in notes)
    return (
        '<h3>Relocated games</h3>'
        '<p class="answer">Relocated games are listed apart from the single-game crowd record.</p>'
        + table(
            ['Season', 'Games', 'Attendance', 'Average', 'Source'],
            body,
            'Relocated WNBA games',
            caption='Multi-game relocation count. Unresolved averages are not calculated here.',
            numeric={1, 2},
        )
        + note_html
    )


def _crowds_block(payload: dict) -> str:
    crowds = sorted(core.number_rows(payload['games'], 'attendance'), key=lambda row: -row['attendance'])
    if not crowds:
        return ''
    body = []
    for index, row in enumerate(crowds):
        label = 'Single-game attendance' if index == 0 and row['attendance'] == 20711 else row['game']
        detail = core.format_number(row['attendance'])
        extra = [part for part in (row.get('game') or '', row.get('venue') or '') if part]
        if extra and label == 'Single-game attendance':
            detail = f"{detail} ({', '.join(extra)})"
        body.append([
            core.link_teams(label),
            core.link_teams(detail),
            core.esc(core.format_day(row['date'])),
            source_cell(row.get('attendance_source') or ''),
        ])
    note = ''
    if any(row.get('date') == '2024-09-19' and row.get('attendance') == 20711 for row in crowds):
        note = "The 20,711 crowd is the record in the league's Sept. 27, 2024 release. A later season topping it has not been confirmed here."
    note_html = f'<p class="note">{core.esc(note)}</p>' if note else ''
    return (
        '<h3>What is the biggest WNBA crowd on record?</h3>'
        f'<p class="answer">{core.link_teams(crowds_answer(payload))}</p>'
        + table(
            ['Record', 'Number', 'Date', 'Source'],
            body,
            'WNBA record crowds',
            caption='Single-game crowds. Relocation totals are in the table above.',
            numeric={1},
        )
        + note_html
    )


def teams_section(payload: dict) -> str:
    rows = core.home_rows(payload)
    if not rows:
        return ''
    body = []
    sources = []
    for row in rows:
        bits = [core.format_number(row['home_attendance'])]
        detail = []
        if core.is_number(row.get('home_games')) and row['home_games']:
            detail.append(f"{row['home_games']} games")
            average = row['home_attendance'] / row['home_games']
            if abs(average - round(average)) < 1e-6:
                detail.append(f"{round(average):,} per game")
        if str(row.get('home_note') or '').strip():
            detail.append(str(row['home_note']).strip())
        text = bits[0] if not detail else f"{bits[0]} ({'; '.join(detail)})"
        body.append([
            core.link_teams(row['home_team']),
            core.esc(row['season']),
            core.esc(text),
            source_cell(row.get('home_attendance_source') or ''),
        ])
        sources.append((row.get('home_attendance_source') or '', row.get('home_attendance_source_date') or ''))
    ranking = complete_team_rank(payload)
    if ranking:
        season, ranked = ranking
        svg = horizontal_chart_svg(
            ranked,
            aria='Average home attendance, ' + str(season) + '. ' + '; '.join(f"{row['team']} {row['label']}" for row in ranked),
        )
        chart = (
            f'<p class="answer">Average home attendance in {season}, highest first. '
            'The label is the rounded per-game figure. Home games are not mixed with road games.</p>'
            f'{chart_figure(svg, "team-ranking.png")}'
        )
    else:
        chart = (
            '<p class="answer">A team ranking chart needs every club\'s counted home games and home total for one season. '
            'This file does not have that complete set, so the ranking chart stays hidden.</p>'
        )
    return (
        '<section class="qa" id="teams">'
        '<h2>Which WNBA team has the biggest home crowds?</h2>'
        f'<p class="answer">{core.link_teams(home_answer(payload))}</p>'
        f'{chart}'
        + table(
            ['Team', 'Season', 'Home attendance', 'Source'],
            body,
            'Home attendance by team',
            caption='Home attendance only. Averages are the total divided by counted home games.',
            numeric={2},
        )
        + _team_side_notes(payload, sources)
        + core.sources_line(sources)
        + '</section>'
    )


def _team_side_notes(payload: dict, sources: list) -> str:
    notes = []
    for row in payload.get('seasons') or []:
        if row.get('road_team') and core.is_number(row.get('road_avg')):
            notes.append(
                f"<p class=\"note\">{core.link_teams(row['road_team'])} averaged "
                f"{row['road_avg']:,} fans on the road in {row['season']}. "
                f"{core.esc(row.get('road_note') or 'Road games, not home.')} "
                f"Source: {source_cell(row.get('road_source') or '')}.</p>"
            )
            sources.append((row.get('road_source') or '', row.get('road_source_date') or ''))
        if core.is_number(row.get('home_change_pct')) and not core.is_number(row.get('home_attendance')):
            notes.append(
                f"<p class=\"note\">{core.link_teams(row.get('home_team') or '')} home attendance "
                f"changed {row['home_change_pct']}% in {row['season']}, as printed by the source. "
                f"{core.esc(row.get('home_note') or '')}</p>"
            )
            sources.append((row.get('home_attendance_source') or '', row.get('home_attendance_source_date') or ''))
    return ''.join(notes)


def finals_measurement(row: dict) -> str:
    season = row.get('season')
    games = row.get('finals_games')
    if season == 2025:
        return f'{games} games. ESPN identifies 2025 as Big Data + Panel.'
    if season == 2024:
        return f'{games} games. ESPN called this the highest Finals audience of the last 25 years.'
    if games:
        return f'{games} games.'
    return ''


def finals_section(payload: dict) -> str:
    rows = sorted(core.number_rows(core.league_rows(payload), 'finals_avg_viewers'), key=lambda row: row['season'])
    if not rows:
        return ''
    points = []
    for row in rows:
        games = row.get('finals_games')
        sub = f'{games} games' if core.is_number(games) else ''
        points.append((str(row['season']), row['finals_avg_viewers'], sub))
    alt = (
        'Reported average WNBA Finals audience: 1.6 million in 2024 and 1.5 million in 2025. '
        'The series had five and four games, respectively; measurement methods differ.'
    )
    if not any(row.get('season') == 2024 and row.get('finals_avg_viewers') == 1_600_000 for row in rows):
        alt = 'Reported average WNBA Finals audience by year. Game counts differ.'
    svg = column_chart_svg(
        points,
        y_max=_round_max([row['finals_avg_viewers'] for row in rows], floor=1),
        unit='Average viewers',
        aria=alt,
        label=compact_millions,
    )
    body = []
    sources = []
    for row in sorted(rows, key=lambda item: -item['season']):
        body.append([
            core.esc(row['season']),
            core.link_teams(str(row.get('finals_matchup') or '')),
            core.esc(row.get('finals_games') if row.get('finals_games') is not None else ''),
            core.esc(core.format_number(row['finals_avg_viewers'])),
            core.esc(row.get('finals_network') or ''),
            core.esc(finals_measurement(row)),
            source_cell(row.get('finals_viewers_source') or ''),
        ])
        sources.append((row.get('finals_viewers_source') or '', row.get('finals_viewers_source_date') or ''))
    return (
        '<section class="qa" id="finals">'
        '<h2>How many people watched the WNBA Finals?</h2>'
        f'<p class="answer">{core.link_teams(finals_answer(payload))}</p>'
        '<p class="note">2026 Finals audiences are not on this chart. Unreported games stay in the tracker below.</p>'
        f'{chart_figure(svg, "finals-history.png")}'
        + table(
            ['Year', 'Matchup', 'Games', 'Average viewers', 'Network', 'Measurement', 'Source'],
            body,
            'WNBA Finals viewership by year',
            caption='Completed Finals series. 2024 had five games and 2025 had four.',
            numeric={2, 3},
            mark_latest=True,
        )
        + _finals_game_table(payload, sources)
        + core.sources_line(sources)
        + tracker_block(payload)
        + '</section>'
    )


def _finals_game_table(payload: dict, sources: list) -> str:
    body = []
    for row in core.league_rows(payload):
        for item in row.get('finals_game_reports') or []:
            when = core.format_day(item['date']) if item.get('date') else ''
            body.append([
                core.esc(row.get('season')),
                core.esc(item.get('game') or ''),
                core.esc(when),
                core.esc(core.format_number(item['viewers'])),
                core.esc(item.get('network') or ''),
                core.esc(item.get('note') or ''),
                source_cell(item.get('source') or ''),
            ])
            sources.append((item.get('source') or '', item.get('source_date') or ''))
    if not body:
        return ''
    return (
        '<h3>2025 Finals, game by game</h3>'
        '<p class="answer">These are individual games from a completed series. They are not added into the series-average bars above. '
        'Games 5, 6 and 7 were not played, so they are left blank.</p>'
        + table(
            ['Year', 'Game', 'Date', 'Viewers', 'Network', 'Note', 'Source'],
            body,
            '2025 WNBA Finals game audiences',
            caption='Reported 2025 Finals games. Games that were not played have no viewer count.',
            numeric={3},
        )
    )


def tracker_when(row: dict) -> str:
    text = core.format_day(row['date'], weekday=True)
    tip = str(row.get('tip_et') or '').strip()
    if tip:
        text = f'{text}, {tip}'
    status = str(row.get('status') or '').strip()
    if status:
        text = f'{text} ({status})'
    return text


def tracker_block(payload: dict) -> str:
    games = sorted(
        [row for row in payload['games'] if core.is_finals_game(row)],
        key=lambda row: (row.get('season') or 0, row['date']),
    )
    if not games:
        return ''
    body = []
    sources = []
    for row in games:
        match_label = row['game'].replace('Finals Game ', '')
        if core.is_number(row.get('viewers')):
            viewers = core.esc(core.format_number(row['viewers']))
            url = row.get('viewers_source') or ''
            sources.append((url, row.get('viewers_source_date') or ''))
        else:
            viewers = '<span class="pending">Awaiting release</span>'
            url = row.get('schedule_source') or ''
            sources.append((url, row.get('schedule_source_date') or ''))
        body.append([
            core.esc(match_label),
            core.esc(tracker_when(row)),
            core.esc(row.get('venue') or ''),
            core.esc(row.get('network') or ''),
            viewers,
            source_cell(url),
        ])
    note = (
        'Games 5, 6 and 7 are if necessary. The Oct. 13, 2026 WNBA release does not list their dates. '
        'Game 3 is at State Farm Arena at 8:00 p.m. ET, which is 5:00 p.m. PT. '
        'Game 4 tips at 1:00 p.m. ET, which is 10:00 a.m. PT, on NBC and Peacock.'
    )
    return (
        '<h3>How many people are watching the 2026 WNBA Finals?</h3>'
        f'<p class="answer">{core.link_teams(tracker_answer(payload))}</p>'
        + table(
            ['Game', 'Date', 'Venue', 'Network', 'Viewers', 'Source'],
            body,
            '2026 WNBA Finals viewership tracker',
            caption='Game-by-game tracker. Awaiting release is not zero.',
            numeric={4},
        )
        + f'<p class="note">{core.esc(note)}</p>'
        + core.sources_line(sources)
    )


def methodology() -> str:
    return (
        '<section class="qa explainer">'
        '<h2>How this page is built</h2>'
        '<ul>'
        '<li><strong>Viewership.</strong> Nielsen estimates reported by the league, the networks, or Sports Media Watch. '
        "Nielsen's Big Data + Panel, used more widely from 2025, may affect comparisons with earlier years. "
        'One adjustment is not applied to every figure.</li>'
        '<li><strong>Attendance.</strong> Figures are what the league, a team release, or Sports Business Journal\'s box-score count reports. '
        'They are not automatically paid attendance or unique fans.</li>'
        '<li><strong>Conflicts.</strong> When a printed average does not match the total divided by the game count, '
        'the cell is labeled unresolved and the printed figure stays next to its source.</li>'
        '<li><strong>No guessing.</strong> A blank cell is not zero. '
        'Spot an error? Email <a href="mailto:hello@fullcourtbuckets.com">Ryan</a>.</li>'
        '</ul></section>'
    )


def embed_snippet() -> str:
    return f'<a href="{core.BASE}{core.ROUTE}">WNBA viewership and attendance statistics (Full Court Buckets)</a>'


def actions_html() -> str:
    return (
        '<div class="data-actions">'
        f'<a class="btn primary" href="{core.CSV_NAME}" download>Download CSV</a>'
        '<button class="btn copy-citation" type="button">Copy citation</button>'
        f'<button class="btn copy-embed" type="button" data-embed="{core.esc(embed_snippet())}">Embed link</button>'
        '</div>'
    )


def citation_text(updated: str) -> str:
    return (
        f'Ryan Moalemi. {core.PAGE_TITLE}. Full Court Buckets. '
        f'Updated {updated}. {core.BASE}{core.ROUTE}'
    )


def contents_html() -> str:
    items = ''.join(f'<li><a href="#{anchor}">{core.esc(label)}</a></li>' for anchor, label in core.NAV_LINKS)
    options = '<option value="">On this page</option>' + ''.join(
        f'<option value="#{anchor}">{core.esc(label)}</option>' for anchor, label in core.NAV_LINKS
    )
    return (
        '<div class="data-nav">'
        '<nav class="contents-rail" aria-label="On this page">'
        '<p class="contents-label">On this page</p>'
        f'<ul>{items}</ul>'
        f'{actions_html()}'
        '</nav>'
        '<div class="on-page-mobile">'
        '<label for="on-this-page">On this page</label>'
        f'<select id="on-this-page">{options}</select>'
        '</div>'
        '</div>'
    )


def _add_cover(found: dict, url: str, date: str, cover: str) -> None:
    if not core.is_source_url(url):
        return
    item = found.setdefault(url, {'dates': [], 'covers': []})
    if date and date not in item['dates']:
        item['dates'].append(date)
    if cover and cover not in item['covers']:
        item['covers'].append(cover)


def register_rows(payload: dict) -> list[dict]:
    found: dict[str, dict] = {}
    for row in payload.get('games') or []:
        name = str(row.get('game') or 'Game')
        _add_cover(found, row.get('viewers_source') or '', row.get('viewers_source_date') or '', f'{name} audience')
        _add_cover(found, row.get('attendance_source') or '', row.get('attendance_source_date') or '', f'{name} attendance')
        _add_cover(found, row.get('schedule_source') or '', row.get('schedule_source_date') or '', f'{name} schedule')
    for row in payload.get('seasons') or []:
        season = row.get('season')
        team = str(row.get('home_team') or '').strip()
        scope = f'{team} {season} home attendance' if team else f'{season} season'
        _add_cover(found, row.get('attendance_source') or '', row.get('attendance_source_date') or '', scope)
        _add_cover(found, row.get('avg_attendance_source') or '', row.get('avg_attendance_source_date') or '', f'{season} average attendance')
        _add_cover(found, row.get('finals_viewers_source') or '', row.get('finals_viewers_source_date') or '', f'{season} Finals audience')
        _add_cover(found, row.get('relocated_source') or '', row.get('relocated_source_date') or '', f'{season} relocated games')
        _add_cover(found, row.get('home_attendance_source') or '', row.get('home_attendance_source_date') or '', scope)
    for row in _broadcasts(payload):
        _add_cover(
            found, row.get('source') or '', row.get('source_date') or '',
            f"{row.get('season')} {row.get('network')} regular-season audience",
        )
    for row in payload.get('sources') or []:
        item = found.setdefault(row['url'], {'dates': [], 'covers': []})
        item['publisher'] = row.get('publisher') or ''
        item['checked'] = row.get('checked_at') or payload['updated']
        if row.get('covers') and row['covers'] not in item['covers']:
            item['covers'].insert(0, row['covers'])
        if row.get('source_date') and row['source_date'] not in item['dates']:
            item['dates'].insert(0, row['source_date'])
    listed = []
    for url, item in found.items():
        listed.append({
            'publisher': item.get('publisher') or core.source_label(url),
            'covers': '; '.join(item['covers']),
            'source_date': core.format_source_date(item['dates'][0]) if item['dates'] else '',
            'checked': core.format_updated(item.get('checked') or payload['updated']),
            'url': url,
        })
    return sorted(listed, key=lambda row: (row['publisher'], row['url']))


def sources_section(payload: dict, updated: str) -> str:
    body = []
    for row in register_rows(payload):
        body.append([
            core.esc(row['publisher']),
            core.esc(row['covers']),
            core.esc(row['source_date']),
            core.esc(row['checked']),
            source_cell(row['url']),
        ])
    cite = citation_text(updated)
    return (
        '<section class="qa" id="sources">'
        '<h2>Sources</h2>'
        '<p class="answer">Every figure on this page links to the report it came from. The register is the same set of URLs.</p>'
        + table(
            ['Publisher', 'Covers', 'Source date', 'Checked', 'Link'],
            body,
            'Source register',
            caption='Sources cited on this page.',
        )
        + '<h2>Cite this page</h2>'
        + f'<blockquote class="cite" id="citation-plain">{core.esc(cite)}</blockquote>'
        + actions_html()
        + '</section>'
    )


def page_script() -> str:
    return """
<script>
(function () {
  var links = document.querySelectorAll('.contents-rail a[href^="#"]');
  var select = document.getElementById('on-this-page');
  if (select) {
    select.addEventListener('change', function () {
      if (!select.value) return;
      var target = document.querySelector(select.value);
      if (target) target.scrollIntoView();
    });
  }
  var current = {};
  links.forEach(function (link) {
    var id = link.getAttribute('href').slice(1);
    if (document.getElementById(id)) current[id] = link;
  });
  if ('IntersectionObserver' in window) {
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        links.forEach(function (link) { link.removeAttribute('aria-current'); });
        var link = current[entry.target.id];
        if (link) link.setAttribute('aria-current', 'true');
        if (select) select.value = '#' + entry.target.id;
      });
    }, {rootMargin: '-140px 0px -420px 0px'});
    Object.keys(current).forEach(function (id) { observer.observe(document.getElementById(id)); });
  }
  function markCopied(button) {
    var label = button.getAttribute('data-label');
    if (!label) {
      label = button.textContent;
      button.setAttribute('data-label', label);
    }
    button.textContent = 'Copied!';
    window.clearTimeout(button._copyTimer);
    button._copyTimer = window.setTimeout(function () {
      button.textContent = label;
    }, 1600);
  }
  function copyWithFallback(button, text) {
    function selectFallback() {
      var area = document.createElement('textarea');
      area.value = text;
      area.setAttribute('readonly', '');
      area.setAttribute('aria-hidden', 'true');
      area.style.position = 'fixed';
      area.style.left = '-9999px';
      area.style.top = '0';
      document.body.appendChild(area);
      area.focus();
      area.select();
      try { document.execCommand('copy'); } catch (err) {}
      document.body.removeChild(area);
      markCopied(button);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () {
        markCopied(button);
      }, selectFallback);
    } else {
      selectFallback();
    }
  }
  document.querySelectorAll('.copy-citation').forEach(function (button) {
    button.addEventListener('click', function () {
      var node = document.getElementById('citation-plain');
      var text = node ? node.textContent : '';
      if (text) copyWithFallback(button, text);
    });
  });
  document.querySelectorAll('.copy-embed').forEach(function (button) {
    button.addEventListener('click', function () {
      var text = button.getAttribute('data-embed') || '';
      if (text) copyWithFallback(button, text);
    });
  });
})();
</script>
"""


def render_page(root: Path, payload: dict) -> str:
    menu = core.site_nav.build_menu(root)
    updated = core.format_updated(payload['updated'])
    cards = render_cards(stat_cards(payload))
    sections = ''.join([
        viewership_section(payload),
        attendance_section(payload),
        teams_section(payload),
        finals_section(payload),
        methodology(),
        sources_section(payload, updated),
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
    page_id = core.BASE + core.ROUTE + '#webpage'
    article_id = core.BASE + core.ROUTE + '#article'
    image = core.BASE + core.OG_IMAGE
    structured = {
        '@context': 'https://schema.org',
        '@graph': [
            {
                '@type': 'WebPage',
                '@id': page_id,
                'name': core.PAGE_TITLE,
                'headline': core.PAGE_TITLE,
                'url': core.BASE + core.ROUTE,
                'description': core.DESCRIPTION,
                'datePublished': '2026-10-13',
                'dateModified': payload['updated'],
                'author': {'@type': 'Person', 'name': 'Ryan Moalemi', 'url': core.BASE + '/authors/ryan-moalemi/'},
                'isPartOf': {'@type': 'WebSite', 'name': 'Full Court Buckets', 'url': core.BASE + '/'},
            },
            {
                '@type': 'Article',
                '@id': article_id,
                'headline': core.PAGE_TITLE,
                'description': core.DESCRIPTION,
                'datePublished': '2026-10-13',
                'dateModified': payload['updated'],
                'author': {'@type': 'Person', 'name': 'Ryan Moalemi', 'url': core.BASE + '/authors/ryan-moalemi/'},
                'publisher': {
                    '@type': 'Organization',
                    'name': 'Full Court Buckets',
                    'logo': {'@type': 'ImageObject', 'url': core.BASE + '/logo.png'},
                },
                'mainEntityOfPage': {'@type': 'WebPage', '@id': page_id},
                'image': [image],
            },
            {
                '@type': 'BreadcrumbList',
                'itemListElement': [
                    {'@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': core.BASE + '/'},
                    {'@type': 'ListItem', 'position': 2, 'name': core.PAGE_TITLE, 'item': core.BASE + core.ROUTE},
                ],
            },
        ],
    }
    if questions:
        structured['@graph'].append({
            '@type': 'FAQPage',
            '@id': core.BASE + core.ROUTE + '#faq',
            'mainEntity': questions,
        })
    schema = json.dumps(structured, ensure_ascii=False).replace('<', '\\u003c')
    css = (Path(__file__).with_name('standings.css')).read_text(encoding='utf-8') + core.EXTRA_CSS + core.links.BYLINE_CSS
    lead = core.link_teams(core.lead_sentence(payload))
    disclosure = f'<p class="how-made">{core.esc(core.links.HOW_MADE_OTHER)} {core.links.HOW_MADE_LINK}</p>'
    byline = (
        '<div class="byline-row article">'
        f'{core.links.BYLINE_HTML}'
        '<span class="byline-sep" aria-hidden="true">|</span>'
        f'<time class="article-date" datetime="{core.esc(payload["updated"])}">Updated {core.esc(updated)}</time>'
        '</div>'
    )
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
{core.GA4_TAG}
{core.ADSENSE_TAG}
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{core.esc(core.PAGE_TITLE)} | Full Court Buckets</title>
<meta name="description" content="{core.esc(core.DESCRIPTION)}">
<meta name="author" content="Ryan Moalemi">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{core.BASE}{core.ROUTE}">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<meta property="og:type" content="article">
<meta property="og:title" content="{core.esc(core.PAGE_TITLE)}">
<meta property="og:description" content="{core.esc(core.DESCRIPTION)}">
<meta property="og:url" content="{core.BASE}{core.ROUTE}">
<meta property="og:image" content="{image}">
<meta property="og:image:alt" content="{core.esc(core.OG_ALT)}">
<meta property="og:site_name" content="Full Court Buckets">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{core.esc(core.PAGE_TITLE)}">
<meta name="twitter:description" content="{core.esc(core.DESCRIPTION)}">
<meta name="twitter:image" content="{image}">
<meta name="twitter:image:alt" content="{core.esc(core.OG_ALT)}">
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
{core.site_nav.render_header(menu, core.ROUTE)}
<main class="page">
<div class="standings-shell">
<div class="page-header">
<p class="eyebrow">WNBA / Data &amp; research</p>
<h1>{core.esc(core.PAGE_TITLE)}</h1>
{byline}
<p class="subhead">{lead}</p>
</div>
<section class="key-stats" aria-label="Key WNBA stats">
<h2>Key WNBA stats</h2>
{cards}
</section>
<div class="data-layout">
{contents_html()}
<div class="data-main">
{sections}
{disclosure}
</div>
</div>
</div>
</main>
{core.site_nav.footer_html(True)}
<script src="/assets/site-nav.js" defer></script>
{page_script()}
</body>
</html>
'''


def _csv_note(value: int, extra: str = '') -> str:
    shown = core.format_number(value)
    note = f'Displayed as {shown}.' if shown != f'{value:,}' else ''
    if extra:
        note = f'{note} {extra}'.strip()
    return note


def _csv_row(metric_id, period, value, unit, scope, url, source_date, checked, notes='') -> dict:
    return {
        'metric_id': metric_id,
        'period': period,
        'value': value,
        'unit': unit,
        'scope': scope,
        'source_url': url,
        'source_date': source_date or '',
        'checked_at': checked,
        'notes': notes,
    }


def csv_rows(payload: dict) -> list[dict]:
    checked = payload['updated']
    rows = []
    for row in core.league_rows(payload):
        season = row.get('season')
        if core.is_number(row.get('total_attendance')):
            rows.append(_csv_row(
                f'attendance-total-{season}', season, row['total_attendance'], 'fans',
                'regular season', row.get('attendance_source') or '', row.get('attendance_source_date') or '',
                checked, _csv_note(row['total_attendance']),
            ))
        if core.is_number(row.get('games_played')):
            game_note = 'Calculated.' if row.get('games_calculated') else ''
            rows.append(_csv_row(
                f'attendance-games-{season}', season, row['games_played'], 'games',
                'regular season',
                row.get('games_source') or row.get('attendance_source') or '',
                row.get('games_source_date') or row.get('attendance_source_date') or '',
                checked, game_note,
            ))
        if core.is_number(row.get('avg_attendance')):
            average_note = 'Calculated from the rounded total divided by the game count.' if row.get('avg_attendance_status') == 'calculated' else ''
            rows.append(_csv_row(
                f'attendance-average-{season}', season, row['avg_attendance'], 'fans per game',
                'regular season', row.get('avg_attendance_source') or '', row.get('avg_attendance_source_date') or '',
                checked, average_note,
            ))
        if core.is_number(row.get('avg_attendance_printed')):
            rows.append(_csv_row(
                f'attendance-average-printed-{season}', season, row['avg_attendance_printed'], 'fans per game',
                'regular season, printed average', row.get('avg_attendance_source') or '',
                row.get('avg_attendance_source_date') or '', checked,
                'Printed by the source. Does not reconcile with the total divided by the game count.',
            ))
        for item in row.get('finals_game_reports') or []:
            rows.append(_csv_row(
                f"finals-game-{season}-{item.get('game')}", season, item['viewers'], 'viewers',
                f"Finals {item.get('game')}", item.get('source') or '', item.get('source_date') or '',
                checked, _csv_note(item['viewers'], item.get('note') or ''),
            ))
        if core.is_number(row.get('finals_avg_viewers')):
            games = row.get('finals_games')
            scope = f'Finals average, {games} games' if core.is_number(games) else 'Finals average'
            rows.append(_csv_row(
                f'finals-average-{season}', season, row['finals_avg_viewers'], 'viewers',
                scope, row.get('finals_viewers_source') or '', row.get('finals_viewers_source_date') or '',
                checked, _csv_note(row['finals_avg_viewers'], finals_measurement(row)),
            ))
        if core.is_number(row.get('relocated_games')):
            rows.append(_csv_row(
                f'relocated-games-{season}', season, row['relocated_games'], 'games',
                'relocated games', row.get('relocated_source') or '', row.get('relocated_source_date') or '',
                checked, '',
            ))
        if core.is_number(row.get('relocated_attendance')):
            rows.append(_csv_row(
                f'relocated-attendance-{season}', season, row['relocated_attendance'], 'fans',
                'relocated games', row.get('relocated_source') or '', row.get('relocated_source_date') or '',
                checked, 'Unresolved: the printed average does not match the total divided by the game count.',
            ))
    for row in payload.get('games') or []:
        if core.is_number(row.get('viewers')):
            rows.append(_csv_row(
                f"audience-{row.get('date')}", row.get('date'), row['viewers'], 'viewers',
                f"{event_type(row)}: {row.get('game')}", row.get('viewers_source') or '',
                row.get('viewers_source_date') or '', checked, _csv_note(row['viewers']),
            ))
        if core.is_number(row.get('peak_viewers')):
            rows.append(_csv_row(
                f"peak-{row.get('date')}", row.get('date'), row['peak_viewers'], 'viewers',
                f"Peak minute: {row.get('game')}", row.get('peak_viewers_source') or '',
                row.get('peak_viewers_source_date') or '', checked, 'Peak minute, not the game average.',
            ))
        if core.is_number(row.get('attendance')):
            rows.append(_csv_row(
                f"crowd-{row.get('date')}", row.get('date'), row['attendance'], 'fans',
                row.get('game') or '', row.get('attendance_source') or '',
                row.get('attendance_source_date') or '', checked, '',
            ))
    for row in core.home_rows(payload):
        rows.append(_csv_row(
            f"home-{row.get('season')}-{row.get('home_team')}", row.get('season'), row['home_attendance'], 'fans',
            f"{row.get('home_team')} home", row.get('home_attendance_source') or '',
            row.get('home_attendance_source_date') or '', checked, str(row.get('home_note') or ''),
        ))
    for row in payload.get('seasons') or []:
        if row.get('road_team') and core.is_number(row.get('road_avg')):
            rows.append(_csv_row(
                f"road-{row.get('season')}-{row.get('road_team')}", row.get('season'), row['road_avg'], 'fans per game',
                f"{row.get('road_team')} road", row.get('road_source') or '',
                row.get('road_source_date') or '', checked, 'Road games, not home.',
            ))
        if core.is_number(row.get('home_change_pct')) and not core.is_number(row.get('home_attendance')):
            rows.append(_csv_row(
                f"home-change-{row.get('season')}-{row.get('home_team')}", row.get('season'), row['home_change_pct'], 'percent',
                f"{row.get('home_team')} home attendance change", row.get('home_attendance_source') or '',
                row.get('home_attendance_source_date') or '', checked, 'Printed change. Season total is not in this file.',
            ))
    for row in _broadcasts(payload):
        games_note = f"{row.get('games')} games" if core.is_number(row.get('games')) else 'Game count not stated.'
        rows.append(_csv_row(
            f"tv-{row.get('season')}-{row.get('network')}", row.get('season'), row['avg_viewers'], 'viewers',
            row.get('scope') or row.get('network') or '', row.get('source') or '',
            row.get('source_date') or '', checked,
            _csv_note(row['avg_viewers'], f"{games_note}. {row.get('measurement') or ''}".strip()),
        ))
    split = growth_split(league_season(payload, 2025), league_season(payload, 2026))
    if split and split.get('method') == 'fraction':
        rows.append(_csv_row(
            'growth-extra-games-2025-2026', '2025-2026', split['extra_games'], 'fans',
            'provisional extra-games piece', '', '', checked,
            'Calculated. Provisional accounting split.',
        ))
        rows.append(_csv_row(
            'growth-average-crowd-2025-2026', '2025-2026', split['average_crowd'], 'fans',
            'provisional average-crowd piece', '', '', checked,
            'Calculated. Provisional accounting split.',
        ))
    for metric in payload.get('metrics') or []:
        rows.append({key: metric.get(key, '') for key in core.CSV_FIELDS})
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=core.CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _draw_columns(path: Path, title: str, points, *, unit: str, note: str, color=ORANGE) -> None:
    width, height = 1600, 560
    image = Image.new('RGB', (width, height), BG)
    draw = ImageDraw.Draw(image)
    draw.text((48, 28), title, font=_font(FONT_BOLD, 36), fill=INK)
    draw.text((48, 78), unit, font=_font(FONT_MED, 22), fill=MUTED)
    values = [value for _name, value, *_rest in [(point[0], point[1]) for point in points]]
    peak = max([value for value in values if value], default=1) * 1.25
    left, right, top, bottom = 120, 1540, 140, 430
    draw.line((left, bottom, right, bottom), fill=MUTED, width=2)
    slot = (right - left) / max(len(points), 1)
    for index, point in enumerate(points):
        name, value = point[0], point[1]
        sub = point[2] if len(point) > 2 else ''
        center = left + slot * (index + 0.5)
        if value:
            bar_height = (bottom - top) * (value / peak)
            draw.rectangle((center - 36, bottom - bar_height, center + 36, bottom), fill=color)
            draw.text((center - 40, bottom - bar_height - 36), compact_millions(int(value)) if value >= 1000 else f'{int(value):,}', font=_font(FONT_BOLD, 22), fill=INK)
        else:
            draw.text((center - 70, bottom - 36), 'Not reported', font=_font(FONT_MED, 18), fill=MUTED)
        draw.text((center - 28, bottom + 16), str(name), font=_font(FONT_BOLD, 22), fill=INK)
        if sub:
            draw.text((center - 40, bottom + 46), sub, font=_font(FONT_MED, 18), fill=MUTED)
    draw.text((48, 510), note[:180], font=_font(FONT_MED, 20), fill=MUTED)
    image.save(path, 'PNG')


def _draw_line(path: Path, title: str, points, *, unit: str, note: str) -> None:
    width, height = 1600, 560
    image = Image.new('RGB', (width, height), BG)
    draw = ImageDraw.Draw(image)
    draw.text((48, 28), title, font=_font(FONT_BOLD, 36), fill=INK)
    draw.text((48, 78), unit, font=_font(FONT_MED, 22), fill=MUTED)
    peak = max([point[1] or 0 for point in points], default=1) * 1.25
    left, right, top, bottom = 140, 1500, 150, 430
    draw.line((left, bottom, right, bottom), fill=MUTED, width=2)
    count = max(len(points), 1)
    coords = []
    dots = []
    segment = []

    def x_at(index: int) -> float:
        if count == 1:
            return (left + right) / 2
        return left + (right - left) * index / (count - 1)

    for index, point in enumerate(points):
        name, value = point[0], point[1]
        marker = point[2] if len(point) > 2 else ''
        x = x_at(index)
        draw.text((x - 24, bottom + 18), str(name), font=_font(FONT_BOLD, 22), fill=INK)
        if value is None:
            if len(segment) >= 2:
                coords.append(segment)
            segment = []
            draw.text((x - 70, bottom - 40), 'Not reported', font=_font(FONT_MED, 18), fill=MUTED)
            continue
        y = bottom - (bottom - top) * (value / peak)
        segment.append((x, y))
        dots.append((x, y, marker))
        draw.text((x - 36, y - 36), f'{int(value):,}', font=_font(FONT_BOLD, 22), fill=INK)
        if marker:
            draw.text((x - 42, y + 12), marker, font=_font(FONT_MED, 16), fill=MUTED)
    if len(segment) >= 2:
        coords.append(segment)
    for segment in coords:
        draw.line(segment, fill=ORANGE, width=4)
    for x, y, marker in dots:
        if marker:
            draw.ellipse((x - 8, y - 8, x + 8, y + 8), outline=ORANGE, width=3)
        else:
            draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=ORANGE)
    draw.text((48, 510), note[:180], font=_font(FONT_MED, 20), fill=MUTED)
    image.save(path, 'PNG')


def _draw_share(path: Path, *, portrait: bool) -> None:
    size = (1080, 1350) if portrait else (1600, 900)
    image = Image.new('RGB', size, SHARE_BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, size[0], 12), fill=ORANGE)
    logo = Image.open(core.ROOT / 'logo.png').convert('RGBA')
    logo.thumbnail((280, 120) if portrait else (320, 130))
    plate = Image.new('RGB', (logo.width + 16, logo.height + 16), (255, 255, 255))
    plate.paste(logo, (8, 8), logo)
    image.paste(plate, (48, 48))
    number_size = 150 if portrait else 132
    y = 280 if portrait else 240
    draw.text((56, y), '11,474', font=_font(FONT_BOLD, number_size), fill=INK)
    draw.text((56, y + number_size + 10), 'fans per regular-season game', font=_font(FONT_MED, 40 if portrait else 36), fill=INK)
    draw.text((56, y + number_size + 70), '2026 WNBA attendance', font=_font(FONT_MED, 32), fill=MUTED)
    footer_y = size[1] - 150
    draw.text((56, footer_y), 'Source: Front Office Sports, Sept. 25, 2026', font=_font(FONT_MED, 26), fill=MUTED)
    draw.text((56, footer_y + 44), 'fullcourtbuckets.com/wnba/viewership-attendance/', font=_font(FONT_MED, 24), fill=ORANGE)
    image.save(path, 'PNG')


def write_downloads(directory: Path, payload: dict) -> None:
    averages = attendance_points(payload, 'avg_attendance')
    if averages:
        _draw_line(
            directory / 'attendance-average.png',
            'Regular-season attendance per game',
            _chart_points(payload, averages, 'avg_attendance'),
            unit='Fans per game',
            note='Open circles are calculated. Missing years are not zero. Full Court Buckets.',
        )
    totals = attendance_points(payload, 'total_attendance')
    average_years = [year for year, _value in averages]
    if totals and average_years:
        known = dict(totals)
        span = [(year, known.get(year)) for year in range(min(average_years), max(average_years) + 1)]
        _draw_columns(
            directory / 'attendance-total.png',
            'Regular-season total attendance',
            _chart_points(payload, span, 'total_attendance'),
            unit='Total fans',
            note='Blank years are not zero. Full Court Buckets.',
        )
    network_rows, season = same_season_broadcasts(payload)
    if network_rows and season:
        _draw_columns(
            directory / 'network-2026.png',
            f'{season} regular-season TV audiences',
            [(row['network'], row['avg_viewers'], f"{row['games']} games") for row in network_rows],
            unit='Average viewers',
            note='Schedules differ. Not a broadcaster ranking.',
        )
    espn_rows = espn_regular_season(payload)
    if espn_rows:
        _draw_columns(
            directory / 'espn-regular-season.png',
            'ESPN regular-season average',
            [(str(row['season']), row['avg_viewers'], f"{row['games']} games") for row in espn_rows],
            unit='Average viewers',
            note='2025 uses Big Data + Panel. Not a percent change.',
            color=PURPLE,
        )
    finals = sorted(core.number_rows(core.league_rows(payload), 'finals_avg_viewers'), key=lambda row: row['season'])
    if finals:
        _draw_columns(
            directory / 'finals-history.png',
            'WNBA Finals average audience',
            [(str(row['season']), row['finals_avg_viewers'], f"{row.get('finals_games') or ''} games") for row in finals],
            unit='Average viewers',
            note='Game counts and measurement differ. 2026 is not plotted.',
        )
    ranking = complete_team_rank(payload)
    if ranking:
        _season, ranked = ranking
        _draw_columns(
            directory / 'team-ranking.png',
            f'{_season} average home attendance',
            [(row['team'], row['average']) for row in ranked],
            unit='Fans per home game',
            note='Rounded labels. Home games only.',
        )
    split = growth_split(league_season(payload, 2025), league_season(payload, 2026))
    if split:
        _draw_columns(
            directory / 'attendance-growth.png',
            'Provisional attendance split',
            [
                (str(split['prior_season']), split['prior_total']),
                ('Extra games', split['extra_games']),
                ('Average', split['average_crowd']),
                (str(split['current_season']), split['current_total']),
            ],
            unit='Fans, provisional',
            note='Accounting split, not a cause of demand.',
        )
    if league_season(payload, 2026) and league_season(payload, 2026).get('avg_attendance') == 11474:
        _draw_share(directory / core.SHARE_LANDSCAPE, portrait=False)
        _draw_share(directory / core.SHARE_PORTRAIT, portrait=True)


def _validate_broadcasts(rows) -> None:
    if rows is None:
        return
    if not isinstance(rows, list):
        raise ValueError('Broadcasts must be a list.')
    for index, row in enumerate(rows):
        label = f'Broadcast row {index + 1}'
        if not isinstance(row, dict):
            raise ValueError(f'{label} is not an object.')
        if not core.is_number(row.get('season')) or not str(row.get('network') or '').strip():
            raise ValueError(f'{label} is missing a season.')
        if not core.is_number(row.get('avg_viewers')) or not core.is_source_url(row.get('source')):
            raise ValueError(f'{label} has a number but no source.')
        if row.get('games') is not None and not core.is_number(row.get('games')):
            raise ValueError(f'{label} has a game count that is not a whole number.')
        if not core.valid_source_date(row.get('source_date')) or not str(row.get('source_date') or '').strip():
            raise ValueError(f'{label} needs a source date.')
