#!/usr/bin/env python3
"""Build /wnba/team-revenue/ from data/wnba-team-revenue-2025.json.

Displayed multiples use Forbes' May 7, 2026 values divided by Forbes' 2025
revenue estimates. The same-12 comparison uses the June 6, 2025 Forbes list
for the 12 franchises that were ranked in both editions. Golden State is
excluded from those totals.
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
PAGE_TITLE = 'WNBA Franchise Values in 2026 and 2025 Revenue by Team'
H1 = 'WNBA franchise values in 2026 and revenue by team'
DESCRIPTION = (
    'Compare 2026 WNBA franchise values and 2025 revenue estimates for 13 teams. '
    'FCB tracks how revenue and valuations changed for the same 12 franchises.'
)
CSV_NAME = 'wnba-team-revenue-2025.csv'
JSON_NAME = 'wnba-team-revenue-2025.json'
OG_NAME = 'share-revenue-multiples.png'
ADSENSE_TAG = (
    '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js'
    '?client=ca-pub-6621195315204235" crossorigin="anonymous"></script>'
)
FORBES_2026 = 'https://www.forbes.com/sites/brettknight/2026/05/07/the-wnbas-most-valuable-teams-2026/'
FORBES_2025 = 'https://www.forbes.com/sites/brettknight/2025/06/06/the-wnbas-most-valuable-teams-2025/'
FORBES_MX = 'https://forbes.com.mx/estos-son-los-equipos-mas-valiosos-de-la-wnba-en-2026/'
EM_DASH = '\u2014'
EN_DASH = '\u2013'
TIMES = '\u00d7'
REQUIRED = (
    'team', 'slug', 'abbr', 'market', 'forbes_2026_value_usd_m', 'forbes_2026_rank',
    'revenue_2025_usd_m', 'forbes_2026_source_url', 'forbes_2026_date',
    'forbes_2025_source_url', 'forbes_2025_date', 'team_page', 'ownership', 'arena',
)
CSV_FIELDS = (
    'team', 'market', 'team_page', 'in_forbes_2026', 'in_same_12',
    'forbes_2026_value_usd_m', 'revenue_2025_usd_m', 'value_per_revenue_2026',
    'forbes_2025_value_usd_m', 'revenue_2024_usd_m', 'value_per_revenue_2025',
    'forbes_2026_rank', 'forbes_2025_rank', 'value_change_pct',
    'forbes_2026_source_url', 'forbes_2026_date',
    'forbes_2025_source_url', 'forbes_2025_date',
    'ownership', 'arena', 'notes',
)
NAV = (
    ('teams', '13 teams'),
    ('same-12-teams', 'Same 12 teams'),
    ('four-teams', 'Four teams at $28 million'),
    ('methods', 'Methods'),
    ('sources', 'Sources'),
)


def esc(value) -> str:
    return html.escape('' if value is None else str(value), quote=True)


def quant(value, places: str) -> Decimal:
    return Decimal(value).quantize(Decimal(places), rounding=ROUND_HALF_UP)


def multiple(value, revenue) -> float:
    return float(quant(Decimal(value) / Decimal(revenue), '0.1'))


def multiple2(value, revenue) -> float:
    return float(quant(Decimal(value) / Decimal(revenue), '0.01'))


def percent(new, old) -> float:
    return float(quant((Decimal(new) - Decimal(old)) / Decimal(old) * 100, '0.1'))


def whole_percent(new, old) -> int:
    return int(quant((Decimal(new) - Decimal(old)) / Decimal(old) * 100, '1'))


def money(millions) -> str:
    return f'${int(millions)} million'


def money_short(millions) -> str:
    return f'${int(millions)}M'


def billions(millions) -> str:
    return f'${Decimal(millions) / Decimal(1000):.3f}B'


def mult(value) -> str:
    return f'{value:.1f}{TIMES}'


def mult2(value) -> str:
    return f'{value:.2f}{TIMES}'


def blank(value) -> str:
    return '' if value is None else value


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def same_twelve(teams: list[dict]) -> list[dict]:
    return [team for team in teams if team.get('forbes_2025_value_usd_m') is not None]


def summarize(teams: list[dict]) -> dict:
    twelve = same_twelve(teams)
    value_2026 = sum(team['forbes_2026_value_usd_m'] for team in teams)
    revenue_2025 = sum(team['revenue_2025_usd_m'] for team in teams)
    value_2026_12 = sum(team['forbes_2026_value_usd_m'] for team in twelve)
    value_2025_12 = sum(team['forbes_2025_value_usd_m'] for team in twelve)
    revenue_2025_12 = sum(team['revenue_2025_usd_m'] for team in twelve)
    revenue_2024_12 = sum(team['revenue_2024_usd_m'] for team in twelve)
    ratio_2025 = multiple2(value_2025_12, revenue_2024_12)
    ratio_2026 = multiple2(value_2026_12, revenue_2025_12)
    return {
        'team_count_2026': len(teams),
        'team_count_same_12': len(twelve),
        'forbes_2026_value_sum_usd_m': value_2026,
        'revenue_2025_sum_usd_m': revenue_2025,
        'league_multiple': multiple2(value_2026, revenue_2025),
        'same_12_value_2025_usd_m': value_2025_12,
        'same_12_value_2026_usd_m': value_2026_12,
        'same_12_revenue_2024_usd_m': revenue_2024_12,
        'same_12_revenue_2025_usd_m': revenue_2025_12,
        'same_12_value_change_pct': percent(value_2026_12, value_2025_12),
        'same_12_revenue_change_pct': percent(revenue_2025_12, revenue_2024_12),
        'same_12_multiple_2025': ratio_2025,
        'same_12_multiple_2026': ratio_2026,
        'same_12_multiple_change': float(quant(Decimal(str(ratio_2026)) - Decimal(str(ratio_2025)), '0.01')),
        'same_12_value_gain_usd_m': value_2026_12 - value_2025_12,
    }


def enrich(payload: dict) -> dict:
    teams = []
    for raw in payload['teams']:
        team = dict(raw)
        team['in_forbes_2026'] = True
        team['in_same_12'] = team.get('forbes_2025_value_usd_m') is not None
        team['value_per_revenue_2026'] = multiple(team['forbes_2026_value_usd_m'], team['revenue_2025_usd_m'])
        if team['in_same_12']:
            team['value_per_revenue_2025'] = multiple(team['forbes_2025_value_usd_m'], team['revenue_2024_usd_m'])
        else:
            team['value_per_revenue_2025'] = None
        teams.append(team)
    data = dict(payload)
    data['teams'] = teams
    data['fcb_checks'] = summarize(teams)
    return data


def validate(payload: dict) -> None:
    if payload.get('updated') != '2026-10-31':
        raise ValueError('Dataset updated date must be 2026-10-31.')
    if payload.get('forbes_2026_url') != FORBES_2026 or payload.get('forbes_2025_url') != FORBES_2025:
        raise ValueError('Forbes source URLs do not match the 2026 and 2025 ranking articles.')
    teams = payload.get('teams') or []
    if len(teams) != 13:
        raise ValueError('The 2026 Forbes list has 13 teams.')
    seen = set()
    for team in teams:
        for key in REQUIRED:
            if team.get(key) in (None, ''):
                raise ValueError(f'{team.get("team") or "A team"} is missing {key}.')
        if team['slug'] in seen:
            raise ValueError(f'Duplicate slug {team["slug"]}.')
        seen.add(team['slug'])
        if team['forbes_2026_source_url'] != FORBES_2026 or team['forbes_2026_date'] != '2026-05-07':
            raise ValueError(f'{team["team"]} is not cited to the May 7, 2026 Forbes article.')
        if team['forbes_2025_source_url'] != FORBES_2025 or team['forbes_2025_date'] != '2025-06-06':
            raise ValueError(f'{team["team"]} is not cited to the June 6, 2025 Forbes article.')
        if team['forbes_2026_value_usd_m'] in {850, 1000}:
            raise ValueError(f'{team["team"]} uses a Sportico or CNBC value, not the Forbes card.')
        got = multiple(team['forbes_2026_value_usd_m'], team['revenue_2025_usd_m'])
        if team.get('value_per_revenue_2026') not in (None, got):
            raise ValueError(f'{team["team"]} multiple does not match the 2026 Forbes value divided by 2025 Forbes revenue.')
        if team.get('forbes_2025_value_usd_m') is None:
            if team.get('revenue_2024_usd_m') is not None:
                raise ValueError(f'{team["team"]} has 2024 revenue without a 2025 Forbes value.')
            continue
        if team.get('revenue_2024_usd_m') is None or team.get('value_change_pct') is None:
            raise ValueError(f'{team["team"]} is missing its 2025 Forbes value change or 2024 revenue.')
        published = team['value_change_pct']
        calculated = whole_percent(team['forbes_2026_value_usd_m'], team['forbes_2025_value_usd_m'])
        if published != calculated:
            raise ValueError(f'{team["team"]} one-year change {published} does not match {calculated}.')
    enriched = enrich({'updated': payload['updated'], 'forbes_2026_url': FORBES_2026, 'forbes_2025_url': FORBES_2025, 'teams': [dict(t) for t in teams]})
    by_slug = {team['slug']: team for team in enriched['teams']}
    golden = by_slug['golden-state-valkyries']
    atlanta = by_slug['atlanta-dream']
    indiana = by_slug['indiana-fever']
    washington = by_slug['washington-mystics']
    seattle = by_slug['seattle-storm']
    if golden['forbes_2025_value_usd_m'] is not None:
        raise ValueError('Golden State was not in the 2025 Forbes ranking and cannot be in the same-12 totals.')
    if (golden['forbes_2026_value_usd_m'], golden['revenue_2025_usd_m'], golden['value_per_revenue_2026']) != (780, 78, 10.0):
        raise ValueError('Golden State must be $780 million, $78 million, and 10.0x.')
    if (atlanta['forbes_2026_value_usd_m'], atlanta['revenue_2025_usd_m'], atlanta['value_per_revenue_2026']) != (250, 16, 15.6):
        raise ValueError('Atlanta must be $250 million, $16 million, and 15.6x.')
    if (indiana['revenue_2025_usd_m'], indiana['value_per_revenue_2026']) != (58, 10.0):
        raise ValueError('Indiana Forbes revenue is $58 million and the multiple is 10.0x.')
    if (washington['revenue_2025_usd_m'], washington['value_per_revenue_2026']) != (18, 15.6):
        raise ValueError('Washington Forbes revenue is $18 million and the multiple is 15.6x.')
    if (seattle['forbes_2026_value_usd_m'], seattle['revenue_2025_usd_m'], seattle['value_per_revenue_2026']) != (430, 28, 15.4):
        raise ValueError('Seattle must be $430 million, $28 million, and 15.4x.')
    checks = enriched['fcb_checks']
    expected = {
        'forbes_2026_value_sum_usd_m': 5385,
        'revenue_2025_sum_usd_m': 430,
        'league_multiple': 12.52,
        'same_12_value_2025_usd_m': 3260,
        'same_12_value_2026_usd_m': 4605,
        'same_12_revenue_2024_usd_m': 226,
        'same_12_revenue_2025_usd_m': 352,
        'same_12_value_change_pct': 41.3,
        'same_12_revenue_change_pct': 55.8,
        'same_12_multiple_2025': 14.42,
        'same_12_multiple_2026': 13.08,
        'same_12_multiple_change': -1.34,
        'same_12_value_gain_usd_m': 1345,
        'team_count_same_12': 12,
    }
    for key, value in expected.items():
        if checks[key] != value:
            raise ValueError(f'{key} is {checks[key]}, expected {value}.')
    missing = payload.get('not_in_source_set') or []
    if {row.get('slug') for row in missing} != {'portland-fire', 'toronto-tempo'}:
        raise ValueError('Portland and Toronto are the only expansion rows.')
    for row in missing:
        if row.get('forbes_2026_value_usd_m') is not None or row.get('revenue_2025_usd_m') is not None:
            raise ValueError(f'{row.get("team")} began play in 2026 and cannot carry a 2025 revenue or a Forbes value here.')
        if 'began play in 2026' not in (row.get('reason') or ''):
            raise ValueError(f'{row.get("team")} needs a note that it began play in 2026.')
    blob = json.dumps(payload, ensure_ascii=False)
    if EM_DASH in blob or EN_DASH in blob:
        raise ValueError('Dataset copy contains a dash that the style guide does not allow.')


def team_link(team: dict, label: str | None = None) -> str:
    return f'<a href="{esc(team["team_page"])}">{esc(label or team["team"])}</a>'


def source_link(url: str, label: str) -> str:
    return f'<a href="{esc(url)}">{esc(label)}</a>'


def byline_html() -> str:
    return links.BYLINE_HTML.replace('>By Ryan Moalemi<', '>Ryan Moalemi, Full Court Buckets<')


def citation_text() -> str:
    return (
        'Full Court Buckets, "WNBA franchise values in 2026 and revenue by team," October 31, 2026, '
        f'{BASE}{ROUTE}. Franchise values and revenue estimates: Brett Knight, "The WNBA\'s Most Valuable Teams 2026," '
        f'Forbes, May 7, 2026, {FORBES_2026}; and Brett Knight, "The WNBA\'s Most Valuable Teams 2025," '
        f'Forbes, June 6, 2025, {FORBES_2025}. Multiples and the same-12 comparison: Full Court Buckets calculations. '
        'Golden State is excluded from both years of the same-12 totals.'
    )


def action_row() -> str:
    return (
        '<div class="data-actions inline">'
        f'<a class="button primary" href="{CSV_NAME}" download>Download team data</a>'
        f'<button class="button copy-citation" type="button" data-copy="{esc(citation_text())}">Copy citation</button>'
        '</div>'
    )


def revenue_bar(teams: list[dict]) -> str:
    rows = sorted(teams, key=lambda team: (-team['revenue_2025_usd_m'], team['forbes_2026_rank']))
    width, row_h, left, right = 640, 28, 52, 72
    height = 28 + row_h * len(rows)
    plot = width - left - right
    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-labelledby="revenue-chart-title">',
        '<title id="revenue-chart-title">Forbes 2025 WNBA revenue estimates. Golden State $78 million, Atlanta $16 million, Indiana $58 million.</title>',
    ]
    for index, team in enumerate(rows):
        y = 8 + index * row_h
        bar = plot * team['revenue_2025_usd_m'] / 78
        color = '#b8006f' if team['slug'] in {'golden-state-valkyries', 'atlanta-dream', 'indiana-fever'} else '#5b22c9'
        parts.append(
            f'<text x="{left - 8}" y="{y + 14}" text-anchor="end" font-size="13" fill="#151413">{esc(team["abbr"])}</text>'
            f'<rect x="{left}" y="{y}" width="{bar:.1f}" height="18" fill="{color}"></rect>'
            f'<text x="{left + bar + 6:.1f}" y="{y + 14}" font-size="13" fill="#151413">{money_short(team["revenue_2025_usd_m"])}</text>'
        )
    parts.append('</svg>')
    return ''.join(parts)


def main_table(teams: list[dict], checks: dict) -> str:
    rows = sorted(teams, key=lambda team: team['forbes_2026_rank'])
    body = []
    for team in rows:
        body.append(
            '<tr>'
            f'<td>{team_link(team)}</td>'
            f'<td class="num">{money_short(team["forbes_2026_value_usd_m"])}</td>'
            f'<td class="num">{money_short(team["revenue_2025_usd_m"])}</td>'
            f'<td class="num">{mult(team["value_per_revenue_2026"])}</td>'
            '</tr>'
        )
    body.append(
        '<tr class="total">'
        '<th scope="row">13 teams combined</th>'
        f'<td class="num">{billions(checks["forbes_2026_value_sum_usd_m"])}</td>'
        f'<td class="num">{money_short(checks["revenue_2025_sum_usd_m"])}</td>'
        f'<td class="num">{mult2(checks["league_multiple"])}</td>'
        '</tr>'
    )
    return (
        '<div class="table-wrap wide"><table class="audience-table wide">'
        '<caption>Forbes franchise values published May 7, 2026, and Forbes revenue estimates for the 2025 season. Value divided by revenue is an FCB calculation, rounded half up to one decimal. The combined multiple uses the sums and is shown to two decimals.</caption>'
        '<thead><tr><th scope="col">Team</th><th scope="col">2026 franchise value</th>'
        '<th scope="col">2025 revenue</th><th scope="col">Value ÷ revenue</th></tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>'
    )


def same_table(checks: dict) -> str:
    change = checks['same_12_multiple_change']
    change_label = f'{change:.2f}{TIMES}'
    return (
        '<div class="table-wrap wide"><table class="audience-table wide">'
        '<caption>The 12 franchises Forbes ranked in both 2025 and 2026. Golden State is excluded. Revenue is the prior season on each list: 2024 revenue in the 2025 ranking, and 2025 revenue in the 2026 ranking.</caption>'
        '<thead><tr><th scope="col">Same 12</th><th scope="col">2025 Forbes</th><th scope="col">2026 Forbes</th><th scope="col">Change</th></tr></thead>'
        '<tbody>'
        '<tr><th scope="row">Combined value</th>'
        f'<td class="num">{billions(checks["same_12_value_2025_usd_m"])}</td>'
        f'<td class="num">{billions(checks["same_12_value_2026_usd_m"])}</td>'
        f'<td class="num">+{checks["same_12_value_change_pct"]:.1f}%</td></tr>'
        '<tr><th scope="row">Prior season revenue</th>'
        f'<td class="num">{money_short(checks["same_12_revenue_2024_usd_m"])} in 2024</td>'
        f'<td class="num">{money_short(checks["same_12_revenue_2025_usd_m"])} in 2025</td>'
        f'<td class="num">+{checks["same_12_revenue_change_pct"]:.1f}%</td></tr>'
        '<tr><th scope="row">Combined value / revenue</th>'
        f'<td class="num">{mult2(checks["same_12_multiple_2025"])}</td>'
        f'<td class="num">{mult2(checks["same_12_multiple_2026"])}</td>'
        f'<td class="num">{change_label}</td></tr>'
        '</tbody></table></div>'
    )


def faq_items(checks: dict) -> list[dict]:
    return [
        {
            'q': 'How large was the revenue gap in the 2026 WNBA Finals?',
            'a': (
                'Forbes estimated Golden State revenue at $78 million and Atlanta revenue at $16 million for the 2025 season. '
                'The $62 million difference was larger than Indiana\'s $58 million, the second-highest revenue estimate on the Forbes list.'
            ),
        },
        {
            'q': 'How does Full Court Buckets calculate the value-to-revenue multiple?',
            'a': (
                'The displayed multiple is the May 7, 2026 Forbes franchise value divided by the Forbes estimate of 2025 revenue, '
                'rounded half up to one decimal. Atlanta is 15.6 times. Golden State is 10.0 times. '
                'The 13-team combined multiple, $5.385 billion divided by $430 million, is 12.52 times.'
            ),
        },
        {
            'q': 'Did franchise values rise faster than revenue?',
            'a': (
                'Not for the same 12 franchises. Their combined Forbes value rose from $3.260 billion to $4.605 billion, up 41.3%. '
                'Their prior-season revenue rose from $226 million in 2024 to $352 million in 2025, up 55.8%. '
                'Value per dollar of revenue fell from 14.42 times to 13.08 times. '
                'Forbes said the league average rose 52%, from $272 million to $414 million, a comparison that adds Golden State to the list.'
            ),
        },
        {
            'q': 'Why is Golden State left out of the same-12 comparison?',
            'a': (
                'Forbes did not value the Valkyries in the June 6, 2025 ranking. The team was three weeks into its inaugural season. '
                'The same-12 totals use only franchises that appear in both the 2025 and 2026 Forbes lists.'
            ),
        },
        {
            'q': 'Are the Portland Fire and Toronto Tempo included?',
            'a': (
                'No. Both began play in 2026 and had no 2025 season. Forbes left them out of the May 7, 2026 ranking. '
                'This page does not assign them a 2025 revenue or a 2026 franchise value.'
            ),
        },
    ]


def faq_html(items: list[dict]) -> str:
    return ''.join(f'<h3>{esc(item["q"])}</h3><p>{esc(item["a"])}</p>' for item in items)


def json_script(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False).replace('<', '\\u003c')
    return f'<script type="application/ld+json">{raw}</script>'


def render_page(payload: dict) -> str:
    teams = payload['teams']
    checks = payload['fcb_checks']
    by_slug = {team['slug']: team for team in teams}
    items = faq_items(checks)
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
                'name': 'WNBA franchise values in 2026 and revenue by team',
                'description': DESCRIPTION,
                'url': BASE + ROUTE,
                'creator': {'@type': 'Organization', 'name': 'Full Court Buckets', 'url': BASE + '/'},
                'isAccessibleForFree': True,
                'temporalCoverage': '2024/2026',
                'dateModified': '2026-10-31',
                'distribution': {
                    '@type': 'DataDownload',
                    'encodingFormat': 'text/csv',
                    'contentUrl': BASE + ROUTE + CSV_NAME,
                },
            },
            {
                '@type': 'FAQPage',
                '@id': BASE + ROUTE + '#faq',
                'mainEntity': [
                    {'@type': 'Question', 'name': item['q'], 'acceptedAnswer': {'@type': 'Answer', 'text': item['a']}}
                    for item in items
                ],
            },
        ],
    }
    four = [by_slug[slug] for slug in ('seattle-storm', 'phoenix-mercury', 'los-angeles-sparks', 'dallas-wings')]
    four_links = ', '.join(
        f'{team_link(team)} {money_short(team["forbes_2026_value_usd_m"])}' for team in four
    )
    nav = ''.join(f'<li><a href="#{anchor}">{esc(label)}</a></li>' for anchor, label in NAV)
    options = ''.join(f'<option value="#{anchor}">{esc(label)}</option>' for anchor, label in NAV)
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
<meta property="og:image:alt" content="Golden State $780 million on $78 million of revenue, 10.0 times. Atlanta $250 million on $16 million, 15.6 times.">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:site" content="@fullcourtbucket">
<meta name="twitter:title" content="{esc(PAGE_TITLE)}">
<meta name="twitter:description" content="{esc(DESCRIPTION)}">
<meta name="twitter:image" content="{BASE}{ROUTE}{OG_NAME}">
<meta name="twitter:image:alt" content="Golden State $780 million on $78 million of revenue, 10.0 times. Atlanta $250 million on $16 million, 15.6 times.">
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
<p class="eyebrow">WNBA / Data and research</p>
<h1>{esc(H1)}</h1>
<div class="byline-row article">{byline_html()}<span class="byline-sep" aria-hidden="true">|</span><time class="article-date" datetime="2026-10-31">October 31, 2026</time></div>
<p class="answer">The revenue gap between the two teams in the 2026 WNBA Finals was bigger than the entire <a href="/wnba/teams/indiana-fever/">Indiana Fever</a> business generated on the court and off it during the 2025 regular season. <a href="{FORBES_2026}">Forbes</a> estimated <a href="/wnba/teams/golden-state-valkyries/">Golden State</a>'s revenue at $78 million and <a href="/wnba/teams/atlanta-dream/">Atlanta</a>'s at $16 million. The $62 million difference exceeded Indiana's $58 million, which ranked second in the league.</p>
<p class="answer">Golden State also led Forbes' 2026 franchise valuations at $780 million, compared with $250 million for Atlanta. That makes the <a href="/wnba/teams/golden-state-valkyries/">Valkyries</a> worth 4.9 times as much as the <a href="/wnba/teams/atlanta-dream/">Dream</a> by revenue, but 3.1 times as much by franchise value. Each dollar of Atlanta revenue corresponded to $15.63 in estimated franchise value, compared with $10.00 for Golden State.</p>
<section class="key-stats" aria-label="Finals revenue and value gap">
<h2>Finals gap</h2>
<ul class="key-list">
<li class="stat-card"><p class="stat-value">$62M</p><p class="stat-label">Revenue gap, Golden State minus Atlanta</p><p class="stat-meta">Larger than Indiana's entire $58 million</p></li>
<li class="stat-card"><p class="stat-value">4.9{TIMES}</p><p class="stat-label">Revenue, Valkyries versus Dream</p><p class="stat-meta">$78 million / $16 million</p></li>
<li class="stat-card"><p class="stat-value">3.1{TIMES}</p><p class="stat-label">Franchise value, Valkyries versus Dream</p><p class="stat-meta">$780 million / $250 million</p></li>
<li class="stat-card"><p class="stat-value">$15.63</p><p class="stat-label">Atlanta value per revenue dollar</p><p class="stat-meta">Golden State is $10.00</p></li>
</ul>
</section>
<div class="data-layout">
<div class="data-nav"><nav class="contents-rail" aria-label="On this page"><p class="contents-label">On this page</p><ul>{nav}</ul></nav>
<div class="on-page-mobile"><label for="on-this-page">On this page</label><select id="on-this-page"><option value="">On this page</option>{options}</select></div></div>
<div class="data-main">
<section class="qa" id="teams">
<h2>2026 franchise value and 2025 revenue</h2>
<p class="answer">Pink bars are Golden State, Indiana, and Atlanta: the Finals clubs and the team whose whole 2025 revenue estimate was smaller than the Finals revenue gap.</p>
<figure class="chart-figure">{revenue_bar(teams)}<figcaption>Forbes estimates of 2025 regular-season revenue, in millions of dollars. Playoff games are excluded, as Forbes states in its methodology.</figcaption></figure>
{action_row()}
{main_table(teams, checks)}
<p class="note">The Portland Fire and the Toronto Tempo began play in 2026 and had no 2025 season. Forbes left both out of the May 7, 2026 ranking, so this table does not give them a revenue or a value. Team pages: <a href="/wnba/teams/portland-fire/">Portland Fire</a> and <a href="/wnba/teams/toronto-tempo/">Toronto Tempo</a>.</p>
</section>
<section class="qa" id="same-12-teams">
<h2>Revenue grew faster than franchise values for the same 12 teams</h2>
<p>Forbes said the average franchise value rose 52%, from $272 million in the 2025 ranking to $414 million in the 2026 ranking. That average compares a 13-team list with a 12-team list. Golden State, left out in 2025, enters in 2026 at $780 million.</p>
<p>Matching the 12 franchises that appear in both editions tells a different story. Revenue on those clubs grew faster than the values, so each dollar of revenue corresponded to less estimated franchise value in 2026 than in 2025.</p>
{same_table(checks)}
<p>Those 12 gained $1.345 billion in combined value, about $1.35 billion. Because revenue grew faster, value per dollar of revenue fell from {mult2(checks["same_12_multiple_2025"])} to {mult2(checks["same_12_multiple_2026"])}.</p>
<p class="note">Forbes described the rounded $272 million average as 14.4 times average revenue. The 14.42{TIMES} in this table is the FCB sum: $3.260 billion divided by $226 million. The 13.08{TIMES} is $4.605 billion divided by $352 million. Golden State is in neither year of these totals.</p>
</section>
<section class="qa" id="four-teams">
<h2>Four teams earned $28 million</h2>
<p>Forbes estimated the same $28 million of 2025 revenue for four clubs. Their 2026 values still spanned $90 million, from Seattle at $430 million to Dallas at $340 million. Phoenix was $425 million and Los Angeles was $350 million. In this table: {four_links}.</p>
<p>Indiana and New York diverge the other way. Indiana's $58 million of revenue ranked second, ahead of New York's $43 million, but New York's franchise value was higher, $600 million to $580 million. Indiana's multiple is 10.0{TIMES}. New York's is 14.0{TIMES}.</p>
<p>Ownership lines on the Forbes cards, and the FCB owner index, are separate from these values. <a href="/wnba/owners/">WNBA owners</a>.</p>
</section>
<section class="qa" id="methods">
<h2>Methods</h2>
<p>The 2026 value and the 2025 revenue come from Brett Knight, "The WNBA's Most Valuable Teams 2026," Forbes, May 7, 2026. Revenue figures are Forbes estimates for the 2025 season, rounded to the nearest million. Playoff games are excluded. Values include the economics of a team's arena and exclude the arena real estate. On Oct. 31, 2026 the English article returned a JavaScript shell without the team cards. The 13 cards were read from the Forbes Mexico translation of that article, which says the text was first published by Forbes US. The cards sum to $5,385 million. Divided by 13, that is $414.2 million, in line with the $414 million average Forbes stated, and $5.385 billion combined.</p>
<p>The prior year comes from Brett Knight, "The WNBA's Most Valuable Teams 2025," Forbes, June 6, 2025. That list values 12 existing franchises and does not value Golden State. Revenue figures are estimates for the 2024 season, rounded to the nearest million, again with playoff games excluded. The 12 values sum to $3,260 million. Divided by 12, that is $271.7 million, which Forbes rounds to the $272 million average it published. The 12 revenue estimates sum to $226 million.</p>
<p>Full Court Buckets calculated every multiple and the same-12 growth rates. A team multiple is that edition's Forbes value divided by that edition's revenue estimate. The one-decimal multiples use half-up rounding. The combined ratios use the sums, not an average of the team multiples, and are shown to two decimals. The same-12 block drops Golden State from both years. The one-year value changes Forbes printed on the 2026 cards match these 2025 bases after the same half-up rounding to a whole percent.</p>
<p class="note">Not used in the table: a Playbook Strategies graphic dated Oct. 31, 2026 printed 2025 revenue of $56 million for Indiana and $16 million for Washington. Forbes prints $58 million and $18 million. The Playbook report itself is behind an email gate, so those two figures stay out of this dataset.</p>
<p class="how-made">How the pages on this site are made: <a href="/how-we-make-full-court-buckets/">How we make Full Court Buckets</a>. Related pages: <a href="/wnba/viewership-attendance/">viewership and attendance</a>, <a href="/news/2026-wnba-finals-ratings-tracker/">2026 Finals ratings tracker</a>, <a href="/news/wnba-expansion-teams/">expansion teams</a>.</p>
</section>
<section class="qa" id="sources">
<h2>Sources</h2>
<ul>
<li>{source_link(FORBES_2026, "The WNBA's Most Valuable Teams 2026")}, Brett Knight, Forbes, May 7, 2026. Values and 2025 revenue. Team cards checked against {source_link(FORBES_MX, "the Forbes Mexico translation")}.</li>
<li>{source_link(FORBES_2025, "The WNBA's Most Valuable Teams 2025")}, Brett Knight, Forbes, June 6, 2025. Values and 2024 revenue for the same 12 franchises. The published average is $272 million, and Forbes describes that average as 14.4 times average revenue.</li>
</ul>
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
if (jump) jump.addEventListener('change', function() {{ if (jump.value) location.hash = jump.value; }});
</script>
</body>
</html>
'''


EXTRA_CSS = """
html{scroll-padding-top:120px}
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
.stat-label,.stat-meta{margin:6px 0 0;font-size:14px;line-height:1.4}
.stat-meta{color:#5a554e}
.data-layout{margin-top:28px}
.contents-rail{display:none}
.contents-label{margin:0 0 8px;font:800 12px/1 "Barlow",sans-serif;letter-spacing:.12em;text-transform:uppercase;color:#5a554e}
.contents-rail ul,.on-page-mobile{margin:0;padding:0;list-style:none}
.contents-rail a{display:inline-flex;align-items:center;min-height:36px;font-weight:700}
.data-actions.inline{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}
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
figcaption,.note,.how-made{max-width:68ch;color:#5a554e;font-size:14px;line-height:1.55}
.data-main,.qa{min-width:0;max-width:100%}
.table-wrap.wide{overflow-x:auto;max-width:100%;-webkit-overflow-scrolling:touch}
.audience-table{width:100%;border-collapse:collapse}
.audience-table th,.audience-table td{padding:10px 8px;border-bottom:1px solid var(--line,#e2ddd6);text-align:left;vertical-align:top}
.audience-table .num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.audience-table caption{caption-side:bottom;padding-top:8px;text-align:left;color:#5a554e;font-size:13px}
.audience-table tr.total th,.audience-table tr.total td{font-weight:700}
.cite{margin-top:12px;padding:12px 14px;border-left:3px solid #5b22c9}
@media(max-width:900px){.key-list{grid-template-columns:1fr 1fr}}
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
    for team in sorted(payload['teams'], key=lambda item: item['forbes_2026_rank']):
        item = {key: blank(team.get(key)) for key in CSV_FIELDS}
        item['notes'] = ''
        rows.append(item)
    for row in payload['not_in_source_set']:
        item = {key: '' for key in CSV_FIELDS}
        item.update({
            'team': row['team'],
            'market': row['market'],
            'team_page': row['team_page'],
            'in_forbes_2026': False,
            'in_same_12': False,
            'notes': row['reason'],
        })
        rows.append(item)
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_share_image(path: Path) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        if path.is_file():
            return
        raise ValueError('Share image is missing and Pillow is not installed.')
    image = Image.new('RGB', (1200, 630), '#f7f5f2')
    draw = ImageDraw.Draw(image)
    font_dir = ROOT / 'assets' / 'fonts'
    bold = ImageFont.truetype(str(font_dir / 'Inter-Bold.ttf'), 54)
    med = ImageFont.truetype(str(font_dir / 'Inter-Medium.ttf'), 32)
    small = ImageFont.truetype(str(font_dir / 'Inter-Medium.ttf'), 24)
    draw.rectangle((0, 0, 1200, 12), fill='#5b22c9')
    draw.text((64, 56), 'WNBA franchise values', font=bold, fill='#2a1458')
    draw.text((64, 124), 'and 2025 revenue', font=bold, fill='#2a1458')
    draw.text((64, 230), 'Golden State  $780M on $78M, 10.0x', font=med, fill='#151413')
    draw.text((64, 286), 'Atlanta  $250M on $16M, 15.6x', font=med, fill='#b8006f')
    draw.text((64, 360), 'Same 12 teams: revenue grew faster than value', font=med, fill='#151413')
    draw.text((64, 540), 'Full Court Buckets. Forbes 2025 and 2026 rankings.', font=small, fill='#5a554e')
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, 'PNG')


def update_sitemaps(root: Path) -> None:
    canonical = BASE + ROUTE
    pages = root / 'pages-sitemap.xml'
    text = pages.read_text(encoding='utf-8')
    if f'<loc>{canonical}</loc>' not in text:
        entry = f'  <url>\n    <loc>{canonical}</loc>\n    <lastmod>2026-10-31</lastmod>\n  </url>\n'
        pages.write_text(text.replace('</urlset>', entry + '</urlset>', 1), encoding='utf-8')
    html_map = root / 'sitemap' / 'index.html'
    page = html_map.read_text(encoding='utf-8')
    if f'href="{ROUTE}"' not in page:
        marker = '<li><a href="/wnba/viewership-attendance/">WNBA viewership and attendance</a></li>'
        if marker not in page:
            raise ValueError('HTML sitemap is missing the viewership link this page should follow.')
        insert = marker + '<li><a href="/wnba/team-revenue/">WNBA franchise values and revenue</a></li>'
        html_map.write_text(page.replace(marker, insert, 1), encoding='utf-8')


def public_payload(payload: dict) -> dict:
    return json.loads(json.dumps(payload))


def upsert_search(root: Path) -> None:
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
    used = {item.get('i', '').lstrip('/') for item in data['items']}
    thumb_dir = root / 'images' / 'search-thumbs'
    if thumb_dir.is_dir():
        for old in thumb_dir.glob('*.webp'):
            rel = old.relative_to(root).as_posix()
            if rel not in used and old.name.startswith('8329dbc'):
                old.unlink()


def build(root: Path) -> None:
    path = root / DATA_FILE
    payload = load(path)
    validate(payload)
    payload = enrich(payload)
    validate(payload)
    rendered = render_page(payload)
    if EM_DASH in rendered or EN_DASH in rendered:
        raise ValueError('Page copy contains a dash the style guide does not allow.')
    if 'creativecommons' in rendered.lower() or 'CC0' in rendered:
        raise ValueError('Page applies a blanket CC0 license.')
    rendered = site_nav.install(rendered, ROUTE, site_nav.build_menu(root))
    rendered = seo_meta.apply_rel(rendered, ROUTE, root)
    rendered = breadcrumbs.fix(rendered, ROUTE, root)
    if EM_DASH in rendered or EN_DASH in rendered:
        raise ValueError('Installed page contains a dash the style guide does not allow.')
    page_dir = root / 'wnba' / 'team-revenue'
    page_dir.mkdir(parents=True, exist_ok=True)
    (page_dir / 'index.html').write_text(rendered, encoding='utf-8')
    write_csv(page_dir / CSV_NAME, csv_rows(payload))
    download = json.dumps(public_payload(payload), indent=2, ensure_ascii=False) + '\n'
    (page_dir / JSON_NAME).write_text(download, encoding='utf-8')
    path.write_text(download, encoding='utf-8')
    write_share_image(page_dir / OG_NAME)
    update_sitemaps(root)
    upsert_search(root)
    print(f'Wrote wnba/team-revenue/index.html from {DATA_FILE}.')


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
