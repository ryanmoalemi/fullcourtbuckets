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
import internal_links as links
import site_nav
import team_hub
import team_names
from link_graph import page_url

BASE = 'https://fullcourtbuckets.com'
ADSENSE_TAG = '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-6621195315204235" crossorigin="anonymous"></script>'
SLUG = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*\Z')
# Former ADU articles. The builder may write a redirect stub and must not recreate the page.
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
# Reader-facing source line. Numbers come from WNBA season averages and game
# lines stored in data/wnba, not from a live box-score page on wnba.com.
STATS_SOURCE = 'Stats from WNBA season averages and game records.'
POSITION_WORDS = {'G': 'guard', 'F': 'forward', 'C': 'center', 'Guard': 'guard', 'Forward': 'forward', 'Center': 'center'}

class BuildError(RuntimeError):
    pass

def reject_removed_adu(relative, content):
    """Block ADU articles. A noindex stub that only redirects to the same path
    on sandiegoadubuilder.com is the GitHub Pages stand-in for a 301."""
    if relative in REMOVED_ADU_PATHS and content == adu_redirect_stub(relative):
        return
    if relative in REMOVED_ADU_PATHS or 'sandiegoadubuilder.com' in content:
        raise BuildError('Refusing to publish removed ADU content: '+relative)

def esc(value):
    return html.escape('' if value is None else str(value), quote=True)

def adu_redirect_stub(relative: str) -> str:
    """Permanent redirect. GitHub Pages cannot send HTTP 301 or 410."""
    if relative not in REMOVED_ADU_PATHS:
        raise BuildError('Not a former ADU path: '+relative)
    target = 'https://sandiegoadubuilder.com/' + relative
    safe = esc(target)
    return (
        '<!doctype html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '<meta charset="utf-8">\n'
        '<title>Moved</title>\n'
        '<meta name="robots" content="noindex">\n'
        f'<link rel="canonical" href="{safe}">\n'
        f'<meta http-equiv="refresh" content="0; url={safe}">\n'
        f'<script>location.replace("{safe}");</script>\n'
        '</head>\n'
        '<body>\n'
        f'<p><a href="{safe}">This page has moved.</a></p>\n'
        '</body>\n'
        '</html>\n'
    )

def adu_redirect_files() -> dict:
    return {relative: adu_redirect_stub(relative) for relative in sorted(REMOVED_ADU_PATHS)}

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
    return f'''<div class="brand-line"></div><header class="site-header"><div class="wrap masthead"><a class="brand" href="/" aria-label="Full Court Buckets home"><img src="/logo.png" alt="Full Court Buckets" width="220" height="76"></a>{nav}</div></header><div class="tagline"><div class="wrap"><span>WNBA NEWS · ANALYSIS · COMMENTARY</span><span>Built by the WNBA community, for the WNBA community</span></div></div>'''

def footer(include_standings=True):
    return site_nav.footer_html(include_standings)

def has_standings(root):
    return root is None or (Path(root)/'standings'/'index.html').is_file()

