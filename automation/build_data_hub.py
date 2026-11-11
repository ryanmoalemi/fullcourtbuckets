#!/usr/bin/env python3
"""Data and research hub at /wnba/data/.

Lists the datasets that already have a page. It does not repeat the methods
essay at /methods/. Dates and formats come from the files those pages publish.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import site_nav

ROOT = Path(__file__).resolve().parents[1]
ROUTE = '/wnba/data/'
TITLE = 'WNBA data and research: revenue, attendance, owners'
DESCRIPTION = (
    'Full Court Buckets datasets: 2025 team revenue, Finals attendance, '
    'WNBA owners, and bars that show the games. Each card lists the update, format and source.'
)


def _modified(route: str) -> str:
    """dateModified from the page's own JSON-LD, so the hub never lags the page."""
    path = ROOT / route.strip('/') / 'index.html'
    try:
        text = path.read_text(encoding='utf-8')
    except OSError:
        return ''
    match = re.search(r'"dateModified"\s*:\s*"(\d{4}-\d{2}-\d{2})', text)
    return match.group(1) if match else ''


def _label(day: str) -> str:
    try:
        return datetime.strptime(day, '%Y-%m-%d').strftime('%b. %-d, %Y').replace('May.', 'May')
    except ValueError:
        return ''


# (route, title, format, scope). Every route must publish a page; missing ones are skipped.
ROWS = (
    ('/news/2026-wnba-finals-ratings-tracker/', 'Finals ratings and attendance database', 'Searchable table, CSV',
     'Every WNBA Finals game since 2002 with attendance and viewers, each tied to its official record.'),
    ('/wnba/viewership-attendance/', 'Viewership and attendance', 'CSV',
     'Season and Finals viewership, regular-season attendance and network splits, with sources for each figure.'),
    ('/wnba/team-revenue/', 'Team revenue and franchise values', 'CSV and JSON',
     'Forbes 2025 revenue and 2026 franchise values for 13 teams, ranked, with value per dollar of revenue.'),
    ('/wnba/owners/', 'Owners', 'CSV',
     'Controlling owners, disclosed investors and facility projects for the 15 teams, each claim linked to a document.'),
    ('/standings/', 'Standings', 'CSV',
     'Final 2026 regular-season standings with records, percentage and games back.'),
    ('/wnba/coaching-tracker/', 'Coaching tracker', 'Table',
     'Head coach openings, hires and vacancy clocks for the 2027 season, dated to when each status was checked.'),
    ('/news/wnba-free-agents-2027/', '2027 free agents', 'Table',
     'Players whose contracts end after 2026 and the share of 2026 production that could reach the market.'),
    ('/wnba/draft-lottery-2027/', '2027 draft lottery', 'Simulator, CSV',
     'Exact chance each 2027 lottery slot lands picks 1 through 7, from the Oct. 28, 2026 league release, plus a draw simulator.'),
    ('/wnba/where-to-watch/', 'Where to watch', 'Searchable directory, CSV',
     'Bars and restaurants that show WNBA games, from team watch-party pages, venue pages and written staff replies.'),
)


def cards() -> str:
    items = []
    for href, title, fmt, scope in ROWS:
        if not (ROOT / href.strip('/') / 'index.html').is_file():
            continue
        day = _modified(href)
        meta = f'Updated {_label(day)}. {fmt}.' if day else f'{fmt}.'
        items.append(
            f'<li><h2><a href="{href}">{title}</a></h2>'
            f'<p class="data-meta">{meta}</p><p>{scope}</p></li>'
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
        '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@600;700;800&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">'
        '<style>body{font-family:Inter,system-ui,sans-serif}main.shell{width:min(1100px,calc(100% - 32px));margin:0 auto;padding:28px 0 64px;color:#151413}'
        'main.shell h1{margin:0 0 10px;font:800 clamp(34px,5vw,52px)/1.05 Barlow,sans-serif;letter-spacing:-.5px;color:#2a1458}'
        'main.shell>p{max-width:65ch;font-size:16px;line-height:1.55;margin:0 0 20px}'
        '.data-hub{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}'
        '.data-hub li{margin:0;padding:16px;border:1px solid #e2ddd6;border-top:4px solid #5b22c9;background:#fff;border-radius:6px}'
        '.data-hub h2{margin:0;font:800 20px/1.2 Barlow,sans-serif}.data-hub h2 a{color:#2a1458}'
        '.data-hub p{margin:6px 0 0;font-size:15px;line-height:1.45}.data-hub .data-meta{font-size:13px;font-weight:600;color:#5a554e}</style>'
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
