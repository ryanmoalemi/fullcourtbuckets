"""Citation boxes, embed snippets, and dataset markup.

Every figure here is copied from a published page or from
data/viewership-attendance.json. A figure that is not in those sources
is labeled unavailable and is not estimated.
"""
from __future__ import annotations

import csv
import html
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = 'https://fullcourtbuckets.com'
CC_BY = 'https://creativecommons.org/licenses/by/4.0/'
WNBA_FINALS_RELEASE = 'https://www.wnba.com/news/wnba-finals-games3-and-4-to-be-played-at-state-farm-arena'
VIEWERSHIP_URL = BASE + '/news/wnba-finals-2026-audience-growth-dream-valkyries/'
TRACKER_SLUG = '2026-wnba-finals-ratings-tracker'
TRACKER_PATH = '/news/' + TRACKER_SLUG + '/'
TRACKER_URL = BASE + TRACKER_PATH
DATA_PAGE_PATH = '/wnba/viewership-attendance/'
CARDS_URL = BASE + '/news/top-10-womens-college-basketball-cards-to-collect-2026/'
EXPANSION_URL = BASE + '/news/wnba-expansion-teams/'
LIBERTY_URL = BASE + '/news/liberty-offseason-five-gm-moves/'
STANDINGS_URL = BASE + '/standings/'

MEDIA_LINE = (
    'Media, data citations & editorial: ryan@fullcourtbuckets.com | '
    'General: hello@fullcourtbuckets.com'
)


def esc(value) -> str:
    return html.escape('' if value is None else str(value), quote=True)


class HTML:
    """A cell or list item that is already safe markup."""

    def __init__(self, value: str):
        self.value = value


def _as_html(value) -> str:
    if isinstance(value, HTML):
        return value.value
    return esc(value)


def media_line_html() -> str:
    return (
        '<p class="media-contact">Media, data citations &amp; editorial: '
        '<a href="mailto:ryan@fullcourtbuckets.com">ryan@fullcourtbuckets.com</a>'
        ' | General: '
        '<a href="mailto:hello@fullcourtbuckets.com">hello@fullcourtbuckets.com</a></p>'
    )


def quick_cite(items: list, citation: str) -> str:
    bullets = '\n'.join(f'<li>{_as_html(item)}</li>' for item in items)
    return (
        '<aside class="fcb-quick-cite" aria-label="Fast facts for media and citations">\n'
        '<p class="fcb-quick-cite-title">Fast Facts for Media &amp; Citations</p>\n'
        f'<ul>\n{bullets}\n</ul>\n'
        '<div class="fcb-actions">\n'
        '<button type="button" class="fcb-copy-citation">Copy Citation &amp; Link</button>\n'
        '</div>\n'
        f'<textarea class="fcb-citation-source" hidden readonly>{esc(citation)}</textarea>\n'
        '</aside>'
    )


def embed_snippet(page_url: str, anchor: str, image: str = '', image_alt: str = '') -> str:
    """Three-line embed: an iframe or an image, the attribution link, and the license."""
    deep = f'{page_url}#{anchor}' if anchor else page_url
    if image:
        first = f'<img src="{image}" alt="{image_alt}">'
    else:
        first = (
            f'<iframe src="{deep}" title="Full Court Buckets" '
            'width="100%" height="420" style="border:0"></iframe>'
        )
    return '\n'.join([
        first,
        f'<a href="{deep}">Source: Full Court Buckets</a>',
        f'<a href="{CC_BY}">CC BY 4.0</a>',
    ])


def embed_block(anchor: str, snippet: str, csv_href: str = '') -> str:
    csv_link = ''
    if csv_href:
        csv_link = f'<a class="fcb-csv" href="{esc(csv_href)}" download>Download CSV</a>'
    return (
        '<div class="fcb-embed">\n'
        '<div class="fcb-actions">\n'
        f'<button type="button" class="fcb-embed-toggle" aria-expanded="false" '
        f'aria-controls="embed-{esc(anchor)}">&lt; &gt; Embed / Cite Data</button>\n'
        f'{csv_link}\n'
        '</div>\n'
        f'<div class="fcb-embed-panel" id="embed-{esc(anchor)}" hidden>\n'
        '<p class="fcb-embed-note">Free to republish with link attribution (CC BY 4.0).</p>\n'
        f'<textarea readonly rows="4">{esc(snippet)}</textarea>\n'
        '<button type="button" class="fcb-copy-embed">Copy Embed Code</button>\n'
        '</div>\n'
        '</div>'
    )


def data_table(headers: list, rows: list, caption: str = '', table_id: str = '') -> str:
    head = ''.join(f'<th scope="col">{esc(header)}</th>' for header in headers)
    body = []
    for row in rows:
        cells = ''.join(f'<td>{_as_html(cell)}</td>' for cell in row)
        body.append(f'<tr>{cells}</tr>')
    cap = f'<caption>{caption}</caption>' if caption else ''
    ident = f' id="{esc(table_id)}"' if table_id else ''
    return (
        f'<div class="fcb-table-wrap"{ident}>'
        f'<table class="fcb-data-table">{cap}<thead><tr>{head}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>'
    )


def dataset_script(name: str, description: str, url: str, csv_url: str) -> str:
    payload = {
        '@context': 'https://schema.org',
        '@type': 'Dataset',
        'name': name,
        'description': description,
        'url': url,
        'creator': {
            '@type': 'Organization',
            'name': 'Full Court Buckets',
            'url': BASE + '/',
        },
        'license': CC_BY,
        'isAccessibleForFree': True,
        'distribution': {
            '@type': 'DataDownload',
            'encodingFormat': 'text/csv',
            'contentUrl': csv_url,
        },
    }
    raw = json.dumps(payload, ensure_ascii=False).replace('<', '\\u003c')
    return f'<script type="application/ld+json">{raw}</script>'


