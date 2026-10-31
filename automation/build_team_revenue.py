#!/usr/bin/env python3
"""Build /wnba/team-revenue/ from data/wnba-team-revenue-2025.json.

The value column is the Forbes May 7, 2026 ranking. The revenue column is the
Playbook Strategies estimate on the Oct. 31, 2026 Katherine Rowe graphic.
value_to_revenue_multiple is Forbes value divided by Playbook revenue.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from analytics import GA4_TAG
import breadcrumbs
import internal_links as links
import search_index
import seo_meta
import site_nav

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = 'data/wnba-team-revenue-2025.json'
ROUTE = '/wnba/team-revenue/'
BASE = 'https://fullcourtbuckets.com'
PAGE_TITLE = 'WNBA team revenue and franchise values for 2026'
H1 = 'WNBA team revenue and franchise value multiples'
DESCRIPTION = (
    'Playbook estimates 2025 WNBA revenue from $16 million in Atlanta and '
    'Washington to $78 million in Golden State. Forbes May 2026 values, with FCB multiples.'
)
CSV_NAME = 'wnba-team-revenue-2025.csv'
JSON_NAME = 'wnba-team-revenue-2025.json'
OG_NAME = 'share-revenue-multiples.png'
ADSENSE_TAG = (
    '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js'
    '?client=ca-pub-6621195315204235" crossorigin="anonymous"></script>'
)
FORBES_US = 'https://www.forbes.com/sites/brettknight/2026/05/07/the-wnbas-most-valuable-teams-2026/'
FORBES_MX = 'https://forbes.com.mx/estos-son-los-equipos-mas-valiosos-de-la-wnba-en-2026/'
PLAYBOOK_POST = 'https://x.com/katherinearowe/status/2116531655661834492'
PLAYBOOK_REPORT = 'https://www.playbookstrategies.co/reports/wnba-market-intelligence-2026'
EM_DASH = '\u2014'
EN_DASH = '\u2013'
REQUIRED = (
    'team', 'slug', 'abbr', 'market', '2025_revenue_usd_m', 'revenue_source',
    'revenue_source_url', 'revenue_notes', 'forbes_2025_revenue_usd_m',
    'playbook_graphic_multiple', 'forbes_2026_value_usd_m', 'forbes_rank',
    'forbes_source_url', 'forbes_date', 'ownership', 'arena', 'team_page',
)
CSV_FIELDS = (
    'team', 'market', 'team_page', 'in_source_set',
    '2025_revenue_usd_m', 'revenue_source', 'revenue_source_url', 'revenue_notes',
    'forbes_2025_revenue_usd_m', 'revenue_conflict',
    'forbes_2026_value_usd_m', 'forbes_rank', 'forbes_yoy_change_pct',
    'forbes_source_url', 'forbes_date', 'forbes_table_checked_url',
    'value_to_revenue_multiple', 'playbook_graphic_multiple',
    'forbes_value_to_forbes_revenue_multiple',
    'ownership', 'arena', 'arena_source_url',
    'attendance_context', 'attendance_context_url',
)
NAV = (
    ('revenue', 'Revenue'),
    ('multiples', 'Multiples'),
    ('table', 'Full table'),
    ('by-value', 'By value'),
    ('by-multiple', 'By multiple'),
    ('gap', 'Gaps'),
    ('methods', 'Methods'),
    ('sources', 'Sources'),
    ('faq', 'FAQ'),
)


def esc(value) -> str:
    return html.escape('' if value is None else str(value), quote=True)


def multiple(value, revenue) -> float:
    """Forbes value divided by a revenue estimate, half up to one decimal."""
    return float(
        (Decimal(value) / Decimal(revenue)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
    )


def money(millions) -> str:
    return f'${int(millions)} million'


def money_short(millions) -> str:
    return f'${int(millions)}M'


def mult(value) -> str:
    return f'{value:.1f}x'


def blank(value) -> str:
    return '' if value is None else value


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def enrich(payload: dict) -> dict:
    teams = []
    for index, raw in enumerate(payload['teams'], start=1):
        team = dict(raw)
        team['playbook_order'] = index
        team['in_source_set'] = True
        team['forbes_table_checked_url'] = FORBES_MX
        team['value_to_revenue_multiple'] = multiple(
            team['forbes_2026_value_usd_m'], team['2025_revenue_usd_m']
        )
        team['forbes_value_to_forbes_revenue_multiple'] = multiple(
            team['forbes_2026_value_usd_m'], team['forbes_2025_revenue_usd_m']
        )
        team['revenue_conflict'] = team['2025_revenue_usd_m'] != team['forbes_2025_revenue_usd_m']
        team['graphic_matches_fcb'] = team['playbook_graphic_multiple'] == team['value_to_revenue_multiple']
        teams.append(team)
    payload = dict(payload)
    payload['teams'] = teams
    payload['fcb_checks'] = checks(teams)
    return payload


def checks(teams: list[dict]) -> dict:
    values = sum(team['forbes_2026_value_usd_m'] for team in teams)
    playbook = sum(team['2025_revenue_usd_m'] for team in teams)
    forbes_rev = sum(team['forbes_2025_revenue_usd_m'] for team in teams)
    return {
        'team_count': len(teams),
        'forbes_value_sum_usd_m': values,
        'forbes_value_average_usd_m': round(values / len(teams), 1),
        'playbook_revenue_sum_usd_m': playbook,
        'forbes_revenue_sum_usd_m': forbes_rev,
        'league_multiple_on_forbes_revenue': float(
            (Decimal(values) / Decimal(forbes_rev)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        ),
        'finals_revenue_ratio': float(
            (Decimal(78) / Decimal(16)).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
        ),
    }


def validate(payload: dict) -> None:
    if payload.get('updated') != '2026-10-31':
        raise ValueError('Dataset updated date must be 2026-10-31.')
    teams = payload.get('teams') or []
    if len(teams) != 13:
        raise ValueError('The source set is the 13 teams that played in 2025.')
    seen = set()
    for team in teams:
        for key in REQUIRED:
            if team.get(key) in (None, ''):
                raise ValueError(f'{team.get("team") or "A team"} is missing {key}.')
        if team['slug'] in seen:
            raise ValueError(f'Duplicate slug {team["slug"]}.')
        seen.add(team['slug'])
        if team['forbes_source_url'] != FORBES_US or team['forbes_date'] != '2026-05-07':
            raise ValueError(f'{team["team"]} is not cited to the May 7, 2026 Forbes article.')
        if team['revenue_source_url'] != PLAYBOOK_POST:
            raise ValueError(f'{team["team"]} revenue is not cited to the Playbook graphic.')
        if team['forbes_2026_value_usd_m'] in {850, 1000}:
            raise ValueError(f'{team["team"]} uses a Sportico or CNBC value, not the Forbes card.')
        got = multiple(team['forbes_2026_value_usd_m'], team['2025_revenue_usd_m'])
        if team.get('value_to_revenue_multiple') not in (None, got):
            raise ValueError(f'{team["team"]} multiple does not match value divided by Playbook revenue.')
        forbes_mult = multiple(team['forbes_2026_value_usd_m'], team['forbes_2025_revenue_usd_m'])
        if team.get('forbes_value_to_forbes_revenue_multiple') not in (None, forbes_mult):
            raise ValueError(f'{team["team"]} Forbes-on-Forbes multiple does not match.')
    enriched = enrich({'updated': payload['updated'], 'teams': [dict(t) for t in teams]})
    by_slug = {team['slug']: team for team in enriched['teams']}
    golden = by_slug['golden-state-valkyries']
    atlanta = by_slug['atlanta-dream']
    washington = by_slug['washington-mystics']
    indiana = by_slug['indiana-fever']
    seattle = by_slug['seattle-storm']
    if (golden['forbes_2026_value_usd_m'], golden['2025_revenue_usd_m'], golden['value_to_revenue_multiple']) != (780, 78, 10.0):
        raise ValueError('Golden State must be $780 million, $78 million, and 10.0x.')
    if (atlanta['forbes_2026_value_usd_m'], atlanta['2025_revenue_usd_m'], atlanta['value_to_revenue_multiple']) != (250, 16, 15.6):
        raise ValueError('Atlanta must be $250 million, $16 million, and 15.6x.')
    if washington['2025_revenue_usd_m'] != 16 or atlanta['2025_revenue_usd_m'] != 16:
        raise ValueError('Washington and Atlanta are tied at $16 million on the Playbook column.')
    if (washington['forbes_2025_revenue_usd_m'], washington['value_to_revenue_multiple'], washington['playbook_graphic_multiple']) != (18, 17.5, 15.6):
        raise ValueError('Washington conflict is Forbes $18 million, FCB 17.5x, graphic 15.6x.')
    if (indiana['2025_revenue_usd_m'], indiana['forbes_2025_revenue_usd_m'], indiana['value_to_revenue_multiple'], indiana['playbook_graphic_multiple']) != (56, 58, 10.4, 10.0):
        raise ValueError('Indiana conflict is Playbook $56 million, Forbes $58 million, FCB 10.4x, graphic 10.0x.')
    if seattle['playbook_graphic_multiple'] != 15.4 or seattle['value_to_revenue_multiple'] != 15.4:
        raise ValueError('Seattle is 15.4x on both the graphic read and the FCB calculation.')
    conflicts = sorted(team['slug'] for team in enriched['teams'] if team['revenue_conflict'])
    if conflicts != ['indiana-fever', 'washington-mystics']:
        raise ValueError(f'Revenue conflicts must be Indiana and Washington, not {conflicts}.')
    summary = enriched['fcb_checks']
    if summary['forbes_value_sum_usd_m'] != 5385 or summary['forbes_value_average_usd_m'] != 414.2:
        raise ValueError('Forbes values must sum to $5,385 million and average $414.2 million.')
    if summary['playbook_revenue_sum_usd_m'] != 426 or summary['forbes_revenue_sum_usd_m'] != 430:
        raise ValueError('Playbook revenue must sum to $426 million and Forbes revenue to $430 million.')
    if summary['league_multiple_on_forbes_revenue'] != 12.52:
        raise ValueError('League value divided by Forbes revenue must be 12.52x before the Forbes 12.5x rounding.')
    ranks = sorted(team['forbes_rank'] for team in teams)
    if ranks != list(range(1, 14)):
        raise ValueError('Forbes ranks must be 1 through 13 with no gaps.')
    missing = payload.get('not_in_source_set') or []
    slugs = {row.get('slug') for row in missing}
    if slugs != {'portland-fire', 'toronto-tempo'}:
        raise ValueError('Portland and Toronto are the expansion rows, and they stay out of the value table.')
    for row in missing:
        if row.get('2025_revenue_usd_m') is not None or row.get('forbes_2026_value_usd_m') is not None:
            raise ValueError(f'{row.get("team")} is not in the source set and cannot carry a number.')
        if 'Not in the source set' not in (row.get('reason') or ''):
            raise ValueError(f'{row.get("team")} needs an explicit not-in-source-set note.')
    blob = json.dumps(payload, ensure_ascii=False)
    if EM_DASH in blob or EN_DASH in blob:
        raise ValueError('Dataset copy contains a dash that the style guide does not allow.')


def team_link(team: dict) -> str:
    return f'<a href="{esc(team["team_page"])}">{esc(team["team"])}</a>'


def source_link(url: str, label: str) -> str:
    return f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(label)}</a>'


def by_revenue(teams: list[dict]) -> list[dict]:
    return sorted(teams, key=lambda team: (-team['2025_revenue_usd_m'], team['playbook_order']))


def by_value(teams: list[dict]) -> list[dict]:
    return sorted(teams, key=lambda team: team['forbes_rank'])


def by_multiple(teams: list[dict]) -> list[dict]:
    return sorted(teams, key=lambda team: (-team['value_to_revenue_multiple'], team['team']))


def tie_ranks(rows: list[dict], key: str) -> list[int]:
    ranks = []
    rank = 0
    last = None
    for index, row in enumerate(rows, start=1):
        value = row[key]
        if value != last:
            rank = index
            last = value
        ranks.append(rank)
    return ranks


def revenue_bar(teams: list[dict]) -> str:
    rows = by_revenue(teams)
    width, row_h, left, right = 640, 28, 148, 64
    height = 36 + row_h * len(rows)
    max_rev = 78
    plot = width - left - right
    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-labelledby="revenue-chart-title">',
        '<title id="revenue-chart-title">2025 WNBA revenue estimates, Playbook Strategies. Golden State $78 million, Atlanta and Washington $16 million.</title>',
    ]
    for index, team in enumerate(rows):
        y = 18 + index * row_h
        bar = plot * team['2025_revenue_usd_m'] / max_rev
        color = '#b8006f' if team['finals_2026'] else '#5b22c9'
        parts.append(
            f'<text x="{left - 8}" y="{y + 16}" text-anchor="end" font-size="13" fill="#151413">{esc(team["abbr"])}</text>'
            f'<rect x="{left}" y="{y}" width="{bar:.1f}" height="18" fill="{color}"></rect>'
            f'<text x="{left + bar + 6:.1f}" y="{y + 14}" font-size="13" fill="#151413">{money_short(team["2025_revenue_usd_m"])}</text>'
        )
    parts.append('</svg>')
    return ''.join(parts)


def scatter(teams: list[dict]) -> str:
    width, height = 640, 420
    left, right, top, bottom = 56, 16, 16, 40
    plot_w = width - left - right
    plot_h = height - top - bottom
    max_x, max_y = 90, 900

    def x_of(revenue):
        return left + plot_w * revenue / max_x

    def y_of(value):
        return top + plot_h * (1 - value / max_y)

    parts = [
        f'<svg class="chart scatter" viewBox="0 0 {width} {height}" role="img" aria-labelledby="scatter-title">',
        '<title id="scatter-title">Forbes 2026 franchise value against Playbook 2025 revenue. Golden State is high revenue and a 10.0x multiple. Atlanta is low revenue and a 15.6x multiple.</title>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height - bottom}" stroke="#e2ddd6"></line>',
        f'<line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" stroke="#e2ddd6"></line>',
    ]
    for tick in (0, 20, 40, 60, 80):
        x = x_of(tick)
        parts.append(
            f'<line x1="{x:.1f}" y1="{height - bottom}" x2="{x:.1f}" y2="{height - bottom + 4}" stroke="#e2ddd6"></line>'
            f'<text x="{x:.1f}" y="{height - 16}" text-anchor="middle" font-size="12" fill="#5a554e">{tick}</text>'
        )
    for tick in (0, 200, 400, 600, 800):
        y = y_of(tick)
        parts.append(
            f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end" font-size="12" fill="#5a554e">{tick}</text>'
        )
    parts.append(
        f'<text x="{width / 2:.0f}" y="{height - 2}" text-anchor="middle" font-size="12" fill="#5a554e">2025 revenue, $ millions (Playbook)</text>'
        f'<text x="16" y="{height / 2:.0f}" text-anchor="middle" font-size="12" fill="#5a554e" transform="rotate(-90 16 {height / 2:.0f})">Forbes 2026 value, $ millions</text>'
    )
    for team in teams:
        x = x_of(team['2025_revenue_usd_m'])
        y = y_of(team['forbes_2026_value_usd_m'])
        color = '#b8006f' if team['finals_2026'] else ('#a85400' if team['revenue_conflict'] else '#5b22c9')
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{color}"><title>{esc(team["team"])}: {money(team["2025_revenue_usd_m"])} revenue, {money(team["forbes_2026_value_usd_m"])} value, {mult(team["value_to_revenue_multiple"])}</title></circle>'
            f'<text x="{x + 7:.1f}" y="{y + 4:.1f}" font-size="12" fill="#151413">{esc(team["abbr"])}</text>'
        )
    parts.append('</svg>')
    return ''.join(parts)


def master_rows(teams: list[dict]) -> str:
    body = []
    for team in teams:
        conflict = ' conflict' if team['revenue_conflict'] else ''
        finals = ' finals' if team['finals_2026'] else ''
        yoy = 'n/a' if team['forbes_yoy_change_pct'] is None else f'{team["forbes_yoy_change_pct"]}%'
        flag = '' if team['graphic_matches_fcb'] else ' <span class="flag">differs</span>'
        body.append(
            '<tr class="' + (finals + conflict).strip() + '">'
            f'<td data-value="{esc(team["team"])}">{team_link(team)}</td>'
            f'<td data-value="{esc(team["market"])}">{esc(team["market"])}</td>'
            f'<td class="num" data-value="{team["2025_revenue_usd_m"]}">{money_short(team["2025_revenue_usd_m"])}</td>'
            f'<td class="num" data-value="{team["forbes_2025_revenue_usd_m"]}">{money_short(team["forbes_2025_revenue_usd_m"])}</td>'
            f'<td class="num" data-value="{team["forbes_2026_value_usd_m"]}">{money_short(team["forbes_2026_value_usd_m"])}</td>'
            f'<td class="num" data-value="{team["forbes_rank"]}">{team["forbes_rank"]}</td>'
            f'<td class="num" data-value="{team["forbes_yoy_change_pct"] if team["forbes_yoy_change_pct"] is not None else -1}">{yoy}</td>'
            f'<td class="num" data-value="{team["value_to_revenue_multiple"]}">{mult(team["value_to_revenue_multiple"])}</td>'
            f'<td class="num" data-value="{team["playbook_graphic_multiple"]}">{mult(team["playbook_graphic_multiple"])}{flag}</td>'
            '</tr>'
        )
    return ''.join(body)


def compact_table(rows: list[dict], rank_key: str, value_label: str, value_fn) -> str:
    ranks = tie_ranks(rows, rank_key)
    body = []
    for rank, team in zip(ranks, rows):
        tied = sum(1 for other in rows if other[rank_key] == team[rank_key]) > 1
        label = f'{rank}' + (' tie' if tied else '')
        body.append(
            '<tr>'
            f'<td class="num">{esc(label)}</td>'
            f'<td>{team_link(team)}</td>'
            f'<td class="num">{value_fn(team)}</td>'
            f'<td class="num">{money_short(team["forbes_2026_value_usd_m"])}</td>'
            f'<td class="num">{money_short(team["2025_revenue_usd_m"])}</td>'
            f'<td class="num">{mult(team["value_to_revenue_multiple"])}</td>'
            '</tr>'
        )
    return (
        '<div class="table-wrap wide"><table class="audience-table wide">'
        f'<thead><tr><th scope="col">Rank</th><th scope="col">Team</th><th scope="col">{esc(value_label)}</th>'
        '<th scope="col">Forbes value</th><th scope="col">Playbook revenue</th><th scope="col">FCB multiple</th></tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>'
    )


def faq_items(teams: list[dict]) -> list[dict]:
    by_slug = {team['slug']: team for team in teams}
    golden = by_slug['golden-state-valkyries']
    atlanta = by_slug['atlanta-dream']
    washington = by_slug['washington-mystics']
    return [
        {
            'q': 'Which WNBA team had the highest 2025 revenue?',
            'a': (
                f'Playbook Strategies estimates the Golden State Valkyries at {money(golden["2025_revenue_usd_m"])} '
                'for 2025, excluding playoffs. Forbes prints the same $78 million and calls it a WNBA record.'
            ),
        },
        {
            'q': 'Which WNBA teams had the lowest 2025 revenue?',
            'a': (
                'On the Playbook graphic, the Atlanta Dream and the Washington Mystics are tied at $16 million, '
                'the lowest estimate. Forbes prints Atlanta at $16 million and Washington at $18 million, so Atlanta '
                'is alone at the bottom of the Forbes revenue column.'
            ),
        },
        {
            'q': 'What is the franchise value multiple on this page?',
            'a': (
                f'The FCB multiple is the May 7, 2026 Forbes value divided by the Playbook 2025 revenue estimate, '
                f'rounded half up to one decimal. Atlanta is {mult(atlanta["value_to_revenue_multiple"])}. '
                f'Golden State is {mult(golden["value_to_revenue_multiple"])}. '
                f'Washington is {mult(washington["value_to_revenue_multiple"])} on that formula. '
                'The Playbook graphic prints Washington at 15.6x, which matches Forbes value divided by Forbes revenue ($280 million / $18 million), not by the $16 million in the same graphic.'
            ),
        },
        {
            'q': 'Why can a lower-revenue team show a higher multiple?',
            'a': (
                'A higher multiple means the valuation is a larger number of times last season\'s estimated revenue. '
                'It does not mean the business is stronger. Forbes valued the league at 12.5 times average 2025 regular-season revenue and Golden State at about 10 times, and wrote that some bankers were cautious about paying a premium for a new revenue base. '
                'Buyers can still price a lower-revenue club for growth, a scarce seat, or a move into a larger building. That reading is FCB analysis of the spread, not a claim Forbes or Playbook made about Atlanta or Washington.'
            ),
        },
        {
            'q': 'Do Forbes and Playbook use the same 2025 revenue?',
            'a': (
                'For 11 of the 13 teams, yes. They differ for the Indiana Fever (Playbook $56 million, Forbes $58 million) '
                'and the Washington Mystics (Playbook $16 million, Forbes $18 million). '
                'The graphic\'s 10.0x for Indiana and 15.6x for Washington match the Forbes revenue, not the Playbook revenue printed in the same row.'
            ),
        },
        {
            'q': 'Are the Portland Fire and Toronto Tempo in this dataset?',
            'a': (
                'No. Forbes left both out of the May 7, 2026 ranking because they begin play in the 2026 season. '
                'The Playbook graphic is the 13 teams that played in 2025. Cleveland, Detroit, and Philadelphia, which Forbes said begin play in 2028, 2029, and 2030, are out too. '
                'A FOX59 table that lists Portland and Toronto, and Golden State at $1 billion, does not match the Forbes cards and is not used.'
            ),
        },
        {
            'q': 'How current are these figures?',
            'a': (
                'Revenue is a 2025 season estimate. Forbes values are from the ranking dated May 7, 2026. '
                'This page was updated Oct. 31, 2026, during the WNBA Finals. It does not include 2026 season revenue.'
            ),
        },
    ]


def faq_html(items: list[dict]) -> str:
    blocks = []
    for item in items:
        blocks.append(f'<h3>{esc(item["q"])}</h3><p>{esc(item["a"])}</p>')
    return ''.join(blocks)


def faq_jsonld(items: list[dict]) -> dict:
    return {
        '@type': 'FAQPage',
        '@id': BASE + ROUTE + '#faq',
        'mainEntity': [
            {
                '@type': 'Question',
                'name': item['q'],
                'acceptedAnswer': {'@type': 'Answer', 'text': item['a']},
            }
            for item in items
        ],
    }


def citation_text() -> str:
    return (
        'Full Court Buckets, "WNBA team revenue and franchise value multiples," updated Oct. 31, 2026, '
        f'{BASE}{ROUTE}. 2025 revenue: Playbook Strategies, WNBA Market Intelligence 2026, graphic posted by '
        f'Katherine Rowe, Oct. 31, 2026, {PLAYBOOK_POST}. Franchise values: Brett Knight, "The WNBA\'s Most '
        f'Valuable Teams 2026," Forbes, May 7, 2026, {FORBES_US}. Team cards checked against the Forbes Mexico '
        f'translation, {FORBES_MX}. Multiples: Full Court Buckets calculation, Forbes value divided by Playbook revenue.'
    )


def json_script(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False).replace('<', '\\u003c')
    return f'<script type="application/ld+json">{raw}</script>'


def gap_html(teams: list[dict]) -> str:
    ordered = by_revenue(teams)
    top, bottom = ordered[:3], ordered[-3:]
    top_rev = sum(team['2025_revenue_usd_m'] for team in top)
    bottom_rev = sum(team['2025_revenue_usd_m'] for team in bottom)
    total = sum(team['2025_revenue_usd_m'] for team in teams)
    top_share = (Decimal(top_rev) / Decimal(total) * 100).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
    bottom_share = (Decimal(bottom_rev) / Decimal(total) * 100).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
    group_ratio = (Decimal(top_rev) / Decimal(bottom_rev)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
    top_names = ', '.join(team_link(team) for team in top)
    bottom_names = ', '.join(team_link(team) for team in bottom)
    return (
        f'<p>With 13 teams, the closest whole count to a quartile is three. The top three by Playbook revenue are {top_names}. '
        f'They combine for {money(top_rev)} of the {money(total)} Playbook total, {top_share} percent. '
        f'The bottom three are {bottom_names}, combining for {money(bottom_rev)}, {bottom_share} percent. '
        f'The top group is {group_ratio} times the bottom group.</p>'
        '<p>Game 7 is the cleanest single gap. Golden State at $78 million against Atlanta at $16 million is 4.875 times, nearly 5 times, and a $62 million difference. '
        'The Forbes values are $780 million and $250 million, 3.12 times, a $530 million difference. '
        'Washington shares Atlanta\'s $16 million Playbook revenue but not its value. Washington is $280 million, so the FCB multiple is 17.5x, above Atlanta\'s 15.6x. '
        'On the Forbes revenue column Washington is $18 million, and Atlanta is the only team at $16 million.</p>'
    )


def sources_html(sources: list[dict]) -> str:
    items = []
    for source in sources:
        bits = [f'<strong>{esc(source["publisher"])}.</strong> ']
        if source.get('author'):
            bits.append(esc(source['author']) + ', ')
        bits.append(source_link(source['url'], source['title']))
        if source.get('date'):
            bits.append(f' ({esc(source["date"])})')
        bits.append('. ' + esc(source.get('role') or ''))
        if source.get('report_url'):
            bits.append(' Report page: ' + source_link(source['report_url'], 'Playbook Strategies'))
            bits.append('.')
        bits.append(' ' + esc(source.get('notes') or ''))
        items.append('<li>' + ''.join(bits) + '</li>')
    return '<ul>' + ''.join(items) + '</ul>'


def missing_html(rows: list[dict]) -> str:
    body = []
    for row in rows:
        body.append(
            '<tr>'
            f'<td><a href="{esc(row["team_page"])}">{esc(row["team"])}</a></td>'
            f'<td>{esc(row["market"])}</td>'
            '<td>Not in the source set</td>'
            f'<td>{esc(row["reason"])}</td>'
            '</tr>'
        )
    return (
        '<div class="table-wrap wide"><table class="audience-table wide">'
        '<caption>Expansion teams Forbes and the Playbook graphic did not value on this basis.</caption>'
        '<thead><tr><th scope="col">Team</th><th scope="col">Market</th><th scope="col">2025 revenue and Forbes 2026 value</th><th scope="col">Why</th></tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>'
    )


def nav_html() -> str:
    items = ''.join(f'<li><a href="#{anchor}">{esc(label)}</a></li>' for anchor, label in NAV)
    options = ''.join(f'<option value="#{anchor}">{esc(label)}</option>' for anchor, label in NAV)
    cite = esc(citation_text())
    return (
        '<div class="data-nav"><nav class="contents-rail" aria-label="On this page"><p class="contents-label">On this page</p>'
        f'<ul>{items}</ul>'
        '<div class="data-actions">'
        f'<a class="button primary" href="{CSV_NAME}" download>Download CSV</a>'
        f'<a class="button" href="{JSON_NAME}" download>Download JSON</a>'
        f'<button class="button copy-citation" type="button" data-copy="{cite}">Copy citation</button>'
        '</div></nav>'
        f'<div class="on-page-mobile"><label for="on-this-page">On this page</label>'
        f'<select id="on-this-page"><option value="">On this page</option>{options}</select></div></div>'
    )


def render_page(payload: dict) -> str:
    teams = payload['teams']
    summary = payload['fcb_checks']
    items = faq_items(teams)
    graph = {
        '@context': 'https://schema.org',
        '@graph': [
            {
                '@type': 'WebPage',
                '@id': BASE + ROUTE + '#webpage',
                'name': H1,
                'headline': H1,
                'url': BASE + ROUTE,
                'description': DESCRIPTION,
                'datePublished': '2026-10-31',
                'dateModified': '2026-10-31',
                'author': {'@type': 'Person', 'name': 'Ryan Moalemi', 'url': BASE + '/authors/ryan-moalemi/'},
                'isPartOf': {'@type': 'WebSite', 'name': 'Full Court Buckets', 'url': BASE + '/'},
            },
            {
                '@type': 'Dataset',
                'name': 'WNBA team revenue and franchise value multiples, 2025 revenue and 2026 Forbes values',
                'description': payload['multiple_definition'],
                'url': BASE + ROUTE,
                'creator': {'@type': 'Organization', 'name': 'Full Court Buckets', 'url': BASE + '/'},
                'license': 'https://creativecommons.org/publicdomain/zero/1.0/',
                'isAccessibleForFree': True,
                'temporalCoverage': '2025/2026',
                'dateModified': '2026-10-31',
                'distribution': [
                    {'@type': 'DataDownload', 'encodingFormat': 'text/csv', 'contentUrl': BASE + ROUTE + CSV_NAME},
                    {'@type': 'DataDownload', 'encodingFormat': 'application/json', 'contentUrl': BASE + ROUTE + JSON_NAME},
                ],
            },
            faq_jsonld(items),
        ],
    }
    yoy_note = 'Golden State has no one-year change because Forbes did not rank the team in 2025.'
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(PAGE_TITLE)}</title>
<meta name="description" content="{esc(DESCRIPTION)}">
<meta name="author" content="Ryan Moalemi">
<meta name="robots" content="index, follow">
<link rel="canonical" href="{BASE}{ROUTE}">
<meta name="theme-color" content="#ffffff">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<meta property="og:title" content="{esc(PAGE_TITLE)}">
<meta property="og:description" content="{esc(DESCRIPTION)}">
<meta property="og:url" content="{BASE}{ROUTE}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Full Court Buckets">
<meta property="og:image" content="{BASE}{ROUTE}{OG_NAME}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Golden State $78 million revenue at 10.0 times value. Atlanta $16 million at 15.6 times. Full Court Buckets.">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:site" content="@fullcourtbucket">
<meta name="twitter:title" content="{esc(PAGE_TITLE)}">
<meta name="twitter:description" content="{esc(DESCRIPTION)}">
<meta name="twitter:image" content="{BASE}{ROUTE}{OG_NAME}">
<meta name="twitter:image:alt" content="Golden State $78 million revenue at 10.0 times value. Atlanta $16 million at 15.6 times. Full Court Buckets.">
{GA4_TAG}
{ADSENSE_TAG}
<link rel="stylesheet" href="/assets/site-nav.css">
<style>
{links.BYLINE_CSS}
{EXTRA_CSS}
</style>
{json_script(graph)}
</head>
<body>
<header></header>
<main class="page">
<div class="standings-shell">
<div class="page-header">
<p class="eyebrow">WNBA / Data and research</p>
<h1>{esc(H1)}</h1>
<div class="byline-row article">{links.BYLINE_HTML}<span class="byline-sep" aria-hidden="true">|</span><time class="article-date" datetime="2026-10-31"><span data-fcb-dynamic="page-updated" data-fcb-source="{DATA_FILE}" data-fcb-updated="2026-10-31">Updated Oct. 31, 2026</span></time></div>
<p class="answer">Game 7 of the 2026 WNBA Finals pairs Playbook Strategies' highest 2025 revenue estimate with one of its two lowest. The <a href="/wnba/teams/golden-state-valkyries/">Golden State Valkyries</a> are at $78 million. The <a href="/wnba/teams/atlanta-dream/">Atlanta Dream</a> are at $16 million, tied with the <a href="/wnba/teams/washington-mystics/">Washington Mystics</a>. Golden State's estimate is 4.875 times Atlanta's, nearly 5 times. Using <a href="{FORBES_US}">Forbes' May 7, 2026 values</a>, Atlanta's franchise value is 15.6 times that Playbook revenue and Golden State's is 10.0 times.</p>
<p class="answer">Those FCB multiples use one valuation column, the Forbes cards, and one revenue column, the <a href="{PLAYBOOK_POST}">Oct. 31, 2026 Playbook graphic</a> posted by Katherine Rowe. They match the graphic for 11 of 13 teams. They do not match for Indiana (FCB 10.4x, graphic 10.0x) or Washington (FCB 17.5x, graphic 15.6x). Playbook's revenue for those two teams differs from the revenue Forbes printed, and the graphic's multiples match the Forbes revenue.</p>
</div>
<section class="key-stats" aria-label="Key revenue and multiple figures">
<h2>Key figures</h2>
<ul class="key-list">
<li class="stat-card"><p class="stat-value">$78M</p><p class="stat-label">Highest 2025 revenue</p><p class="stat-period">Golden State, Playbook and Forbes</p><p class="stat-meta">Excludes playoffs | <a href="{PLAYBOOK_POST}">Katherine Rowe / Playbook</a></p></li>
<li class="stat-card"><p class="stat-value">$16M</p><p class="stat-label">Lowest Playbook revenue, tied</p><p class="stat-period">Atlanta and Washington</p><p class="stat-meta">Forbes prints Washington at $18M, so Atlanta is alone at $16M on that column</p></li>
<li class="stat-card"><p class="stat-value">4.9x</p><p class="stat-label">Finals revenue gap</p><p class="stat-period">$78M / $16M = 4.875</p><p class="stat-meta"><a href="/news/finals-game-7-preview-dream-valkyries/">Game 7 preview</a></p></li>
<li class="stat-card"><p class="stat-value">15.6x</p><p class="stat-label">Atlanta value / Playbook revenue</p><p class="stat-period">Golden State is 10.0x on the same formula</p><p class="stat-meta">$250M / $16M and $780M / $78M</p></li>
</ul>
</section>
<div class="data-layout">
{nav_html()}
<div class="data-main">
<section class="qa" id="revenue">
<h2>2025 revenue</h2>
<p class="answer">Playbook's public graphic ranks the 13 teams that played in 2025. The bars below use that column. Pink marks the Finals clubs.</p>
<figure class="chart-figure">{revenue_bar(teams)}<figcaption>Playbook Strategies 2025 revenue estimates, millions of dollars. Playoffs excluded. Source: <a href="{PLAYBOOK_POST}">Katherine Rowe, Oct. 31, 2026</a>.</figcaption></figure>
</section>
<section class="qa" id="multiples">
<h2>Value against revenue</h2>
<p class="answer">Each point is a Forbes May 7, 2026 value plotted on the Playbook revenue. Pink is the Finals. Orange is a team whose Playbook revenue differs from Forbes (Indiana and Washington).</p>
<figure class="chart-figure">{scatter(teams)}<figcaption>Horizontal position is Playbook 2025 revenue. Vertical position is the Forbes 2026 value. The multiple is the slope from the origin to the point.</figcaption></figure>
</section>
<section class="qa" id="table">
<h2>Full table</h2>
<p class="scroll-hint">Swipe to see more.</p>
<p class="note">Sorted in the order of the Playbook graphic. Click a column heading to resort this table in the browser. "Graphic multiple" is the figure printed on that graphic. "FCB multiple" is Forbes value divided by the Playbook revenue in this row. A "differs" tag means those two are not the same number.</p>
<div class="table-wrap wide">
<table class="audience-table wide" id="revenue-table" data-sortable>
<caption>13 WNBA teams that played in 2025. Revenue in millions of dollars. Values are the Forbes May 7, 2026 cards.</caption>
<thead><tr>
<th scope="col"><button type="button" data-sort="0" data-type="text">Team</button></th>
<th scope="col"><button type="button" data-sort="1" data-type="text">Market</button></th>
<th scope="col"><button type="button" data-sort="2" data-type="num">Playbook revenue</button></th>
<th scope="col"><button type="button" data-sort="3" data-type="num">Forbes revenue</button></th>
<th scope="col"><button type="button" data-sort="4" data-type="num">Forbes value</button></th>
<th scope="col"><button type="button" data-sort="5" data-type="num">Forbes rank</button></th>
<th scope="col"><button type="button" data-sort="6" data-type="num">Value change</button></th>
<th scope="col"><button type="button" data-sort="7" data-type="num">FCB multiple</button></th>
<th scope="col"><button type="button" data-sort="8" data-type="num">Graphic multiple</button></th>
</tr></thead>
<tbody>{master_rows(teams)}</tbody>
</table>
</div>
<p class="note">{esc(yoy_note)} Ownership and arena for each club are in the download. Arena names are the WNBA.com strings in FCB team facts checked Oct. 28, 2026. They are context, not part of the valuation math.</p>
</section>
<section class="qa" id="by-value">
<h2>Ranked by Forbes value</h2>
{compact_table(by_value(teams), 'forbes_rank', 'Forbes rank', lambda team: str(team['forbes_rank']))}
<p class="note">The 13 values sum to $5,385 million. Divided by 13, that is ${summary['forbes_value_average_usd_m']} million, in line with the $414 million average Forbes stated, and about $5.4 billion combined. Divided by the $430 million sum of the Forbes revenue cards, the league multiple is {summary['league_multiple_on_forbes_revenue']} times, which rounds to the 12.5 times Forbes stated for average 2025 regular-season revenue.</p>
</section>
<section class="qa" id="by-multiple">
<h2>Ranked by FCB multiple</h2>
{compact_table(by_multiple(teams), 'value_to_revenue_multiple', 'FCB multiple', lambda team: mult(team['value_to_revenue_multiple']))}
<p class="note">Washington leads this ranking at 17.5x because the formula uses Playbook's $16 million, not Forbes' $18 million. The graphic prints Washington at 15.6x, the same mark as Atlanta, which is $280 million divided by $18 million.</p>
</section>
<section class="qa" id="gap">
<h2>Where the gap is</h2>
{gap_html(teams)}
<p class="note">Related FCB pages: <a href="/wnba/viewership-attendance/">viewership and attendance</a>, <a href="/news/2026-wnba-finals-ratings-tracker/">2026 Finals ratings tracker</a>, <a href="/news/finals-game-7-preview-dream-valkyries/">Game 7 preview</a>, <a href="/news/wnba-finals-2026-schedule-dream-valkyries/">Finals schedule</a>, <a href="/news/wnba-expansion-teams/">expansion teams</a>, <a href="/wnba/owners/">owner index</a>.</p>
</section>
<section class="qa" id="reading">
<h2>Reading the multiple</h2>
<p>This section is FCB analysis of the spread. It is not a Forbes or Playbook finding about a named team.</p>
<p>A 15.6x club has not been shown to be a better business than a 10.0x club. The multiple says the May 2026 valuation is that many times the 2025 revenue estimate. Forbes applied about 10 times revenue to Golden State and about 12.5 times average revenue to the league. The article said bankers and investors were cautious about paying a premium for a franchise whose revenue is new, even while calling that revenue real.</p>
<p>Lower-revenue teams can still print higher multiples when a buyer is pricing growth, scarcity, or a building the club does not fully use yet. Atlanta's home arena on the WNBA.com listing is Gateway Center Arena. Golden State plays at Chase Center. The revenue gap and the multiple gap can describe the same building constraint from opposite sides: a small revenue base, and a price that assumes the base will not stay that small. Connecticut is the sale closest to these cards. Forbes reported an agreement for about $300 million, the same number as the Sun's Forbes value, with plans to move the team to Houston.</p>
<p>Sportico's separate May 2026 model is not in the value column. It puts Golden State at $850 million, the league average at $427 million, and the 13 teams at $5.55 billion including real estate. Sportico's league revenue estimate for those clubs is $410 million, against $426 million on the Playbook cards and $430 million on the Forbes cards. CNBC's $1 billion Golden State value uses a 15-team set. None of those replace the Forbes cards in this file.</p>
</section>
<section class="qa" id="not-included">
<h2>Not in the source set</h2>
<p>{esc(payload.get('rejected_note') or '')}</p>
{missing_html(payload['not_in_source_set'])}
</section>
<section class="qa" id="methods">
<h2>Methods</h2>
<p>{esc(payload['revenue_definition'])}</p>
<p>{esc(payload['valuation_definition'])}</p>
<p>{esc(payload['multiple_definition'])}</p>
<p>{esc(payload['timing_note'])}</p>
<p>The English Forbes article did not return the team table to a client without JavaScript on Oct. 31, 2026. Every value, Forbes revenue, one-year change, and owner line was read from the Forbes Mexico translation of the same May 7, 2026 article, which prints the 13 cards and says the text was first published by Forbes US. Grey Journal's Oct. 23, 2026 table matches those cards, including a complete Atlanta row at $250 million, $16 million, and a 32 percent one-year change. Grey Journal conflicts with Playbook on Fever revenue ($58 million vs $56 million) and Mystics revenue ($18 million vs $16 million). It does not conflict with the Forbes prose that names the Fever at $58 million.</p>
<p>Seattle's graphic multiple is recorded as 15.4x. That is the bar on the Oct. 31, 2026 graphic, and it is also $430 million divided by $28 million. Phoenix and Minnesota print at 15.2x. A short grouping of the same post put Seattle with the 15.2x clubs. This file keeps 15.4x.</p>
<p>{esc(payload.get('arena_note') or '')}</p>
<p>The download is the FCB dataset: both revenue columns, the Forbes value, the FCB multiple, and the graphic multiple. License: <a href="https://creativecommons.org/publicdomain/zero/1.0/">CC0</a>. Checked Oct. 31, 2026.</p>
<p class="how-made">How the pages on this site are made: <a href="/how-we-make-full-court-buckets/">How we make Full Court Buckets</a>.</p>
</section>
<section class="qa" id="sources">
<h2>Sources</h2>
{sources_html(payload['sources'])}
<p class="cite">{esc(citation_text())}</p>
</section>
<section class="qa" id="faq">
<h2>FAQ</h2>
{faq_html(items)}
</section>
</div>
</div>
</div>
</main>
<script>
document.querySelectorAll('.copy-citation').forEach(function(btn) {{
  btn.addEventListener('click', function() {{
    var text = btn.getAttribute('data-copy') || '';
    var done = function() {{
      var old = btn.textContent;
      btn.textContent = 'Copied';
      setTimeout(function() {{ btn.textContent = old; }}, 1500);
    }};
    if (navigator.clipboard && navigator.clipboard.writeText) {{
      navigator.clipboard.writeText(text).then(done);
    }}
  }});
}});
var jump = document.getElementById('on-this-page');
if (jump) jump.addEventListener('change', function() {{
  if (jump.value) location.hash = jump.value;
}});
document.querySelectorAll('table[data-sortable] th button').forEach(function(btn) {{
  btn.addEventListener('click', function() {{
    var table = btn.closest('table');
    var body = table.tBodies[0];
    var index = Number(btn.getAttribute('data-sort'));
    var type = btn.getAttribute('data-type');
    var dir = btn.getAttribute('data-dir') === 'asc' ? 'desc' : 'asc';
    table.querySelectorAll('th button').forEach(function(other) {{ other.removeAttribute('data-dir'); }});
    btn.setAttribute('data-dir', dir);
    var rows = Array.prototype.slice.call(body.rows);
    rows.sort(function(a, b) {{
      var av = a.cells[index].getAttribute('data-value') || '';
      var bv = b.cells[index].getAttribute('data-value') || '';
      if (type === 'num') {{ av = Number(av); bv = Number(bv); }}
      if (av < bv) return dir === 'asc' ? -1 : 1;
      if (av > bv) return dir === 'asc' ? 1 : -1;
      return 0;
    }});
    rows.forEach(function(row) {{ body.appendChild(row); }});
  }});
}});
</script>
</body>
</html>
'''


EXTRA_CSS = """
.page{padding:28px 0 72px}
.standings-shell{width:min(1100px,calc(100% - 32px));margin:0 auto;min-width:0;max-width:100%}
.eyebrow{margin:0 0 8px;color:#b8006f;font:800 12px/1.2 Inter,system-ui,sans-serif;letter-spacing:.08em;text-transform:uppercase}
h1{margin:0 0 8px;font:800 clamp(32px,4vw,48px)/1.12 "Barlow",sans-serif;letter-spacing:-.4px;max-width:18em}
.answer,.qa p,.qa li,.cite,.note,.how-made,figcaption{overflow-wrap:anywhere}
.answer{max-width:68ch;margin:0 0 12px;font-size:17px;line-height:1.6}
.byline-row{display:flex;align-items:center;gap:10px 12px;margin:8px 0 16px;flex-wrap:wrap}
.byline-sep{color:#6f6a64}
.key-list{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:0;padding:0;list-style:none}
.stat-card{margin:0;padding:16px;border:1px solid var(--line,#e2ddd6);background:#fff}
.stat-value{margin:0;font:800 36px/1 "Barlow",sans-serif}
.stat-label,.stat-period,.stat-meta{margin:6px 0 0;font-size:14px;line-height:1.4}
.stat-meta{color:#5a554e}
.data-layout{margin-top:28px}
.contents-rail{display:none}
.contents-label{margin:0 0 8px;font:800 12px/1 "Barlow",sans-serif;letter-spacing:.12em;text-transform:uppercase;color:#5a554e}
.contents-rail ul,.on-page-mobile{margin:0;padding:0;list-style:none}
.contents-rail a{display:inline-flex;align-items:center;min-height:36px;font-weight:700}
.data-actions{display:flex;flex-direction:column;align-items:flex-start;gap:8px;margin-top:12px}
.button{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:0 14px;border:1px solid #5b22c9;border-radius:3px;background:#fff;color:#5b22c9;font:700 14px/1 Inter,system-ui,sans-serif;text-decoration:none;cursor:pointer}
.button.primary{background:#5b22c9;color:#fff}
.on-page-mobile label{display:block;font-weight:700}
.on-page-mobile select{display:block;width:100%;min-height:44px;margin-top:6px}
.qa{margin-top:40px}
.qa h2{margin:0 0 10px;font:800 clamp(24px,3vw,32px)/1.15 "Barlow",sans-serif}
.qa h3{margin:16px 0 6px;font:700 18px/1.3 "Barlow",sans-serif}
.qa p,.qa li{max-width:68ch;font-size:16px;line-height:1.6}
.chart-figure{margin:0 0 8px;max-width:720px}
.chart{display:block;width:100%;height:auto;max-width:100%;background:#fff;border:1px solid var(--line,#e2ddd6);overflow:hidden}
.chart.scatter{max-height:none}
figcaption,.note,.how-made{max-width:68ch;color:#5a554e;font-size:14px;line-height:1.55}
.data-main,.qa{min-width:0;max-width:100%}
.table-wrap.wide{overflow-x:auto;max-width:100%;-webkit-overflow-scrolling:touch}
.audience-table{width:100%;border-collapse:collapse}
.audience-table th,.audience-table td{padding:10px 8px;border-bottom:1px solid var(--line,#e2ddd6);text-align:left;vertical-align:top}
.audience-table th button{min-height:44px;padding:0;border:0;background:transparent;font:700 13px/1.3 Inter,system-ui,sans-serif;color:#45413b;cursor:pointer;text-align:left}
.audience-table .num{text-align:right;font-variant-numeric:tabular-nums}
.audience-table caption{caption-side:bottom;padding-top:8px;text-align:left;color:#5a554e;font-size:13px}
.flag{color:#a85400;font-size:12px;font-weight:700}
.cite{margin-top:12px;padding:12px 14px;border-left:3px solid #5b22c9}
.scroll-hint{display:none;color:#5a554e}
@media(max-width:900px){
.key-list{grid-template-columns:1fr 1fr}
.scroll-hint{display:block}
}
@media(max-width:520px){.key-list{grid-template-columns:1fr}}
@media(min-width:1100px){
.data-layout{display:grid;grid-template-columns:180px minmax(0,1fr);column-gap:28px;align-items:start}
.data-nav{position:sticky;top:80px}
.contents-rail{display:block}
.on-page-mobile{display:none}
}
"""


def csv_rows(payload: dict) -> list[dict]:
    rows = []
    for team in payload['teams']:
        rows.append({key: blank(team.get(key)) for key in CSV_FIELDS})
    for row in payload['not_in_source_set']:
        item = {key: '' for key in CSV_FIELDS}
        item.update({
            'team': row['team'],
            'market': row['market'],
            'team_page': row['team_page'],
            'in_source_set': False,
            'revenue_notes': row['reason'],
            'revenue_source': 'Not in the source set',
        })
        rows.append(item)
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_share_image(path: Path) -> None:
    if path.is_file():
        return
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise ValueError('Share image is missing and Pillow is not installed.')
    image = Image.new('RGB', (1200, 630), '#f7f5f2')
    draw = ImageDraw.Draw(image)
    font_dir = ROOT / 'assets' / 'fonts'
    bold = ImageFont.truetype(str(font_dir / 'Inter-Bold.ttf'), 54)
    med = ImageFont.truetype(str(font_dir / 'Inter-Medium.ttf'), 32)
    small = ImageFont.truetype(str(font_dir / 'Inter-Medium.ttf'), 24)
    draw.rectangle((0, 0, 1200, 12), fill='#5b22c9')
    draw.text((64, 56), 'WNBA revenue and', font=bold, fill='#2a1458')
    draw.text((64, 124), 'franchise multiples', font=bold, fill='#2a1458')
    draw.text((64, 230), 'Golden State  $78M   10.0x', font=med, fill='#151413')
    draw.text((64, 286), 'Atlanta and Washington  $16M', font=med, fill='#151413')
    draw.text((64, 342), 'Atlanta 15.6x on the Forbes value', font=med, fill='#b8006f')
    draw.text((64, 540), 'Full Court Buckets. 2025 revenue, May 2026 values.', font=small, fill='#5a554e')
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, 'PNG')


def update_sitemaps(root: Path) -> None:
    canonical = BASE + ROUTE
    pages = root / 'pages-sitemap.xml'
    text = pages.read_text(encoding='utf-8')
    if f'<loc>{canonical}</loc>' not in text:
        entry = (
            '  <url>\n'
            f'    <loc>{canonical}</loc>\n'
            '    <lastmod>2026-10-31</lastmod>\n'
            '  </url>\n'
        )
        pages.write_text(text.replace('</urlset>', entry + '</urlset>', 1), encoding='utf-8')
    html_map = root / 'sitemap' / 'index.html'
    page = html_map.read_text(encoding='utf-8')
    href = f'href="{ROUTE}"'
    if href not in page:
        marker = '<li><a href="/wnba/viewership-attendance/">WNBA viewership and attendance</a></li>'
        if marker not in page:
            raise ValueError('HTML sitemap is missing the viewership link this page should follow.')
        insert = marker + '<li><a href="/wnba/team-revenue/">WNBA team revenue and franchise values</a></li>'
        html_map.write_text(page.replace(marker, insert, 1), encoding='utf-8')


def public_payload(payload: dict) -> dict:
    """Drop builder-only flags from the download without dropping the columns."""
    data = json.loads(json.dumps(payload))
    for team in data['teams']:
        team.pop('playbook_order', None)
        team.pop('graphic_matches_fcb', None)
    return data


def build(root: Path) -> None:
    path = root / DATA_FILE
    payload = load(path)
    validate(payload)
    payload = enrich(payload)
    validate(payload)
    if EM_DASH in json.dumps(payload) or EN_DASH in json.dumps(payload):
        raise ValueError('Enriched dataset contains a dash the style guide does not allow.')
    page_dir = root / 'wnba' / 'team-revenue'
    page_dir.mkdir(parents=True, exist_ok=True)
    rendered = render_page(payload)
    if EM_DASH in rendered or EN_DASH in rendered:
        raise ValueError('Page copy contains a dash the style guide does not allow.')
    if 'ESPN data' in rendered or 'per ESPN' in rendered or 'Source: ESPN' in rendered:
        raise ValueError('Page credits an ESPN stats feed.')
    rendered = site_nav.install(rendered, ROUTE, site_nav.build_menu(root))
    rendered = seo_meta.apply_rel(rendered, ROUTE, root)
    rendered = breadcrumbs.fix(rendered, ROUTE, root)
    if EM_DASH in rendered or EN_DASH in rendered:
        raise ValueError('Installed page contains a dash the style guide does not allow.')
    (page_dir / 'index.html').write_text(rendered, encoding='utf-8')
    write_csv(page_dir / CSV_NAME, csv_rows(payload))
    (page_dir / JSON_NAME).write_text(
        json.dumps(public_payload(payload), indent=2, ensure_ascii=False) + '\n',
        encoding='utf-8',
    )
    write_share_image(page_dir / OG_NAME)
    # Keep the source file aligned with the calculated multiples.
    path.write_text(json.dumps(public_payload(payload), indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    update_sitemaps(root)
    upsert_search(root)
    print(f'Wrote wnba/team-revenue/index.html from {DATA_FILE}.')


def upsert_search(root: Path) -> None:
    """Add this page to the search index without regenerating every other entry."""
    page = (root / 'wnba' / 'team-revenue' / 'index.html').read_text(encoding='utf-8')
    entry = search_index.page_entry(root, 'wnba/team-revenue/index.html', page, set())
    if not entry:
        raise ValueError('Search index could not read the revenue page.')
    path = root / 'search-index.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    data['items'] = [item for item in data['items'] if item.get('u') != ROUTE]
    data['items'].append(entry)
    rank = {kind: index for index, kind in enumerate(search_index.TYPE_ORDER)}
    data['items'].sort(key=lambda item: (rank.get(item.get('k'), 99), item.get('t', '').casefold()))
    text = json.dumps(data, separators=(',', ':'), ensure_ascii=False) + '\n'
    if path.read_text(encoding='utf-8') != text:
        path.write_text(text, encoding='utf-8')


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
