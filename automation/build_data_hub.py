#!/usr/bin/env python3
"""Data and research hub at /wnba/data/.

Lists the datasets that already have a page. It does not repeat the methods
essay at /methods/. Dates and formats come from the files those pages publish.
"""
from __future__ import annotations

import json
from pathlib import Path

import site_nav

ROOT = Path(__file__).resolve().parents[1]
ROUTE = '/wnba/data/'
TITLE = 'WNBA data and research: revenue, attendance, owners'
DESCRIPTION = (
    'Full Court Buckets datasets: 2025 team revenue, Finals attendance, '
    'WNBA owners, and bars that show the games. Each card lists the update, format and source.'
)


def _day(path: Path, key: str) -> str:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return ''
    return str(data.get(key) or '')[:10]


def cards() -> str:
    revenue_day = '2026-10-31'
    attendance_day = _day(ROOT / 'data' / 'viewership-attendance.json', 'updated') or '2026-11-03'
    owners_day = '2026-10-19'
    watch_day = '2026-11-04'
    rows = [
        (
            '/wnba/team-revenue/',
            'Team revenue',
            f'Updated {revenue_day}. CSV and JSON.',
            'Forbes 2025 revenue and 2026 franchise values for 13 teams. Portland and Toronto are outside that dataset.',
        ),
        (
            '/wnba/viewership-attendance/',
            'Finals attendance',
            f'Updated {attendance_day}. CSV.',
            'WNBA Finals attendance and viewership in the FCB archive since 2002, each game tied to its official record.',
        ),
        (
            '/wnba/owners/',
            'Owners',
            f'Updated {owners_day}. CSV.',
            'Controlling owners, disclosed investors and facility projects for the 15 teams, each claim linked to a document.',
        ),
        (
            '/wnba/where-to-watch/',
            'Where to watch',
            f'Updated {watch_day}. CSV.',
            'Bars and restaurants that show WNBA games, from team watch-party pages, venue pages and written staff replies.',
        ),
    ]
    items = []
    for href, title, meta, scope in rows:
        items.append(
            f'<li><a href="{href}"><strong>{title}</strong></a>'
            f'<p>{meta}</p><p>{scope}</p></li>'
        )
    return '<ul class="data-hub">' + ''.join(items) + '</ul>'


def render() -> str:
    menu = site_nav.build_menu(ROOT)
    body = (
        f'<main id="content" class="shell"><h1>Data and research</h1>'
        '<p>These are the datasets on this site. Each one names when it was last updated, '
        'the file format, and what the source covers. How the numbers are checked is on '
        '<a href="/methods/">How we calculate</a>.</p>'
        f'{cards()}'
        '</main>'
    )
    header = site_nav.render_header(menu, ROUTE)
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{TITLE}</title>'
        f'<meta name="description" content="{DESCRIPTION}">'
        '<meta name="robots" content="index,follow">'
        f'<link rel="canonical" href="https://fullcourtbuckets.com{ROUTE}">'
        '<link rel="icon" href="/favicon.svg">'
        '<link rel="stylesheet" href="/assets/site-nav.css">'
        '<style>.data-hub{list-style:none;padding:0}.data-hub li{margin:0 0 18px;max-width:65ch}'
        '.data-hub p{margin:4px 0}</style>'
        '</head><body>'
        f'{site_nav.SKIP_LINK}{header}{body}{site_nav.footer_html()}'
        '<script src="/assets/site-nav.js" defer></script></body></html>'
    )


def main() -> None:
    path = ROOT / 'wnba' / 'data' / 'index.html'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(), encoding='utf-8')
    print(path)


if __name__ == '__main__':
    main()
