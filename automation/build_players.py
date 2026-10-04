#!/usr/bin/env python3
"""Build static FCB profiles from validated local JSON, never from browser API calls.
Python 3.11+, standard library only. No credentials, scraped biographies, or inferred trades.
"""
from __future__ import annotations
import argparse
import datetime as dt
import html
import json
import math
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from analytics import GA4_TAG
import homepage_rail
import internal_links as links
import site_nav
import team_hub
import team_names
from link_graph import page_url

BASE = 'https://fullcourtbuckets.com'
ROBOTS_TXT = (
    'User-agent: *\n'
    'Allow: /\n'
    'Disallow: /review/\n'
    'Disallow: /data/games/\n'
    '\n'
    'Sitemap: https://fullcourtbuckets.com/sitemap.xml\n'
)
SITEMAP_INDEX_LOCS = (
    '/player-sitemap.xml',
    '/pages-sitemap.xml',
)
ADSENSE_TAG = '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-6621195315204235" crossorigin="anonymous"></script>'
SLUG = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*\Z')
# Former ADU articles. They stay deleted so those URLs 404. Do not recreate the pages or stubs.
REMOVED_ADU_PATHS = frozenset({
    'adu-cost.html',
    'adu-feasibility-studies.html',
    'adu-financing.html',
    'adu-garage-conversions.html',
    'adu-handbook.html',
    'adu-permitting.html',
    'adu-rental-income.html',
    'attached-adus.html',
    'detached-adus.html',
    'entitymap.html',
    'jadus.html',
    'pre-approved-adu-plans.html',
    'projects/craftsman-backyard-cottage.html',
    'projects/rice-street-east-block.html',
    'projects/rice-street-west-block.html',
    'san-diego-adus.html',
})
COLUMNS = [('games_played','GP'),('min','MIN'),('pts','PTS'),('reb','REB'),('ast','AST'),
           ('stl','STL'),('blk','BLK'),('turnover','TO'),('fg_pct','FG%'),('fg3_pct','3P%'),('ft_pct','FT%')]
# Reader-facing source line. Published pages do not name or link the data vendor.
STATS_SOURCE = 'Full Court Buckets gathers its own game data and verifies it.'
POSITION_WORDS = {'G': 'guard', 'F': 'forward', 'C': 'center', 'Guard': 'guard', 'Forward': 'forward', 'Center': 'center'}

class BuildError(RuntimeError):
    pass

def reject_removed_adu(relative, content):
    """Block ADU articles and the old sandiegoadubuilder.com redirect stubs."""
    if relative in REMOVED_ADU_PATHS or 'sandiegoadubuilder.com' in content:
        raise BuildError('Refusing to publish removed ADU content: '+relative)

def delete_removed_adu(root: Path) -> None:
    for relative in REMOVED_ADU_PATHS:
        path = Path(root) / relative
        if path.is_file():
            path.unlink()

def esc(value):
    return html.escape('' if value is None else str(value), quote=True)

def value(n, integer=False):
    if isinstance(n, bool) or not isinstance(n, (float, int)) or not math.isfinite(n):
        return '-'
    return str(int(n)) if integer and int(n) == n else f'{n:.1f}'

def timestamp(raw, short=False):
    try:
        date = dt.datetime.fromisoformat(str(raw).replace('Z','+00:00'))
        if date.tzinfo is not None:
            date = date.astimezone(ZoneInfo('America/Los_Angeles'))
        return date.strftime('%b %d, %Y' if short else '%b %d, %Y at %I:%M %p PT')
    except (ValueError, TypeError):
        return 'Not listed'

def tname(team):
    raw = ((team or {}).get('full_name') or (team or {}).get('name') or '').strip()
    if not raw:
        return 'Team not listed'
    return team_names.public_name(raw)

def team_change_html(profile, linking=None, budget=None):
    """Newest-first sentences. The feed does not say trade, signing, or waiver."""
    lines = []
    for entry in profile.get('team_changes') or []:
        if not isinstance(entry, dict):
            continue
        src, dst, raw = entry.get('from'), entry.get('to'), entry.get('date')
        if not src or not dst or not raw:
            continue
        try:
            day = dt.date.fromisoformat(str(raw)[:10])
        except ValueError:
            continue
        label = f'{day.strftime("%b")} {day.day}, {day.year}'
        src_html = links.linked_team_name(src, linking, budget)
        dst_html = links.linked_team_name(dst, linking, budget)
        lines.append(f'<p class="muted">Joined the {dst_html} from the {src_html} on {esc(label)}.</p>')
    if not lines:
        return ''
    return '<p class="muted small">Team change</p>' + ''.join(lines)

def bio_fields(player):
    # Some provider biography fields contain shifted text. Do not relabel or guess it.
    clean = {}
    for key in ('position','height','jersey_number','college','weight'):
        text = str(player.get(key) or '').strip()
        if not text or len(text) > 150:
            continue
        if key == 'weight' and not re.fullmatch(r'\d{2,3}(?:\.\d+)?\s*(?:lbs?\.?|kg)?',text,re.I):
            continue
        if key == 'height' and not re.search(r'\d',text):
            continue
        if key == 'jersey_number' and not re.fullmatch(r'\d{1,2}',text):
            continue
        if key == 'college' and (not re.search(r'[A-Za-z]',text) or re.fullmatch(r'\d+\s*(?:lbs?|kg)?',text,re.I)):
            continue
        clean[key] = text
    return clean

def pacific_day(raw):
    """Calendar day in Pacific time for a stored timestamp. None when the value is not a date."""
    try:
        date = dt.datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return None
    if date.tzinfo is None:
        date = date.replace(tzinfo=dt.timezone.utc)
    return date.astimezone(ZoneInfo('America/Los_Angeles')).date()

def long_date(day):
    if day is None:
        return ''
    return f'{day.strftime("%B")} {day.day}, {day.year}'

def stats_day(profile):
    """Last day the player's numbers changed. Falls back to the last check already stored in the file."""
    if not isinstance(profile, dict):
        return None
    return pacific_day(profile.get('stats_updated_at') or profile.get('checked_at'))

def plain_average(n):
    if isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n):
        return None
    return f'{n:.1f}'

def plain_games(n):
    if isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n):
        return None
    return str(int(n)) if int(n) == n else f'{n:.1f}'

def season_sentence(row):
    """One sentence from a single season line. Missing numbers are left out, never filled in."""
    if not isinstance(row, dict):
        return ''
    year = row.get('season')
    if isinstance(year, bool) or not isinstance(year, int):
        return ''
    label = 'playoffs' if row.get('season_type') == 3 else 'season'
    bits = []
    for key, word in (('pts', 'points'), ('reb', 'rebounds'), ('ast', 'assists')):
        num = plain_average(row.get(key))
        if num is not None:
            bits.append(f'{num} {word}')
    games = plain_games(row.get('games_played'))
    if bits:
        listed = bits[0] if len(bits) == 1 else ', '.join(bits[:-1]) + ' and ' + bits[-1]
        sentence = f'In the {year} {label} she averaged {listed}'
        if games is not None:
            sentence += f' in {games} games'
        return sentence + '.'
    if games is not None:
        return f'In the {year} {label} she played {games} games.'
    return ''

def answer_summary(profile):
    """One or two plain sentences under the player name. Only facts present on the profile."""
    p = profile.get('player') or {}
    name = (str(p.get('first_name') or '') + ' ' + str(p.get('last_name') or '')).strip()
    fields = bio_fields(p)
    active = profile.get('active_in_provider_feed') is True
    team = profile.get('current_team') if active and isinstance(profile.get('current_team'), dict) else None
    team_name = team_names.public_name(((team or {}).get('full_name') or (team or {}).get('name') or '').strip())
    pos = POSITION_WORDS.get(fields.get('position') or '', '')
    if name and active and pos and team_name:
        lead = f'{name} is a {pos} for the {team_name}.'
    elif name and active and team_name:
        lead = f'{name} plays for the {team_name}.'
    elif name and active and pos:
        lead = f'{name} is a {pos}.'
    elif name and pos:
        lead = f'{name} is a {pos} and is not on a current roster.'
    elif name and not active:
        lead = f'{name} is not on a current roster.'
    elif name:
        lead = f'{name} plays in the WNBA.'
    else:
        lead = ''
    stats = season_sentence(headline(profile))
    return ' '.join(part for part in (lead, stats) if part)

def headline(profile):
    rows = profile.get('season_stats',[])
    for kind in (2,3):
        selected = [r for r in rows if r['season_type']==kind]
        if not selected:
            continue
        year = max(r['season'] for r in selected)
        latest = [r for r in selected if r['season']==year]
        # No synthetic career averages, no combined aggregate plus team-stint sums.
        if len(latest)==1:
            return latest[0]
        aggregate=[r for r in latest if not (r.get('team') or {}).get('id')]
        if len(aggregate)==1:
            return aggregate[0]
        return None
    return None

def validate(profile, slug):
    if not SLUG.fullmatch(slug) or profile.get('slug')!=slug:
        raise BuildError('Invalid or mismatched player slug.')
    p=profile.get('player',{})
    if isinstance(p.get('id'),bool) or not isinstance(p.get('id'),int) or p['id'] <= 0 or not (p.get('first_name') or p.get('last_name')):
        raise BuildError('Missing player identity.')
    seen=set()
    for row in profile.get('season_stats',[]):
        if row.get('player_id')!=p['id'] or row.get('season_type') not in (2,3) or row.get('season',0)<2008:
            raise BuildError('Invalid player, season, or competition in profile.')
        key=(row['season'],row['season_type'],(row.get('team') or {}).get('id'))
        if key in seen:
            raise BuildError('Duplicate season/team row.')
        seen.add(key)
    for game in profile.get('recent_completed_games',[]):
        if game.get('player_id')!=p['id']:
            raise BuildError('Game record belongs to a different player.')

def header(route='/', menu=None):
    if menu is None:
        menu = site_nav.build_menu(Path(__file__).resolve().parents[1])
    nav = site_nav.render(menu, route)
    return f'''<div class="brand-line"></div><header class="site-header"><div class="wrap masthead"><a class="brand" href="/" aria-label="Full Court Buckets home"><img src="/logo.png" alt="Full Court Buckets" width="220" height="76"></a>{nav}</div></header><div class="tagline"><div class="wrap"><span>WNBA NEWS · ANALYSIS · COMMENTARY</span><span>Independent WNBA news and analysis</span></div></div>'''

def footer(include_standings=True):
    html_text = site_nav.footer_html(include_standings)
    if links.TIKTOK_URL not in html_text or 'Follow us' not in html_text:
        raise BuildError('Shared footer is missing the TikTok profile.')
    return html_text

def has_standings(root):
    return root is None or (Path(root)/'standings'/'index.html').is_file()

