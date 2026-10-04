#!/usr/bin/env python3
"""Rebuild standings/index.html from the ESPN WNBA standings feed.

One row per team. East and West stay in feed order. The league playoff seed
is the top 8 by record across both conferences. Tied records keep the order
the feed already listed, which is ESPN's tiebreak order. Nothing is hardcoded
to a team name. If the feed fails, the last good page stays on disk.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from analytics import GA4_TAG
import internal_links as links
import site_nav
import team_names

FEED_URL = 'https://site.api.espn.com/apis/v2/sports/basketball/wnba/standings'
ESPN_PAGE = 'https://www.espn.com/wnba/standings'
BASE = 'https://fullcourtbuckets.com'
ROUTE = '/standings/'
ADSENSE_TAG = '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-6621195315204235" crossorigin="anonymous"></script>'
EXPECTED_TEAMS = 15
PLAYOFF_SPOTS = 8
WNBA_STANDINGS_PAGE = 'https://www.wnba.com/standings'
WNBA_POSTSEASON_FAQ = 'https://www.wnba.com/news/2026-wnba-postseason-faq'


def esc(value) -> str:
    return html.escape('' if value is None else str(value), quote=True)


def _stats(entry: dict) -> dict:
    found = {}
    for stat in entry.get('stats') or []:
        if not isinstance(stat, dict):
            continue
        for key in (stat.get('name'), stat.get('type'), stat.get('abbreviation')):
            text = str(key or '').strip().casefold()
            if text:
                found[text] = stat
    return found


def _display(stats: dict, *keys: str) -> str:
    for key in keys:
        stat = stats.get(key.casefold())
        if not stat:
            continue
        text = str(stat.get('displayValue') or '').strip()
        if text:
            return text
    return ''


def _int_stat(stats: dict, key: str):
    stat = stats.get(key.casefold()) or {}
    value = stat.get('value')
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        text = str(stat.get('displayValue') or '').strip()
        if text.isdigit():
            return int(text)
        return None
    return int(value)


def _float_stat(stats: dict, key: str):
    stat = stats.get(key.casefold()) or {}
    value = stat.get('value')
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _games_back(display: str) -> str:
    text = (display or '').strip()
    if text in ('', '-', '—', '–'):
        return '0'
    return text


def _league_games_back(leader: dict, team: dict) -> str:
    gap = ((leader['wins'] - team['wins']) + (team['losses'] - leader['losses'])) / 2
    if gap <= 0:
        return '0'
    if abs(gap - round(gap)) < 1e-9:
        return str(int(round(gap)))
    return f'{gap:.1f}'


def parse_standings(payload: dict, updated_at: str) -> dict:
    """Turn the ESPN v2 payload into one record per team, plus league seeds."""
    if not isinstance(payload, dict):
        raise ValueError('Standings payload is not an object.')
    children = payload.get('children') or []
    if not isinstance(children, list) or not children:
        raise ValueError('Standings payload has no conferences.')
    raw = []
    feed_index = 0
    for child in children:
        if not isinstance(child, dict):
            continue
        label = str(child.get('name') or '').strip()
        conference = 'Eastern' if 'east' in label.casefold() else 'Western' if 'west' in label.casefold() else ''
        if not conference:
            raise ValueError(f'Unrecognized conference name: {label}')
        entries = ((child.get('standings') or {}).get('entries')) or []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            team = entry.get('team') or {}
            name = team_names.public_name(str(team.get('displayName') or team.get('name') or '').strip())
            stats = _stats(entry)
            wins, losses = _int_stat(stats, 'wins'), _int_stat(stats, 'losses')
            if not name or wins is None or losses is None:
                continue
            raw.append({
                'name': name,
                'abbreviation': str(team.get('abbreviation') or name.split()[-1][:3]).upper(),
                'wins': wins,
                'losses': losses,
                'pct': _float_stat(stats, 'winpercent'),
                'conference': conference,
                'conferenceRank': 0,
                'conferenceGamesBack': _games_back(_display(stats, 'gamesbehind', 'gb')),
                'home': _display(stats, 'home'),
                'road': _display(stats, 'road'),
                'streak': _display(stats, 'streak'),
                'last10': _display(stats, 'last ten games', 'lasttengames'),
                'feed_index': feed_index,
            })
            feed_index += 1
    # The feed lists each conference best to worst. A repeated name is a bad row.
    seen = set()
    unique = []
    for team in raw:
        if team['name'] in seen:
            continue
        seen.add(team['name'])
        unique.append(team)
    if len(unique) != EXPECTED_TEAMS:
        raise ValueError(f'Expected {EXPECTED_TEAMS} teams, found {len(unique)}.')
    for conference in ('Eastern', 'Western'):
        rank = 0
        for team in unique:
            if team['conference'] != conference:
                continue
            rank += 1
            team['conferenceRank'] = rank
    ordered = sorted(unique, key=lambda team: (-team['wins'], team['losses'], team['feed_index']))
    leader = ordered[0]
    season = payload.get('season') or {}
    year = season.get('year') if isinstance(season, dict) else None
    teams = []
    for index, team in enumerate(ordered, start=1):
        teams.append({
            'rank': index,
            'playoffSeed': index if index <= PLAYOFF_SPOTS else None,
            'name': team['name'],
            'abbreviation': team['abbreviation'],
            'wins': team['wins'],
            'losses': team['losses'],
            'pct': team['pct'] if team['pct'] is not None else (team['wins'] / (team['wins'] + team['losses'])),
            'gamesBack': _league_games_back(leader, team),
            'conferenceGamesBack': team['conferenceGamesBack'],
            'home': team['home'],
            'road': team['road'],
            'streak': team['streak'],
            'last10': team['last10'],
            'conference': team['conference'],
            'conferenceRank': team['conferenceRank'],
        })
    return {
        'updatedAt': updated_at,
        'source': FEED_URL,
        'sourcePage': ESPN_PAGE,
        'season': year,
        'teams': teams,
    }


def standings_hash(table: dict) -> str:
    """Hash of the table a reader sees. The updatedAt stamp is not part of the data."""
    payload = {'season': table.get('season'), 'teams': table.get('teams')}
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def keep_updated_at(previous, table: dict, proposed: str) -> str:
    """Keep the stored date when the standings hash is unchanged."""
    if isinstance(previous, dict) and standings_hash(previous) == standings_hash(table):
        kept = previous.get('updatedAt')
        if isinstance(kept, str) and kept.strip():
            return kept
    return proposed


def fetch_standings(url: str = FEED_URL) -> dict:
    request = Request(url, headers={'User-Agent': 'FullCourtBuckets/1.0'})
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode('utf-8'))
    return payload


def _streak_html(value: str) -> str:
    text = esc(value or '-')
    if str(value or '').startswith('W'):
        return f'<span class="winning">{text}</span>'
    if str(value or '').startswith('L'):
        return f'<span class="losing">{text}</span>'
    return f'<span class="secondary">{text}</span>'


def _pct_html(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ''
    text = f'{number:.3f}'
    if number < 1:
        text = text.replace('0.', '.', 1)
    return text


def _team_cell(team: dict, href: str) -> str:
    name = esc(team['name'])
    badge = esc(team.get('abbreviation') or '')
    label = f'<a class="team-name" href="{esc(href)}">{name}</a>' if href else f'<span class="team-name">{name}</span>'
    return f'<td><div class="team-cell"><span class="team-badge">{badge}</span>{label}</div></td>'


def _row(team: dict, href: str, wide: bool) -> str:
    rank = team['rank'] if wide else team.get('conferenceRank')
    games_back = team.get('gamesBack') if wide else team.get('conferenceGamesBack')
    cells = (
        f'<td><span class="rank">{esc(rank)}</span></td>'
        + _team_cell(team, href)
        + f'<td>{esc(team.get("wins"))}</td><td>{esc(team.get("losses"))}</td>'
        + f'<td class="percent">{esc(_pct_html(team.get("pct")))}</td><td>{esc(games_back)}</td>'
    )
    if wide:
        cells += (
            f'<td>{esc(team.get("home") or "-")}</td><td>{esc(team.get("road") or "-")}</td>'
            f'<td>{_streak_html(team.get("streak") or "")}</td><td>{esc(team.get("last10") or "-")}</td>'
        )
    playoff = wide and isinstance(team.get('rank'), int) and team['rank'] <= PLAYOFF_SPOTS
    klass = ' class="playoff-row"' if playoff else ''
    row = f'<tr{klass}>{cells}</tr>'
    if wide and team.get('rank') == PLAYOFF_SPOTS:
        row += '<tr class="playoff-line"><td colspan="10">Playoff Line</td></tr>'
    return row


def standings_refresh_clock() -> tuple[str, str]:
    """Clock time from the workflow that rebuilds this page, plus a note when it is not 6:45 AM PT."""
    workflow = Path(__file__).resolve().parents[1] / '.github' / 'workflows' / 'fcb-wnba.yml'
    text = workflow.read_text(encoding='utf-8') if workflow.is_file() else ''
    match = re.search(
        r"cron:\s*'(\d+)\s+(\d+)\s+\*\s+\*\s\*'\s*\n\s*timezone:\s*America/Los_Angeles",
        text,
    )
    if not match:
        return '', (
            'Standings refresh time: .github/workflows/fcb-wnba.yml has no America/Los_Angeles cron, '
            'so "standings refresh daily at 6:45 AM PT" was not published.'
        )
    minute, hour = int(match.group(1)), int(match.group(2))
    suffix = 'AM' if hour < 12 else 'PM'
    shown = hour % 12 or 12
    clock = f'{shown}:{minute:02d} {suffix} PT'
    note = ''
    if clock != '6:45 AM PT':
        note = (
            'Standings refresh time: the approved line "standings refresh daily at 6:45 AM PT" was not published. '
            f'.github/workflows/fcb-wnba.yml rebuilds standings at {clock} '
            f'(cron {minute} {hour} * * * America/Los_Angeles). '
            'The 6:45 AM PT job is the FAQ consistency check, and it does not rebuild standings.'
        )
    return clock, note


def season_length_answer(table: dict) -> tuple[str, str]:
    """Games played from the standings file. Remaining games only when every team has finished the same schedule."""
    teams = [team for team in (table.get('teams') or []) if isinstance(team, dict)]
    played = []
    for team in teams:
        wins, losses = team.get('wins'), team.get('losses')
        if isinstance(wins, bool) or isinstance(losses, bool) or not isinstance(wins, int) or not isinstance(losses, int):
            return '', 'Season length: a standings row is missing a win or loss total, so games remaining were not stated.'
        played.append(wins + losses)
    if not played:
        return '', 'Season length: the standings file has no team rows, so games remaining were not stated.'
    year = table.get('season') or 'This'
    if len(set(played)) == 1 and links.regular_season_is_final(table):
        games = played[0]
        return (
            f'The {year} regular season on this page is {games} games. '
            f'Every team has played {games}, so no regular-season games are left.',
            '',
        )
    if len(set(played)) == 1:
        games = played[0]
        return (
            f'Teams on this page have each played {games} games in {year}. '
            'Games remaining are not a separate field in the standings file.',
            'Season length: every team has the same games played, but the schedule is not marked final, so games remaining were not invented.',
        )
    return (
        f'{year} games played on this page run from {min(played)} to {max(played)}. '
        'Games remaining are not a separate field in the standings file.',
        'Season length: teams do not show the same games played, and the file has no games-remaining field.',
    )


def standings_faq(table: dict) -> tuple[str, dict | None, list[str]]:
    """FAQ block, FAQPage node, and notes for facts that were not published."""
    notes = []
    tie_plain = (
        'The WNBA standings page lists this order for playoff eligibility and home-court advantage '
        f'({WNBA_STANDINGS_PAGE}). '
        'Step 1: better record in head-to-head games. '
        'Step 2: better winning percentage against teams that are .500 or better at the end of the season. '
        'Step 3: better point differential in the head-to-head games, points scored minus points allowed. '
        'Step 4: better point differential against all opponents, points scored minus points allowed. '
        'If more than two teams are tied, as many teams as possible are dropped at that step. '
        'As soon as one or more teams are separated, start again at step 1 with the teams that are still tied.'
    )
    tie_html = tie_plain.replace(
        f'({WNBA_STANDINGS_PAGE})',
        f'(<a href="{esc(WNBA_STANDINGS_PAGE)}" target="_blank" rel="noopener">WNBA standings</a>)',
    )
    format_plain = (
        'The WNBA says the 2026 playoffs take the top eight teams by regular-season record, regardless of conference '
        f'({WNBA_POSTSEASON_FAQ}). '
        'The first round is a best-of-three, played 1-1-1. '
        'The semifinals are a best-of-five, played 2-2-1. '
        'The Finals are a best-of-seven, played 2-2-1-1-1.'
    )
    format_html = format_plain.replace(
        f'({WNBA_POSTSEASON_FAQ})',
        f'(<a href="{esc(WNBA_POSTSEASON_FAQ)}" target="_blank" rel="noopener">WNBA postseason FAQ</a>)',
    )
    length_plain, length_note = season_length_answer(table)
    if length_note:
        notes.append(length_note)
    clock, clock_note = standings_refresh_clock()
    if clock_note:
        notes.append(clock_note)
    pairs = [
        ('How do WNBA playoff tiebreakers work?', tie_plain, tie_html),
        ('What is the 2026 WNBA playoff format by round?', format_plain, format_html),
    ]
    if length_plain:
        pairs.append(('How long is the WNBA season, and how many games are left?', length_plain, length_plain))
    if clock:
        refresh = f'Full Court Buckets refreshes these standings daily at {clock}.'
        pairs.append(('When do these standings refresh?', refresh, refresh))
    items = ''.join(
        f'<div class="faq-item"><h3>{esc(question)}</h3><p>{html_answer}</p></div>'
        for question, _plain, html_answer in pairs
    )
    block = (
        '<section class="section" id="faq">'
        '<p class="eyebrow">Standings FAQ</p>'
        '<h2>Frequently asked questions</h2>'
        f'{items}'
        '</section>'
    )
    entity = {
        '@type': 'FAQPage',
        '@id': BASE + ROUTE + '#faq',
        'mainEntity': [
            {
                '@type': 'Question',
                'name': question,
                'acceptedAnswer': {'@type': 'Answer', 'text': plain},
            }
            for question, plain, _html in pairs
        ],
    }
    return block, entity, notes


def team_hrefs(root: Path) -> dict[str, str]:
    path = root / 'data' / 'wnba' / 'players-index.json'
    if not path.is_file():
        return {}
    index = json.loads(path.read_text(encoding='utf-8'))
    linking = links.catalog_from_index(index)
    found = {}
    for slot in linking['by_id'].values():
        href = links.team_href(slot)
        found[slot['full_name']] = href
        nick = slot.get('name') or ''
        if nick:
            found.setdefault(nick, href)
    return found


def render_page(root: Path, table: dict) -> str:
    hrefs = team_hrefs(root)
    menu = site_nav.build_menu(root)
    nav = site_nav.render(menu, ROUTE)
    teams = table['teams']
    leader = teams[0]
    when = links._long_date(table.get('updatedAt'))
    sentence = f'The {leader["name"]} lead the WNBA standings at {leader["wins"]}-{leader["losses"]}.'
    support = f'{sentence} Updated {when}.' if when else sentence
    year = table.get('season') or ''
    heading = links.standings_title(table)
    modified = links._iso_day(table.get('updatedAt'))
    def by_conference(name):
        rows = [team for team in teams if team['conference'] == name]
        return sorted(rows, key=lambda team: team.get('conferenceRank') or 99)

    body_rows = ''.join(_row(team, hrefs.get(team['name'], ''), True) for team in teams)
    east = ''.join(_row(team, hrefs.get(team['name'], ''), False) for team in by_conference('Eastern'))
    west = ''.join(_row(team, hrefs.get(team['name'], ''), False) for team in by_conference('Western'))
    css = (Path(__file__).with_name('standings.css')).read_text(encoding='utf-8')
    description = (
        f'{year} WNBA standings for all {len(teams)} teams: wins, losses, winning percentage, '
        'games back, home and road records, and playoff seeds.'
    )
    structured = {
        '@context': 'https://schema.org',
        '@graph': [
            {
                '@type': 'WebPage',
                'name': f'{year} WNBA Standings',
                'url': BASE + ROUTE,
                'description': description,
                'dateModified': modified,
                'isPartOf': {'@type': 'WebSite', 'name': 'Full Court Buckets', 'url': BASE + '/'},
            },
            {
                '@type': 'BreadcrumbList',
                'itemListElement': [
                    {'@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': BASE + '/'},
                    {'@type': 'ListItem', 'position': 2, 'name': 'Standings', 'item': BASE + ROUTE},
                ],
            },
        ],
    }
    faq_html, faq_entity, _notes = standings_faq(table)
    if faq_entity:
        structured['@graph'].append(faq_entity)
    schema = json.dumps(structured, ensure_ascii=False).replace('<', '\\u003c')
    conf_head = '<tr><th>RK</th><th>TEAM</th><th>W</th><th>L</th><th>PCT</th><th>GB</th></tr>'
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
{GA4_TAG}
{ADSENSE_TAG}
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(year)} WNBA Standings | Full Court Buckets</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{BASE}{ROUTE}">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<meta property="og:type" content="website">
<meta property="og:title" content="{esc(year)} WNBA Standings | Full Court Buckets">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{BASE}{ROUTE}">
<meta property="og:site_name" content="Full Court Buckets">
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
<div class="utility"><div class="shell"><div class="utility-tag">WNBA News • Analysis • Commentary</div><div class="utility-note">Independent WNBA news and analysis</div></div></div>
<header><div class="shell nav"><a class="brand" href="/"><img src="/logo.png" alt="Full Court Buckets"></a>{nav}<a class="watch-btn nav-watch" href="/#latest">Latest Stories</a></div></header>
<main class="page">
<div class="standings-shell">
<div class="page-header">
<div class="eyebrow">League</div>
<h1>{esc(heading)}</h1>
<p class="subhead">{esc(heading if links.regular_season_is_final(table) else f'{year} Regular Season')}</p>
<p class="support" id="standings-updated">{esc(support)}</p>
</div>
<section class="panel">
<div class="panel-head">
<h2>{esc(year)} WNBA Standings</h2>
<div class="last-updated"><span class="dot"></span><span id="updatedAt">Updated: {esc(when)}</span></div>
</div>
<div class="table-wrap">
<table class="standings-table" aria-label="{esc(year)} WNBA Standings">
<thead>
<tr>
<th>RK</th><th>TEAM</th><th>W</th><th>L</th><th>PCT</th><th>GB</th><th>HOME</th><th>ROAD</th><th>STREAK</th><th>L10</th>
</tr>
</thead>
<tbody id="standingsBody">{body_rows}</tbody>
</table>
</div>
</section>
<div class="conference-wrap">
<section class="conf-card">
<div class="conf-header"><h3>Eastern Conference</h3></div>
<div class="table-wrap">
<table class="conf-table" aria-label="Eastern Conference Standings">
<thead>{conf_head}</thead>
<tbody id="eastStandings">{east}</tbody>
</table>
</div>
</section>
<section class="conf-card">
<div class="conf-header"><h3>Western Conference</h3></div>
<div class="table-wrap">
<table class="conf-table" aria-label="Western Conference Standings">
<thead>{conf_head}</thead>
<tbody id="westStandings">{west}</tbody>
</table>
</div>
</section>
</div>
<!-- fcb-rosters:start --><!-- fcb-rosters:end -->
<div class="info-grid">
<div class="info-card"><span class="info-label">Playoff Field</span><p>Top 8 teams qualify</p></div>
<div class="info-card"><span class="info-label">Regular Season</span><p>League standings determine playoff seeding</p></div>
<div class="info-card"><span class="info-label">Tiebreakers</span><p>Head-to-head record is the first tiebreaker</p></div>
</div>
<section class="explainer">
<h3>How WNBA Standings Work</h3>
<p>The eight teams with the best regular-season records qualify for the WNBA Playoffs. Playoff seeding is based on regular-season record rather than conference.</p>
<p>If teams finish with identical records, WNBA tiebreak procedures are used to determine playoff qualification and seeding. This page keeps the order already published in the standings feed when records match.</p>
<p><strong>Tiebreakers</strong></p>
<ul>
<li>Better head-to-head record</li>
<li>Better winning percentage against teams that finish .500 or better</li>
<li>Better head-to-head point differential</li>
<li>Better point differential against all opponents</li>
</ul>
</section>
{faq_html}
<p class="source-note">Source: <a href="{ESPN_PAGE}" target="_blank" rel="noopener">ESPN standings</a>.</p>
</div>
</main>
{site_nav.footer_html(True)}
<script src="/assets/site-nav.js" defer></script>
</body>
</html>
'''


def build(root: Path, payload: dict | None = None, updated_at: str | None = None) -> bool:
    """Write the standings page. Return False and keep the last page if the feed fails."""
    page = root / 'standings' / 'index.html'
    data_path = root / 'api' / 'wnba-standings'
    try:
        if payload is None:
            payload = fetch_standings()
        if not updated_at:
            updated_at = dt.datetime.now(ZoneInfo('America/Los_Angeles')).isoformat(timespec='seconds')
        table = parse_standings(payload, updated_at)
        if data_path.is_file():
            try:
                previous = json.loads(data_path.read_text(encoding='utf-8-sig'))
            except (OSError, json.JSONDecodeError):
                previous = None
            table['updatedAt'] = keep_updated_at(previous, table, table.get('updatedAt') or updated_at)
    except Exception as exc:
        print(f'Standings feed failed ({exc}). Keeping the last good page.')
        return False
    names = [team['name'] for team in table['teams']]
    if len(names) != EXPECTED_TEAMS or len(set(names)) != EXPECTED_TEAMS:
        print('Standings feed did not return 15 unique teams. Keeping the last good page.')
        return False
    html_text = render_page(root, table)
    # Player build refreshes these tables from the same JSON. Keep that pass aligned.
    index_path = root / 'data' / 'wnba' / 'players-index.json'
    if index_path.is_file():
        index = json.loads(index_path.read_text(encoding='utf-8'))
        linking = links.catalog_from_index(index)
        html_text = links.apply_standings(html_text, linking, table)
        html_text = site_nav.install(html_text, ROUTE, site_nav.build_menu(root))
    page.parent.mkdir(parents=True, exist_ok=True)
    data_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = page.with_suffix('.html.tmp')
    temporary.write_text(html_text, encoding='utf-8')
    temporary.replace(page)
    data_path.write_text(json.dumps(table, indent=2) + '\n', encoding='utf-8')
    print(f'Wrote standings for {len(names)} teams, updated {links._long_date(table.get("updatedAt"))}.')
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    build(args.root)
