"""Pull draft, college, and international rows from Basketball-Reference.

Writes data/wnba/career-extras.json. Does not invent a field the page does not show.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

UA = 'FullCourtBuckets/1.0 (https://fullcourtbuckets.com/; career fact check)'
ROOT = Path(__file__).resolve().parents[1]
EXTRAS = ROOT / 'data' / 'wnba' / 'career-extras.json'
PAUSE = 0.35

DRAFT_RE = re.compile(
    r'<strong>\s*Draft:\s*</strong>\s*(?:<a[^>]*>)?([^<]+?)(?:</a>)?,\s*'
    r'(\d+)(?:st|nd|rd|th) round \((\d+)(?:st|nd|rd|th) pick, (\d+)(?:st|nd|rd|th) overall\),\s*'
    r'<a[^>]*>(\d{4}) Draft</a>',
    re.I | re.S,
)
COLLEGE_RE = re.compile(
    r'College:\s*</strong>\s*(?:<a[^>]*>)?([^<]+)',
    re.I | re.S,
)
INTL_RE = re.compile(r'https://www\.basketball-reference\.com/international/players/[a-z0-9\-]+\.html')


def norm(value: str) -> str:
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = ''.join(char for char in text if not unicodedata.combining(char))
    text = text.replace("'", '').replace('’', '').replace('`', '')
    return re.sub(r'[^a-z0-9]+', ' ', text.casefold()).strip()


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={'User-Agent': UA})
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                return response.read().decode('utf-8', 'replace')
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f'{url} failed: {last}')


def _direct_player_url(html: str, name: str) -> str:
    """A one-result search is the player page itself, not a result list."""
    canonical = re.search(r'rel="canonical" href="([^"]+)"', html)
    href = canonical.group(1) if canonical else ''
    if '/wnba/players/' not in href or 'search.fcgi' in href:
        return ''
    plain = re.sub(r'<[^>]+>', ' ', html)
    plain = html_unescape(plain)
    plain = re.sub(r'\s+', ' ', plain)
    wanted = norm(name)
    heading = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
    heading_text = re.sub(r'<[^>]+>', ' ', heading.group(1)) if heading else ''
    if norm(html_unescape(heading_text)) == wanted:
        return href
    formerly = re.search(r'Formerly known as ([^)]+)', plain, re.I)
    if formerly and norm(formerly.group(1)) == wanted:
        return href
    return ''


def html_unescape(value: str) -> str:
    return (
        value.replace('&amp;', '&')
        .replace('&quot;', '"')
        .replace('&#39;', "'")
        .replace('&nbsp;', ' ')
        .replace('&#x27;', "'")
    )


def search_wnba(name: str) -> str:
    url = 'https://www.basketball-reference.com/search/search.fcgi?search=' + urllib.parse.quote(name)
    html = fetch(url)
    time.sleep(PAUSE)
    direct = _direct_player_url(html, name)
    if direct:
        return direct
    wanted = norm(name)
    hits = []
    for block in html.split('class="search-item"')[1:]:
        league = re.search(r'class="search-item-league">([^<]+)', block)
        link = re.search(r'<a href="([^"]+)">([^<]+)</a>', block)
        if not league or not link:
            continue
        if league.group(1).strip().upper() != 'WNBA':
            continue
        href, label = link.group(1), re.sub(r'\s*\([^)]*\)\s*$', '', link.group(2)).strip()
        if '/wnba/players/' not in href:
            continue
        if norm(label) == wanted:
            hits.append(href if href.startswith('http') else 'https://www.basketball-reference.com' + href)
    unique = list(dict.fromkeys(hits))
    if len(unique) == 1:
        return unique[0]
    return ''


def parse_player(html: str, page_url: str) -> dict:
    extra = {'bbref': page_url}
    draft = DRAFT_RE.search(html)
    if draft:
        extra['draft'] = {
            'team': re.sub(r'\s+', ' ', draft.group(1)).strip(),
            'round': int(draft.group(2)),
            'pick': int(draft.group(3)),
            'overall': int(draft.group(4)),
            'year': int(draft.group(5)),
            'source': page_url,
        }
    college = COLLEGE_RE.search(html)
    if college:
        name = re.sub(r'\s+', ' ', college.group(1)).strip()
        if name and name.lower() not in {'none', 'n/a'}:
            extra['college'] = {'name': name, 'source': page_url}
    return extra


def parse_international(html: str, page_url: str) -> dict:
    start = html.find('id="player-stats-per_game-tournament-"')
    if start < 0:
        return {}
    end = html.find('</table>', start)
    table = html[start:end]
    rows = []
    for raw in re.findall(r'<tr[^>]*>(.*?)</tr>', table, re.S):
        cells = {}
        for key, value in re.findall(r'data-stat="([^"]+)"[^>]*>(.*?)</t[dh]>', raw, re.S):
            text = re.sub(r'<[^>]+>', '', value)
            text = re.sub(r'\s+', ' ', text).strip()
            cells[key] = text
        season = cells.get('season') or ''
        team = cells.get('team') or ''
        if not team or 'season' in season.casefold():
            continue
        row = {'season': season, 'team': team, 'league': cells.get('league') or ''}
        games = cells.get('g') or ''
        points = cells.get('pts_per_g') or ''
        if re.fullmatch(r'\d+', games):
            row['games'] = int(games)
        if re.fullmatch(r'\d+(?:\.\d+)?', points):
            row['pts'] = float(points)
        rows.append(row)
    if not rows:
        return {}
    return {'source': page_url, 'rows': rows}


def research_player(name: str) -> dict:
    page = search_wnba(name)
    if not page:
        return {'match': 'none'}
    html = fetch(page)
    time.sleep(PAUSE)
    extra = parse_player(html, page)
    extra['match'] = 'wnba'
    intl = INTL_RE.search(html)
    if intl:
        intl_url = intl.group(0)
        intl_html = fetch(intl_url)
        time.sleep(PAUSE)
        table = parse_international(intl_html, intl_url)
        if table:
            extra['international'] = table
    return extra


def inactive_players() -> list[dict]:
    index = json.loads((ROOT / 'data' / 'wnba' / 'players-index.json').read_text(encoding='utf-8'))
    rows = []
    for entry in index['players']:
        if entry.get('active_in_provider_feed'):
            continue
        path = ROOT / str(entry['data_path']).lstrip('/')
        profile = json.loads(path.read_text(encoding='utf-8'))
        stats = profile.get('season_stats') or []
        regular = [row for row in stats if row.get('season_type') == 2]
        years = {row.get('season') for row in regular}
        best = 0.0
        games = 0
        for row in regular:
            points = row.get('pts')
            played = row.get('games_played')
            if isinstance(points, (int, float)) and not isinstance(points, bool):
                best = max(best, float(points))
            if isinstance(played, (int, float)) and not isinstance(played, bool):
                games += played
        rows.append({
            'slug': entry['slug'],
            'name': entry['name'],
            'years': len(years),
            'best': best,
            'games': games,
        })
    priority = {'marta-xargay': 0, 'crystal-bradford': 1}
    rows.sort(key=lambda row: (priority.get(row['slug'], 2), -row['years'], -row['best'], -row['games'], row['name'].casefold()))
    return rows


def main() -> None:
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    offset = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    existing = {}
    if EXTRAS.is_file():
        existing = json.loads(EXTRAS.read_text(encoding='utf-8'))
    players = inactive_players()
    if offset or limit:
        players = players[offset:offset + limit if limit else None]
    print(f'researching {len(players)} inactive players', flush=True)
    for index, player in enumerate(players, 1):
        slug = player['slug']
        if slug in existing and existing[slug].get('match') in {'wnba', 'none'}:
            print(f'{index} skip {slug}', flush=True)
            continue
        try:
            extra = research_player(player['name'])
        except Exception as exc:  # noqa: BLE001
            print(f'{index} ERROR {slug}: {exc}', flush=True)
            continue
        extra['slug'] = slug
        extra['name'] = player['name']
        existing[slug] = extra
        EXTRAS.write_text(json.dumps(existing, indent=2) + '\n', encoding='utf-8')
        draft = (extra.get('draft') or {}).get('year')
        print(f'{index} {slug} match={extra.get("match")} draft={draft} intl={len((extra.get("international") or {}).get("rows") or [])}', flush=True)
    print(f'saved {len(existing)}', flush=True)


if __name__ == '__main__':
    main()