def document(title, description, route, body, structured=None, include_standings=True, menu=None, robots='index,follow,max-image-preview:large'):
    canonical=BASE+route
    schema=json.dumps(structured or {},ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">\n{GA4_TAG}\n{ADSENSE_TAG}\n<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><meta name="description" content="{esc(description)}"><meta name="robots" content="{esc(robots)}"><link rel="canonical" href="{canonical}"><link rel="icon" href="/favicon.svg"><meta property="og:type" content="website"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(description)}"><meta property="og:url" content="{canonical}"><meta property="og:site_name" content="Full Court Buckets"><meta name="theme-color" content="#0c0c10"><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700;800;900&amp;family=Inter:wght@400;500;600;700;800&amp;display=swap" rel="stylesheet"><link rel="stylesheet" href="/wnba/assets/players.css"><link rel="stylesheet" href="/assets/site-nav.css"><script type="application/ld+json">{schema}</script><script src="/assets/site-nav.js" defer></script><script src="/wnba/assets/players.js" defer></script></head><body><a class="skip" href="#content">Skip to content</a>{header(route, menu)}<main id="content" class="wrap">{body}</main>{footer(include_standings)}</body></html>'''

def stats_table(profile, kind, highlight_year=None):
    rows=sorted([r for r in profile.get('season_stats',[]) if r['season_type']==kind],key=lambda r:-r['season'])
    if not rows:
        return ''
    label='Regular season' if kind==2 else 'Playoffs'
    cells=[]
    for r in rows:
        cols=''.join(f'<td>{value(r.get(key),key=="games_played")}</td>' for key,_ in COLUMNS)
        mark = kind == 2 and highlight_year is not None and r.get('season') == highlight_year
        klass = ' class="rookie-year"' if mark else ''
        cells.append(f'<tr{klass} data-season="{r["season"]}"><th scope="row">{r["season"]}</th><td class="team-cell">{esc(tname(r.get("team")))}</td>{cols}</tr>')
    heads=''.join(f'<th scope="col"><abbr title="{esc({"GP":"Games played","MIN":"Minutes per game","PTS":"Points per game","REB":"Rebounds per game","AST":"Assists per game","STL":"Steals per game","BLK":"Blocks per game","TO":"Turnovers per game","FG%":"Field goal percentage","3P%":"Three-point percentage","FT%":"Free throw percentage"}[text])}">{text}</abbr></th>' for _,text in COLUMNS)
    return f'<div class="competition" data-competition="{kind}"><h3>{label}</h3><div class="table-scroll" role="region" aria-label="{label} season statistics" tabindex="0"><table><caption>{label}: per-game averages, except games played and shooting percentages.</caption><thead><tr><th scope="col">YEAR</th><th scope="col">TEAM</th>{heads}</tr></thead><tbody>{"".join(cells)}</tbody></table></div></div>'

def latest_completed_game(profile):
    """Newest completed game on the page, regular season or playoffs."""
    games = [game for game in profile.get('recent_completed_games') or [] if isinstance(game, dict)]
    if not games:
        return None
    return max(games, key=lambda game: str(game.get('date') or ''))


def game_display(game):
    """The same date, opponent, result, and counting stats the game table prints."""
    tid = (game.get('team') or {}).get('id')
    home = (game.get('home_team') or {}).get('id')
    away = (game.get('visitor_team') or {}).get('id')
    if tid not in (home, away) or tid is None:
        opponent = 'Opponent not listed'
        outcome = '-'
    else:
        at_home = tid == home
        opponent = ('vs. ' if at_home else '@ ') + tname(game.get('visitor_team' if at_home else 'home_team'))
        ours, theirs = (game.get('home_score'), game.get('away_score')) if at_home else (game.get('away_score'), game.get('home_score'))
        outcome = (('W' if ours > theirs else 'L' if ours < theirs else 'T') + f' {ours}-{theirs}') if isinstance(ours, (int, float)) and isinstance(theirs, (int, float)) else '-'
    kind = 'Playoffs' if game.get('postseason') is True else 'Regular' if game.get('postseason') is False else 'Not listed'
    return {
        'date': timestamp(game.get('date'), True),
        'opponent': opponent,
        'kind': kind,
        'outcome': outcome,
        'pts': value(game.get('pts'), True),
        'reb': value(game.get('reb'), True),
        'ast': value(game.get('ast'), True),
    }


def game_table(profile):
    games=profile.get('recent_completed_games',[])
    if not games:
        return ''
    rows=[]
    for g in sorted(games,key=lambda r:str(r.get('date','')),reverse=True):
        shown = game_display(g)
        nums=''.join(f'<td>{value(g.get(k),True)}</td>' for k in ('pts','reb','ast','stl','blk','turnover'))
        rows.append(f'<tr><th scope="row">{esc(shown["date"])}</th><td class="team-cell">{esc(shown["opponent"])}</td><td>{shown["kind"]}</td><td>{shown["outcome"]}</td><td>{esc(g.get("minutes") or "Not listed")}</td>{nums}</tr>')
    return f'''<section id="games" class="section"><p class="eyebrow">Completed games</p><h2>Recent game log</h2><p class="muted small">Recent games: {esc(profile.get('game_log_window_start'))} onward. Dates shown in Pacific time. This is not a complete career game log.</p><div class="table-scroll" role="region" tabindex="0" aria-label="Recent completed game statistics"><table><caption>Regular-season and playoff games are labeled separately.</caption><thead><tr><th scope="col">DATE</th><th scope="col">OPPONENT</th><th scope="col">TYPE</th><th scope="col">RESULT</th><th scope="col">MIN</th><th scope="col">PTS</th><th scope="col">REB</th><th scope="col">AST</th><th scope="col">STL</th><th scope="col">BLK</th><th scope="col">TO</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>'''


def player_name(profile) -> str:
    p = profile.get('player') or {}
    return (str(p.get('first_name') or '') + ' ' + str(p.get('last_name') or '')).strip()


def faq_stat_kind(question: str) -> str:
    """Season averages, games played, and last-game answers are rebuilt from page data."""
    text = str(question or '').casefold()
    if 'college' in text:
        return ''
    if 'last game' in text:
        return 'last_game'
    if 'rookie year' in text:
        return 'rookie'
    if 'three-point percentage' in text or '3-point percentage' in text:
        return 'three_point'
    if 'how many years' in text and 'wnba' in text:
        return 'years'
    if text.startswith('which teams') or 'teams has' in text:
        return 'teams'
    if 'fiba' in text:
        return 'fiba'
    if 'points per game' in text or 'tracked game' in text or re.search(r'\bstats\b', text):
        return 'season'
    return ''


def regular_season_years(profile) -> list[int]:
    years = set()
    for row in profile.get('season_stats') or []:
        if not isinstance(row, dict) or row.get('season_type') != 2:
            continue
        year = row.get('season')
        if isinstance(year, bool) or not isinstance(year, int):
            continue
        years.add(year)
    return sorted(years)


def years_faq_answer(profile, name: str) -> str:
    """Count of regular-season rows. A gap is named. This is not a career points total."""
    years = regular_season_years(profile)
    if not years:
        return ''
    count = len(years)
    noun = 'regular season' if count == 1 else 'regular seasons'
    gaps = [year for year in range(years[0], years[-1] + 1) if year not in years]
    if count <= 4:
        sentence = f'{name} has {count} {noun} on this page: {_listed([str(year) for year in years])}.'
    else:
        sentence = f'{name} has {count} {noun} on this page, from {years[0]} to {years[-1]}.'
    if gaps:
        listed = _listed([str(year) for year in gaps])
        verb = 'is' if len(gaps) == 1 else 'are'
        sentence += f' {listed} {verb} not listed.'
    return sentence


def three_point_faq_answer(profile, name: str) -> str:
    """The same 3P% the season table prints for the headline row."""
    row = headline(profile)
    if not row:
        return ''
    pct = value(row.get('fg3_pct'))
    year = row.get('season')
    if pct == '-' or not year:
        return ''
    competition = 'regular season' if row.get('season_type') == 2 else 'playoffs'
    return f"In the {year} {competition}, {name}'s three-point percentage on this page is {pct}."


def rookie_faq_answer(profile, name: str) -> str:
    """First regular-season year after coverage starts, so a pre-2008 career is not guessed."""
    years = regular_season_years(profile)
    if not years:
        return ''
    first = years[0]
    coverage = profile.get('coverage_start')
    if not isinstance(coverage, int) or isinstance(coverage, bool):
        coverage = 2008
    if first <= coverage:
        return ''
    rows = [
        row for row in profile.get('season_stats') or []
        if isinstance(row, dict) and row.get('season') == first and row.get('season_type') == 2
    ]
    games = plain_games(rows[0].get('games_played')) if len(rows) == 1 else None
    sentence = f'The first regular-season row for {name} is {first}.'
    if games:
        sentence += f' She played {games} games in that row.'
    sentence += ' That row is highlighted in the regular-season table.'
    return sentence


def teams_faq_answer(profile, name: str) -> str:
    """Team names printed on the regular-season rows, plus the current team when it differs."""
    names = []
    rows = [row for row in profile.get('season_stats') or [] if isinstance(row, dict) and row.get('season_type') == 2]
    for row in sorted(rows, key=lambda item: item.get('season') or 0):
        team = tname(row.get('team'))
        if team and team != 'Team not listed' and team not in names:
            names.append(team)
    if not names:
        return ''
    sentence = f'The regular-season table lists {_listed([f"the {team}" for team in names])} for {name}.'
    current = profile.get('current_team')
    if profile.get('active_in_provider_feed') is True and isinstance(current, dict):
        current_name = tname(current)
        if current_name and current_name != 'Team not listed' and current_name not in names:
            sentence += f' Her current team on this page is the {current_name}.'
    return sentence


def fiba_faq_answer(profile, name: str, root: Path) -> str:
    """Link the FIBA story only when that story names this player."""
    path = Path(root) / 'news' / 'fiba-womens-basketball-world-cup-2026' / 'index.html'
    if not path.is_file():
        return ''
    last = name.split()[-1] if name else ''
    if not last or last not in path.read_text(encoding='utf-8'):
        return ''
    return (
        f'Full Court Buckets lists {name} on the Team USA roster in '
        '<a href="/news/fiba-womens-basketball-world-cup-2026/">This Is the Olympics of the WNBA</a>.'
    )


_FAQ_ANCHOR = re.compile(r'<a href="(/[^"]+)">([^<]+)</a>')


def faq_answer_html(answer: str) -> str:
    """Escape answer text. Keep same-tab links that the builder inserted."""
    if '<a href="' not in answer:
        return esc(answer)
    parts = []
    pos = 0
    for match in _FAQ_ANCHOR.finditer(answer):
        parts.append(esc(answer[pos:match.start()]))
        parts.append(f'<a href="{esc(match.group(1))}">{esc(match.group(2))}</a>')
        pos = match.end()
    parts.append(esc(answer[pos:]))
    return ''.join(parts)


def _listed(bits: list[str]) -> str:
    if not bits:
        return ''
    if len(bits) == 1:
        return bits[0]
    return ', '.join(bits[:-1]) + ', and ' + bits[-1]


def season_faq_answer(profile, name: str) -> str:
    """Season averages and games played from the same row as the hero and the stats table."""
    row = headline(profile)
    if row:
        bits = []
        for key, word in (('pts', 'points'), ('reb', 'rebounds'), ('ast', 'assists')):
            num = value(row.get(key))
            if num != '-':
                bits.append(f'{num} {word}')
        games = value(row.get('games_played'), True)
        year = row.get('season')
        competition = 'regular season' if row.get('season_type') == 2 else 'playoffs'
        team = tname(row.get('team'))
        noun = 'game' if games == '1' else 'games'
        team_bit = f' for the {team}' if team and team != 'Team not listed' else ''
        if bits and games != '-':
            return (
                f'In the {year} {competition}, {name} averaged {_listed(bits)} in {games} {noun}{team_bit}. '
                'Her full season-by-season numbers are on this page.'
            )
        if games != '-':
            return f'In the {year} {competition}, {name} played {games} {noun}{team_bit}.'
    games = [game for game in profile.get('recent_completed_games') or [] if isinstance(game, dict)]
    if not profile.get('season_stats') and games:
        return tracked_games_answer(name, games, profile)
    if profile.get('season_stats'):
        return f"{name}'s latest season is listed by team on this page, not as one combined average."
    return 'Season averages are not listed on this page yet.'


def tracked_games_answer(name: str, games: list, profile) -> str:
    """Averages of the games in the log. One game stays singular."""
    count = len(games)
    noun = 'game' if count == 1 else 'games'

    def mean(key):
        nums = []
        for game in games:
            num = game.get(key)
            if isinstance(num, bool) or not isinstance(num, (int, float)) or not math.isfinite(num):
                return None
            nums.append(float(num))
        if not nums:
            return None
        return value(sum(nums) / len(nums))

    bits = []
    for key, word in (('pts', 'points'), ('reb', 'rebounds'), ('ast', 'assists')):
        num = mean(key)
        if num is not None:
            bits.append(f'{num} {word}')
    team = tname(profile.get('current_team') if isinstance(profile.get('current_team'), dict) else None)
    team_bit = f' for the {team}' if team and team != 'Team not listed' else ''
    if not bits:
        return f'In her most recent {count} tracked {noun}, a points average is not listed{team_bit}.'
    return (
        f'In her most recent {count} tracked {noun}, {name} averaged {_listed(bits)}{team_bit}. '
        'Full game-by-game numbers are on this page.'
    )


def last_game_answer(profile, name: str) -> str:
    """Last completed game, including playoffs, using the game table's date and numbers."""
    game = latest_completed_game(profile)
    if not game:
        return 'A completed game is not listed on this page yet.'
    shown = game_display(game)
    bits = []
    for key, word in (('pts', 'points'), ('reb', 'rebounds'), ('ast', 'assists')):
        if shown[key] not in ('', '-'):
            bits.append(f'{shown[key]} {word}')
    played = f'{name} had {_listed(bits)}' if bits else f'{name} played'
    kind = f', {shown["kind"]}' if shown['kind'] not in ('', 'Not listed') else ''
    result = f' in a {shown["outcome"]}' if shown['outcome'] not in ('', '-') else ''
    return f'In her most recent completed game ({shown["date"]}, {shown["opponent"]}{kind}), {played}{result}.'


def _faq_quote(answer: str) -> str:
    """Short page quote so a needs-fix issue can name both texts."""
    text = re.sub(r'\s+', ' ', '' if answer is None else str(answer)).strip()
    if len(text) > 180:
        return text[:177].rstrip() + '...'
    return text


def _faq_conflict(slug: str, detail: str, answer: str) -> str:
    return f'{slug} FAQ does not match the stats table: {detail}; page says "{_faq_quote(answer)}".'


def faq_table_mismatches(profile, pairs) -> list[str]:
    """Season, games-played, and last-game answers that disagree with the tables."""
    slug = profile.get('slug') or 'player'
    row = headline(profile)
    game = latest_completed_game(profile)
    shown = game_display(game) if game else None
    logged = [item for item in profile.get('recent_completed_games') or [] if isinstance(item, dict)]
    problems = []
    for question, answer in pairs:
        kind = faq_stat_kind(question)
        if kind == 'season' and row:
            for key, word in (('pts', 'points'), ('reb', 'rebounds'), ('ast', 'assists')):
                num = value(row.get(key))
                if num != '-' and f'{num} {word}' not in answer:
                    problems.append(_faq_conflict(slug, f'table says {num} {word}', answer))
            games = value(row.get('games_played'), True)
            if games != '-' and f'in {games} game' not in answer and f'played {games} game' not in answer:
                problems.append(_faq_conflict(slug, f'table says {games} games played', answer))
            year = row.get('season')
            if year and str(year) not in answer:
                problems.append(_faq_conflict(slug, f'table says season {year}', answer))
        elif kind == 'season' and not profile.get('season_stats') and logged:
            noun = 'game' if len(logged) == 1 else 'games'
            if f'{len(logged)} tracked {noun}' not in answer:
                problems.append(_faq_conflict(slug, f'game log says {len(logged)} tracked {noun}', answer))
            if len(logged) == 1 and f'{len(logged)} tracked games' in answer:
                problems.append(_faq_conflict(slug, 'game log says 1 tracked game', answer))
            for key, word in (('pts', 'points'), ('reb', 'rebounds'), ('ast', 'assists')):
                nums = []
                for item in logged:
                    num = item.get(key)
                    if isinstance(num, bool) or not isinstance(num, (int, float)) or not math.isfinite(num):
                        nums = []
                        break
                    nums.append(float(num))
                if not nums:
                    continue
                shown_avg = value(sum(nums) / len(nums))
                if f'{shown_avg} {word}' not in answer:
                    problems.append(_faq_conflict(slug, f'game log says {shown_avg} {word}', answer))
        elif kind == 'season' and not row:
            if re.search(r'\d+\.\d+\s+points', answer):
                problems.append(_faq_conflict(slug, 'table does not show one season average', answer))
        elif kind == 'last_game' and shown:
            if shown['date'] not in ('', 'Not listed') and shown['date'] not in answer:
                problems.append(_faq_conflict(slug, f'game table says {shown["date"]}', answer))
            for key, word in (('pts', 'points'), ('reb', 'rebounds'), ('ast', 'assists')):
                num = shown[key]
                if num not in ('', '-') and f'{num} {word}' not in answer:
                    problems.append(_faq_conflict(slug, f'game table says {num} {word}', answer))
        elif kind == 'last_game':
            if re.search(r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b', answer):
                problems.append(_faq_conflict(slug, 'game table has no last-game date', answer))
        elif kind == 'three_point' and row:
            pct = value(row.get('fg3_pct'))
            if pct != '-' and pct not in answer:
                problems.append(_faq_conflict(slug, f'table says {pct} three-point percentage', answer))
            year = row.get('season')
            if year and str(year) not in answer:
                problems.append(_faq_conflict(slug, f'table says season {year}', answer))
    return problems


def assert_faq_matches_tables(profile, pairs) -> None:
    """Raise when a season, games-played, or last-game FAQ disagrees with the tables.

    The message names the table value and the page text. A single page's failure
    does not stop the site build; heal_stat_text keeps that page and files an issue.
    """
    problems = faq_table_mismatches(profile, pairs)
    if problems:
        raise BuildError('\n'.join(problems))


def curated_faq_pairs(profile, root: Path):
    """Load rewritten Q&As from data/wnba/faq/{slug}.json. A missing file means no FAQ."""
    slug = profile.get('slug') or ''
    path = Path(root) / 'data' / 'wnba' / 'faq' / f'{slug}.json'
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildError(f'Unreadable curated FAQ for {slug}.') from exc
    if not isinstance(data, dict):
        raise BuildError(f'Curated FAQ for {slug} must be a JSON object.')
    file_slug = data.get('slug')
    if file_slug not in (None, '') and file_slug != slug:
        raise BuildError(f'Curated FAQ slug does not match {slug}.')
    items = data.get('items') or []
    if not isinstance(items, list):
        raise BuildError(f'Curated FAQ items for {slug} must be a list.')
    pairs = []
    for item in items:
        if not isinstance(item, dict):
            raise BuildError(f'Invalid curated FAQ item for {slug}.')
        question = item.get('question')
        answer = item.get('answer')
        if not isinstance(question, str) or not question.strip() or not isinstance(answer, str) or not answer.strip():
            raise BuildError(f'Curated FAQ item for {slug} is missing a question or answer.')
        pairs.append((question.strip(), answer.strip()))
    return pairs

def faq_answer_pairs(profile, root: Path):
    """Keep curated questions. Rebuild season, games-played, and last-game answers from profile data."""
    raw = curated_faq_pairs(profile, root)
    if not raw:
        return []
    name = player_name(profile) or 'This player'
    slug = profile.get('slug') or 'player'
    pairs = []
    for question, answer in raw:
        kind = faq_stat_kind(question)
        if kind == 'season':
            answer = season_faq_answer(profile, name)
        elif kind == 'last_game':
            answer = last_game_answer(profile, name)
        elif kind == 'years':
            answer = years_faq_answer(profile, name)
        elif kind == 'three_point':
            answer = three_point_faq_answer(profile, name)
        elif kind == 'rookie':
            answer = rookie_faq_answer(profile, name)
        elif kind == 'teams':
            answer = teams_faq_answer(profile, name)
        elif kind == 'fiba':
            answer = fiba_faq_answer(profile, name, root)
        if kind in {'years', 'three_point', 'rookie', 'teams', 'fiba'} and not answer:
            raise BuildError(f'{slug} FAQ could not be answered from the page data: {question}')
        pairs.append((question, answer))
    assert_faq_matches_tables(profile, pairs)
    return pairs


def faq_section(profile, root=None):
    """Render every curated FAQ item. Do not invent template or stats-generated questions.
    Players without data/wnba/faq/{slug}.json, or with an empty items list, get no FAQ block.
    Numeric season, games-played, and last-game answers come from the same profile as the tables.
    """
    if root is None:
        root = Path(__file__).resolve().parents[1]
    pairs = faq_answer_pairs(profile, root)
    if not pairs:
        return '', None
    items = ''.join(
        f'<div class="faq-item"><h3>{esc(q)}</h3><p>{faq_answer_html(a)}</p></div>'
        for q, a in pairs
    )
    block = (
        f'<section class="section" id="faq">'
        f'<p class="eyebrow">Player FAQ</p>'
        f'<h2>Frequently asked questions</h2>'
        f'{items}'
        f'</section>'
    )
    slug = profile.get('slug') or ''
    entity = {
        '@type': 'FAQPage',
        '@id': f'{BASE}/wnba/{slug}/#faq',
        'mainEntity': [
            {
                '@type': 'Question',
                'name': q,
                'acceptedAnswer': {'@type': 'Answer', 'text': a},
            }
            for q, a in pairs
        ],
    }
    return block, entity

def teammates_html(profile, linking, budget):
    """Current teammates only, from the same roster. Partial lists say so."""
    if not linking or profile.get('active_in_provider_feed') is not True:
        return ''
    team = profile.get('current_team') or {}
    slot = linking['by_id'].get(team.get('id')) if isinstance(team, dict) else None
    if not slot:
        return ''
    others = [player for player in slot['players'] if player['slug'] != profile.get('slug')]
    chosen = []
    for player in others:
        if not budget.take():
            break
        chosen.append(player)
    if not chosen:
        return ''
    items = ''.join(
        f'<li>{links.inline_link(player["name"], "/wnba/"+player["slug"]+"/")}</li>'
        for player in chosen
    )
    sentence = 'Other players listed on this roster.' if len(chosen) == len(others) else 'Some of the other players listed on this roster.'
    return (
        '<section class="section" id="teammates"><p class="eyebrow">Same roster</p><h2>Teammates</h2>'
        f'<p>{sentence}</p><ul class="teammate-list">{items}</ul></section>'
    )

# Archive provider id -> slug to keep. Same person, two ids. The other slug is a redirect stub.
DUPLICATE_PLAYER_IDS = {
    99338: 'alicia-florez-245094',
}
DESCRIPTION_MAX = 155
TITLE_LIMIT = 70
SKIP_PLAYER_DIRS = frozenset({'teams', 'assets', 'couples'})


def cap_description(text, limit=DESCRIPTION_MAX) -> str:
    """Trim at a word boundary. Descriptions stay at or under the limit."""
    cleaned = re.sub(r'\s+', ' ', '' if text is None else str(text)).strip()
    if len(cleaned) <= limit:
        return cleaned
    clipped = cleaned[:limit + 1]
    if ' ' in clipped:
        clipped = clipped.rsplit(' ', 1)[0]
    return clipped.rstrip(' ,;:') or cleaned[:limit].rstrip()


def player_title(name: str) -> str:
    """'<Name> WNBA Stats & Profile | Full Court Buckets', shorter when that runs past 70 characters."""
    full = f'{name} WNBA Stats & Profile | Full Court Buckets'
    if len(full) <= TITLE_LIMIT:
        return full
    short = f'{name} WNBA Stats | Full Court Buckets'
    if len(short) <= TITLE_LIMIT:
        return short
    tiny = f'{name} | Full Court Buckets'
    if len(tiny) <= TITLE_LIMIT:
        return tiny
    return cap_description(tiny, TITLE_LIMIT)


def player_has_records(profile) -> bool:
    return bool(profile.get('season_stats'))


def player_has_playoff_stats(profile) -> bool:
    """True only when a playoff season row is on the same profile as the stats table."""
    return any(
        isinstance(row, dict) and row.get('season_type') == 3
        for row in profile.get('season_stats') or []
    )


def player_indexable(profile, root) -> bool:
    """Pages with no season stats are noindex and stay out of the sitemap."""
    return player_has_records(profile)


def player_description(profile) -> str:
    p = profile.get('player') or {}
    name = (str(p.get('first_name') or '') + ' ' + str(p.get('last_name') or '')).strip()
    if player_has_records(profile):
        records = 'regular-season and playoff records' if player_has_playoff_stats(profile) else 'regular-season records'
        text = f'{name} WNBA season statistics, {records}, team information and recent game logs.'
        if 'playoff' in text.casefold() and not player_has_playoff_stats(profile):
            raise BuildError(f'{profile.get("slug") or name} mentions playoffs without playoff stats.')
        years = sorted({r['season'] for r in profile.get('season_stats') or [] if isinstance(r.get('season'), int)})
        if years:
            span = f'{years[0]} to {years[-1]}' if len(years) > 1 else str(years[0])
            extra = f' Seasons on record: {span}.'
            if len(text + extra) <= DESCRIPTION_MAX:
                text += extra
        covered = text + ' Available coverage from 2008 onward.'
        if 'Available coverage from 2008 onward.' not in text and len(covered) <= DESCRIPTION_MAX:
            text = covered
        return cap_description(text)
    fields = bio_fields(p)
    pos = POSITION_WORDS.get(fields.get('position') or '', '')
    active = profile.get('active_in_provider_feed') is True
    team = profile.get('current_team') if active and isinstance(profile.get('current_team'), dict) else None
    team_name = team_names.public_name(((team or {}).get('full_name') or (team or {}).get('name') or '').strip())
    if name and pos and team_name:
        lead = f'{name} is a {pos} for the {team_name}.'
    elif name and team_name:
        lead = f'{name} plays for the {team_name}.'
    elif name and pos:
        lead = f'{name} is a {pos}.'
    elif name:
        lead = f'{name} is a WNBA player profile.'
    else:
        lead = 'WNBA player profile.'
    return cap_description(lead + ' No season records are listed on this page yet.')


def _name_from_player_html(text: str) -> str:
    match = re.search(r'<title>(.*?)</title>', text, re.I | re.S)
    if not match:
        return ''
    title = html.unescape(re.sub(r'\s+', ' ', match.group(1))).strip()
    title = re.split(r'\s+WNBA\b', title, maxsplit=1)[0].strip()
    if title.casefold() in {'moved', 'redirect'}:
        return ''
    return title


def orphan_player_target(directory_slug: str, html_text: str, published_names: dict, published_slugs: set) -> str:
    """Where an old /wnba/<slug>/ folder should send people.

    A titled page matches the current profile with the same name. A later rebuild
    only has the redirect stub, so the folder name is also matched to one current
    slug (matilde-villa -> matilde-villa-270867). Anything else goes to the hub.
    """
    name = _name_from_player_html(html_text)
    owners = published_names.get(name.casefold(), []) if name else []
    if len(owners) == 1:
        return f'{BASE}/wnba/{owners[0]}/'
    prefixed = sorted(
        slug for slug in published_slugs
        if slug == directory_slug or slug.startswith(directory_slug + '-')
    )
    if len(prefixed) == 1:
        return f'{BASE}/wnba/{prefixed[0]}/'
    canonical = re.search(r'rel="canonical" href="([^"]+)"', html_text or '')
    if canonical:
        target = canonical.group(1).rstrip('/')
        marker = f'{BASE}/wnba/'
        if target.startswith(marker):
            slug = target[len(marker):]
            if slug in published_slugs and '/' not in slug:
                return target + '/'
    return f'{BASE}/wnba/'


def _ordinal(number: int) -> str:
    if 10 <= number % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(number % 10, 'th')
    return f'{number}{suffix}'


def load_standings_by_name(root) -> dict:
    if root is None:
        return {}
    path = Path(root) / 'api' / 'wnba-standings'
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, json.JSONDecodeError):
        return {}
    found = {}
    for team in data.get('teams') or []:
        if not isinstance(team, dict):
            continue
        name = team_names.public_name(str(team.get('name') or '').strip())
        if name and name not in found:
            found[name] = team
    return found


def _season_line_2026(profile: dict):
    rows = [r for r in profile.get('season_stats') or [] if r.get('season') == 2026 and r.get('season_type') == 2]
    if len(rows) == 1:
        return rows[0]
    aggregate = [r for r in rows if not (r.get('team') or {}).get('id')]
    if len(aggregate) == 1:
        return aggregate[0]
    return None


def _roster_stats(root, player: dict) -> dict:
    empty = {'number': '', 'position': '', 'pts': None, 'reb': None, 'ast': None, 'min': None, 'min_raw': None}
    if root is None:
        return empty
    path = Path(root) / 'data' / 'wnba' / 'players' / f'{player["slug"]}.json'
    if not path.is_file():
        return empty
    try:
        profile = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return empty
    fields = bio_fields(profile.get('player') or {})
    line = _season_line_2026(profile)
    return {
        'number': fields.get('jersey_number') or '',
        'position': {'G': 'Guard', 'F': 'Forward', 'C': 'Center'}.get(fields.get('position'), fields.get('position') or ''),
        'pts': plain_average((line or {}).get('pts')) if line else None,
        'reb': plain_average((line or {}).get('reb')) if line else None,
        'ast': plain_average((line or {}).get('ast')) if line else None,
        'min': plain_average((line or {}).get('min')) if line else None,
        'min_raw': (line or {}).get('min') if line and plain_average((line or {}).get('min')) else None,
    }


def _stat_cell(text) -> str:
    return esc(text if text else '-')


def team_description(slot: dict, standing: dict | None) -> str:
    count = len(slot.get('players') or [])
    noun = 'player' if count == 1 else 'players'
    conference = str(slot.get('conference') or '').strip()
    if not conference and standing:
        label = str(standing.get('conference') or '').strip()
        conference = f'{label} Conference' if label and 'conference' not in label.casefold() else label
    bits = [slot['full_name']]
    if conference:
        bits.append(conference if conference.endswith('Conference') else conference)
    sentence = ', '.join(bits)
    if standing and isinstance(standing.get('wins'), int) and isinstance(standing.get('losses'), int):
        sentence += f'. 2026 record {standing["wins"]}-{standing["losses"]}'
        rank = standing.get('conferenceRank')
        if isinstance(rank, int) and not isinstance(rank, bool):
            sentence += f', {_ordinal(rank)} in the conference'
        seed = standing.get('playoffSeed')
        if isinstance(seed, int) and not isinstance(seed, bool) and 1 <= seed <= 8:
            sentence += f', No. {seed} playoff seed'
        else:
            sentence += ', outside the top eight playoff seeds'
    sentence += f', {count} {noun} listed.'
    if len(sentence) < 110:
        sentence += ' Season averages are on each player page.'
    return cap_description(sentence)


AI_NOTE = (
    'Built by Full Court Buckets from ESPN and WNBA data. '
    'Profile text and FAQs drafted with AI tools and checked against the stats on this page.'
)
PORTRAIT_SENTENCE = 'Portrait is an AI illustration.'


def ai_disclosure_html(include_portrait=False) -> str:
    """One visible line under the stats. The portrait sentence is only for AI portraits."""
    portrait = f' {PORTRAIT_SENTENCE}' if include_portrait else ''
    link = '<a href="/how-we-make-full-court-buckets/">How we make Full Court Buckets</a>'
    return f'<p class="ai-note">{AI_NOTE}{portrait} {link}</p>'


def profile_page(profile, root=None, linking=None, menu=None):
    p=profile['player']; name=(str(p.get('first_name') or '')+' '+str(p.get('last_name') or '')).strip()
    slug=profile['slug']; fields=bio_fields(p); active=profile.get('active_in_provider_feed') is True
    team=profile.get('current_team') if active else None
    budget=links.Budget() if linking else None
    row=headline(profile); stats=profile.get('season_stats',[])
    years=sorted({r['season'] for r in stats})
    span=f'{years[0]}–{years[-1]}' if len(years)>1 else str(years[0]) if years else 'No season records yet'
    state='Listed active' if active else 'Archive profile'
    position={'G':'Guard','F':'Forward','C':'Center'}.get(fields.get('position'),fields.get('position',''))
    number=fields.get('jersey_number','')
    note=(f'{row["season"]} · '+('regular season' if row['season_type']==2 else 'playoffs')) if row else 'No single season line for the latest year'
    metrics=''.join(f'<div class="metric"><strong>{value((row or {}).get(k))}</strong><span>{label}<small>PER GAME</small></span></div>' for k,label in [('pts','POINTS'),('ast','ASSISTS'),('reb','REBOUNDS')])
    meta=' / '.join(esc(x) for x in [('#'+number) if number else '',position,tname(team) if team else ''] if x)
    details=[('Roster','On the current roster' if active else 'Not on a current roster'),('Records available',span)]
    if team: details.append(('Current team',tname(team)))
    for key,label in [('position','Position'),('height','Height'),('jersey_number','Jersey number'),('college','College'),('weight','Weight')]:
        if key in fields: details.append((label,fields[key]))
    detail_html=''.join(f'<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k,v in details)
    regular=[r for r in stats if r['season_type']==2]
    if not stats:
        intro = player_description(profile)
    else:
        intro=f'{name}: WNBA player statistics and available season records from 2008 onward.'
    if row:
        intro=f'{name} averaged {row["pts"]:.1f} points, {row["reb"]:.1f} rebounds and {row["ast"]:.1f} assists in {row["games_played"]} games in the {row["season"]} '+('regular season.' if row['season_type']==2 else 'playoffs.') if all(isinstance(row.get(k),(int,float)) for k in ('pts','reb','ast','games_played')) else intro
    overview=f'<p>{esc(intro)}</p>'
    if team:
        team_label=links.linked_team_name(tname(team), linking, budget)
        overview+=f'<p class="muted">Current team: <strong>{team_label}</strong>.</p>'
    overview+=team_change_html(profile, linking, budget)
    if not active: overview+='<p class="muted">This player is not on a current roster. The page does not call that retirement or free agency.</p>'
    overview += couple_note(root, slug)
    if slug == 'angel-reese' and root is not None and (Path(root) / 'data' / 'reese-cards.json').is_file():
        import build_reese_cards
        overview += build_reese_cards.PLAYER_CALLOUT
    highlight_year = None
    faq_root = root or Path(__file__).resolve().parents[1]
    try:
        raw_faq = curated_faq_pairs(profile, faq_root)
    except BuildError:
        raw_faq = []
    if any(faq_stat_kind(question) == 'rookie' for question, _answer in raw_faq):
        listed_years = regular_season_years(profile)
        highlight_year = listed_years[0] if listed_years else None
    tablehtml=stats_table(profile,2,highlight_year)+stats_table(profile,3)
    controls=''
    if tablehtml:
        kinds=sorted({r['season_type'] for r in stats})
        radios=''.join(f'<button type="button" data-kind="{k}" aria-pressed="false">{"Regular season" if k==2 else "Playoffs"}</button>' for k in kinds)
        opts=''.join(f'<option value="{y}">{y}</option>' for y in sorted(years,reverse=True))
        controls=f'<div class="filters js-only"><div class="segmented" role="group" aria-label="Competition">{radios}<button type="button" data-kind="all" aria-pressed="true">Both</button></div><label>Season <select id="season-filter"><option value="all">All seasons</option>{opts}</select></label></div>'
    statshtml=f'<section class="section" id="stats"><p class="eyebrow">The numbers</p><h2>Season-by-season stats</h2>{controls}{tablehtml}<p id="stats-empty" class="muted" hidden>No records for this selection.</p><p class="muted small">Statistics since 2008. Each season stays with the team she played for that year. These figures are season averages, not a full career total.</p></section>' if tablehtml else ''
    all_teams=[]
    for r in sorted(stats,key=lambda r:-r['season']):
        item=(r['season'],tname(r.get('team')))
        if item not in all_teams: all_teams.append(item)
    latest_year=all_teams[0][0] if all_teams else None
    timeline_rows=[]
    for year, team_name in all_teams:
        label=esc(team_name)
        if linking and not active and year == latest_year:
            label=links.linked_team_name(team_name, linking, budget)
        timeline_rows.append(f'<li><strong>{year}</strong><span>{label}</span></li>')
    timeline=''.join(timeline_rows)
    history=f'<section class="section" id="teams"><p class="eyebrow">Team records</p><h2>Teams by season</h2><p class="muted small">The team she played for in each season. This is not every roster move.</p><ul class="timeline">{timeline}</ul></section>' if timeline else ''
    teammates=teammates_html(profile, linking, budget) if linking else ''
    summary=answer_summary(profile)
    summary_html=f'<p class="answer-summary">{esc(summary)}</p>' if summary else ''
    day=stats_day(profile)
    fresh=long_date(day)
    updated_html=f'<p class="stats-updated">Stats updated {esc(fresh)}. {esc(STATS_SOURCE)}</p>' if fresh else f'<p class="stats-updated">{esc(STATS_SOURCE)}</p>'
    # Visible dates follow the data-hash stamp, not the last time the file was rebuilt.
    checked=fresh or 'Not listed'
    latest=profile.get('recent_completed_games',[])
    latest_label=timestamp(max(g['date'] for g in latest),True) if latest else None
    last_game=f'<p>Most recent completed game: <b>{esc(latest_label)}</b>.</p>' if latest_label else ''
    # Stats, the game log, and teammates sit above the overview. Sources stay last.
    nav_links=[]
    if stats: nav_links.append('<a href="#stats">Stats</a>')
    if latest: nav_links.append('<a href="#games">Game log</a>')
    if teammates: nav_links.append('<a href="#teammates">Teammates</a>')
    nav_links.append('<a href="#overview">Overview</a>')
    if timeline: nav_links.append('<a href="#teams">Teams</a>')
    nav_links.append('<a href="#sources">Sources</a>')
    nav=''.join(nav_links)
    hero=f'''<div class="breadcrumbs"><a href="/">Home</a><span>/</span><a href="/wnba/">Players</a><span>/</span><span>{esc(name)}</span></div><section class="hero" aria-labelledby="player-name"><div class="hero-main"><div class="hero-copy"><div class="hero-kicker"><span class="status">{state}</span><span>WNBA PLAYER PROFILE</span></div><h1 id="player-name"><span>{esc(p.get('first_name'))}</span> <b class="gradient">{esc(p.get('last_name') or p.get('first_name'))}</b></h1>{summary_html}{updated_html}<p class="hero-meta">{meta}</p><div class="actions">{('<a class="button" href="#stats">View stats <span>→</span></a>' if stats else '<a class="button" href="#overview">Player overview →</a>')}<button type="button" id="share" class="text-button js-only">Share ↑</button><span id="share-status" role="status"></span></div></div><div class="hero-art" aria-hidden="true"><span class="ghost-number">{esc(number or 'FCB')}</span><div class="number-card"><span>{esc(p.get('last_name') or name)}</span><strong class="gradient">{esc(number or 'FCB')}</strong></div><small>FULL COURT BUCKETS · PLAYER ARCHIVE</small></div></div><div class="hero-stats">{metrics}<div class="stat-context"><b>{esc(note)}</b><span>Per-game averages</span></div></div></section><nav class="section-nav" aria-label="On this page">{nav}</nav>'''
    faq_html, faq_entity = faq_section(profile, root)
    numbers_note = 'No season records are listed on this page yet. A missing number is shown as a dash and is not turned into zero.' if not stats else 'Numbers on this page start in 2008. Regular-season and playoff statistics are listed separately. Season averages are not turned into a career total. A missing number is shown as a dash and is not turned into zero.'
    archive_line = 'Season records are not on this page yet.' if not stats else 'Explore the available records from 2008 onward.'
    sources=f'''<details class="sources section" id="sources"><summary>About these numbers</summary><p>Season statistics and recent games are listed on this page. Player ID: {p['id']}.</p><p>Last updated {esc(checked)}. A later game may not be on the page yet.</p>{last_game}<p>{numbers_note}</p><p>Height, college and similar details appear only when they are clear. Not appearing on a current roster is not the same as retirement. A new team listed here is not labeled as a trade or a signing.</p><p>This profile does not include news stories or a list of trades and signings. The number artwork is a design element, not a player photograph.</p><a href="/data/wnba/players/{slug}.json">View player data</a></details>'''
    overview_html=f'<section class="section" id="overview"><p class="eyebrow">Player overview</p><h2>{esc(name)}</h2>{overview}<div class="overview-strip"><div><b>{len(set(r["season"] for r in regular))}</b><span>Regular seasons on record</span></div><div><b>{esc(span)}</b><span>Available statistical years</span></div></div></section>'
    archive=f'<section class="archive-band"><div><p class="eyebrow">Full Court Buckets · Player archive</p><h2>WNBA players. Past and present.</h2><p>{esc(archive_line)}</p></div><a class="button" href="/wnba/">Browse players →</a></section>'
    body=hero+f'<div class="content-grid"><div>{statshtml}{ai_disclosure_html()}{game_table(profile)}{teammates}{overview_html}{history}</div><aside><section class="side-card"><p class="eyebrow">The essentials</p><h2>Player details</h2><dl>{detail_html}</dl></section><section class="freshness"><p class="eyebrow">Page status</p><h3>Last updated</h3><p>{esc(checked)}.</p>{last_game}<p class="small">Refreshed through the season, then less often once the season ends.</p></section><a class="button wide" href="/wnba/">Explore WNBA players →</a></aside></div>'+(faq_html or '')+sources+archive
    route=f'/wnba/{slug}/'
    title = player_title(name)
    webpage={'@type':'WebPage','name':title,'url':BASE+route,'about':{'@id':BASE+route+'#player'}}
    if day:
        webpage['dateModified']=day.isoformat()
    structured={'@context':'https://schema.org','@graph':[{'@type':'Person','@id':BASE+route+'#player','name':name,'url':BASE+route}, webpage, {'@type':'BreadcrumbList','itemListElement':[{'@type':'ListItem','position':1,'name':'Home','item':BASE+'/'},{'@type':'ListItem','position':2,'name':'Players','item':BASE+'/wnba/'},{'@type':'ListItem','position':3,'name':name,'item':BASE+route}]}]}
    if faq_entity:
        structured['@graph'].append(faq_entity)
    robots = 'index,follow,max-image-preview:large' if player_indexable(profile, root) else 'noindex'
    return document(title, player_description(profile), route, body, structured, has_standings(root), menu, robots)

def couple_note(root, slug):
    """One sourced relationship line. Empty unless this profile is in the couples data."""
    if root is None or not slug:
        return ''
    try:
        import build_couples
    except ImportError:
        return ''
    return build_couples.note_for_slug(root, slug)

def directory_page(index, linking=None, include_standings=True, menu=None, root=None):
    entries=[p for p in index['players'] if p.get('id') not in DUPLICATE_PLAYER_IDS]
    cards=[]
    for p in sorted(entries,key=lambda p:p['name'].casefold()):
        state='Listed active' if p.get('active_in_provider_feed') else 'Archive profile'
        team=tname(p['current_team']) if p.get('current_team') else 'Historical player records'
        query=' '.join([p['name'],team,state]).casefold()
        cards.append(f'<a class="player-card" href="/wnba/{p["slug"]}/" data-search="{esc(query)}" data-active="{str(bool(p.get("active_in_provider_feed"))).lower()}"><span class="eyebrow">{state}</span><h2>{esc(p["name"])}</h2><p>{esc(team)}</p><span class="small">View profile →</span></a>')
    team_html=''
    if linking and linking['by_id']:
        items=''.join(
            f'<li>{links.inline_link(slot["full_name"], links.team_href(slot))}</li>'
            for slot in sorted(linking['by_id'].values(), key=lambda slot: slot['full_name'].casefold())
        )
        team_html=f'<section class="section hub-links" id="teams"><h2>Teams</h2><ul class="team-index">{items}</ul><p>{links.inline_link("All teams", "/wnba/teams/")}</p></section>'
    updated=f'<p class="muted small directory-updated">Last updated {esc(timestamp(index.get("checked_at")))}. An archive profile means the player is not on a current roster.</p>'
    filters='<div class="directory-filters js-only"><label for="player-search">Find a player<input type="search" id="player-search" placeholder="Search a player or team" autocomplete="off"></label><label for="active-filter">Show<select id="active-filter"><option value="all">All profiles</option><option value="true">Listed active</option><option value="false">Archive profiles</option></select></label></div>'
    # Search sits under the title so it is on the first mobile screen. The card grid follows. The update note stays at the end.
    body=f'''<div class="breadcrumbs"><a href="/">Home</a><span>/</span><span>Players</span></div><section class="directory-header player-hub"><p class="eyebrow">Full Court Buckets · The player archive</p><h1>WNBA players.<br><span class="gradient">Past and present.</span></h1><p>{len(entries)} profiles. Available statistics from 2008 onward.</p></section>{filters}<p class="small muted" id="result-count" role="status">{len(entries)} profiles</p><div class="player-grid">{''.join(cards)}</div><p id="no-players" hidden>No players match your search.</p>{team_html}{updated}'''
    return document('WNBA Player Stats & Profiles, 2008 Onward | Full Court Buckets','Browse WNBA player profiles, season statistics, team information and recent game logs. Available coverage begins in 2008.','/wnba/',body,include_standings=include_standings,menu=menu)

def redirect_stub(old_route: str, new_route: str, menu) -> str:
    """HTML redirect. GitHub Pages cannot send a server redirect."""
    if not old_route.startswith('/wnba/teams/') or not old_route.endswith('/'):
        raise BuildError('Legacy team address must stay under /wnba/teams/.')
    if not new_route.startswith('/wnba/teams/') or not new_route.endswith('/') or old_route == new_route:
        raise BuildError('Team redirect target is not a different team page.')
    new_url = BASE + new_route
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Moved</title>'
        '<meta name="robots" content="noindex">'
        f'<link rel="canonical" href="{new_url}">'
        f'<meta http-equiv="refresh" content="0;url={new_url}">'
        '<link rel="icon" href="/favicon.svg">'
        f'<script>location.replace({json.dumps(new_url)});</script>'
        '</head><body><main>'
        f'<p>Moved from {esc(old_route)}.</p>'
        f'<p><a href="{esc(new_url)}">Continue</a></p>'
        '</main></body></html>'
    )
    return site_nav.install(page, old_route, menu)


def team_page(slot, include_standings=True, menu=None, stories='', root=None):
    name=slot['full_name']
    route=links.team_href(slot)
    table = load_standings_by_name(root)
    standing = table.get(name) or table.get(slot.get('name') or '')
    conf=f'<p class="muted">{esc(slot["conference"])}.</p>' if slot.get('conference') else ''
    standings_link=f'<p>{links.inline_link("WNBA standings", "/standings/")}</p>' if include_standings else ''
    record = ''
    if standing and isinstance(standing.get('wins'), int) and isinstance(standing.get('losses'), int):
        bits = [f'2026 record: {standing["wins"]}-{standing["losses"]}.']
        rank = standing.get('conferenceRank')
        conference = slot.get('conference') or standing.get('conference') or 'conference'
        if isinstance(rank, int) and not isinstance(rank, bool):
            bits.append(f'Conference rank: {_ordinal(rank)} in the {conference}.')
        seed = standing.get('playoffSeed')
        if isinstance(seed, int) and not isinstance(seed, bool) and 1 <= seed <= 8:
            bits.append(f'Playoff seed: {seed}.')
        else:
            bits.append('Playoff seed: outside the top eight.')
        record = f'<p>{" ".join(bits)}</p>'
    rows = []
    leaders = []
    minute_rows = []
    for player in slot['players']:
        stats = _roster_stats(root, player)
        if isinstance(stats.get('min_raw'), (int, float)) and not isinstance(stats.get('min_raw'), bool):
            minute_rows.append({'name': player['name'], 'slug': player['slug'], **stats})
        rows.append(
            '<tr>'
            f'<td>{_stat_cell(stats["number"])}</td>'
            f'<td>{links.inline_link(player["name"], "/wnba/"+player["slug"]+"/")}</td>'
            f'<td>{_stat_cell(stats["position"])}</td>'
            f'<td>{_stat_cell(stats["pts"])}</td>'
            f'<td>{_stat_cell(stats["reb"])}</td>'
            f'<td>{_stat_cell(stats["ast"])}</td>'
            '</tr>'
        )
        if stats['pts'] is not None or stats['reb'] is not None or stats['ast'] is not None:
            leaders.append({'name': player['name'], 'slug': player['slug'], **stats})
    roster = (
        '<div class="table-scroll" role="region" tabindex="0" aria-label="Current roster">'
        '<table><caption>Current roster. 2026 regular-season per-game averages when a season line is on file.</caption>'
        '<thead><tr><th scope="col">No.</th><th scope="col">Player</th><th scope="col">Pos</th>'
        '<th scope="col">PPG</th><th scope="col">RPG</th><th scope="col">APG</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )
    lines = []
    for key, label in (('pts', 'Points'), ('reb', 'Rebounds'), ('ast', 'Assists')):
        scored = [row for row in leaders if row.get(key) is not None]
        if not scored:
            continue
        best = max(float(row[key]) for row in scored)
        tied = [row for row in scored if float(row[key]) == best]
        names = ', '.join(links.inline_link(row['name'], '/wnba/'+row['slug']+'/') for row in tied)
        lines.append(f'<li>{label}: {names} ({tied[0][key]} per game).</li>')
    minute_rows.sort(key=lambda row: (-float(row['min_raw']), row['name'].casefold()))
    chosen = []
    for row in minute_rows:
        if len(chosen) >= 5 and float(row['min_raw']) < float(chosen[-1]['min_raw']):
            break
        chosen.append(row)
    minute_html = ''
    if chosen:
        bits = [
            f'{links.inline_link(row["name"], "/wnba/"+row["slug"]+"/")} ({row["min"]} per game)'
            for row in chosen
        ]
        minute_html = f'<p>Most minutes: {_listed(bits)}.</p>'
    leader_html = ''
    if lines or minute_html:
        list_html = f'<ul class="teammate-list">{"".join(lines)}</ul>' if lines else ''
        leader_html = (
            '<section class="section" id="leaders"><p class="eyebrow">2026 regular season</p>'
            f'<h2>Team leaders</h2>{minute_html}{list_html}</section>'
        )
    count=len(slot['players'])
    noun='player' if count == 1 else 'players'
    body=f'''<div class="breadcrumbs"><a href="/">Home</a><span>/</span><a href="/wnba/">WNBA</a><span>/</span><a href="/wnba/teams/">Teams</a><span>/</span><span>{esc(name)}</span></div><section class="directory-header"><p class="eyebrow">WNBA team</p><h1>{esc(name)}</h1><p>{count} {noun} are listed on the current roster.</p>{record}{conf}{standings_link}</section><section class="section" id="roster"><p class="eyebrow">Current roster</p><h2>Players</h2>{roster}</section>{leader_html}{stories}<p>{links.inline_link('All teams', '/wnba/teams/')}</p><p>{links.inline_link('All players', '/wnba/')}</p>'''
    structured={'@context':'https://schema.org','@graph':[
        {'@type':'SportsTeam','name':name,'url':BASE+route,'sport':'Basketball'},
        {'@type':'BreadcrumbList','itemListElement':[
            {'@type':'ListItem','position':1,'name':'Home','item':BASE+'/'},
            {'@type':'ListItem','position':2,'name':'WNBA','item':BASE+'/wnba/'},
            {'@type':'ListItem','position':3,'name':'Teams','item':BASE+'/wnba/teams/'},
            {'@type':'ListItem','position':4,'name':name,'item':BASE+route},
        ]},
    ]}
    return document(f'{name} Roster | Full Court Buckets', team_description(slot, standing), route, body, structured, include_standings, menu)

def teams_hub_page(root, linking, include_standings=True, menu=None):
    body, structured, title, description = team_hub.hub_parts(root, linking)
    return document(title, description, team_hub.HUB, body, structured, include_standings, menu)

def _iso_date(raw) -> str:
    text = str(raw or '').strip()
    if not text:
        return ''
    try:
        date = dt.datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        return text[:10] if len(text) >= 10 and text[4] == '-' and text[7] == '-' else ''
    if date.tzinfo is not None:
        date = date.astimezone(ZoneInfo('America/Los_Angeles'))
    return date.date().isoformat()


def _player_lastmod(profile) -> str:
    day = stats_day(profile)
    return day.isoformat() if day else ''


_NOINDEX_RE = re.compile(
    r'<meta\b[^>]*name=["\']robots["\'][^>]*content=["\'][^"\']*noindex|'
    r'<meta\b[^>]*content=["\'][^"\']*noindex[^"\']*["\'][^>]*name=["\']robots["\']',
    re.I,
)
_REFRESH_RE = re.compile(r'http-equiv=["\']refresh["\']', re.I)


def page_indexable(text: str) -> bool:
    if not text or _REFRESH_RE.search(text) or _NOINDEX_RE.search(text):
        return False
    return True


def _stored_html(root: Path, files: dict, relative: str) -> str:
    if relative in files:
        return files[relative]
    path = root / relative
    if path.is_file():
        return path.read_text(encoding='utf-8')
    return ''


def _sitemap_document(entries: list) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    seen = set()
    for path, lastmod in entries:
        if path in seen:
            continue
        seen.add(path)
        lines.append('  <url>')
        lines.append(f'    <loc>{BASE}{path}</loc>')
        if lastmod:
            lines.append(f'    <lastmod>{lastmod}</lastmod>')
        lines.append('  </url>')
    lines.append('</urlset>')
    return '\n'.join(lines) + '\n'


def _sitemap_index() -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for path in SITEMAP_INDEX_LOCS:
        lines.append('  <sitemap>')
        lines.append(f'    <loc>{BASE}{path}</loc>')
        lines.append('  </sitemap>')
    lines.append('</sitemapindex>')
    return '\n'.join(lines) + '\n'


def _sitemap_sections(root: Path, linking: dict, articles: list, player_rows: list, page_rows: list, player_index: dict) -> str:
    """HTML sections in the approved order. Every XML loc is linked, with leftovers appended."""
    page_set = {path for path, _last in page_rows}
    labels = {}

    def link_list(pairs: list[tuple[str, str]]) -> str:
        items = []
        for href, label in pairs:
            if href not in page_set:
                continue
            labels[href] = label
            items.append(f'<li><a href="{esc(href)}">{esc(label)}</a></li>')
        return f'<ul class="sitemap-list">{"".join(items)}</ul>' if items else ''

    main = link_list([
        ('/', 'Home'),
        ('/standings/', 'Standings'),
        ('/news/', 'News'),
        ('/wnba/', 'Players A-Z'),
        ('/wnba/teams/', 'Teams'),
    ])
    sections = []
    if main:
        sections.append(f'<section class="section" id="sitemap-main"><h2>Main</h2>{main}</section>')

    ranks = {}
    standings_path = root / 'api' / 'wnba-standings'
    if standings_path.is_file():
        try:
            table = json.loads(standings_path.read_text(encoding='utf-8-sig'))
        except (OSError, json.JSONDecodeError):
            table = {}
        for team in table.get('teams') or []:
            if isinstance(team, dict) and team.get('name'):
                ranks[(str(team.get('conference') or ''), team['name'])] = team.get('conferenceRank') or 99
    grouped = {'Eastern Conference': [], 'Western Conference': [], 'Other': []}
    for slot in linking['by_id'].values():
        href = links.team_href(slot)
        if href not in page_set:
            continue
        group = team_hub.conference_group(slot.get('conference') or '') or 'Other'
        grouped.setdefault(group, []).append(slot)
    team_html = []
    for group in ('Eastern Conference', 'Western Conference', 'Other'):
        slots = grouped.get(group) or []
        if not slots:
            continue
        conference_key = 'Eastern' if group.startswith('Eastern') else 'Western' if group.startswith('Western') else ''

        def sort_key(slot, conference_key=conference_key):
            return (ranks.get((conference_key, slot['full_name']), 99), slot['full_name'].casefold())

        slots.sort(key=sort_key)
        pairs = [(links.team_href(slot), slot['full_name']) for slot in slots]
        team_html.append(f'<h3>{esc(group)}</h3>{link_list(pairs)}')
    if team_html:
        sections.append(f'<section class="section" id="sitemap-teams"><h2>Teams</h2>{"".join(team_html)}</section>')

    news_pairs = []
    ordered = sorted(articles, key=lambda article: str(article.get('date') or ''), reverse=True)
    for article in ordered:
        try:
            slug = links.article_slug(article)
        except ValueError:
            continue
        href = f'/news/{slug}/'
        if href not in page_set:
            continue
        news_pairs.append((href, str(article.get('title') or slug)))
    if '/wnba/couples/' in page_set:
        news_pairs.append(('/wnba/couples/', 'WNBA Couples'))
    news = link_list(news_pairs)
    if news:
        sections.append(f'<section class="section" id="sitemap-news"><h2>News</h2>{news}</section>')

    names = {}
    for entry in player_index.get('players') or []:
        slug = entry.get('slug')
        if slug:
            names[f'/wnba/{slug}/'] = str(entry.get('name') or slug)
    players = []
    for path, _last in player_rows:
        label = names.get(path) or path.strip('/').split('/')[-1]
        labels[path] = label
        players.append((label, path))
    players.sort(key=lambda item: item[0].casefold())
    by_letter = {}
    for label, path in players:
        letter = next((char.upper() for char in label if char.isalpha()), '#')
        by_letter.setdefault(letter, []).append((path, label))
    if by_letter:
        jump = ''.join(
            f'<a href="#players-{esc(letter.casefold())}">{esc(letter)}</a>'
            for letter in by_letter
        )
        blocks = []
        for letter, rows in by_letter.items():
            items = ''.join(f'<li><a href="{esc(path)}">{esc(label)}</a></li>' for path, label in rows)
            blocks.append(f'<h3 id="players-{esc(letter.casefold())}">{esc(letter)}</h3><ul class="sitemap-list">{items}</ul>')
        sections.append(
            f'<section class="section" id="sitemap-players"><h2>Players A-Z</h2>'
            f'<p class="sitemap-jump">{jump}</p>{"".join(blocks)}</section>'
        )

    about = (
        link_list([
            ('/about/', 'About'),
            ('/how-we-make-full-court-buckets/', 'How we make Full Court Buckets'),
        ])
        + '<h3>Authors</h3>'
        + link_list([
            ('/authors/ryan-moalemi/', 'Ryan Moalemi'),
            ('/authors/ryan-moalemi/ryans-angel-reese-cards/', "Ryan's Angel Reese cards"),
        ])
        + link_list([
            ('/contact/', 'Contact'),
            ('/privacy/', 'Privacy'),
            ('/terms/', 'Terms'),
        ])
    )
    if '<a ' in about:
        sections.append(f'<section class="section" id="sitemap-about"><h2>About FCB</h2>{about}</section>')

    body = ''.join(sections)
    linked = set(re.findall(r'href="([^"]+)"', body))
    missing = []
    for path, _last in list(player_rows) + list(page_rows):
        if path not in linked:
            missing.append(path)
            labels.setdefault(path, 'Site map' if path == '/sitemap/' else path)
    if missing:
        extras = ''.join(f'<li><a href="{esc(path)}">{esc(labels.get(path, path))}</a></li>' for path in missing)
        body += f'<section class="section" id="also-listed"><h2>Also listed</h2><ul class="sitemap-list">{extras}</ul></section>'
    return body


def html_sitemap_page(root: Path, menu, linking: dict, articles: list, player_rows: list, page_rows: list, player_index: dict) -> str:
    sections = _sitemap_sections(root, linking, articles, player_rows, page_rows, player_index)
    body = (
        '<div class="breadcrumbs"><a href="/">Home</a><span>/</span><span>Site map</span></div>'
        '<section class="directory-header"><p class="eyebrow">Full Court Buckets</p>'
        '<h1>Site map</h1>'
        '<p>Every indexable page, taken from the same list as the XML sitemaps.</p></section>'
        + sections
    )
    page = document(
        'Site map | Full Court Buckets',
        'HTML site map of Full Court Buckets: home, standings, news, teams, WNBA players, and about pages.',
        '/sitemap/',
        body,
        {
            '@context': 'https://schema.org',
            '@graph': [
                {
                    '@type': 'WebPage',
                    'name': 'Site map',
                    'url': BASE + '/sitemap/',
                    'description': 'HTML site map of Full Court Buckets: home, standings, news, teams, WNBA players, and about pages.',
                    'isPartOf': {'@type': 'WebSite', 'name': 'Full Court Buckets', 'url': BASE + '/'},
                },
                {
                    '@type': 'BreadcrumbList',
                    'itemListElement': [
                        {'@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': BASE + '/'},
                        {'@type': 'ListItem', 'position': 2, 'name': 'Site map', 'item': BASE + '/sitemap/'},
                    ],
                },
            ],
        },
        has_standings(root),
        menu,
        robots='index,follow',
    )
    return site_nav.install(page, '/sitemap/', menu)


def missing_data_markdown(root: Path) -> str:
    """Facts the approved Q&As did not use because they are not in the files."""
    lines = [
        '# Missing data',
        '',
        'Approved questions that were skipped, or answered only as far as the files go.',
        'Nothing here was guessed from memory.',
        '',
    ]

    def profile(slug: str) -> dict:
        path = root / 'data' / 'wnba' / 'players' / f'{slug}.json'
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            return {}

    aja = profile('aja-wilson')
    lines.append("## A'ja Wilson")
    lines.append('')
    if aja.get('career_totals_complete') is not True:
        lines.append(
            '- Career points total: `career_totals_complete` is false and the season rows are per-game averages. '
            'Averages were not turned into a career total.'
        )
    plum_faq = root / 'data' / 'wnba' / 'faq' / 'kelsey-plum.json'
    clark_faq = root / 'data' / 'wnba' / 'faq' / 'caitlin-clark.json'
    injury_sources = False
    for path in (plum_faq, clark_faq):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            continue
        for item in data.get('items') or []:
            if 'injured' in str(item.get('question') or '').casefold() and item.get('sources'):
                injury_sources = True
    if not injury_sources and 'injury' not in json.dumps(aja).casefold():
        lines.append(
            "- Is A'ja Wilson injured?: the Plum and Clark pages ask an injury question, but those items have empty `sources` "
            "and the player file has no injury status. The question was not copied."
        )
    lines.append('')
    lines.append('## Kelsey Plum')
    lines.append('')
    plum = profile('kelsey-plum')
    lines.append(
        '- Championships: her player file has no championship field, and the FAQ file has no official citation for a title count. '
        'The question was skipped.'
    )
    games = [game for game in plum.get('recent_completed_games') or [] if isinstance(game, dict)]
    latest = max(games, key=lambda game: str(game.get('date') or '')) if games else None
    if not latest or not isinstance(latest.get('pts'), (int, float)) or isinstance(latest.get('pts'), bool):
        when = (latest or {}).get('date') or 'none on file'
        lines.append(
            f'- Last game points: the newest completed game ({when}) does not have a points total. '
            'The A\'ja Wilson and Caitlin Clark last-game answers are used only when the game table has points. This one was skipped.'
        )
    season_teams = []
    for row in plum.get('season_stats') or []:
        if isinstance(row, dict) and row.get('season_type') == 2:
            team = tname(row.get('team'))
            if team not in season_teams:
                season_teams.append(team)
    current = tname(plum.get('current_team') if isinstance(plum.get('current_team'), dict) else None)
    if season_teams and current and current not in season_teams:
        listed = ', '.join(season_teams)
        lines.append(
            f'- Teams played for: the regular-season rows name only {listed}, while the current team field is {current}. '
            'The FAQ repeats those names and does not add clubs that are not in the file.'
        )
    lines.append('')
    lines.append('## Caitlin Clark')
    lines.append('')
    card_hits = list((root / 'data').glob('*clark*card*')) + list((root / 'content').glob('*clark*card*'))
    if not card_hits:
        lines.append(
            '- Card content: the only card collection on file is `data/reese-cards.json` (Ryan\'s Angel Reese cards). '
            'No Caitlin Clark card page or card count is stored, so no card link was added.'
        )
    lines.append('')
    lines.append('## Team pages')
    lines.append('')
    teams_path = root / 'data' / 'wnba' / 'teams.json'
    coach = False
    if teams_path.is_file():
        try:
            blob = teams_path.read_text(encoding='utf-8').casefold()
        except OSError:
            blob = ''
        coach = 'head coach' in blob or '"owner"' in blob
    if not coach:
        lines.append(
            '- Head coach and owner: `data/wnba/teams.json` has no coach or owner fields, and no official source file is in the repo. '
            'Those fields were not added. Most minutes is a separate line, taken from 2026 regular-season minutes on the roster.'
        )
    lines.append('')
    lines.append('## Standings')
    lines.append('')
    try:
        import build_standings
        _clock, note = build_standings.standings_refresh_clock()
        _length, length_note = ('', '')
        data_path = root / 'api' / 'wnba-standings'
        if data_path.is_file():
            table = json.loads(data_path.read_text(encoding='utf-8-sig'))
            _length, length_note = build_standings.season_length_answer(table)
        if note:
            lines.append(f'- {note}')
        if length_note:
            lines.append(f'- {length_note}')
        if not note and not length_note:
            lines.append('- No standings question was skipped.')
    except Exception as exc:
        lines.append(f'- Standings notes could not be read: {exc}')
    lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def sitemap_rows(root: Path, files: dict, linking: dict, indexable_players: list, articles: list):
    """One list of indexable players and one list of every other indexable page."""
    newest = ''
    article_dates = {}
    for article in articles:
        try:
            slug = links.article_slug(article)
        except ValueError:
            continue
        day = _iso_date(article.get('date'))
        article_dates[slug] = day
        if day > newest:
            newest = day
    standings_day = ''
    data_path = root / 'api' / 'wnba-standings'
    if data_path.is_file():
        try:
            payload = json.loads(data_path.read_text(encoding='utf-8-sig'))
        except (OSError, json.JSONDecodeError):
            payload = {}
        standings_day = _iso_date(payload.get('updatedAt'))
    players = []
    pages = []

    def add_page(relative, loc, lastmod):
        # The HTML sitemap is written from these rows, so it cannot be read yet.
        if loc == '/sitemap/':
            pages.append((loc, lastmod or newest))
            return
        if not page_indexable(_stored_html(root, files, relative)):
            return
        pages.append((loc, lastmod or newest))

    for slug, lastmod in indexable_players:
        relative = f'wnba/{slug}/index.html'
        if page_indexable(_stored_html(root, files, relative)):
            players.append((f'/wnba/{slug}/', lastmod or newest))
    static = [
        ('index.html', '/'),
        ('about/index.html', '/about/'),
        ('how-we-make-full-court-buckets/index.html', '/how-we-make-full-court-buckets/'),
        ('contact/index.html', '/contact/'),
        ('privacy/index.html', '/privacy/'),
        ('terms/index.html', '/terms/'),
        ('wnba/index.html', '/wnba/'),
        ('news/index.html', '/news/'),
        ('authors/ryan-moalemi/index.html', '/authors/ryan-moalemi/'),
        ('authors/ryan-moalemi/ryans-angel-reese-cards/index.html', '/authors/ryan-moalemi/ryans-angel-reese-cards/'),
        ('standings/index.html', '/standings/'),
        ('wnba/teams/index.html', '/wnba/teams/'),
        ('wnba/couples/index.html', '/wnba/couples/'),
        ('sitemap/index.html', '/sitemap/'),
    ]
    collection_route = '/authors/ryan-moalemi/ryans-angel-reese-cards/'
    collection_day = ''
    collection_file = root / 'data' / 'reese-cards.json'
    if collection_file.is_file():
        import build_reese_cards
        collection_day = build_reese_cards.value_as_of(root)
    for relative, loc in static:
        if loc == '/standings/':
            lastmod = standings_day
        elif loc == collection_route and collection_day:
            lastmod = collection_day
        else:
            lastmod = newest
        add_page(relative, loc, lastmod)
    for slot in linking['by_id'].values():
        add_page('wnba/teams/' + slot['slug'] + '/index.html', links.team_href(slot), newest)
    for slug, day in article_dates.items():
        add_page(f'news/{slug}/index.html', f'/news/{slug}/', day or newest)
    players.sort()
    pages.sort()
    return players, pages


def contextual_link_count(page: str) -> int:
    """Auto player links. The collection callout is one fixed link, not part of that budget."""
    return page.count('class="inline-link"') - page.count('class="reese-cards-link"')


def build(root: Path):
    delete_removed_adu(root)
    data=root/'data/wnba'
    index=json.loads((data/'players-index.json').read_text())
    status=json.loads((data/'status.json').read_text())
    if status.get('status')!='ok' or not index.get('players'):
        raise BuildError('No successful nonempty import is available.')
    published_players=[p for p in index['players'] if p.get('id') not in DUPLICATE_PLAYER_IDS]
    published_index={**index, 'players': published_players}
    linking=links.catalog_from_index(published_index)
    menu=site_nav.build_menu(root, site_nav.planned_paths(root, published_index, linking))
    import heal_stat_text
    files={}; ids=set(); slugs=set(); indexable_players=[]; held=[]
    for entry in index['players']:
        slug=entry.get('slug','')
        if not SLUG.fullmatch(slug) or slug in slugs or entry.get('id') in ids:
            raise BuildError('Unsafe, missing, or duplicate identity in directory.')
        slugs.add(slug); ids.add(entry['id'])
        profile=json.loads((data/'players'/f'{slug}.json').read_text())
        validate(profile,slug)
        if profile['player']['id']!=entry['id']:
            raise BuildError('Profile does not match its directory identity.')
        if entry.get('id') in DUPLICATE_PLAYER_IDS:
            target=DUPLICATE_PLAYER_IDS[entry['id']]
            if target == slug or not SLUG.fullmatch(str(target)):
                raise BuildError('Duplicate player map does not point at a different slug.')
            files[f'wnba/{slug}/index.html']=links.permanent_redirect(f'{BASE}/wnba/{target}/')
            continue
        relative=f'wnba/{slug}/index.html'
        previous_path=root/relative
        previous=previous_path.read_text(encoding='utf-8') if previous_path.is_file() else ''
        try:
            page=profile_page(profile, root, linking, menu)
        except BuildError as exc:
            # A bad FAQ, meta description, or schema on one player must not stop every other page.
            if not heal_stat_text.is_stat_text_failure(exc):
                raise
            held.append(heal_stat_text.needs_fix_issue(slug, [str(exc)]))
            if not previous:
                continue
            page=previous
        else:
            if contextual_link_count(page) > links.MAX_PLAYER_LINKS:
                raise BuildError(f'Too many contextual links on {slug}.')
            outcome=heal_stat_text.heal_page(profile, page, root, previous=previous or None)
            if outcome.action=='kept':
                held.append(heal_stat_text.needs_fix_issue(slug, outcome.mismatches))
                if not previous:
                    continue
                page=previous
            else:
                page=outcome.html
        files[relative]=page
        if player_indexable(profile, root):
            indexable_players.append((slug, _player_lastmod(profile)))
    published_names={}
    for entry in published_players:
        published_names.setdefault(str(entry.get('name') or '').casefold(), []).append(entry['slug'])
    published_slugs={entry['slug'] for entry in published_players}
    wnba_dir=root/'wnba'
    if wnba_dir.is_dir():
        for child in sorted(wnba_dir.iterdir(), key=lambda path: path.name):
            if not child.is_dir() or child.name in SKIP_PLAYER_DIRS or child.name in slugs:
                continue
            if not (child/'index.html').is_file():
                continue
            html_text=(child/'index.html').read_text(encoding='utf-8')
            target=orphan_player_target(child.name, html_text, published_names, published_slugs)
            files[f'wnba/{child.name}/index.html']=links.permanent_redirect(target)
    include_standings=(root/'standings'/'index.html').is_file()
    for slot in linking['by_id'].values():
        files[f'wnba/teams/{slot["slug"]}/index.html']=team_page(slot, include_standings, menu, links.team_news_html(root, slot['slug']), root)
    for team_id, old_slug in team_names.LEGACY_SLUGS.items():
        slot = linking['by_id'].get(team_id)
        if not slot or slot['slug'] == old_slug:
            continue
        old_route = f'/wnba/teams/{old_slug}/'
        files[f'wnba/teams/{old_slug}/index.html'] = redirect_stub(old_route, links.team_href(slot), menu)
    files['wnba/index.html']=directory_page(index, linking, include_standings, menu, root)
    if linking['by_id']:
        files['wnba/teams/index.html']=teams_hub_page(root, linking, include_standings, menu)
    for name in ('players.css','players.js'):
        files['wnba/assets/'+name]=(root/'automation'/name).read_text()
    files['assets/site-nav.css']=site_nav.CSS_TEXT
    files['assets/site-nav.js']=site_nav.JS_TEXT
    homepage=root/'index.html'
    if homepage.exists():
        original=homepage.read_text()
        if 'Full Court Buckets' not in original:
            raise BuildError('Homepage safety check failed; not changing navigation.')
        text=site_nav.install(
            links.apply_homepage(original, links.load_articles(root), homepage_rail.load_rail(root, original)),
            '/',
            menu,
        )
        if text != original:
            files['index.html']=text
    phrases=links.article_phrases(published_index, linking)
    for relative, content in links.assemble_news_pages(root).items():
        if links.is_redirect_html(content):
            files[relative]=content
            continue
        current=page_url(Path(relative))
        if relative not in links.GENERATED_LISTING_PAGES:
            content=links.ensure_footer_hubs(links.link_copy(content, phrases))
        files[relative]=site_nav.install(content, current, menu)
    standings_path=root/'standings'/'index.html'
    standings_data=root/'api'/'wnba-standings'
    if standings_path.is_file() and standings_data.is_file():
        import build_standings
        table=json.loads(standings_data.read_text(encoding='utf-8-sig'))
        rendered=build_standings.render_page(root, table)
        files['standings/index.html']=site_nav.install(
            links.apply_standings(rendered, linking, table),
            '/standings/',
            menu,
        )
    elif standings_path.is_file():
        original=standings_path.read_text(encoding='utf-8')
        updated=site_nav.install(original, '/standings/', menu)
        if updated != original:
            files['standings/index.html']=updated
    for relative in ('about/index.html','contact/index.html','privacy/index.html','terms/index.html','how-we-make-full-court-buckets/index.html'):
        path=root/relative
        if not path.is_file():
            continue
        original=path.read_text(encoding='utf-8')
        updated=site_nav.install(links.apply_known_page_links(original, relative), page_url(Path(relative)), menu)
        if updated != original:
            files[relative]=updated
    import build_reese_cards
    collection_page = build_reese_cards.render_page(root, menu)
    if collection_page:
        files[build_reese_cards.RELATIVE] = collection_page
    files.update(links.legacy_player_redirect_files({entry['slug'] for entry in published_players}))
    files.update(site_nav.install_tree(root, menu, set(files)))
    report={'status':'ok','profile_count':len(slugs),'team_page_count':len(linking['by_id']),'data_checked_at':index.get('checked_at'), 'source':STATS_SOURCE,'coverage_start':2008,'complete_career_totals':False,'news_connected':False,'transactions_connected':False,'directory':'/wnba/'}
    files['data/wnba/site-build.json']=json.dumps(report,indent=2)+'\n'
    articles=links.load_articles(root)
    for relative, content in list(files.items()):
        if relative.endswith('.html'):
            files[relative]=links.rewrite_legacy_article_urls(content, articles)
    player_rows, page_rows = sitemap_rows(root, files, linking, indexable_players, articles)
    files['player-sitemap.xml'] = _sitemap_document(player_rows)
    files['pages-sitemap.xml'] = _sitemap_document(page_rows)
    files['sitemap.xml'] = _sitemap_index()
    files['sitemap/index.html'] = html_sitemap_page(root, menu, linking, articles, player_rows, page_rows, published_index)
    files['docs/missing-data.md'] = missing_data_markdown(root)
    files['robots.txt'] = ROBOTS_TXT
    links.verify_hrefs(root, files)
    # All profiles are validated and rendered before any existing page is replaced.
    changes=0
    for relative,content in files.items():
        reject_removed_adu(relative, content)
        if 'balldontlie' in content.casefold():
            raise BuildError('Refusing to publish a file that names the data vendor: '+relative)
        path=root/relative
        if path.exists() and path.read_text()==content:
            continue
        path.parent.mkdir(parents=True,exist_ok=True)
        temporary=path.with_suffix(path.suffix+'.tmp')
        temporary.write_text(content)
        temporary.replace(path)
        changes+=1
    if held:
        print(f'Held {len(held)} player page(s) on the last published copy.')
        heal_stat_text.file_needs_fix_issues(held)
    print(f'Built {len(slugs)} static player profiles and directory; {changes} files changed.')
    return len(slugs)

def refresh_published_news(root: Path | None = None) -> int:
    """Move posts to /news/<slug>/ and retarget links without rebuilding player profiles."""
    root = root or Path(__file__).resolve().parents[1]
    delete_removed_adu(root)
    index = json.loads((root / 'data/wnba/players-index.json').read_text(encoding='utf-8'))
    linking = links.catalog_from_index(index)
    menu = site_nav.build_menu(root, site_nav.planned_paths(root, index, linking))
    phrases = links.article_phrases(index, linking)
    files: dict[str, str] = {}
    for relative, content in links.assemble_news_pages(root).items():
        if links.is_redirect_html(content):
            files[relative] = content
            continue
        current = page_url(Path(relative))
        if relative not in links.GENERATED_LISTING_PAGES:
            content = links.ensure_footer_hubs(links.link_copy(content, phrases))
        files[relative] = site_nav.install(content, current, menu)
    homepage = root / 'index.html'
    if homepage.is_file():
        homepage_text = homepage.read_text(encoding='utf-8')
        files['index.html'] = site_nav.install(
            links.apply_homepage(
                homepage_text,
                links.load_articles(root),
                homepage_rail.load_rail(root, homepage_text),
            ),
            '/',
            menu,
        )
    articles = links.load_articles(root)
    for name in ('sitemap.xml', 'pages-sitemap.xml'):
        path = root / name
        if path.is_file():
            files[name] = links.sync_news_sitemap(path.read_text(encoding='utf-8'), articles)
    from link_graph import iter_html
    for path in iter_html(root):
        rel = path.relative_to(root).as_posix()
        if rel in files:
            continue
        original = path.read_text(encoding='utf-8')
        if links.is_redirect_html(original) and 'site-footer' not in original:
            continue
        updated = site_nav.install(
            links.rewrite_legacy_article_urls(original, articles),
            page_url(path.relative_to(root)),
            menu,
        )
        if updated != original:
            files[rel] = updated
    for relative, content in list(files.items()):
        if str(relative).endswith('.html'):
            files[relative] = links.rewrite_legacy_article_urls(content, articles)
    changes = 0
    for relative, content in files.items():
        reject_removed_adu(relative, content)
        path = root / relative
        if path.exists() and path.read_text(encoding='utf-8') == content:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        changes += 1
    print(f'Published news paths; {changes} files changed.')
    return changes


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    build(args.root)