def document(title, description, route, body, structured=None, include_standings=True, menu=None, robots='index,follow,max-image-preview:large'):
    canonical=BASE+route
    schema=json.dumps(structured or {},ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">\n{GA4_TAG}\n{ADSENSE_TAG}\n<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><meta name="description" content="{esc(description)}"><meta name="robots" content="{esc(robots)}"><link rel="canonical" href="{canonical}"><link rel="icon" href="/favicon.svg"><meta property="og:type" content="website"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(description)}"><meta property="og:url" content="{canonical}"><meta property="og:site_name" content="Full Court Buckets"><meta name="theme-color" content="#0c0c10"><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700;800;900&amp;family=Inter:wght@400;500;600;700;800&amp;display=swap" rel="stylesheet"><link rel="stylesheet" href="/wnba/assets/players.css"><link rel="stylesheet" href="/assets/site-nav.css"><script type="application/ld+json">{schema}</script><script src="/assets/site-nav.js" defer></script><script src="/wnba/assets/players.js" defer></script></head><body><a class="skip" href="#content">Skip to content</a>{header(route, menu)}<main id="content" class="wrap">{body}</main>{footer(include_standings)}</body></html>'''

def stats_table(profile, kind):
    rows=sorted([r for r in profile.get('season_stats',[]) if r['season_type']==kind],key=lambda r:-r['season'])
    if not rows:
        return ''
    label='Regular season' if kind==2 else 'Playoffs'
    cells=[]
    for r in rows:
        cols=''.join(f'<td>{value(r.get(key),key=="games_played")}</td>' for key,_ in COLUMNS)
        cells.append(f'<tr data-season="{r["season"]}"><th scope="row">{r["season"]}</th><td class="team-cell">{esc(tname(r.get("team")))}</td>{cols}</tr>')
    heads=''.join(f'<th scope="col"><abbr title="{esc({"GP":"Games played","MIN":"Minutes per game","PTS":"Points per game","REB":"Rebounds per game","AST":"Assists per game","STL":"Steals per game","BLK":"Blocks per game","TO":"Turnovers per game","FG%":"Field goal percentage","3P%":"Three-point percentage","FT%":"Free throw percentage"}[text])}">{text}</abbr></th>' for _,text in COLUMNS)
    return f'<div class="competition" data-competition="{kind}"><h3>{label}</h3><div class="table-scroll" role="region" aria-label="{label} season statistics" tabindex="0"><table><caption>{label}: per-game averages, except games played and shooting percentages.</caption><thead><tr><th scope="col">YEAR</th><th scope="col">TEAM</th>{heads}</tr></thead><tbody>{"".join(cells)}</tbody></table></div></div>'

def game_table(profile):
    games=profile.get('recent_completed_games',[])
    if not games:
        return ''
    rows=[]
    for g in sorted(games,key=lambda r:str(r.get('date','')),reverse=True):
        tid=(g.get('team') or {}).get('id')
        home=(g.get('home_team') or {}).get('id')
        away=(g.get('visitor_team') or {}).get('id')
        if tid not in (home,away) or tid is None:
            opponent='Opponent not listed'; outcome='-'
        else:
            at_home=tid==home
            opponent=('vs. ' if at_home else '@ ')+tname(g.get('visitor_team' if at_home else 'home_team'))
            ours,theirs=(g.get('home_score'),g.get('away_score')) if at_home else (g.get('away_score'),g.get('home_score'))
            outcome=(('W' if ours>theirs else 'L' if ours<theirs else 'T')+f' {ours}-{theirs}') if isinstance(ours,(int,float)) and isinstance(theirs,(int,float)) else '-'
        label='Playoffs' if g.get('postseason') is True else 'Regular' if g.get('postseason') is False else 'Not listed'
        nums=''.join(f'<td>{value(g.get(k),True)}</td>' for k in ('pts','reb','ast','stl','blk','turnover'))
        rows.append(f'<tr><th scope="row">{esc(timestamp(g.get("date"),True))}</th><td class="team-cell">{esc(opponent)}</td><td>{label}</td><td>{outcome}</td><td>{esc(g.get("minutes") or "Not listed")}</td>{nums}</tr>')
    return f'''<section id="games" class="section"><p class="eyebrow">Completed games</p><h2>Recent game log</h2><p class="muted small">Recent games: {esc(profile.get('game_log_window_start'))} onward. Dates shown in Pacific time. This is not a complete career game log.</p><div class="table-scroll" role="region" tabindex="0" aria-label="Recent completed game statistics"><table><caption>Regular-season and playoff games are labeled separately.</caption><thead><tr><th scope="col">DATE</th><th scope="col">OPPONENT</th><th scope="col">TYPE</th><th scope="col">RESULT</th><th scope="col">MIN</th><th scope="col">PTS</th><th scope="col">REB</th><th scope="col">AST</th><th scope="col">STL</th><th scope="col">BLK</th><th scope="col">TO</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>'''


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

def faq_section(profile, root=None):
    """Render every curated FAQ item. Do not invent template or stats-generated questions.
    Players without data/wnba/faq/{slug}.json, or with an empty items list, get no FAQ block.
    """
    if root is None:
        root = Path(__file__).resolve().parents[1]
    pairs = curated_faq_pairs(profile, root)
    if not pairs:
        return '', None
    items = ''.join(
        f'<div class="faq-item"><h3>{esc(q)}</h3><p>{esc(a)}</p></div>'
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


def player_indexable(profile, root) -> bool:
    """No season rows stay indexable only when a curated FAQ is on file."""
    if player_has_records(profile):
        return True
    if root is None:
        return False
    return bool(curated_faq_pairs(profile, root))


def player_description(profile) -> str:
    p = profile.get('player') or {}
    name = (str(p.get('first_name') or '') + ' ' + str(p.get('last_name') or '')).strip()
    if player_has_records(profile):
        text = f'{name} WNBA season statistics, regular-season and playoff records, team information and recent game logs.'
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
    empty = {'number': '', 'position': '', 'pts': None, 'reb': None, 'ast': None}
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
    tablehtml=stats_table(profile,2)+stats_table(profile,3)
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
    updated_html=f'<p class="stats-updated">Stats updated {esc(long_date(day))}. {esc(STATS_SOURCE)}</p>' if day else f'<p class="stats-updated">{esc(STATS_SOURCE)}</p>'
    checked=timestamp(profile.get('checked_at'))
    latest=profile.get('recent_completed_games',[])
    latest_label=timestamp(max(g['date'] for g in latest),True) if latest else None
    last_game=f'<p>Most recent completed game: <b>{esc(latest_label)}</b>.</p>' if latest_label else ''
    nav='<a href="#overview">Overview</a>'+('<a href="#stats">Stats</a>' if stats else '')+('<a href="#games">Game log</a>' if latest else '')+('<a href="#teams">Teams</a>' if timeline else '')+('<a href="#teammates">Teammates</a>' if teammates else '')+'<a href="#sources">Sources</a>'
    hero=f'''<div class="breadcrumbs"><a href="/">Home</a><span>/</span><a href="/wnba/">Players</a><span>/</span><span>{esc(name)}</span></div><section class="hero" aria-labelledby="player-name"><div class="hero-main"><div class="hero-copy"><div class="hero-kicker"><span class="status">{state}</span><span>WNBA PLAYER PROFILE</span></div><h1 id="player-name"><span>{esc(p.get('first_name'))}</span><b class="gradient">{esc(p.get('last_name') or p.get('first_name'))}</b></h1>{summary_html}{updated_html}<p class="hero-meta">{meta}</p><div class="actions">{('<a class="button" href="#stats">View stats <span>→</span></a>' if stats else '<a class="button" href="#overview">Player overview →</a>')}<button type="button" id="share" class="text-button js-only">Share ↑</button><span id="share-status" role="status"></span></div></div><div class="hero-art" aria-hidden="true"><span class="ghost-number">{esc(number or 'FCB')}</span><div class="number-card"><span>{esc(p.get('last_name') or name)}</span><strong class="gradient">{esc(number or 'FCB')}</strong></div><small>FULL COURT BUCKETS · PLAYER ARCHIVE</small></div></div><div class="hero-stats">{metrics}<div class="stat-context"><b>{esc(note)}</b><span>Per-game averages</span></div></div></section><nav class="section-nav" aria-label="On this page">{nav}</nav>'''
    faq_html, faq_entity = faq_section(profile, root)
    numbers_note = 'No season records are listed on this page yet. A missing number is shown as a dash and is not turned into zero.' if not stats else 'Numbers on this page start in 2008. Regular-season and playoff statistics are listed separately. Season averages are not turned into a career total. A missing number is shown as a dash and is not turned into zero.'
    archive_line = 'Season records are not on this page yet.' if not stats else 'Explore the available records from 2008 onward.'
    sources=f'''<details class="sources section" id="sources"><summary>About these numbers</summary><p>Season statistics and recent games are listed on this page. Player ID: {p['id']}.</p><p>Last updated {esc(checked)}. A later game may not be on the page yet.</p>{last_game}<p>{numbers_note}</p><p>Height, college and similar details appear only when they are clear. Not appearing on a current roster is not the same as retirement. A new team listed here is not labeled as a trade or a signing.</p><p>This profile does not include news stories or a list of trades and signings. The number artwork is a design element, not a player photograph.</p><a href="/data/wnba/players/{slug}.json">View player data</a></details>'''
    body=hero+f'<div class="content-grid"><div><section class="section" id="overview"><p class="eyebrow">Player overview</p><h2>{esc(name)}</h2>{overview}<div class="overview-strip"><div><b>{len(set(r["season"] for r in regular))}</b><span>Regular seasons on record</span></div><div><b>{esc(span)}</b><span>Available statistical years</span></div></div></section>{statshtml}{game_table(profile)}{history}{teammates}</div><aside><section class="side-card"><p class="eyebrow">The essentials</p><h2>Player details</h2><dl>{detail_html}</dl></section><section class="freshness"><p class="eyebrow">Page status</p><h3>Last updated</h3><p>{esc(checked)}.</p>{last_game}<p class="small">Refreshed through the season, then less often once the season ends.</p></section><a class="button wide" href="/wnba/">Explore WNBA players →</a></aside></div>'+sources+(faq_html or '')+f'<section class="archive-band"><div><p class="eyebrow">Full Court Buckets · Player archive</p><h2>WNBA players. Past and present.</h2><p>{esc(archive_line)}</p></div><a class="button" href="/wnba/">Browse players →</a></section>'
    route=f'/wnba/{slug}/'
    webpage={'@type':'WebPage','name':name+' WNBA Stats & Player Profile','url':BASE+route,'about':{'@id':BASE+route+'#player'}}
    if day:
        webpage['dateModified']=day.isoformat()
    structured={'@context':'https://schema.org','@graph':[{'@type':'Person','@id':BASE+route+'#player','name':name,'url':BASE+route}, webpage, {'@type':'BreadcrumbList','itemListElement':[{'@type':'ListItem','position':1,'name':'Home','item':BASE+'/'},{'@type':'ListItem','position':2,'name':'Players','item':BASE+'/wnba/'},{'@type':'ListItem','position':3,'name':name,'item':BASE+route}]}]}
    if faq_entity:
        structured['@graph'].append(faq_entity)
    robots = 'index,follow,max-image-preview:large' if player_indexable(profile, root) else 'noindex'
    return document(player_title(name), player_description(profile), route, body, structured, has_standings(root), menu, robots)

def couple_note(root, slug):
    """One sourced relationship line. Empty unless this profile is in the couples data."""
    if root is None or not slug:
        return ''
    try:
        import build_couples
    except ImportError:
        return ''
    return build_couples.note_for_slug(root, slug)

def couples_hub_link(root):
    if root is None or not (Path(root) / 'wnba' / 'couples' / 'index.html').is_file():
        return ''
    return '<p><a class="inline-link" href="/wnba/couples/">Confirmed WNBA relationships</a></p>'

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
    # Search sits under the title so it is on the first mobile screen. Teams and the couples link stay below the list for internal links.
    body=f'''<div class="breadcrumbs"><a href="/">Home</a><span>/</span><span>Players</span></div><section class="directory-header player-hub"><p class="eyebrow">Full Court Buckets · The player archive</p><h1>WNBA players.<br><span class="gradient">Past and present.</span></h1><p>{len(entries)} profiles. Available statistics from 2008 onward.</p></section>{filters}{updated}<p class="small muted" id="result-count" role="status">{len(entries)} profiles</p><div class="player-grid">{''.join(cards)}</div><p id="no-players" hidden>No players match your search.</p>{team_html}{couples_hub_link(root)}'''
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
    for player in slot['players']:
        stats = _roster_stats(root, player)
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
    leader_html = ''
    if leaders:
        lines = []
        for key, label in (('pts', 'Points'), ('reb', 'Rebounds'), ('ast', 'Assists')):
            scored = [row for row in leaders if row.get(key) is not None]
            if not scored:
                continue
            best = max(float(row[key]) for row in scored)
            tied = [row for row in scored if float(row[key]) == best]
            names = ', '.join(links.inline_link(row['name'], '/wnba/'+row['slug']+'/') for row in tied)
            lines.append(f'<li>{label}: {names} ({tied[0][key]} per game).</li>')
        if lines:
            leader_html = (
                '<section class="section" id="leaders"><p class="eyebrow">2026 regular season</p>'
                f'<h2>Team leaders</h2><ul class="teammate-list">{"".join(lines)}</ul></section>'
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
    for path, lastmod in entries:
        lines.append('  <url>')
        lines.append(f'    <loc>{BASE}{path}</loc>')
        if lastmod:
            lines.append(f'    <lastmod>{lastmod}</lastmod>')
        lines.append('  </url>')
    lines.append('</urlset>')
    return '\n'.join(lines) + '\n'


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
        ('contact/index.html', '/contact/'),
        ('privacy/index.html', '/privacy/'),
        ('terms/index.html', '/terms/'),
        ('wnba/index.html', '/wnba/'),
        ('news/index.html', '/news/'),
        ('standings/index.html', '/standings/'),
        ('wnba/teams/index.html', '/wnba/teams/'),
        ('wnba/couples/index.html', '/wnba/couples/'),
    ]
    for relative, loc in static:
        lastmod = standings_day if loc == '/standings/' else newest
        add_page(relative, loc, lastmod)
    for slot in linking['by_id'].values():
        add_page('wnba/teams/' + slot['slug'] + '/index.html', links.team_href(slot), newest)
    for slug, day in article_dates.items():
        add_page(f'news/{slug}/index.html', f'/news/{slug}/', day or newest)
    players.sort()
    pages.sort()
    return players, pages


def build(root: Path):
    data=root/'data/wnba'
    index=json.loads((data/'players-index.json').read_text())
    status=json.loads((data/'status.json').read_text())
    if status.get('status')!='ok' or not index.get('players'):
        raise BuildError('No successful nonempty import is available.')
    published_players=[p for p in index['players'] if p.get('id') not in DUPLICATE_PLAYER_IDS]
    published_index={**index, 'players': published_players}
    linking=links.catalog_from_index(published_index)
    menu=site_nav.build_menu(root, site_nav.planned_paths(root, published_index, linking))
    files={}; ids=set(); slugs=set(); indexable_players=[]
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
        page=profile_page(profile, root, linking, menu)
        if page.count('class="inline-link"') > links.MAX_PLAYER_LINKS:
            raise BuildError(f'Too many contextual links on {slug}.')
        files[f'wnba/{slug}/index.html']=page
        if player_indexable(profile, root):
            indexable_players.append((slug, _player_lastmod(profile)))
    published_names={}
    for entry in published_players:
        published_names.setdefault(str(entry.get('name') or '').casefold(), []).append(entry['slug'])
    wnba_dir=root/'wnba'
    if wnba_dir.is_dir():
        for child in sorted(wnba_dir.iterdir(), key=lambda path: path.name):
            if not child.is_dir() or child.name in SKIP_PLAYER_DIRS or child.name in slugs:
                continue
            if not (child/'index.html').is_file():
                continue
            name=_name_from_player_html((child/'index.html').read_text(encoding='utf-8'))
            owners=published_names.get(name.casefold(), []) if name else []
            target=f'{BASE}/wnba/{owners[0]}/' if len(owners)==1 else f'{BASE}/wnba/'
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
        text=site_nav.install(links.apply_homepage(original, links.load_articles(root)), '/', menu)
        if text != original:
            files['index.html']=text
    phrases=links.article_phrases(published_index, linking)
    for relative, content in links.assemble_news_pages(root).items():
        if links.is_redirect_html(content):
            files[relative]=content
            continue
        current=page_url(Path(relative))
        if relative != 'news/index.html':
            content=links.ensure_footer_hubs(links.link_copy(content, phrases))
        files[relative]=site_nav.install(content, current, menu)
    standings_path=root/'standings'/'index.html'
    standings_data=root/'api'/'wnba-standings'
    if standings_path.is_file() and standings_data.is_file():
        original=standings_path.read_text(encoding='utf-8')
        updated=site_nav.install(
            links.apply_standings(original, linking, json.loads(standings_data.read_text(encoding='utf-8-sig'))),
            '/standings/',
            menu,
        )
        if updated != original:
            files['standings/index.html']=updated
    elif standings_path.is_file():
        original=standings_path.read_text(encoding='utf-8')
        updated=site_nav.install(original, '/standings/', menu)
        if updated != original:
            files['standings/index.html']=updated
    for relative in ('about/index.html','contact/index.html','privacy/index.html','terms/index.html'):
        path=root/relative
        if not path.is_file():
            continue
        original=path.read_text(encoding='utf-8')
        updated=site_nav.install(links.apply_known_page_links(original, relative), page_url(Path(relative)), menu)
        if updated != original:
            files[relative]=updated
    files.update(links.legacy_player_redirect_files({entry['slug'] for entry in published_players}))
    files.update(adu_redirect_files())
    files.update(site_nav.install_tree(root, menu, set(files)))
    robots=root/'robots.txt'
    robots_text=robots.read_text() if robots.exists() else 'User-agent: *\nAllow: /\n'
    sitemap='Sitemap: '+BASE+'/player-sitemap.xml'
    if sitemap not in robots_text:
        files['robots.txt']=robots_text.rstrip()+'\n'+sitemap+'\n'
    report={'status':'ok','profile_count':len(slugs),'team_page_count':len(linking['by_id']),'data_checked_at':index.get('checked_at'), 'source':'BALLDONTLIE','coverage_start':2008,'complete_career_totals':False,'news_connected':False,'transactions_connected':False,'directory':'/wnba/'}
    files['data/wnba/site-build.json']=json.dumps(report,indent=2)+'\n'
    articles=links.load_articles(root)
    for relative, content in list(files.items()):
        if relative.endswith('.html'):
            files[relative]=links.rewrite_legacy_article_urls(content, articles)
    player_rows, page_rows = sitemap_rows(root, files, linking, indexable_players, articles)
    files['player-sitemap.xml'] = _sitemap_document(player_rows)
    files['pages-sitemap.xml'] = _sitemap_document(page_rows)
    files['sitemap.xml'] = _sitemap_document(sorted(player_rows + page_rows))
    links.verify_hrefs(root, files)
    # All profiles are validated and rendered before any existing page is replaced.
    changes=0
    for relative,content in files.items():
        reject_removed_adu(relative, content)
        path=root/relative
        if path.exists() and path.read_text()==content:
            continue
        path.parent.mkdir(parents=True,exist_ok=True)
        temporary=path.with_suffix(path.suffix+'.tmp')
        temporary.write_text(content)
        temporary.replace(path)
        changes+=1
    print(f'Built {len(slugs)} static player profiles and directory; {changes} files changed.')
    return len(slugs)

def refresh_published_news(root: Path | None = None) -> int:
    """Move posts to /news/<slug>/ and retarget links without rebuilding player profiles."""
    root = root or Path(__file__).resolve().parents[1]
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
        if relative != 'news/index.html':
            content = links.ensure_footer_hubs(links.link_copy(content, phrases))
        files[relative] = site_nav.install(content, current, menu)
    homepage = root / 'index.html'
    if homepage.is_file():
        files['index.html'] = site_nav.install(
            links.apply_homepage(homepage.read_text(encoding='utf-8'), links.load_articles(root)),
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