def write_csv(path: Path, headers: list, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def _comma(value: int) -> str:
    return f'{value:,}'


# Games 1-4 dates, tip times, and venues are the rows in
# data/viewership-attendance.json, from the WNBA release of Oct. 13, 2026.
# Networks for games 2, 3, and 5-7 are USA and Peacock. Games 1 and 4 are
# NBC and Peacock. NBC Sports (Oct. 13, 2026) and the Valkyries Game 1 preview
# list those networks. Games 5-7 dates and tip times are not in the WNBA release.
NBC_FINALS_NETWORKS = 'https://www.nbcsports.com/wnba/news/wnba-finals-games-3-and-4-between-dream-and-valkyries-move-to-state-farm-arena'
VALKYRIES_FINALS_PREVIEW = 'https://valkyries.wnba.com/news/gameday-preview-20261017'
FINALS_TRACKER_ROWS = [
    ['1', 'Sat, Oct. 17, 2026', 'Atlanta Dream at Golden State Valkyries, Chase Center',
     'NBC, Peacock', '3:30 p.m. ET / 12:30 p.m. PT', 'Pending tip-off', 'Pending tip-off',
     'Pending tip-off', 'Scheduled'],
    ['2', 'Mon, Oct. 19, 2026', 'Atlanta Dream at Golden State Valkyries, Chase Center',
     'USA and Peacock', '8:00 p.m. ET / 5:00 p.m. PT', 'Pending tip-off', 'Pending tip-off',
     'Pending tip-off', 'Scheduled'],
    ['3', 'Wed, Oct. 21, 2026', 'Golden State Valkyries at Atlanta Dream, State Farm Arena',
     'USA and Peacock', '8:00 p.m. ET / 5:00 p.m. PT', 'Pending tip-off', 'Pending tip-off',
     'Pending tip-off', 'Scheduled'],
    ['4', 'Sat, Oct. 24, 2026', 'Golden State Valkyries at Atlanta Dream, State Farm Arena',
     'NBC and Peacock', '1:00 p.m. ET / 10:00 a.m. PT', 'Pending tip-off', 'Pending tip-off',
     'Pending tip-off', 'Scheduled'],
    ['5', 'Not listed', 'If necessary', 'USA and Peacock',
     'Not listed', 'Pending tip-off', 'Pending tip-off', 'Pending tip-off', 'If necessary'],
    ['6', 'Not listed', 'If necessary', 'USA and Peacock',
     'Not listed', 'Pending tip-off', 'Pending tip-off', 'Pending tip-off', 'If necessary'],
    ['7', 'Not listed', 'If necessary', 'USA and Peacock',
     'Not listed', 'Pending tip-off', 'Pending tip-off', 'Pending tip-off', 'If necessary'],
]
TRACKER_CAPTION = (
    'Games 1-4: date, tip time, and venue from the WNBA release of Oct. 13, 2026. '
    'Games 2 and 3, and games 5-7 if necessary, are on USA and Peacock. '
    'Games 1 and 4 are on NBC and Peacock. '
    'NBC Sports and the Golden State Valkyries published those networks. '
    'Viewer cells stay pending until a network releases them. '
    'The WNBA release does not list dates or tip times for games 5-7.'
)

# The ratings page reads this file. Last updated is its last change, not a typed date.
VIEWERSHIP_DATA_REL = 'data/viewership-attendance.json'

FINALS_TRACKER_HEADERS = [
    'Game', 'Date', 'Matchup', 'Network', 'Tip time', 'Overnight rating',
    'Avg. viewers', 'Peak viewers', 'Status',
]

VIEWERSHIP_CITE = (
    'Full Court Buckets, "WNBA Finals arrive after 51 games topped 1 million viewers," '
    'October 11, 2026.\n'
    f'{VIEWERSHIP_URL}\n'
    '51 regular-season telecasts exceeded 1 million viewers in 2026, up from 19 in 2025 '
    '(about 2.7 times as many). ESPN-network games without Indiana averaged 984,000 viewers, '
    'up 24%. The 10-game first round averaged 1.3 million, up 37%. October 2026 US search '
    'estimates: Atlanta Dream 1.22 million, Angel Reese 1.0 million, Golden State Valkyries 550,000.'
)

AUDIENCE_ROWS = [
    ['ESPN networks regular season, 29 games', '1.37 million', 'Up 17%'],
    ['ESPN networks games without Indiana', '984,000', 'Up 24%'],
    ['Playoff first round, 10 games', '1.3 million', 'Up 37%'],
    ['Semifinal opening games, 2 games', '1.15 million', 'Up 10%'],
]

SEARCH_ROWS = [
    ['Atlanta Dream', '1.22 million'],
    ['Angel Reese', '1.0 million'],
    ['Golden State Valkyries', '550,000'],
    ['Gabby Williams', '60,500'],
    ['WNBA Finals', '60,500'],
]

PLAYOFF_COMPARE_ROWS = [
    ['Gabby Williams', '6', '22.7', '4.8', '0.0', '1.7', '44.9', '40.5', '92.0'],
    ['Angel Reese', '5', '18.0', '8.4', '2.2', '1.6', '43.3', '38.5', '87.1'],
]


def finals_history_rows(payload: dict) -> list[list[str]]:
    """Finals averages stored with a source. Years that are absent stay unavailable."""
    by_year = {}
    for row in payload.get('seasons') or []:
        year = row.get('season')
        if year in by_year:
            continue
        if row.get('finals_avg_viewers') and row.get('finals_viewers_source'):
            by_year[year] = row
    rows = []
    for year in range(2020, 2027):
        row = by_year.get(year)
        if not row:
            label = 'Pending tip-off' if year == 2026 else 'Not in the Full Court Buckets viewership file'
            rows.append([str(year), label, label, label, label])
            continue
        rows.append([
            str(year),
            str(row.get('finals_matchup') or ''),
            str(row.get('finals_games') if row.get('finals_games') is not None else ''),
            _comma(int(row['finals_avg_viewers'])),
            str(row.get('finals_network') or ''),
        ])
    return rows


def viewership_blocks(payload: dict) -> dict:
    cite = quick_cite([
        HTML('<strong>51</strong> regular-season telecasts exceeded 1 million viewers in 2026, up from <strong>19</strong> in 2025 (about 2.7 times as many).'),
        HTML('ESPN-network games without Indiana averaged <strong>984,000</strong> viewers, up 24%. The 10-game first round averaged <strong>1.3 million</strong>, up 37%.'),
        HTML('October 2026 US search estimates: Atlanta Dream <strong>1.22 million</strong>, Angel Reese <strong>1.0 million</strong>, Golden State Valkyries <strong>550,000</strong>.'),
    ], VIEWERSHIP_CITE)
    tracker = (
        '<h2 class="section-title" id="finals-ratings-tracker">2026 WNBA Finals game-by-game ratings</h2>\n'
        + data_table(
            FINALS_TRACKER_HEADERS,
            FINALS_TRACKER_ROWS,
            caption=TRACKER_CAPTION,
        )
        + '\n' + finals_network_note() + '\n'
        + embed_block(
            'finals-ratings-tracker',
            embed_snippet(TRACKER_URL, 'finals-ratings-tracker'),
            'finals-ratings.csv',
        )
    )
    history = (
        '<h2 class="section-title" id="finals-average-viewers">Finals average viewers, where a source is on file</h2>\n'
        + data_table(
            ['Season', 'Matchup', 'Games', 'Average viewers', 'Network'],
            finals_history_rows(payload),
            caption=(
                '2022 through 2025 averages are the sourced rows in the Full Court Buckets viewership file. '
                '2020 and 2021 are not in that file. 2026 is pending tip-off. '
                'This is not a complete history.'
            ),
        )
        + '\n'
        + embed_block(
            'finals-average-viewers',
            embed_snippet(TRACKER_URL, 'finals-average-viewers'),
            'finals-ratings.csv',
        )
    )
    return {'cite': cite, 'tracker': tracker + '\n' + history}


def viewership_csv_rows(payload: dict) -> tuple[list, list]:
    headers = ['section', 'label', 'value', 'comparison', 'network', 'status', 'notes']
    rows = []
    for label, value, change in AUDIENCE_ROWS:
        rows.append(['2026 audience averages', label, value, change, '', 'Reported', 'Published on this page'])
    for name, volume in SEARCH_ROWS:
        rows.append(['October 2026 US search estimates', name, volume, '', '', 'Estimate', 'Full Court Buckets keyword research'])
    for row in PLAYOFF_COMPARE_ROWS:
        rows.append(['2026 playoffs per game', row[0], row[2] + ' PPG', row[3] + ' RPG', '', 'FCB verified', 'GP ' + row[1]])
    for row in FINALS_TRACKER_ROWS:
        rows.append(['2026 Finals tracker', 'Game ' + row[0], row[1], row[2], row[3], row[8], row[4]])
    for row in finals_history_rows(payload):
        rows.append(['Finals average viewers', row[0], row[3], row[1], row[4], row[3], 'Games ' + row[2]])
    return headers, rows


# Benchmarks that are both in the published audience article and, where a level
# is stored, in data/viewership-attendance.json. The 24% and 37% comparisons
# are the published wording. They are not a 168% claim.
TRACKER_BENCHMARK_ROWS = [
    ['Regular-season telecasts over 1 million viewers', '51 in 2026, 19 in 2025', 'About 2.7 times as many',
     'Sports Business Journal, Sept. 30, 2026'],
    ['ESPN and ABC games without the Fever', '984,000', 'Up 24%',
     'Front Office Sports, Sept. 25, 2026, for the average. The 24% comparison is the one on the audience article, credited there to the ESPN release of Sept. 25, 2026.'],
    ['Playoff first round, 10 games', '1.3 million', 'Up 37%',
     "Just Women's Sports, Oct. 8, 2026; Front Office Sports, Colin Salao, Oct. 6, 2026"],
    ['Semifinal opening games, 2 games', '1.15 million', 'Up 10%',
     'Front Office Sports, Oct. 7, 2026'],
    ['Liberty at Dream, semifinals Game 2', '1.4 million', 'One game',
     'Sports Media Watch, Oct. 13, 2026'],
]

TRACKER_CITE = (
    'Full Court Buckets, "2026 WNBA Finals ratings tracker: game-by-game TV viewers," '
    'October 14, 2026.\n'
    f'{TRACKER_URL}\n'
    'Past Finals averages: 2022 534K, 2023 728K, 2024 1.6M, 2025 1.5M. '
    'NBC and Peacock averaged 1.75 million across 7 regular-season games, TV and streaming. '
    '51 regular-season telecasts exceeded 1 million viewers in 2026, up from 19 in 2025 '
    '(about 2.7 times as many). Games without the Fever averaged 984,000 viewers, '
    'up 24%. The 10-game first round averaged 1.3 million, up 37%. October 2026 US search '
    'estimates: Atlanta Dream 1.22 million, Angel Reese 1.0 million, Golden State Valkyries 550,000. '
    'Games 1-4 follow the WNBA release of Oct. 13, 2026. Games 5-7 are not listed. '
    'Viewer cells are pending tip-off.'
)

SBJ_51_URL = 'https://www.sportsbusinessjournal.com/Articles/2026/09/30/wnba-has-best-regular-season-viewership-since-2000-in-year-1-of-new-media-deal/'
FOS_GROWTH_URL = 'https://frontofficesports.com/article/wnba-continues-attendance-viewership-growth/'
ESPN_REGULAR_SEASON_RELEASE = 'https://espnpressroom.com/press-release/espn-delivered-its-most-watched-wnba-regular-season-ever/'
JWS_FIRST_ROUND_URL = 'https://justwomenssports.com/reads/wnba-playoffs-viewership-semifinals-ratings-surge/'
FOS_FIRST_ROUND_URL = 'https://frontofficesports.com/article/wnba-playoffs-deliver-most-watched-first-round-ever/'
FOS_SEMIS_URL = 'https://frontofficesports.com/article/wnba-semifinals-open-with-1-15m-viewers-up-10/'
SMW_RATINGS_TRACKER_URL = 'https://www.sportsmediawatch.com/sports-ratings-tracker/'


def finals_tracker_data_path(root: Path) -> Path:
    return root / VIEWERSHIP_DATA_REL


def pacific_calendar_date(moment: datetime):
    """Calendar day in America/Los_Angeles. A naive timestamp is UTC."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(ZoneInfo('America/Los_Angeles')).date()


def finals_tracker_updated(root: Path):
    """Pacific calendar date of the viewership file's last change.

    A committed file uses the git commit instant, converted to
    America/Los_Angeles. An uncommitted edit uses the file's modification
    time in that same zone. The label is never typed into the page.
    """
    path = finals_tracker_data_path(root)
    try:
        status = subprocess.run(
            ['git', '-C', str(root), 'status', '--porcelain', '--', VIEWERSHIP_DATA_REL],
            check=False,
            capture_output=True,
            text=True,
        )
        if status.returncode == 0 and status.stdout.strip():
            return pacific_calendar_date(datetime.fromtimestamp(path.stat().st_mtime, timezone.utc))
        log = subprocess.run(
            ['git', '-C', str(root), 'log', '-1', '--format=%ct', '--', VIEWERSHIP_DATA_REL],
            check=False,
            capture_output=True,
            text=True,
        )
        stamp = log.stdout.strip()
        if log.returncode == 0 and stamp.isdigit():
            return pacific_calendar_date(datetime.fromtimestamp(int(stamp), timezone.utc))
    except (OSError, ValueError):
        pass
    return pacific_calendar_date(datetime.fromtimestamp(path.stat().st_mtime, timezone.utc))


def finals_tracker_updated_label(root: Path) -> str:
    day = finals_tracker_updated(root)
    return f'{day.strftime("%B")} {day.day}, {day.year}'


def finals_tracker_update_callout(root: Path) -> str:
    """Update note after the quick cite. The date is the data file's last change."""
    label = esc(finals_tracker_updated_label(root))
    return (
        '<aside class="fcb-tracker-update" aria-label="How this tracker is updated">\n'
        '<p>How this tracker is updated: After each Finals game, we add average viewers, '
        'peak audience and overnight rating once the network that aired it releases them, '
        'usually within 1 to 2 days. Every number is checked against the network\'s own release '
        f'before it goes up. Last updated: {label}.</p>\n'
        '</aside>'
    )


def finals_network_note() -> str:
    """Dates from the WNBA release. Networks from NBC Sports and the Valkyries."""
    return (
        f'<p class="fcb-note">Schedule dates for games 1-4: <a href="{esc(WNBA_FINALS_RELEASE)}">WNBA release, Oct. 13, 2026</a>. '
        f'Networks: <a href="{esc(NBC_FINALS_NETWORKS)}">NBC Sports, Oct. 13, 2026</a> and the '
        f'<a href="{esc(VALKYRIES_FINALS_PREVIEW)}">Valkyries Game 1 preview</a>. '
        'Games 2, 3, and 5-7 are USA and Peacock. Games 1 and 4 are NBC and Peacock. '
        'Full Court Buckets gathers and verifies its own data. A network audience is credited to the network that released it.</p>'
    )


def ratings_hub_crosslink() -> str:
    """Pointer from the audience story. The table itself stays on the hub."""
    return (
        '<h2 class="section-title" id="finals-ratings-tracker">'
        '<span id="finals-ratings-hub"></span>'
        'Game-by-game Finals ratings</h2>\n'
        '<p>This page is the season-long audience story. The game-by-game sheet, using the '
        f'<a href="{esc(WNBA_FINALS_RELEASE)}">WNBA release of Oct. 13, 2026</a>, is the '
        f'<a href="{TRACKER_PATH}#finals-ratings-tracker">2026 WNBA Finals ratings tracker</a>. '
        'Multi-year attendance and viewership stay on the '
        f'<a href="{DATA_PAGE_PATH}">viewership and attendance page</a>.</p>'
    )


def ratings_hub_blocks(payload: dict) -> str:
    """Game-by-game hub. Schedule rows and history come from the shared tracker."""
    cite = quick_cite([
        HTML('<strong>51</strong> regular-season telecasts exceeded 1 million viewers in 2026, up from <strong>19</strong> in 2025 (about 2.7 times as many).'),
        HTML('Games without the Fever averaged <strong>984,000</strong> viewers, up 24%. The 10-game first round averaged <strong>1.3 million</strong>, up 37%.'),
        HTML('October 2026 US search estimates: Atlanta Dream <strong>1.22 million</strong>, Angel Reese <strong>1.0 million</strong>, Golden State Valkyries <strong>550,000</strong>.'),
    ], TRACKER_CITE)
    tracker = (
        '<h2 class="section-title" id="finals-ratings-tracker">2026 WNBA Finals game-by-game ratings</h2>\n'
        '<p>Games 1 through 4 are the only ones dated in the Oct. 13, 2026 WNBA release. '
        'Games 5, 6 and 7 are if necessary. That release does not list a date or a tip time for them, so those cells say Not listed. '
        'NBC Sports and the Valkyries list games 5-7 on USA and Peacock. '
        'Average viewers, peak audience, and the overnight rating stay Pending tip-off until the network that aired the game releases a number.</p>\n'
        + data_table(
            FINALS_TRACKER_HEADERS,
            FINALS_TRACKER_ROWS,
            caption=TRACKER_CAPTION,
        )
        + '\n' + finals_network_note() + '\n'
        + embed_block(
            'finals-ratings-tracker',
            embed_snippet(TRACKER_URL, 'finals-ratings-tracker'),
            'finals-ratings.csv',
        )
    )
    benchmarks = (
        '<h2 class="section-title" id="finals-benchmarks">Regular-season and playoff benchmarks</h2>\n'
        '<p>These are the published comparisons around this Finals, not a forecast. '
        f'The season-long story is <a href="/news/wnba-finals-2026-audience-growth-dream-valkyries/">WNBA Finals arrive after 51 games topped 1 million viewers</a>. '
        f'The multi-year file is the <a href="{DATA_PAGE_PATH}">viewership and attendance page</a>.</p>\n'
        + data_table(
            ['Measure', '2026 figure', 'Comparison', 'Where it is published'],
            TRACKER_BENCHMARK_ROWS,
            caption=(
                '51 and 19 count telecasts over 1 million viewers. That is about 2.7 times as many games, not 51 million people. '
                '984,000 is the stored average for ESPN and ABC games without the Fever.'
            ),
        )
        + '\n<p class="fcb-note">Sources: '
        f'<a href="{esc(SBJ_51_URL)}">Sports Business Journal, Sept. 30, 2026</a> (51 and 19). '
        f'<a href="{esc(FOS_GROWTH_URL)}">Front Office Sports, Sept. 25, 2026</a> (984,000). '
        f'The up 24% comparison is the one on the audience article, credited there to the '
        f'<a href="{esc(ESPN_REGULAR_SEASON_RELEASE)}">ESPN release, Sept. 25, 2026</a>. '
        f'<a href="{esc(JWS_FIRST_ROUND_URL)}">Just Women\'s Sports, Oct. 8, 2026</a> '
        f'and <a href="{esc(FOS_FIRST_ROUND_URL)}">Front Office Sports, Colin Salao, Oct. 6, 2026</a> '
        '(first round, 1.3 million, up 37%). '
        f'<a href="{esc(FOS_SEMIS_URL)}">Front Office Sports, Oct. 7, 2026</a> (semifinal openers). '
        f'<a href="{esc(SMW_RATINGS_TRACKER_URL)}">Sports Media Watch, Oct. 13, 2026</a> '
        '(Liberty at Dream, semifinals Game 2, 1.4 million average).</p>\n'
        + embed_block(
            'finals-benchmarks',
            embed_snippet(TRACKER_URL, 'finals-benchmarks'),
            'finals-ratings.csv',
        )
        + '\n<h3 id="october-search-interest">October search interest</h3>\n'
        '<p>Television averages count viewers. Search volume counts queries. '
        'Full Court Buckets keyword research estimates US monthly Google searches for October 2026 at '
        '1.22 million for the Atlanta Dream, 1.0 million for Angel Reese, 550,000 for the Golden State Valkyries, '
        'and 60,500 each for Gabby Williams and WNBA Finals. Searches are not unique fans.</p>\n'
        + data_table(
            ['Query', 'Estimated US monthly searches, October 2026'],
            SEARCH_ROWS,
            caption='Full Court Buckets keyword research. Estimates, not a television audience.',
        )
        + '\n'
        + embed_block(
            'october-search-interest',
            embed_snippet(TRACKER_URL, 'october-search-interest'),
            'finals-ratings.csv',
        )
    )
    history = (
        '<h2 class="section-title" id="finals-average-viewers">Finals average viewers, where a source is on file</h2>\n'
        + data_table(
            ['Season', 'Matchup', 'Games', 'Average viewers', 'Network'],
            finals_history_rows(payload),
            caption=(
                '2022 through 2025 averages are the sourced rows in the Full Court Buckets viewership file. '
                '2020 and 2021 are not in that file. 2026 is pending tip-off. '
                'This is not a complete history. Each release is linked from the viewership and attendance page.'
            ),
        )
        + '\n<p class="fcb-note">The network column is who aired the series. '
        'It is not a credit to a stats feed. Full Court Buckets gathers and verifies its own data.</p>\n'
        + embed_block(
            'finals-average-viewers',
            embed_snippet(TRACKER_URL, 'finals-average-viewers'),
            'finals-ratings.csv',
        )
        + '\n<h2 class="section-title" id="figures-left-off">Figures left off this page</h2>\n'
        '<ul>\n'
        '<li>1.37 million across 29 regular-season games, up 17%. The audience article prints it. The viewership file instead lists a 1.4 million ESPN and ABC average and does not give a game count, so neither figure is used as a benchmark here.</li>\n'
        '<li>The 1.2 million ESPN-only split and the 1.6 million ABC-only split. The file says they are parts of that combined average, and it does not state a game count.</li>\n'
        '<li>USA Network at 543,000 and Prime Video at 437,000. The file marks the first as partial and does not state a game count for the second.</li>\n'
        '<li>The 1.2 million to 1.6 million Finals forecast, plus revenue and season-ticket figures. Those stay on the audience article. The forecast is not a released rating.</li>\n'
        '</ul>'
    )
    return cite + '\n' + tracker + '\n' + benchmarks + '\n' + history


def _nbc_regular_season_csv_row(payload: dict) -> list:
    """Verified NBC and Peacock regular-season average. TV and streaming, 7 games."""
    viewers = 1_750_000
    games = 7
    source = (
        'https://www.nbcsports.com/pressbox/press-releases/'
        'fever-sky-on-sunday-night-basketball-on-nbc-and-peacock-is-the-most-watched-'
        'wnba-regular-season-game-since-opening-weekend-of-leagues-inaugural-1997-season'
    )
    for row in (payload or {}).get('broadcasts') or []:
        if row.get('season') != 2026 or row.get('network') != 'NBC':
            continue
        value = row.get('avg_viewers')
        count = row.get('games')
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            viewers = value
        if isinstance(count, int) and not isinstance(count, bool) and count > 0:
            games = count
        link = row.get('source')
        if isinstance(link, str) and link.startswith('http'):
            source = link
        break
    if viewers >= 1_000_000 and viewers % 10_000 == 0:
        shown = f'{viewers / 1_000_000:.2f}'.rstrip('0').rstrip('.') + ' million'
    else:
        shown = f'{viewers:,}'
    return [
        '2026 benchmarks',
        'NBC and Peacock regular-season average',
        shown,
        f'{games} games, TV and streaming',
        'NBC and Peacock',
        'Published',
        f'NBC Sports, Aug. 26, 2026. {source}',
    ]


def ratings_hub_csv_rows(payload: dict) -> tuple[list, list]:
    headers = ['section', 'label', 'value', 'comparison', 'network', 'status', 'notes']
    rows = []
    for label, value, change, source in TRACKER_BENCHMARK_ROWS:
        rows.append(['2026 benchmarks', label, value, change, '', 'Published', source])
    rows.append(_nbc_regular_season_csv_row(payload))
    for name, volume in SEARCH_ROWS:
        rows.append(['October 2026 US search estimates', name, volume, '', '', 'Estimate', 'Full Court Buckets keyword research'])
    for row in FINALS_TRACKER_ROWS:
        rows.append(['2026 Finals tracker', 'Game ' + row[0], row[6], row[7], row[3], row[8], row[1] + '; ' + row[4]])
    for row in finals_history_rows(payload):
        rows.append(['Finals average viewers', row[0], row[3], row[1], row[4], row[3], 'Games ' + row[2]])
    return headers, rows


# Sale selected for this guide. Dates and grades are the ones printed on the page.
# Sarah Strong's displayed date is September 26, 2026 PT, not September 27.
CARD_ROWS = [
    ['JuJu Watkins', 'USC', '1/1 SuperFractor autograph, PSA 10, Goldin, Sep 26, 2026', '$24,404', 'Not a separate entry price on this page', 'Above $1,000', 'Not stated on this page'],
    ['Sarah Strong', 'UConn', '1/1 patch SuperFractor, PSA 7, Goldin, Sep 26, 2026 PT', '$1,220', 'Not a separate entry price on this page', 'Above $1,000', 'Not stated on this page'],
    ['Hannah Hidalgo', 'Notre Dame', 'PSA 10 aqua refractor autograph, Fanatics Collect, Feb 9, 2026', '$150', 'Not a separate entry price on this page', '$100 to $999', '25.3 points and 5.6 steals'],
    ['Madison Booker', 'Texas', 'Ungraded prospect autograph, SportsCardsPro, Jul 6, 2026', '$25.41', '$25.41, the sale selected for this guide', 'Under $30', 'Not stated on this page'],
    ['Mikayla Blakes', 'Vanderbilt', 'PSA 10 Sapphire prospect autograph, SportsCardsPro, Sep 13, 2025', '$178.50', 'Not a separate entry price on this page', '$100 to $999', '27.0 points per game'],
    ['Joyce Edwards', 'South Carolina', 'Ungraded red autograph numbered to 5, SportsCardsPro, Mar 15, 2025', '$245', 'Not a separate entry price on this page', '$100 to $999', '19.2 points and 6.8 rebounds'],
    ['MiLaysia Fulwiley', 'LSU', 'Ungraded gold wave autograph numbered to 50, SportsCardsPro, Apr 1, 2024', '$170', 'Not a separate entry price on this page', '$100 to $999', '14.6 points per game'],
    ['Mikaylah Williams', 'LSU', 'Gold Sapphire numbered to 50, SportsCardsPro, Jul 18, 2026', '$19.97', '$19.97, the sale selected for this guide', 'Under $30', '14.2 points, 5.3 rebounds, 3.6 assists'],
    ['Audi Crooks', 'Oklahoma State', 'Gold patch autograph numbered to 50, CGC Authentic, Fanatics Collect, Apr 6, 2026', '$28.80', '$28.80, the sale selected for this guide', 'Under $30', '25.8 points per game and 64.9 percent shooting'],
    ['Jaloni Cambridge', 'Ohio State', 'Ungraded red autograph numbered to 5, SportsCardsPro, Apr 10, 2025', '$79.99', 'Not a separate entry price on this page', 'Under $100', 'Not stated on this page'],
]

CARD_HEADERS = [
    'Player', 'School', 'Sale selected for this guide', 'Price', 'Entry example',
    'Price band', '2025-26 production on this page',
]

CARDS_CITE = (
    'Full Court Buckets, "10 women\'s college basketball cards and what their recorded sales tell us," '
    'updated October 9, 2026.\n'
    f'{CARDS_URL}\n'
    'Sale selected for this guide: JuJu Watkins 1/1 SuperFractor PSA 10, $24,404, Goldin, Sep 26, 2026. '
    'Sarah Strong 1/1 patch SuperFractor PSA 7, $1,220, Goldin, Sep 26, 2026 PT. '
    'Madison Booker $25.41, Audi Crooks $28.80, Mikaylah Williams $19.97. '
    'These are selected sales, not a ranking of player value.'
)


def cards_blocks() -> str:
    cite = quick_cite([
        HTML('JuJu Watkins: <strong>$24,404</strong> for a 1/1 SuperFractor autograph, PSA 10, on Goldin, Sep 26, 2026.'),
        HTML('Sarah Strong: <strong>$1,220</strong> for a 1/1 patch SuperFractor, PSA 7, on Goldin, Sep 26, 2026 PT.'),
        HTML('Under $30 on this list: Madison Booker <strong>$25.41</strong>, Audi Crooks <strong>$28.80</strong>, Mikaylah Williams <strong>$19.97</strong>.'),
    ], CARDS_CITE)
    table = (
        '<h2 class="section-title" id="card-sales-comparison-table">Sales selected for this guide</h2>\n'
        '<p class="fcb-verified-badge">Verified Auction Records: Goldin, Fanatics Collect &amp; SportsCardsPro (Updated Oct 2026)</p>\n'
        + data_table(
            CARD_HEADERS,
            CARD_ROWS,
            caption=(
                'Each price is the sale selected for this guide, not a claim that it is the top sale. '
                'WNBA draft eligibility year and true shooting percentage are not in this guide, so those columns are left out. '
                'A production cell says "Not stated on this page" when the player section does not give a 2025-26 points, rebounds, or shooting line.'
            ),
        )
        + '\n'
        + embed_block(
            'card-sales-comparison-table',
            embed_snippet(CARDS_URL, 'card-sales-comparison-table'),
            'card-sales.csv',
        )
    )
    return cite + '\n' + table


FEE_ROWS = [
    ['Cleveland', '2028', '$250 million', 'NBA ownership group. Arena not stated on this page.', '16'],
    ['Detroit', '2029', '$250 million', 'NBA ownership group. Arena not stated on this page.', '17'],
    ['Philadelphia', '2030', '$250 million', 'NBA ownership group. Arena not stated on this page.', '18'],
]

EXPANSION_CITE = (
    'Full Court Buckets, "WNBA Expansion Teams 2026: Portland Fire and Toronto Tempo."\n'
    f'{EXPANSION_URL}\n'
    'The WNBA has 15 teams in 2026. Portland finished 17-27. Toronto finished 11-33. '
    'Cleveland is scheduled for 2028, Detroit for 2029, and Philadelphia for 2030. '
    'Each of those three paid a $250 million expansion fee, per the AP story linked on this page. '
    'That takes the league from 15 teams to 18.'
)


def expansion_fee_block() -> str:
    return (
        '<h2 class="section-title" id="expansion-fee-table">Future expansion fees on this page</h2>\n'
        + data_table(
            ['Expansion city', 'Debut season', 'Expansion fee', 'Ownership and arena', 'League size that season'],
            FEE_ROWS,
            caption=(
                'The $250 million fee is the figure this page cites from AP for Cleveland, Detroit, and Philadelphia. '
                'League size counts 15 teams in 2026, then one added franchise in each debut season. '
                'Expansion fees for Golden State, Portland, and Toronto are not stated on this page, so they are not in this table. '
                'Point differential for the 2026 expansion clubs is not in this comparison either.'
            ),
        )
        + '\n'
        + embed_block(
            'expansion-fee-table',
            embed_snippet(EXPANSION_URL, 'expansion-fee-table'),
            'expansion.csv',
        )
    )


def expansion_quick_cite() -> str:
    return quick_cite([
        HTML('The WNBA has <strong>15</strong> teams in 2026. Portland finished <strong>17-27</strong>. Toronto finished <strong>11-33</strong>.'),
        HTML('Toronto won the March 27 coin toss and took the No. 6 pick in the regular draft, which gave Portland the first expansion pick.'),
        HTML('Cleveland <strong>2028</strong>, Detroit <strong>2029</strong>, Philadelphia <strong>2030</strong>. Each paid a <strong>$250 million</strong> expansion fee.'),
    ], EXPANSION_CITE)


LIBERTY_CITE = (
    'Full Court Buckets, "Liberty lost the turnover battle by 18 in the sweep. '
    'Here are 5 moves I\'d make as GM," updated October 13, 2026.\n'
    f'{LIBERTY_URL}\n'
    'Atlanta swept the New York Liberty, 92-82, 101-98 in overtime, and 85-83. '
    'Field-goal percentage: Liberty 47.1%, Dream 42.0%. '
    'New York committed 18 more turnovers (45 to 27).'
)


def liberty_sweep_block() -> str:
    cite = quick_cite([
        HTML('Team field-goal percentage: New York Liberty <strong>47.1%</strong>, Atlanta Dream <strong>42.0%</strong>.'),
        HTML('Series turnover margin: New York <strong>-18</strong> (45 turnovers to 27).'),
        HTML('Series result: Atlanta sweeps <strong>3-0</strong>. Game 3: Dream 85, Liberty 83.'),
    ], LIBERTY_CITE)
    table = data_table(
        ['Measure', 'New York Liberty', 'Atlanta Dream'],
        [
            ['Field-goal percentage', '47.1%', '42.0%'],
            ['Turnovers', '45', '27'],
            ['Turnover margin', '-18', '+18'],
            ['Series result', 'Swept, 0-3', 'Sweep, 3-0'],
            ['Game 3', '83', '85'],
        ],
        caption=(
            'Totals across three games, the same counts as the semifinal table lower on this page. '
            'Effective field-goal percentage, turnover percentage, offensive-rebound percentage, and free-throw rate '
            'are not in this story, so they are not shown.'
        ),
        table_id='sweep-stat-breakdown',
    )
    embed = embed_block(
        'sweep-stat-breakdown',
        embed_snippet(LIBERTY_URL, 'sweep-stat-breakdown'),
        'liberty-series.csv',
    )
    return cite + '\n' + table + '\n' + embed


CONTRACT_ROWS = [
    ['2027 salary cap', 'Not a published dollar figure on this page', 'Unavailable', 'Her Hoop Stats WNBA Salary Cap Database, updated Oct. 1, 2026; USA Today'],
    ['Six listed 2027 cap hits', 'Listed on the Oct. 1 sheet', '$5,224,516', 'Her Hoop Stats, Oct. 1, 2026'],
    ['Breanna Stewart, 2026 cap hit', 'Described as a three-year standard max that rises if the cap rises', '$1,190,000 (17% of that page\'s $7 million cap)', 'Newsweek, April 17, 2026'],
    ['Elizabeth Williams, 2027 cap hit', 'Under contract with Chicago, then an unrestricted free agent. A trade in this piece, not a signed Liberty deal.', '$600,000', 'Her Hoop Stats'],
    ['Pauline Astier and Han Xu', 'Reserved. They can only re-sign with New York.', 'No dollar figure listed', 'Oct. 1 sheet'],
    ['Marine Johannes', 'Restricted free agent', 'No dollar figure listed', 'Oct. 1 sheet'],
    ['Manuela Puoch', 'Unsigned 2026 third-rounder', '$288,600 scale figure for 2027', 'Oct. 1 sheet'],
]


def liberty_contract_block() -> str:
    return (
        '<h2 class="section-title" id="liberty-2027-contracts">2027 contract status on this page</h2>\n'
        + data_table(
            ['Item', 'Status', 'Figure on this page', 'Where this page credits it'],
            CONTRACT_ROWS,
            caption=(
                'Reported status only. The planning amounts later in this story ($950,000, $400,000, $300,000, and the $7,474,516 total) '
                'are the author\'s budgets, not reported contracts, and they stay in that table.'
            ),
        )
        + '\n'
        + embed_block(
            'liberty-2027-contracts',
            embed_snippet(LIBERTY_URL, 'liberty-2027-contracts'),
            'liberty-series.csv',
        )
    )


def standings_tie_groups(teams: list) -> list[tuple]:
    grouped = {}
    for team in teams:
        key = (team.get('wins'), team.get('losses'))
        grouped.setdefault(key, []).append(team)
    ties = []
    for key, rows in grouped.items():
        if len(rows) > 1:
            ties.append((key, rows))
    ties.sort(key=lambda item: (-(item[0][0] or 0), item[0][1] or 0))
    return ties


def standings_tie_block(teams: list) -> str:
    rows = []
    for (wins, losses), group in standings_tie_groups(teams):
        names = ', '.join(str(team.get('name') or '') for team in group)
        rows.append([
            f'{wins}-{losses}',
            names,
            'Not in the standings file',
        ])
    if not rows:
        rows.append(['None', 'No shared record on this page', 'Not applicable'])
    return (
        '<h2 id="standings-tie-log">Tied records in the 2026 standings</h2>\n'
        + data_table(
            ['Record', 'Teams, in the order kept on this page', 'Tiebreaker step that separated them'],
            rows,
            caption=(
                'The standings file does not record which tiebreaker step separated teams with the same record. '
                'This page keeps the order already published in the standings feed. '
                'The four steps are head-to-head record, record against teams that finish .500 or better, '
                'head-to-head point differential, and overall point differential.'
            ),
        )
        + '\n'
        + embed_block(
            'standings-tie-log',
            embed_snippet(STANDINGS_URL, 'standings-tie-log'),
            'standings-2026.csv',
        )
    )


def standings_quick_cite(leader: str, wins, losses, count: int, games_sentence: str) -> str:
    citation = (
        f'Full Court Buckets, 2026 WNBA standings.\n{STANDINGS_URL}\n'
        f'The {leader} lead the WNBA standings at {wins}-{losses}. '
        f'{count} teams are listed. {games_sentence}'
    )
    return quick_cite([
        HTML(f'The <strong>{esc(leader)}</strong> lead at <strong>{esc(wins)}-{esc(losses)}</strong>.'),
        HTML(f'<strong>{esc(count)}</strong> teams are on this page. {esc(games_sentence)}'),
        HTML('The top <strong>8</strong> records qualify. The first tiebreaker is head-to-head record.'),
    ], citation)


def standings_csv_rows(teams: list) -> tuple[list, list]:
    headers = ['rank', 'team', 'wins', 'losses', 'pct', 'games_back', 'home', 'road', 'streak', 'last10', 'conference', 'playoff_seed']
    rows = []
    for team in teams:
        rows.append([
            team.get('rank'), team.get('name'), team.get('wins'), team.get('losses'),
            team.get('pct'), team.get('gamesBack'), team.get('home'), team.get('road'),
            team.get('streak'), team.get('last10'), team.get('conference'), team.get('playoffSeed'),
        ])
    return headers, rows


def slugify(text: str) -> str:
    cleaned = text.lower().replace('\u2019', '').replace("'", '')
    cleaned = re.sub(r'[^a-z0-9]+', '-', cleaned).strip('-')
    return cleaned[:70] or 'section'


def _norm_heading(text: str) -> str:
    text = html.unescape(text).replace('\u2019', "'")
    return ' '.join(text.split()).lower()


def add_heading_anchors(html_text: str, forced: dict | None = None, players: list | None = None,
                        start: str = '<article', end: str = '<footer') -> str:
    """Add a hover # link on each h2 and h3 in the page body. Keep an id that already exists."""
    forced = forced or {}
    players = players or []
    begin = html_text.find(start)
    finish = html_text.find(end, begin if begin >= 0 else 0)
    if begin < 0 or finish < begin:
        return html_text
    region = html_text[begin:finish]
    used = set(re.findall(r'\bid="([^"]+)"', html_text))
    pattern = re.compile(r'<(h[23])(\s[^>]*)?>(.*?)</\1>', re.I | re.S)

    def repl(match: re.Match) -> str:
        tag = match.group(1)
        attrs = match.group(2) or ''
        inner = match.group(3)
        if 'fcb-anchor' in inner:
            return match.group(0)
        plain = re.sub(r'<[^>]+>', '', inner)
        key = _norm_heading(plain)
        wanted = forced.get(key)
        if not wanted:
            for name, slug in players:
                if name in key:
                    wanted = slug
                    break
        if not wanted:
            wanted = slugify(key)
        current = re.search(r'\bid="([^"]+)"', attrs)
        if current:
            ident = current.group(1)
        elif wanted in used:
            ident = wanted
        else:
            ident = wanted
            base = ident
            suffix = 2
            while ident in used:
                ident = f'{base}-{suffix}'
                suffix += 1
            used.add(ident)
            attrs = f'{attrs} id="{ident}"'
        link = f'<a class="fcb-anchor" href="#{ident}" aria-label="Link to this section">#</a>'
        return f'<{tag}{attrs}>{link}{inner}</{tag}>'

    region = pattern.sub(repl, region)
    return html_text[:begin] + region + html_text[finish:]


VIEWERSHIP_FORCED = {
    'williams vs. reese in the 2026 playoffs': 'williams-vs-reese',
    'the audience is growing beyond indiana': 'audience-beyond-indiana',
    'search interest is a different count': 'search-demand-estimates',
    'what audience should the finals draw': 'finals-audience-estimate',
    'the finalists are turning attention into repeat customers': 'repeat-customers',
    '2026 wnba finals schedule': 'finals-tv-schedule',
    '2026 wnba finals game-by-game ratings': 'finals-ratings-tracker',
    'finals average viewers, where a source is on file': 'finals-average-viewers',
}

EXPANSION_FORCED = {
    'portland and toronto at a glance': 'portland-toronto-at-a-glance',
    'portland fire: the name came back': 'portland-fire',
    'toronto tempo: the first wnba team outside the us': 'toronto-tempo',
    'wnba expansion draft results': 'expansion-draft-results',
    'wnba expansion draft rules': 'expansion-draft-rules',
    'who each team took': 'expansion-draft-picks',
    'first-season results': 'first-season-results',
    "what's next: new wnba teams coming": 'future-expansion-timeline',
    'future expansion fees on this page': 'expansion-fee-table',
    'faq': 'expansion-faq',
    'how many teams are in the wnba in 2026?': 'how-many-teams-2026',
    'are there wnba expansion teams in 2027?': 'expansion-teams-2027',
    'sources': 'sources',
}

LIBERTY_FORCED = {
    '1. keep the five and address the lost possessions': 'gm-move-1',
    '2. offer a second-round pick for elizabeth williams': 'gm-move-2',
    '3. give astier and fauthoux a real share of the offense': 'gm-move-3',
    '4. draft okananwa and keep a rebounding prospect in view': 'gm-move-4',
    '5. set spending limits before filling the last six spots': 'gm-move-5',
    '2027 contract status on this page': 'liberty-2027-contracts',
    'the 12 players i would take into 2027': 'liberty-2027-roster',
}

CARD_PLAYERS = [
    ('juju watkins', 'juju-watkins'),
    ('sarah strong', 'sarah-strong'),
    ('hannah hidalgo', 'hannah-hidalgo'),
    ('madison booker', 'madison-booker'),
    ('mikayla blakes', 'mikayla-blakes'),
    ('joyce edwards', 'joyce-edwards'),
    ('milaysia fulwiley', 'milaysia-fulwiley'),
    ('mikaylah williams', 'mikaylah-williams'),
    ('audi crooks', 'audi-crooks'),
    ('jaloni cambridge', 'jaloni-cambridge'),
]

STANDINGS_FORCED = {
    'how wnba standings work': 'wnba-tiebreaker-rules',
    'frequently asked questions': 'standings-faq',
    'series coverage': 'series-coverage',
    'eastern conference': 'eastern-conference',
    'western conference': 'western-conference',
    'current rosters': 'rosters',
    'tied records in the 2026 standings': 'standings-tie-log',
}
