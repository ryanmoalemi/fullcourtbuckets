#!/usr/bin/env python3
"""Build /wnba/team-revenue/ from data/wnba-team-revenue-2025.json.

The page leads with a ranked comparison of Forbes' 2025 revenue estimates
for all 13 teams. Franchise-value multiples and the same-12 growth block
sit below that ranking. Displayed multiples use Forbes' May 7, 2026 values
divided by Forbes' 2025 revenue estimates. The same-12 comparison uses the
June 6, 2025 Forbes list for the 12 franchises ranked in both editions.
Golden State is excluded from those totals.

Tied revenue sorts by market name, which puts the four $28 million clubs
in the journalist table order: Dallas, Los Angeles, Phoenix, Seattle.
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
import team_hub

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = 'data/wnba-team-revenue-2025.json'
ROUTE = '/wnba/team-revenue/'
BASE = 'https://fullcourtbuckets.com'
PAGE_TITLE = 'WNBA team revenue, ranked: 2025 estimates for 13 teams'
H1 = 'WNBA team revenue, ranked'
DESCRIPTION = (
    'Ranked 2025 WNBA team revenue for all 13 Forbes clubs, from Golden State at '
    '$78 million to Atlanta at $16 million. The combined total is $430 million.'
)
OG_ALT = (
    '2025 WNBA team revenue, ranked. Golden State $78 million is nearly 5 times '
    'Atlanta at $16 million. Four teams are tied at $28 million. Combined $430 million.'
)
LEDE = (
    'Use these figures in your WNBA reporting to compare all 13 teams covered by Forbes. '
    'Estimates cover the 2025 regular season, excluding playoff revenue, and were published in May 2026.'
)
ATTRIBUTION = (
    'Revenue estimates are from Forbes. Full Court Buckets compiled the ranking and calculated the combined total.'
)
EXPANSION_NOTE = (
    'Portland and Toronto began play in 2026 and fall outside this 2025 revenue dataset.'
)
# Journalist order: revenue high to low, ties by market name.
REVENUE_ORDER = (
    'golden-state-valkyries',
    'indiana-fever',
    'new-york-liberty',
    'las-vegas-aces',
    'chicago-sky',
    'dallas-wings',
    'los-angeles-sparks',
    'phoenix-mercury',
    'seattle-storm',
    'minnesota-lynx',
    'connecticut-sun',
    'washington-mystics',
    'atlanta-dream',
)
REVENUE_AMOUNTS = (78, 58, 43, 34, 30, 28, 28, 28, 28, 21, 20, 18, 16)
FINALS = frozenset({'golden-state-valkyries', 'atlanta-dream'})
CLUSTER = frozenset({'dallas-wings', 'los-angeles-sparks', 'phoenix-mercury', 'seattle-storm'})
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
    'revenue_2025_rank',
    'forbes_2025_value_usd_m', 'revenue_2024_usd_m', 'value_per_revenue_2025',
    'forbes_2026_rank', 'forbes_2025_rank', 'value_change_pct',
    'forbes_2026_source_url', 'forbes_2026_date',
    'forbes_2025_source_url', 'forbes_2025_date',
    'ownership', 'arena', 'notes',
)
NAV = (
    ('ranking', 'Revenue ranking'),
    ('values', 'Franchise values'),
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


def revenue_ranked(teams: list[dict]) -> list[dict]:
    """High to low. Equal revenue sorts by market, then team name."""
    return sorted(teams, key=lambda team: (-team['revenue_2025_usd_m'], team['market'], team['team']))


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
    for index, team in enumerate(revenue_ranked(teams), start=1):
        team['revenue_2025_rank'] = index
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
    ranked_slugs = [team['slug'] for team in revenue_ranked(teams)]
    if tuple(ranked_slugs) != REVENUE_ORDER:
        raise ValueError('2025 revenue ranking does not match the journalist order.')
    amounts = tuple(team['revenue_2025_usd_m'] for team in revenue_ranked(teams))
    if amounts != REVENUE_AMOUNTS:
        raise ValueError(f'2025 revenue amounts are {amounts}, expected {REVENUE_AMOUNTS}.')
    if sum(amounts) != 430:
        raise ValueError('The 13 revenue estimates must sum to $430 million.')
    for team in teams:
        expected_rank = REVENUE_ORDER.index(team['slug']) + 1
        got = team.get('revenue_2025_rank')
        if got not in (None, expected_rank):
            raise ValueError(f'{team["team"]} revenue rank {got} does not match {expected_rank}.')
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


def team_mark(team: dict) -> str:
    """Circle crop of the licensed team photo already used on the teams hub."""
    visual = team_hub.VISUALS.get(team['slug']) or {}
    src = visual.get('src') or ''
    if src.startswith('/') and (ROOT / src.lstrip('/')).is_file():
        return (f'<img class="rev-logo" src="{esc(src)}" alt="" width="36" height="36" decoding="async">')
    return f'<span class="rev-logo rev-logo-fallback" aria-hidden="true">{esc(team["abbr"])}</span>'


def team_link_with_mark(team: dict) -> str:
    return (
        f'<a class="rev-team" href="{esc(team["team_page"])}">'
        f'{team_mark(team)}<span>{esc(team["team"])}</span></a>'
    )


def source_link(url: str, label: str) -> str:
    return f'<a href="{esc(url)}">{esc(label)}</a>'


def byline_html() -> str:
    return links.BYLINE_HTML.replace('>By Ryan Moalemi<', '>Ryan Moalemi, Full Court Buckets<')


def citation_text() -> str:
    return (
        'Full Court Buckets, "WNBA team revenue, ranked," October 31, 2026, '
        f'{BASE}{ROUTE}. Revenue estimates: Brett Knight, "The WNBA\'s Most Valuable Teams 2026," '
        f'Forbes, May 7, 2026, {FORBES_2026}. '
        'Full Court Buckets compiled the ranking and calculated the combined total of $430 million. '
        'Franchise values: the same Forbes article, and Brett Knight, "The WNBA\'s Most Valuable Teams 2025," '
        f'Forbes, June 6, 2025, {FORBES_2025}. Multiples and the same-12 comparison: Full Court Buckets calculations. '
        'Golden State is excluded from both years of the same-12 totals.'
    )


def action_row() -> str:
    csv_url = BASE + ROUTE + CSV_NAME
    return (
        '<div class="cite-sticky">'
        f'<a class="button primary" href="{esc(csv_url)}" download>Download the CSV</a>'
        '<span class="cite-dot" aria-hidden="true">·</span>'
        f'<a class="button" href="{esc(FORBES_2026)}">View the Forbes source</a>'
        '<span class="cite-dot" aria-hidden="true">·</span>'
        f'<button class="button copy-citation" type="button" data-copy="{esc(citation_text())}">Copy citation</button>'
        '</div>'
    )


def revenue_chart(teams: list[dict]) -> str:
    """HTML bars so labels and values stay readable when the viewport shrinks."""
    rows = revenue_ranked(teams)
    parts = []
    cluster_started = False
    for index, team in enumerate(rows, start=1):
        slug = team['slug']
        classes = ['rev-row']
        if slug in FINALS:
            classes.append('is-finals')
        if slug in CLUSTER:
            classes.append('is-cluster')
            if not cluster_started:
                classes.append('is-cluster-first')
                parts.append('<li class="rev-band-label"><span>Four teams tied at $28M</span></li>')
                cluster_started = True
            if index == rows.index(team) + 1 and all(
                rows[i]['slug'] not in CLUSTER for i in range(index, len(rows))
            ):
                classes.append('is-cluster-last')
        pct = team['revenue_2025_usd_m'] / 78 * 100
        tag = '<span class="rev-tag">Finals</span>' if slug in FINALS else ''
        notch = ''
        if slug == 'golden-state-valkyries':
            notch = '<span class="rev-notch" style="left:20.51%"></span>'
        parts.append(
            f'<li class="{" ".join(classes)}">'
            f'<span class="rev-rank">{index}</span>'
            f'<span class="rev-name">{team_link_with_mark(team)}{tag}</span>'
            f'<span class="rev-track" aria-hidden="true"><span class="rev-bar" style="width:{pct:.2f}%">{notch}</span></span>'
            f'<span class="rev-val">{money_short(team["revenue_2025_usd_m"])}</span>'
            '</li>'
        )
    axis = (
        '<div class="rev-axis-wrap" aria-hidden="true"><div class="rev-axis">'
        '<span style="left:0%">$0</span>'
        '<span style="left:25.64%">$20M</span>'
        '<span style="left:51.28%">$40M</span>'
        '<span style="left:76.92%">$60M</span>'
        '<span style="left:100%">$78M</span>'
        '</div></div>'
    )
    return (
        '<div class="rev-chart">'
        '<p id="revenue-chart-title" class="rev-chart-note">Bars share one scale. Golden State fills the row. '
        'The white mark on that bar is Atlanta at $16 million, about one fifth of the way across.</p>'
        f'<ol class="rev-rows">{"".join(parts)}</ol>'
        f'{axis}'
        '</div>'
    )


def revenue_table(teams: list[dict]) -> str:
    body = []
    for team in revenue_ranked(teams):
        classes = []
        if team['slug'] in FINALS:
            classes.append('is-finals')
        if team['slug'] in CLUSTER:
            classes.append('is-cluster')
        tag = ' <span class="rev-tag">Finals</span>' if team['slug'] in FINALS else ''
        attr = f' class="{" ".join(classes)}"' if classes else ''
        body.append(
            f'<tr{attr}>'
            f'<td>{team_link_with_mark(team)}{tag}</td>'
            f'<td class="num">{money_short(team["revenue_2025_usd_m"])}</td>'
            '</tr>'
        )
    body.append(
        '<tr class="total"><th scope="row">Combined</th>'
        '<td class="num">$430M</td></tr>'
    )
    return (
        '<div class="table-wrap fit"><table class="audience-table revenue-table">'
        f'<caption>{esc(ATTRIBUTION)}</caption>'
        '<thead><tr><th scope="col">Team</th><th scope="col">Estimated revenue</th></tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>'
    )


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
                'name': 'WNBA team revenue, ranked',
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
<meta name="theme-color" content="#0b0b10">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<meta property="og:title" content="{esc(PAGE_TITLE)}">
<meta property="og:description" content="{esc(DESCRIPTION)}">
<meta property="og:url" content="{BASE}{ROUTE}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="Full Court Buckets">
<meta property="og:image" content="{BASE}{ROUTE}{OG_NAME}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{esc(OG_ALT)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:site" content="@fullcourtbucket">
<meta name="twitter:title" content="{esc(PAGE_TITLE)}">
<meta name="twitter:description" content="{esc(DESCRIPTION)}">
<meta name="twitter:image" content="{BASE}{ROUTE}{OG_NAME}">
<meta name="twitter:image:alt" content="{esc(OG_ALT)}">
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
<section class="rev-hero" id="ranking" aria-labelledby="revenue-chart-title">
{action_row()}
<div class="rev-stage">
{revenue_chart(teams)}
<div class="rev-table-col">
{revenue_table(teams)}
<p class="note"><a href="/wnba/teams/portland-fire/">Portland</a> and <a href="/wnba/teams/toronto-tempo/">Toronto</a> began play in 2026 and fall outside this 2025 revenue dataset.</p>
</div>
</div>
<ul class="scale-list" aria-label="Scale of the 2025 revenue estimates">
<li class="scale-card"><p class="scale-value">Nearly 5{TIMES}</p><p class="scale-label">Golden State versus Atlanta</p><p class="scale-meta">$78 million to $16 million</p></li>
<li class="scale-card"><p class="scale-value">$28M</p><p class="scale-label">Four teams tied</p><p class="scale-meta">Dallas, Los Angeles, Phoenix, Seattle</p></li>
<li class="scale-card scale-total"><p class="scale-value">$430M</p><p class="scale-label">Combined</p><p class="scale-meta">All 13 teams Forbes ranked</p></li>
</ul>
</section>
<p class="lede">{esc(LEDE)}</p>
<div class="data-layout">
<div class="data-nav"><nav class="contents-rail" aria-label="On this page"><p class="contents-label">On this page</p><ul>{nav}</ul></nav>
<div class="on-page-mobile"><label for="on-this-page">On this page</label><select id="on-this-page"><option value="">On this page</option>{options}</select></div></div>
<div class="data-main">
<details class="fold" open id="values">
<summary><h2>2026 franchise value and 2025 revenue</h2></summary>
<div class="fold-body">
<p>The revenue gap between the two teams in the 2026 WNBA Finals was bigger than the entire <a href="/wnba/teams/indiana-fever/">Indiana Fever</a> business generated on the court and off it during the 2025 regular season. <a href="{FORBES_2026}">Forbes</a> estimated <a href="/wnba/teams/golden-state-valkyries/">Golden State</a>'s revenue at $78 million and <a href="/wnba/teams/atlanta-dream/">Atlanta</a>'s at $16 million. The $62 million difference exceeded Indiana's $58 million, which ranked second in the league.</p>
<p>Golden State also led Forbes' 2026 franchise valuations at $780 million, compared with $250 million for Atlanta. That makes the <a href="/wnba/teams/golden-state-valkyries/">Valkyries</a> worth 4.9 times as much as the <a href="/wnba/teams/atlanta-dream/">Dream</a> by revenue, but 3.1 times as much by franchise value. Each dollar of Atlanta revenue corresponded to $15.63 in estimated franchise value, compared with $10.00 for Golden State.</p>
{main_table(teams, checks)}
<p class="note">The <a href="/wnba/teams/portland-fire/">Portland Fire</a> and the <a href="/wnba/teams/toronto-tempo/">Toronto Tempo</a> began play in 2026 and had no 2025 season. Forbes left both out of the May 7, 2026 ranking, so this table does not give them a revenue or a value.</p>
</div>
</details>
<details class="fold" open id="same-12-teams">
<summary><h2>Revenue grew faster than franchise values for the same 12 teams</h2></summary>
<div class="fold-body">
<p>Forbes said the average franchise value rose 52%, from $272 million in the 2025 ranking to $414 million in the 2026 ranking. That average compares a 13-team list with a 12-team list. Golden State, left out in 2025, enters in 2026 at $780 million.</p>
<p>Matching the 12 franchises that appear in both editions tells a different story. Revenue on those clubs grew faster than the values, so each dollar of revenue corresponded to less estimated franchise value in 2026 than in 2025.</p>
{same_table(checks)}
<p>Those 12 gained $1.345 billion in combined value, about $1.35 billion. Because revenue grew faster, value per dollar of revenue fell from {mult2(checks["same_12_multiple_2025"])} to {mult2(checks["same_12_multiple_2026"])}.</p>
<p class="note">Forbes described the rounded $272 million average as 14.4 times average revenue. The 14.42{TIMES} in this table is the FCB sum: $3.260 billion divided by $226 million. The 13.08{TIMES} is $4.605 billion divided by $352 million. Golden State is in neither year of these totals.</p>
</div>
</details>
<details class="fold" open id="four-teams">
<summary><h2>Four teams earned $28 million</h2></summary>
<div class="fold-body">
<p>Forbes estimated the same $28 million of 2025 revenue for four clubs. Their 2026 values still spanned $90 million, from Seattle at $430 million to Dallas at $340 million. Phoenix was $425 million and Los Angeles was $350 million. In this table: {four_links}.</p>
<p>Indiana and New York diverge the other way. Indiana's $58 million of revenue ranked second, ahead of New York's $43 million, but New York's franchise value was higher, $600 million to $580 million. Indiana's multiple is 10.0{TIMES}. New York's is 14.0{TIMES}.</p>
<p>Ownership lines on the Forbes cards, and the FCB owner index, are separate from these values. <a href="/wnba/owners/">WNBA owners</a>.</p>
</div>
</details>
<details class="fold" open id="methods">
<summary><h2>Methods</h2></summary>
<div class="fold-body">
<p>The 2026 value and the 2025 revenue come from Brett Knight, "The WNBA's Most Valuable Teams 2026," Forbes, May 7, 2026. Revenue figures are Forbes estimates for the 2025 season, rounded to the nearest million. Playoff games are excluded. Values include the economics of a team's arena and exclude the arena real estate. On Oct. 31, 2026 the English article returned a JavaScript shell without the team cards. The 13 cards were read from the Forbes Mexico translation of that article, which says the text was first published by Forbes US. The cards sum to $5,385 million. Divided by 13, that is $414.2 million, in line with the $414 million average Forbes stated, and $5.385 billion combined.</p>
<p>The prior year comes from Brett Knight, "The WNBA's Most Valuable Teams 2025," Forbes, June 6, 2025. That list values 12 existing franchises and does not value Golden State. Revenue figures are estimates for the 2024 season, rounded to the nearest million, again with playoff games excluded. The 12 values sum to $3,260 million. Divided by 12, that is $271.7 million, which Forbes rounds to the $272 million average it published. The 12 revenue estimates sum to $226 million.</p>
<p>Full Court Buckets calculated every multiple and the same-12 growth rates. A team multiple is that edition's Forbes value divided by that edition's revenue estimate. The one-decimal multiples use half-up rounding. The combined ratios use the sums, not an average of the team multiples, and are shown to two decimals. The same-12 block drops Golden State from both years. The one-year value changes Forbes printed on the 2026 cards match these 2025 bases after the same half-up rounding to a whole percent.</p>
<p class="note">Not used in the table: a Playbook Strategies graphic dated Oct. 31, 2026 printed 2025 revenue of $56 million for Indiana and $16 million for Washington. Forbes prints $58 million and $18 million. The Playbook report itself is behind an email gate, so those two figures stay out of this dataset.</p>
<p class="how-made">How the pages on this site are made: <a href="/how-we-make-full-court-buckets/">How we make Full Court Buckets</a>. Related pages: <a href="/wnba/viewership-attendance/">viewership and attendance</a>, <a href="/news/2026-wnba-finals-ratings-tracker/">2026 Finals ratings tracker</a>, <a href="/news/wnba-expansion-teams/">expansion teams</a>.</p>
</div>
</details>
<details class="fold" open id="sources">
<summary><h2>Sources</h2></summary>
<div class="fold-body">
<ul>
<li>{source_link(FORBES_2026, "The WNBA's Most Valuable Teams 2026")}, Brett Knight, Forbes, May 7, 2026. Values and 2025 revenue. Team cards checked against {source_link(FORBES_MX, "the Forbes Mexico translation")}.</li>
<li>{source_link(FORBES_2025, "The WNBA's Most Valuable Teams 2025")}, Brett Knight, Forbes, June 6, 2025. Values and 2024 revenue for the same 12 franchises. The published average is $272 million, and Forbes describes that average as 14.4 times average revenue.</li>
</ul>
<p class="cite">{esc(citation_text())}</p>
</div>
</details>
<details class="fold" open id="faq">
<summary><h2>FAQ</h2></summary>
<div class="fold-body">
{faq_html(items)}
</div>
</details>
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
function foldForWidth() {{
  var narrow = window.matchMedia('(max-width: 899px)').matches;
  var current = (location.hash || '').slice(1);
  document.querySelectorAll('details.fold').forEach(function(el) {{
    if (el.dataset.userSet === '1') return;
    el.open = !narrow || el.id === current;
  }});
}}
document.querySelectorAll('details.fold > summary').forEach(function(summary) {{
  summary.addEventListener('click', function() {{
    var el = summary.parentNode;
    if (el && el.dataset) el.dataset.userSet = '1';
  }});
}});
window.addEventListener('hashchange', foldForWidth);
window.addEventListener('resize', foldForWidth);
foldForWidth();
</script>
</body>
</html>
'''


EXTRA_CSS = """
html{scroll-padding-top:128px}
.page{padding:28px 0 80px}
.standings-shell{width:min(1180px,calc(100% - 40px));margin:0 auto;min-width:0;max-width:100%}
h1{margin:0 0 8px;font:800 clamp(36px,5vw,60px)/1.05 "Barlow",sans-serif;letter-spacing:-.6px;max-width:16em}
.lede,.fold-body p,.fold-body li,.cite,.note,.how-made{overflow-wrap:anywhere}
.lede{max-width:68ch;margin:22px 0 0;font-size:18px;line-height:1.55}
html body .byline-row.article{display:flex;align-items:center;gap:10px 12px;margin:10px 0 16px;flex-wrap:wrap;background:transparent!important;border:0!important;box-shadow:none!important}
.byline-sep{color:#6f6a64}
.byline-row .article-date{font:600 15px/1.3 Inter,system-ui,sans-serif}
.cite-sticky{display:flex;flex-wrap:wrap;align-items:center;gap:8px 10px;margin:0 0 18px}
.cite-dot{color:#5a554e;font-size:18px}
.button{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:0 14px;border-radius:3px;font:700 15px/1 Inter,system-ui,sans-serif;text-decoration:none;cursor:pointer}
.button.primary{background:#5b22c9!important;border:1px solid #5b22c9!important;color:#fff!important}
.button:focus-visible,a:focus-visible,summary:focus-visible,select:focus-visible{outline:2px solid #5b22c9;outline-offset:3px}
.rev-hero{margin:8px 0 8px}
.scale-list{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:18px 0 0;padding:0;list-style:none}
.scale-card{margin:0;padding:16px 16px 14px;border:1px solid #e2ddd6;background:#fff;box-shadow:0 1px 3px rgba(40,20,80,.06)}
.scale-total{border-top:4px solid #b8006f}
.scale-value{margin:0;font:800 clamp(34px,4vw,52px)/.95 "Barlow",sans-serif;letter-spacing:-.6px;font-variant-numeric:tabular-nums}
.scale-total .scale-value{color:#b8006f!important}
.scale-label{margin:8px 0 0;font-size:16px;line-height:1.3;font-weight:700}
.scale-meta{margin:4px 0 0;font-size:15px;line-height:1.35}
.rev-stage{display:grid;grid-template-columns:minmax(0,1fr);gap:22px;align-items:start}
.rev-chart{position:relative;min-width:0;padding:18px 16px 8px;border:1px solid #e2ddd6;background:#fff;box-shadow:0 1px 3px rgba(40,20,80,.06);overflow:hidden}
.rev-chart::before{content:"";display:block;height:5px;margin:-18px -16px 14px;background:linear-gradient(90deg,#5b22c9,#b8006f 62%,#c25e00)}
.rev-chart-note{max-width:68ch;margin:0 0 12px;color:#5a554e!important;font-size:15px;line-height:1.45}
.rev-rows{list-style:none;margin:0;padding:0}
.rev-row,.rev-band-label{display:grid;grid-template-columns:2rem minmax(12.5rem,17rem) minmax(0,1fr) 4.6rem;gap:8px 12px;align-items:center}
.rev-row{min-height:48px;padding:4px 6px}
.rev-rank{color:#5a554e;font:800 15px/1 "Barlow",sans-serif;font-variant-numeric:tabular-nums}
.rev-name{display:flex;flex-wrap:wrap;align-items:center;column-gap:8px;row-gap:4px;min-width:0;font-size:16px;line-height:1.25;font-weight:700}
.rev-team{display:inline-flex;align-items:center;gap:8px;min-width:0;max-width:100%;text-decoration:none}
.rev-team:hover span{text-decoration:underline;text-underline-offset:3px}
.rev-logo{display:block;width:36px;height:36px;max-width:36px;flex:0 0 36px;border-radius:50%;object-fit:cover;object-position:center 20%;border:1px solid #e2ddd6;background:#ece8f3}
.rev-logo-fallback{display:inline-flex;align-items:center;justify-content:center;color:#2a1458;background:#e9e4f5;font:800 11px/1 "Barlow",sans-serif;letter-spacing:.02em}
.rev-val{color:#2a1458;font:800 18px/1 "Barlow",sans-serif;text-align:right;font-variant-numeric:tabular-nums}
.rev-track{display:block;height:22px;background:#ece8f3;border-radius:0 4px 4px 0}
.rev-bar{display:block;position:relative;height:22px;border-radius:0 4px 4px 0;background:#5b22c9;min-width:4px}
.is-finals .rev-bar{height:26px;background:linear-gradient(90deg,#5b22c9 0%,#b8006f 68%,#c25e00 100%)}
.is-finals .rev-track{height:26px}
.is-finals{background:#fff7fb}
.rev-notch{position:absolute;top:-5px;bottom:-5px;width:2px;background:#fff;box-shadow:0 0 0 1px #2a1458}
.rev-tag{display:inline-block;margin-left:8px;padding:2px 7px;border:1px solid #b8006f;border-radius:99px;background:#fff0f6;color:#b8006f;font:800 14px/1.2 "Barlow",sans-serif;letter-spacing:.04em;text-transform:uppercase;vertical-align:1px}
.rev-band-label{margin:8px 0 0;padding:0 6px}
.rev-band-label span{grid-column:2 / -1;color:#5b22c9;font:700 15px/1.3 Inter,system-ui,sans-serif}
.is-cluster{background:#f6f1ff}
.is-cluster-first{box-shadow:inset 0 1px 0 #d8c8ff;border-radius:8px 8px 0 0}
.is-cluster-last{box-shadow:inset 0 -1px 0 #d8c8ff;border-radius:0 0 8px 8px;margin-bottom:4px}
.rev-axis-wrap{display:grid;grid-template-columns:2rem minmax(12.5rem,17rem) minmax(0,1fr) 4.6rem;gap:8px 12px;padding:6px 6px 10px}
.rev-axis{grid-column:3;position:relative;height:28px;border-top:1px solid #e2ddd6}
.rev-axis span{position:absolute;top:8px;transform:translateX(-50%);color:#5a554e;font:600 14px/1 Inter,system-ui,sans-serif;white-space:nowrap}
.rev-axis span:first-child{transform:none}
.rev-axis span:last-child{transform:translateX(-100%)}
.rev-table-col{min-width:0}
.note,.how-made{max-width:68ch;margin:12px 0 0;font-size:15px;line-height:1.5}
.data-layout{margin-top:36px}
.contents-rail{display:none}
.contents-label{margin:0 0 10px;font:800 12px/1 "Barlow",sans-serif;letter-spacing:.12em;text-transform:uppercase}
.contents-rail ul,.on-page-mobile{margin:0;padding:0;list-style:none}
.contents-rail a{display:inline-flex;align-items:center;min-height:36px;font-weight:700;text-decoration:none}
.on-page-mobile label{display:block;font-size:15px;font-weight:700}
.on-page-mobile select{display:block;width:100%;min-height:44px;margin-top:6px;padding:0 10px;font:600 16px/1.2 Inter,system-ui,sans-serif}
.fold{margin-top:12px}
.fold>summary{display:flex;align-items:center;gap:12px;min-height:52px;padding:8px 2px;cursor:pointer;list-style:none}
.fold>summary::-webkit-details-marker{display:none}
.fold>summary h2{margin:0;font:800 clamp(22px,3vw,30px)/1.15 "Barlow",sans-serif;letter-spacing:-.3px}
.fold>summary::after{content:"";flex:0 0 auto;width:10px;height:10px;margin-left:auto;border-right:2px solid #5b22c9;border-bottom:2px solid #5b22c9;transform:rotate(45deg) translateY(-2px)}
.fold[open]>summary::after{transform:rotate(-135deg) translateY(-2px)}
.fold-body{padding:0 0 18px}
.fold-body p,.fold-body li{max-width:68ch;font-size:16px;line-height:1.6}
.fold-body h3{margin:16px 0 6px;font:700 18px/1.3 "Barlow",sans-serif}
.table-wrap.wide,.table-wrap.fit{max-width:100%}
.table-wrap.wide{overflow-x:auto;-webkit-overflow-scrolling:touch}
.audience-table{width:100%;border-collapse:collapse}
.audience-table th,.audience-table td{padding:11px 10px;text-align:left;vertical-align:middle}
.audience-table .num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;font-weight:700}
.audience-table caption{caption-side:bottom;padding-top:10px;text-align:left;color:#5a554e!important;font-size:15px!important;line-height:1.45}
.audience-table tr.total th,.audience-table tr.total td{font-weight:800}
.audience-table tr.is-finals td:first-child{box-shadow:inset 3px 0 0 #b8006f}
.audience-table tr.is-cluster td:first-child{box-shadow:inset 3px 0 0 #c4b6e8}
.audience-table.revenue-table td:first-child{display:flex;flex-wrap:wrap;align-items:center;gap:4px 8px}
.cite{margin-top:12px;padding:12px 14px;border-left:3px solid #5b22c9;font-size:16px;line-height:1.5}
@media(max-width:979px){
.rev-row,.rev-band-label,.rev-axis-wrap{grid-template-columns:1.6rem minmax(0,1fr) auto}
.rev-row{grid-template-areas:"rank name val" "track track track";row-gap:10px;min-height:0;padding:10px 4px 12px}
.rev-rank{grid-area:rank}
.rev-name{grid-area:name;display:flex;flex-wrap:wrap;align-items:center;column-gap:8px;row-gap:4px;font-size:16px}
.rev-tag{margin-left:0}
.rev-notch{top:0;bottom:0}
.rev-val{grid-area:val;font-size:18px}
.rev-track{grid-area:track}
.rev-band-label span{grid-column:2 / -1}
.rev-axis-wrap{grid-template-columns:1fr;padding:2px 4px 12px}
.rev-axis{grid-column:1}
}
@media(max-width:720px){
.standings-shell{width:min(1180px,calc(100% - 28px))}
h1{font-size:34px}
.lede{font-size:17px}
.scale-list{grid-template-columns:1fr}
.cite-dot{display:none}
.rev-name,.rev-val{font-size:16px}
.rev-val{font-size:18px}
.rev-logo{width:32px;height:32px;max-width:32px;flex-basis:32px}
.rev-chart-note,.note,.scale-meta{font-size:15px}
}
@media(min-width:900px){
.cite-sticky{position:sticky;top:64px;z-index:4;margin-left:-12px;margin-right:-12px;padding:10px 12px;background:rgba(247,245,242,.96);border:1px solid #e2ddd6;box-shadow:0 8px 18px rgba(40,20,80,.06)}
.fold>summary{pointer-events:none;cursor:default}
.fold>summary::after{display:none}
.fold:not([open])>.fold-body{display:block}
}
@media(min-width:980px){
.rev-stage{grid-template-columns:minmax(0,1.6fr) minmax(280px,.72fr);gap:28px}
}
@media(min-width:1100px){
.data-layout{display:grid;grid-template-columns:180px minmax(0,1fr);column-gap:28px;align-items:start}
.data-nav{position:sticky;top:132px}
.contents-rail{display:block}
.on-page-mobile{display:none}
}
@media print{
.site-header,.ticker,.site-footer,.data-nav,.on-page-mobile,.cite-dot{display:none!important}
.cite-sticky{position:static;background:#fff;border:0;box-shadow:none;padding:0}
.rev-bar,.is-finals .rev-bar,.rev-chart::before,.scale-total{print-color-adjust:exact;-webkit-print-color-adjust:exact}
.rev-notch{background:#151413!important;box-shadow:none}
.fold:not([open])>.fold-body{display:block!important}
.fold>summary{pointer-events:none}
.fold>summary::after{display:none}
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
    image = Image.new('RGB', (1200, 630), '#0b0b10')
    draw = ImageDraw.Draw(image)
    font_dir = ROOT / 'assets' / 'fonts'
    display = ImageFont.truetype(str(font_dir / 'BarlowCondensed-ExtraBold.ttf'), 72)
    med = ImageFont.truetype(str(font_dir / 'Inter-Bold.ttf'), 26)
    small = ImageFont.truetype(str(font_dir / 'Inter-Medium.ttf'), 22)
    label = ImageFont.truetype(str(font_dir / 'Inter-Bold.ttf'), 18)
    for x in range(1200):
        t = x / 1199
        if t < 0.5:
            a, b, u = (125, 53, 255), (241, 0, 145), t * 2
        else:
            a, b, u = (241, 0, 145), (255, 152, 0), (t - 0.5) * 2
        color = tuple(int(a[i] + (b[i] - a[i]) * u) for i in range(3))
        draw.line([(x, 0), (x, 8)], fill=color)
    draw.text((48, 22), 'WNBA TEAM REVENUE, RANKED', font=small, fill='#f10091')
    draw.text((48, 48), '2025 season', font=display, fill='#f5f3ef')
    draw.text((700, 40), f'Nearly 5{TIMES}', font=display, fill='#ffffff')
    draw.text((700, 118), 'Golden State $78M to Atlanta $16M', font=med, fill='#ffb0dc')
    draw.text((48, 128), 'Combined $430M', font=med, fill='#ffffff')
    bars = (
        ('GS', 78, True), ('IND', 58, False), ('NY', 43, False), ('LV', 34, False),
        ('CHI', 30, False), ('DAL', 28, False), ('LA', 28, False), ('PHX', 28, False),
        ('SEA', 28, False), ('MIN', 21, False), ('CON', 20, False), ('WAS', 18, False),
        ('ATL', 16, True),
    )
    top, left, plot = 168, 120, 860
    row_h = 32
    for abbr, amount, finals in bars:
        y = top
        top += row_h
        width = max(8, plot * amount / 78)
        if abbr in {'DAL', 'LA', 'PHX', 'SEA'}:
            draw.rectangle((40, y - 4, 1160, y + 26), fill='#161228')
        draw.text((108, y + 1), abbr, font=label, fill='#f5f3ef', anchor='ra')
        color = '#f10091' if finals else '#7d35ff'
        draw.rectangle((left, y, left + width, y + 16), fill=color)
        if abbr == 'GS':
            mark = left + plot * 16 / 78
            draw.rectangle((mark, y - 3, mark + 2, y + 19), fill='#ffffff')
        draw.text((left + width + 8, y - 1), f'${amount}M', font=label, fill='#f5f3ef')
    draw.text((48, 590), 'Full Court Buckets. Forbes estimates, May 2026. Playoffs excluded. Four teams tied at $28M.', font=small, fill='#b4bbc7')
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, 'PNG')
    webp = path.with_suffix('.webp')
    image.save(webp, 'WEBP', quality=86)


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
        insert = marker + '<li><a href="/wnba/team-revenue/">WNBA team revenue, ranked</a></li>'
        html_map.write_text(page.replace(marker, insert, 1), encoding='utf-8')
    else:
        old = '<li><a href="/wnba/team-revenue/">WNBA team revenue and franchise values</a></li>'
        new = '<li><a href="/wnba/team-revenue/">WNBA team revenue, ranked</a></li>'
        if old in page:
            html_map.write_text(page.replace(old, new, 1), encoding='utf-8')


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
