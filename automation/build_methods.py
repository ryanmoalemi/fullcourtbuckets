#!/usr/bin/env python3
"""Write /methods/, the hub for calculations this site actually runs."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'automation'))

from analytics import GA4_TAG  # noqa: E402
import breadcrumbs  # noqa: E402
import site_nav  # noqa: E402
import social_meta  # noqa: E402

ADSENSE_TAG = (
    '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js'
    '?client=ca-pub-6621195315204235" crossorigin="anonymous"></script>'
)

REL = 'methods/index.html'
ROUTE = '/methods/'
TITLE = 'How we calculate WNBA stats | Full Court Buckets'
DESCRIPTION = (
    'Methods for Full Court Buckets player averages, standings order, team history, '
    'revenue multiples, inflation-adjusted fees, and viewership.'
)

BODY = '''
<main class="wrap">
<h1>How we calculate</h1>
<p>Full Court Buckets prints the method next to the table it describes. This page collects those methods. A number that is not in the linked source is not estimated here.</p>
<h2>Player season averages</h2>
<p>The season table lists per-game averages, except games played and shooting percentages. For minutes, points, rebounds, assists, steals, blocks, and turnovers, the counting total is recovered from the stored average times games played, then that total is divided by games and rounded half up to one decimal. That is the figure <a href="https://www.wnba.com/" target="_blank" rel="noopener">WNBA.com</a> prints: 729 points in 43 games is 17.0, not 16.9. Field-goal, three-point, and free-throw percentages stay as stored on the season row. They are not recomputed from makes and attempts on the page. Games played is the integer on the row.</p>
<p>Coverage starts in 2008. Each season stays with the team she played for that year. Season averages are not added into a career total. A missing number is a dash and is not turned into zero.</p>
<h2>Recent game log</h2>
<p>The game log lists recent completed games from the date printed on the page. It is not a complete career game log. Dates are shown in Pacific time. Regular-season and playoff games are labeled separately.</p>
<p>A career-high link is added only when a player FAQ states a single-game points high with a full date, a box score in our game files has that player, that date, and those points, and an FCB recap covers that game. A high inside the recent window is not labeled a career high on its own.</p>
<h2>Standings</h2>
<p>The standings table uses the wins, losses, winning percentage, and order in the standings file. When records match, the page keeps that file's order. It does not reorder tied teams on its own.</p>
<p>The tiebreaker steps printed on the standings page are the WNBA's, from the <a href="https://www.wnba.com/standings" target="_blank" rel="noopener">WNBA standings page</a>. Step 1 is the better record in head-to-head games. Step 2 is the better winning percentage against teams that are .500 or better at the end of the season. Step 3 is the better point differential in those head-to-head games. Step 4 is the better point differential against all opponents. If more than two teams are tied, as many teams as possible are dropped at that step. The teams that are still tied start again at step 1.</p>
<h2>Team history</h2>
<p>Wins, losses, and finish from 2010 on come from <a href="https://www.wnba.com/standings" target="_blank" rel="noopener">WNBA.com standings</a>. Finish is the standings rank: by conference through 2015, and league-wide from 2016. For 1997 to 2009, the win-loss record is counted from final regular-season scores on the <a href="https://www.wnba.com/schedule" target="_blank" rel="noopener">WNBA.com schedule</a>. The finish for 1998, 2002 to 2004, and 2007 to 2009 is the conference rank from archived WNBA.com standings pages on the <a href="https://web.archive.org/" target="_blank" rel="noopener">Wayback Machine</a>. No archived official table was found for 1997, 1999 to 2001, 2005, or 2006, so those finishes come from <a href="https://www.basketball-reference.com/wnba/" target="_blank" rel="noopener">Basketball-Reference</a>, which is not an official source. Every win-loss total in those years matches the WNBA.com count. The team history CSV names the source of each finish. The playoff result is the series line on the same schedule. The team name is the name the franchise played under that season.</p>
<h2>Team revenue</h2>
<p>The revenue ranking uses <a href="https://www.forbes.com/sites/brettknight/2026/05/07/the-wnbas-most-valuable-teams-2026/" target="_blank" rel="noopener">Forbes, May 7, 2026</a>, for franchise values and 2025 revenue estimates, and the <a href="https://www.forbes.com/sites/brettknight/2025/06/06/the-wnbas-most-valuable-teams-2025/" target="_blank" rel="noopener">June 6, 2025 Forbes list</a> for the 12 franchises ranked in both editions. Golden State is left out of the same-12 totals. Full Court Buckets ranks the 13 clubs and adds the combined total. The revenue figures themselves are Forbes estimates.</p>
<p>A displayed team multiple is the 2026 Forbes value divided by the 2025 Forbes revenue, rounded half up to one decimal. The league multiple and the same-12 multiples are the same division, rounded half up to two decimals. A percent change is rounded half up to one decimal.</p>
<h2>Franchise sales and expansion fees</h2>
<p>Fee comparisons in 2026 dollars use BLS CPI-U, series <a href="https://data.bls.gov/timeseries/CUUR0000SA0" target="_blank" rel="noopener">CUUR0000SA0</a>. Annual averages are set against the January through September 2026 average, not a full-year 2026 average. The series, period, and index value are on each row of transactions.csv. Multiples use the unrounded values. The adjustment measures purchasing power, not investor returns.</p>
<p>The count of investors with professional playing experience is the count of distinct person IDs marked yes for that field and matched to an active franchise. An executive career is a separate tag, not an exclusion. Olympic participation alone does not qualify. The count is of disclosures, not of holdings confirmed as current.</p>
<h2>Viewership and attendance</h2>
<p>Viewership figures are Nielsen estimates as reported by the league, the networks, or Sports Media Watch. The source URL is on the row. Nielsen's Big Data + Panel, used more widely from 2025, may affect comparisons with earlier years. One adjustment is not applied to every figure. Attendance figures are what the league, a team release, or Sports Business Journal's box-score count reports. They are not automatically paid attendance or unique fans.</p>
<p>When a printed average does not match the total divided by the game count, the cell is labeled unresolved and the printed figure stays next to its source. A relocated average is published only when it equals the relocated total divided by the relocated game count, rounded to the nearest whole number. A blank cell is not zero.</p>
<p>When both seasons have a sourced attendance total, a game count, and an average, the change is split into extra games and the change in the average crowd. Extra games are the current game count minus the prior game count, times the prior total, divided by the prior game count, then rounded half up to a whole number. The average-crowd piece is the rest of the change, so the two pieces add back to the difference between the seasons.</p>
<h2>Famous relatives</h2>
<p>The famous-relatives table is one row per WNBA player and relative. Team names come from Full Court Buckets player data at build time. Every row links its sources. A source marked as a report is a news report used where no primary record was found. The CSV is those same rows.</p>
<h2>Where to watch</h2>
<p>The bar directory is a list of venues, not a rating. Each logo is taken from that venue's own website. The downloadable CSV is the same list.</p>
<h2>Downloads</h2>
<p>Full Court Buckets tables, charts, embeds, CSVs, and dataset metadata are free to use and republish (<a href="https://creativecommons.org/publicdomain/zero/1.0/" target="_blank" rel="noopener">CC0</a>). Third-party photos keep their own licenses. Email a correction, with the page address, to <a href="mailto:hello@fullcourtbuckets.com">hello@fullcourtbuckets.com</a>.</p>
<p>How stories are edited is a separate page: <a href="/how-we-make-full-court-buckets/">How we make Full Court Buckets</a>.</p>
</main>
'''


def page_html() -> str:
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
{GA4_TAG}
{ADSENSE_TAG}
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{TITLE}</title>
<meta name="description" content="{DESCRIPTION}">
<meta name="author" content="Ryan Moalemi">
<meta name="robots" content="index,follow">
<link rel="canonical" href="https://fullcourtbuckets.com{ROUTE}">
<link rel="icon" href="/favicon.svg">
</head>
<body>
{BODY}
</body>
</html>
'''


def build(root: Path = ROOT) -> None:
    path = root / REL
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_text(page_html(), encoding='utf-8')
    text = page_html()
    text = social_meta.social_block(
        text,
        social_meta.default_image_url(),
        'Full Court Buckets: WNBA stats, news and where to watch',
        1200,
        630,
    )
    text = breadcrumbs.fix(text, ROUTE, root)
    menu = site_nav.build_menu(root)
    text = site_nav.install(text, ROUTE, menu)
    path.write_text(text, encoding='utf-8')


if __name__ == '__main__':
    build()
