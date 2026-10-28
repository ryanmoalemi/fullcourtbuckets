"""Extra blocks for the 15 WNBA team pages.

Sources:
* api/wnba-standings for the record line (built by build_standings.py).
* data/wnba/team-facts.json, a snapshot of each club's WNBA.com team page
  (automation/fetch_team_facts.py), for team ranks and developmental tags.
* The players' own 2026 season lines in data/wnba/players.
* data/wnba/player-draft.json, team-history.json and schedule-2026.json, snapshots
  of WNBA.com player pages, standings and the league schedule feed
  (automation/fetch_team_extras.py).
* data/wnba/arena-capacity.json, venue-operator or league capacity figures with a
  source URL per arena.

Time-sensitive text sits in data-fcb-dynamic sections that the builder refills
on every run. Nothing here is invented: a missing field is left out.
"""
from __future__ import annotations

import csv
import html
import io
import json
import re
import unicodedata
from pathlib import Path

BASE = 'https://fullcourtbuckets.com'
FACTS_PATH = ('data', 'wnba', 'team-facts.json')
END = '<!--/fcb-dynamic-->'
CC0 = 'https://creativecommons.org/publicdomain/zero/1.0/'


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def _ordinal(number: int) -> str:
    if 10 <= number % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(number % 10, 'th')
    return f'{number}{suffix}'


def norm_name(name: str) -> str:
    text = unicodedata.normalize('NFKD', str(name or '')).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z]', '', text.casefold())


_FACTS_CACHE: dict = {}


def load_facts(root) -> dict:
    if root is None:
        return {}
    path = Path(root).joinpath(*FACTS_PATH)
    key = str(path)
    if key not in _FACTS_CACHE:
        try:
            _FACTS_CACHE[key] = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            _FACTS_CACHE[key] = {}
    return _FACTS_CACHE[key]


def team_facts(root, name: str) -> dict:
    return (load_facts(root).get('teams') or {}).get(name) or {}


def facts_checked(root) -> str:
    """Day the WNBA.com snapshot was taken, in Pacific time (the site's clock)."""
    raw = str(load_facts(root).get('checked_at') or '')
    if not raw:
        return ''
    try:
        import datetime as dt
        from zoneinfo import ZoneInfo
        return dt.datetime.fromisoformat(raw).astimezone(ZoneInfo('America/Los_Angeles')).date().isoformat()
    except ValueError:
        return raw[:10]


def roster_facts(facts: dict, player_name: str, number: str = '') -> dict:
    roster = facts.get('roster') or {}
    wanted = norm_name(player_name)
    for name, row in roster.items():
        if norm_name(name) == wanted:
            return row
    # Same surname and jersey number (Madison/Madi Scott, accents).
    last = norm_name(str(player_name).split()[-1]) if player_name else ''
    for name, row in roster.items():
        if number and str(row.get('number') or '') == str(number) and norm_name(name.split()[-1]) == last:
            return row
    return {}


def dynamic(tag: str, kind: str, source: str, updated: str, body: str, attrs: str = '') -> str:
    return (
        f'<{tag}{attrs} data-fcb-dynamic="{esc(kind)}" data-fcb-source="{esc(source)}" '
        f'data-fcb-updated="{esc(updated)}">{body}</{tag}>{END}'
    )


def standings_day(root) -> str:
    if root is None:
        return ''
    try:
        data = json.loads((Path(root) / 'api' / 'wnba-standings').read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return ''
    return str(data.get('updatedAt') or '')[:10]


def record_text(name: str, standing: dict | None, conference: str) -> str:
    if not standing or not isinstance(standing.get('wins'), int) or not isinstance(standing.get('losses'), int):
        return ''
    text = f'{standing["wins"]}-{standing["losses"]} in the 2026 regular season'
    rank = standing.get('conferenceRank')
    if isinstance(rank, int) and not isinstance(rank, bool):
        text += f', {_ordinal(rank)} in the {conference or "conference"}'
    seed = standing.get('playoffSeed')
    if isinstance(seed, int) and not isinstance(seed, bool) and 1 <= seed <= 8:
        text += f' and the No. {seed} playoff seed'
    return text


def lead_html(root, slot: dict, standing: dict | None, count: int) -> str:
    """One-line lead under the H1: record, seed and roster size."""
    name = slot['full_name']
    conference = str(slot.get('conference') or (standing or {}).get('conference') or '').strip()
    if conference and not conference.endswith('Conference'):
        conference += ' Conference'
    noun = 'player' if count == 1 else 'players'
    record = record_text(name, standing, conference)
    sentence = f'The {name} went {record}. ' if record else ''
    sentence += f'{count} {noun} are on the current roster.'
    return dynamic('p', 'team-status', 'api/wnba-standings', standings_day(root), esc(sentence), ' class="team-lead"')


RANK_LABELS = (('ppg', 'Points'), ('rpg', 'Rebounds'), ('apg', 'Assists'), ('oppg', 'Points allowed'))


def ranks_html(root, slot: dict) -> str:
    facts = team_facts(root, slot['full_name'])
    ranks = facts.get('ranks') or {}
    items = []
    for key, label in RANK_LABELS:
        row = ranks.get(key) or {}
        value, rank = row.get('value'), row.get('rank')
        if value is None or not isinstance(rank, int):
            continue
        items.append(
            f'<li><span class="rank-label">{esc(label)}</span> <strong>{esc(value)}</strong> '
            f'per game <span class="rank-place">({_ordinal(rank)} of 15)</span></li>'
        )
    if not items:
        return ''
    source = esc(facts.get('source') or 'https://www.wnba.com/')
    body = (
        f'<ul class="team-ranks">{"".join(items)}</ul>'
        f'<p class="muted small">League ranks as listed on <a href="{source}" target="_blank" rel="noopener">WNBA.com</a>, '
        f'checked {esc(facts_checked(root))}.</p>'
    )
    return (
        '<section class="section" id="team-ranks"><p class="eyebrow">2026 regular season</p><h2>League ranks</h2>'
        + dynamic('div', 'team-ranks', 'data/wnba/team-facts.json', facts_checked(root), body)
        + '</section>'
    )


def faq_items(root, slot: dict, standing: dict | None, leaders: dict, count: int) -> list[tuple[str, str]]:
    """Questions answered only from data on this page."""
    name = slot['full_name']
    facts = team_facts(root, name)
    items = []
    conference = str(slot.get('conference') or '').strip()
    record = record_text(name, standing, conference)
    if record:
        items.append((f'What was the {name} record in 2026?', f'The {name} went {record}.'))
    items.append((f'Who is on the {name} roster?', f'{count} players are on the current {name} roster. The table at the top of this page lists each one with number, position and 2026 per-game averages.'))
    for key, label in (('pts', 'points'), ('reb', 'rebounds'), ('ast', 'assists')):
        row = leaders.get(key)
        if row:
            items.append((f'Who led the {name} in {label} in 2026?', f'{row["name"]} led the {name} with {row[key]} {label} per game in the 2026 regular season.'))
    if facts.get('head_coach'):
        items.append((f'Who is the {name} head coach?', f'{facts["head_coach"]} is the head coach of the {name}, according to WNBA.com.'))
    if facts.get('arena'):
        items.append((f'Where do the {name} play home games?', f'WNBA.com lists {str(facts["arena"]).strip()} as the {name} home arena.'))
    items.append((f'Where can I watch {name} games with other fans?', 'The Full Court Buckets where-to-watch guide lists bars that show WNBA games, many confirmed with staff.'))
    return items


def faq_html(items: list[tuple[str, str]], updated: str) -> str:
    if not items:
        return ''
    rows = ''.join(
        f'<details class="team-faq-item"><summary>{esc(q)}</summary><p>{esc(a)}'
        + (' <a href="/wnba/where-to-watch/">Where to watch WNBA games</a>.' if 'where-to-watch' in a else '')
        + '</p></details>'
        for q, a in items
    )
    return (
        '<section class="section" id="faq"><p class="eyebrow">Questions</p><h2>Frequently asked questions</h2>'
        + dynamic('div', 'team-faq', 'api/wnba-standings data/wnba/team-facts.json', updated, rows)
        + '</section>'
    )


def faq_schema(items: list[tuple[str, str]], url: str) -> dict | None:
    if not items:
        return None
    return {
        '@type': 'FAQPage', '@id': url + '#faq',
        'mainEntity': [
            {'@type': 'Question', 'name': q, 'acceptedAnswer': {'@type': 'Answer', 'text': a}}
            for q, a in items
        ],
    }


CSV_FIELDS = ('team', 'number', 'player', 'position', 'developmental', 'draft_year', 'draft_round', 'draft_pick', 'undrafted', 'ppg', 'rpg', 'apg', 'mpg', 'profile_url')


def csv_name(slot: dict) -> str:
    return f'{slot["slug"]}-roster-2026.csv'


def roster_csv(slot: dict, rows: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow(CSV_FIELDS)
    for row in rows:
        writer.writerow([
            slot['full_name'], row.get('number') or '', row['name'], row.get('position') or '',
            'yes' if row.get('developmental') else 'no',
            *draft_fields(row.get('draft') or {}),
            row.get('pts') or '', row.get('reb') or '', row.get('ast') or '', row.get('min') or '',
            f'{BASE}/wnba/{row["slug"]}/',
        ])
    return buffer.getvalue()


def download_html(slot: dict, route: str, updated: str) -> str:
    name = slot['full_name']
    href = route + csv_name(slot)
    cite = (
        f'Full Court Buckets, "{name} 2026 roster and season averages," '
        f'{BASE}{route}, updated {updated}. CC0 1.0.'
    )
    body = (
        f'<p><a class="data-download" href="{esc(href)}" download>Download the {esc(name)} roster (CSV)</a>. '
        f'<a class="data-download" href="{esc(route + history_csv_name(slot))}" download>season-by-season history (CSV)</a> and '
        f'<a class="data-download" href="{esc(route + schedule_csv_name(slot))}" download>2026 schedule and results (CSV)</a>. '
        f'All released under <a href="{CC0}" target="_blank" rel="noopener">CC0 1.0</a>: free to use with no permission needed.</p>'
        f'<p class="cite-this"><strong>Cite this:</strong> {esc(cite)}</p>'
    )
    return (
        '<section class="section" id="data-download"><p class="eyebrow">Data</p><h2>Download and cite</h2>'
        + dynamic('div', 'team-download', 'data/wnba/players', updated, body)
        + '</section>'
    )


# ---------------------------------------------------------------- phase 2 --

_PORTRAITS: dict = {}


def portraits(root) -> dict:
    """Approved player portraits keyed by slug (content/player-illustrations.json)."""
    if root is None:
        return {}
    key = str(root)
    if key not in _PORTRAITS:
        found = {}
        try:
            data = json.loads((Path(root) / 'content' / 'player-illustrations.json').read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            data = {}
        for row in data.get('portraits') or []:
            if row.get('approved') and row.get('slug') and str(row.get('src') or '').startswith('/'):
                found[row['slug']] = row['src']
        _PORTRAITS[key] = found
    return _PORTRAITS[key]


def initials(name: str) -> str:
    parts = [part for part in re.split(r'[\s-]+', str(name or '')) if part[:1].isalpha()]
    if not parts:
        return '?'
    letters = parts[0][0] + (parts[-1][0] if len(parts) > 1 else '')
    return letters.upper()


def headshot_html(root, slug: str, name: str) -> str:
    """Circle headshot beside a name; an initials avatar when no approved photo exists."""
    src = portraits(root).get(slug)
    if src:
        return (f'<img class="roster-face" src="{esc(src)}" alt="" width="40" height="40" '
                f'loading="lazy" decoding="async">')
    return f'<span class="roster-face roster-face-fallback" aria-hidden="true">{esc(initials(name))}</span>'


def bio_cells(official: dict) -> list[str]:
    """Height, age, experience and school/country from WNBA.com; blank when not listed."""
    raw = official.get('experience')
    exp = str(raw).strip() if raw is not None else ''
    if exp == 'R':
        exp = 'Rookie'
    elif exp:
        exp = f'{exp} yr' if exp == '1' else f'{exp} yrs'
    school = str(official.get('school') or '').strip()
    country = str(official.get('country') or '').strip()
    if school and country and country != 'USA':
        origin = f'{school} / {country}'
    else:
        origin = school or country
    values = [str(official.get('height') or '').strip(), official.get('age'), exp, origin]
    return [esc(v) if v not in (None, '') else '' for v in values]


def _games(root) -> list[dict]:
    if root is None:
        return []
    out = []
    for path in sorted((Path(root) / 'data' / 'games').glob('2026-*.json')):
        try:
            game = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            continue
        if game.get('status') == 'final' and game.get('season') in (2026, None):
            out.append(game)
    return out


def _recaps(slot: dict) -> list:
    try:
        import team_season
        return list(team_season.COVERAGE.get(slot['slug']) or [])
    except Exception:
        return []


def _finals_teams(root) -> dict:
    """Abbreviation to full name for the clubs in data/finals-schedule.json."""
    try:
        finals = json.loads((Path(root) / 'data' / 'finals-schedule.json').read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    names = {}
    for game in _games(root):
        for side in ('home', 'away'):
            t = game.get(side) or {}
            if t.get('abbreviation'):
                names[t['abbreviation']] = t.get('full_name') or t['abbreviation']
    clubs = {g.get('home') for g in finals.get('games') or [] if g.get('home')}
    return {abbr: names.get(abbr, abbr) for abbr in sorted(clubs)}


def playoff_html(root, slot: dict) -> str:
    """2026 playoff results and next scheduled games, from data/games and data/finals-schedule.json."""
    if root is None:
        return ''
    name = slot['full_name']
    played = []
    abbr = ''
    for game in _games(root):
        home, away = game.get('home') or {}, game.get('away') or {}
        if name not in (home.get('full_name'), away.get('full_name')):
            continue
        mine, other = (home, away) if home.get('full_name') == name else (away, home)
        abbr = mine.get('abbreviation') or abbr
        if not isinstance(mine.get('score'), int) or not isinstance(other.get('score'), int):
            continue
        played.append((game, mine, other, mine is home))
    try:
        pbp = json.loads((Path(root) / 'data' / 'fcb-game-pages.json').read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        pbp = {}
    try:
        finals = json.loads((Path(root) / 'data' / 'finals-schedule.json').read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        finals = {}
    clubs = _finals_teams(root)
    upcoming = [g for g in finals.get('games') or [] if abbr and abbr in clubs]
    if not played and not upcoming:
        return ''
    recaps = {score: (href, label) for href, label, score in _recaps(slot)}
    rows = []
    for game, mine, other, at_home in played:
        won = mine['score'] > other['score']
        score = f'{mine["score"]}-{other["score"]}'
        alt = f'{other["score"]}-{mine["score"]}'
        ot = ' (OT)' if game.get('overtime') else ''
        extra = []
        recap = recaps.get(score) or recaps.get(alt)
        if recap:
            extra.append(f'<a class="inline-link" href="{esc(recap[0])}">Recap</a>')
        page = pbp.get(str(game.get('espn_game_id') or ''))
        if page:
            extra.append(f'<a class="inline-link" href="{esc(page)}">Play-by-play</a>')
        rows.append(
            f'<tr><td>{esc(game.get("date") or "")}</td>'
            f'<td>{"vs." if at_home else "at"} {esc(other.get("full_name") or "")}</td>'
            f'<td>{"W" if won else "L"} {esc(score)}{ot}</td><td>{" · ".join(extra)}</td></tr>'
        )
    for game in upcoming:
        where = 'vs.' if game.get('home') == abbr else 'at'
        opp = next((t for t in clubs if t != abbr), '')
        tag = ' (if needed)' if game.get('if_needed') else ''
        rows.append(
            f'<tr class="upcoming"><td>{esc(game.get("day") or game.get("date") or "")}</td>'
            f'<td>Finals Game {esc(game.get("game"))}{tag}: {where} {esc(clubs.get(opp, opp))}</td>'
            f'<td>{esc(game.get("time") or "")}</td><td>{esc(game.get("tv") or "")}</td></tr>'
        )
    last = max([g.get('date') or '' for g, *_ in played] + [''])
    table = (
        '<div class="table-scroll" role="region" tabindex="0" aria-label="2026 playoff games">'
        '<table><caption>2026 playoff results and upcoming games. Scores from the site\'s committed box scores; '
        'times as published by the league.</caption>'
        '<thead><tr><th scope="col">Date</th><th scope="col">Game</th><th scope="col">Result or time</th>'
        '<th scope="col">Links or TV</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
    )
    body = dynamic('div', 'team-schedule', 'data/games data/finals-schedule.json', last, table)
    return ('<section class="section" id="schedule"><p class="eyebrow">2026 postseason</p>'
            f'<h2>Playoff results and schedule</h2>{body}</section>')


def franchise_html(root, slot: dict) -> str:
    """Franchise facts as listed on the club's WNBA.com team page. Missing fields stay out."""
    facts = team_facts(root, slot['full_name'])
    if not facts:
        return ''
    source = facts.get('source') or ''
    items = []
    if facts.get('founded'):
        items.append(('First season', esc(facts['founded'])))
    arena = str(facts.get('arena') or '').strip()
    if arena:
        cap, cap_src = arena_capacity(root, slot['full_name'], facts)
        cap_html = ''
        if cap:
            label = f'{cap:,}' + (f' for {cap_src["label"]}' if cap_src.get('label') else '')
            cap_html = (f' (capacity {label}, per <a href="{esc(cap_src["source"])}" target="_blank" '
                        f'rel="noopener">{esc(cap_src["source_name"])}</a>)')
        items.append(('Arena', esc(arena) + cap_html))
    for key, label in (('head_coach', 'Head coach'), ('general_manager', 'General manager'), ('owner', 'Owner')):
        if facts.get(key):
            items.append((label, esc(str(facts[key]).strip())))
    titles = [str(t.get('year')) for t in facts.get('championships') or [] if t.get('year')]
    items.append(('WNBA championships', esc(', '.join(titles)) if titles else 'None'))
    cups = facts.get('commissioners_cup') or []
    if cups:
        items.append(("Commissioner's Cup", esc(', '.join(str(c) for c in cups))))
    site = facts.get('official_site')
    if site:
        items.append(('Official site', f'<a href="{esc(site)}" rel="noopener" target="_blank">{esc(site.split("//")[-1].rstrip("/"))}</a>'))
    dl = ''.join(f'<div><dt>{k}</dt><dd>{v}</dd></div>' for k, v in items)
    parts = [f'<dl class="franchise-facts">{dl}</dl>']
    leaders = facts.get('franchise_leaders') or {}
    li = ''.join(
        f'<li>{esc(k.capitalize())}: {esc(v.get("player"))} ({int(v["total"]):,})</li>'
        for k, v in leaders.items() if v.get('player') and isinstance(v.get('total'), int)
    )
    if li:
        parts.append(f'<h3>Franchise career leaders</h3><ul class="teammate-list">{li}</ul>')
    hof = facts.get('hall_of_fame') or []
    if hof:
        rows = ''.join(
            f'<tr><td>{esc(h.get("player") or "")}</td><td>{esc(h.get("position") or "")}</td>'
            f'<td>{esc(h.get("seasons") or "")}</td><td>{esc(h.get("inducted") or "")}</td></tr>'
            for h in hof
        )
        parts.append(
            '<h3>Hall of Famers</h3><div class="table-scroll" role="region" tabindex="0" aria-label="Hall of Famers">'
            '<table><thead><tr><th scope="col">Player</th><th scope="col">Pos</th><th scope="col">With team</th>'
            f'<th scope="col">Inducted</th></tr></thead><tbody>{rows}</tbody></table></div>'
        )
    if cap and cap_src.get('override'):
        parts.append(f'<p class="muted small">{esc(cap_src["override"])}</p>')
    credit = (f'<p class="muted small">Franchise facts as listed on <a href="{esc(source)}" target="_blank" '
              f'rel="noopener">WNBA.com</a>, checked {esc(facts_checked(root))}.</p>') if source else ''
    return ('<section class="section" id="franchise"><p class="eyebrow">Franchise</p>'
            f'<h2>About the {esc(slot["full_name"])}</h2>{"".join(parts)}{credit}</section>')


# ------------------------------------------------- draft, history, schedule --

_JSON: dict = {}


def _load(root, name: str) -> dict:
    if root is None:
        return {}
    path = Path(root) / 'data' / 'wnba' / name
    key = str(path)
    if key not in _JSON:
        try:
            _JSON[key] = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            _JSON[key] = {}
    return _JSON[key]


def _as_int(value):
    try:
        return int(str(value).replace(',', '').strip())
    except (TypeError, ValueError):
        return None


def arena_capacity(root, team: str, facts: dict) -> tuple[int | None, dict]:
    """Capacity and its source: the venue/league figure when filed, else WNBA.com's."""
    filed = (_load(root, 'arena-capacity.json').get('teams') or {}).get(team) or {}
    if _as_int(filed.get('capacity')):
        return _as_int(filed['capacity']), filed
    cap = _as_int(facts.get('arena_capacity'))
    if cap:
        return cap, {'source': facts.get('source') or '', 'source_name': 'WNBA.com', 'label': ''}
    return None, {}


def player_draft(root, team: str, name: str) -> dict:
    wanted = norm_name(name)
    rows = (_load(root, 'player-draft.json').get('players') or {}).values()
    for row in rows:
        if row.get('team') == team and norm_name(row.get('player')) == wanted:
            return row
    for row in rows:
        if norm_name(row.get('player')) == wanted:
            return row
    return {}


def draft_text(row: dict) -> str:
    if row.get('undrafted'):
        return 'Undrafted'
    if row.get('year') and row.get('round') and row.get('pick'):
        return f'{row["year"]} R{row["round"]}, No. {row["pick"]}'
    return ''


def draft_fields(row: dict) -> list:
    if row.get('undrafted'):
        return ['', '', '', 'yes']
    if row.get('year'):
        return [row.get('year') or '', row.get('round') or '', row.get('pick') or '', 'no']
    return ['', '', '', '']


def history_csv_name(slot: dict) -> str:
    return f'{slot["slug"]}-history.csv'


def schedule_csv_name(slot: dict) -> str:
    return f'{slot["slug"]}-schedule-2026.csv'


def team_history(root, team: str) -> list[dict]:
    return list((_load(root, 'team-history.json').get('teams') or {}).get(team) or [])


def history_html(root, slot: dict) -> str:
    rows = team_history(root, slot['full_name'])
    if not rows:
        return ''
    updated = str(_load(root, 'team-history.json').get('checked_at') or '')[:10]
    body = []
    for r in rows:
        wl = f'{r["wins"]}-{r["losses"]}' if isinstance(r.get('wins'), int) and isinstance(r.get('losses'), int) else ''
        body.append(f'<tr><td>{r["season"]}</td><td>{esc(r.get("team_name") or "")}</td><td>{esc(wl)}</td>'
                    f'<td>{esc(r.get("finish") or "")}</td><td>{esc(r.get("playoffs") or "")}</td></tr>')
    table = (
        '<div class="table-scroll" role="region" tabindex="0" aria-label="Season-by-season history">'
        '<table><caption>Season-by-season regular-season record, finish and playoff result.</caption>'
        '<thead><tr><th scope="col">Season</th><th scope="col">Team</th><th scope="col">W-L</th>'
        '<th scope="col">Finish</th><th scope="col">Playoffs</th></tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>'
        '<p class="muted small">Methods: W-L and finish from <a href="https://www.wnba.com/standings" target="_blank" '
        'rel="noopener">WNBA.com standings</a> for 2010 on (finish is the standings rank: by conference through 2015, '
        'league-wide from 2016). WNBA.com does not publish standings before 2010, so for 1997-2009 the W-L is counted '
        'from final regular-season scores in the <a href="https://www.wnba.com/schedule" target="_blank" rel="noopener">'
        'WNBA.com schedule</a> and the finish is left blank. Playoff result from the series line in the same schedule. '
        'Team name is the name the franchise played under that season.</p>'
    )
    return ('<section class="section" id="history"><p class="eyebrow">Franchise history</p>'
            f'<h2>Season by season</h2>{dynamic("div", "team-history", "data/wnba/team-history.json", updated, table)}</section>')


def _team_id(root, team: str):
    for tid, name in (_load(root, 'schedule-2026.json').get('teams') or {}).items():
        if name == team:
            return int(tid)
    return None


def team_schedule(root, team: str) -> list[dict]:
    data = _load(root, 'schedule-2026.json')
    tid = _team_id(root, team)
    names = {int(k): v for k, v in (data.get('teams') or {}).items()}
    out = []
    for g in data.get('games') or []:
        if tid not in (g['home']['id'], g['away']['id']):
            continue
        home = g['home']['id'] == tid
        mine, other = (g['home'], g['away']) if home else (g['away'], g['home'])
        result = ''
        if isinstance(mine.get('score'), int) and isinstance(other.get('score'), int) and (mine['score'] or other['score']):
            result = f'{"W" if mine["score"] > other["score"] else "L"} {mine["score"]}-{other["score"]}'
        kind = {'Regular Season': 'Regular season', 'Comm Cup': "Commissioner's Cup final"}.get(g['type'], g['type'])
        if g['type'] == 'Playoffs' and g.get('label'):
            kind = f'Playoffs: {g["label"]}'
        out.append({'date': g.get('date') or '', 'type': kind, 'home': home,
                    'opponent': names.get(other['id']) or other.get('tricode') or '',
                    'result': result, 'arena': g.get('arena') or '', 'series': g.get('series') or ''})
    return out


def schedule_html(root, slot: dict) -> str:
    games = team_schedule(root, slot['full_name'])
    if not games:
        return ''
    recaps = {score: href for href, label, score in _recaps(slot)}
    updated = str(_load(root, 'schedule-2026.json').get('checked_at') or '')[:10]
    rows, w, l = [], 0, 0
    for g in games:
        score = g['result'][2:]
        alt = '-'.join(reversed(score.split('-'))) if score else ''
        recap = recaps.get(score) or recaps.get(alt) if score else None
        link = f'<a class="inline-link" href="{esc(recap)}">Recap</a>' if recap else ''
        if g['type'] == 'Regular season' and g['result']:
            w += g['result'].startswith('W')
            l += g['result'].startswith('L')
        rows.append(f'<tr><td>{esc(g["date"])}</td><td>{esc(g["type"])}</td>'
                    f'<td>{"vs." if g["home"] else "at"} {esc(g["opponent"])}</td><td>{esc(g["result"])}</td>'
                    f'<td>{esc(g["arena"])}</td><td>{link}</td></tr>')
    table = (
        '<div class="table-scroll" role="region" tabindex="0" aria-label="2026 schedule and results">'
        f'<table><caption>Every 2026 game: regular season ({w}-{l}), Commissioner\'s Cup final and playoffs.</caption>'
        '<thead><tr><th scope="col">Date</th><th scope="col">Game</th><th scope="col">Opponent</th>'
        '<th scope="col">Result</th><th scope="col">Arena</th><th scope="col">Links</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>'
        '<p class="muted small">Methods: dates (U.S. Eastern), opponents, arenas and final scores from the '
        '<a href="https://www.wnba.com/schedule?season=2026" target="_blank" rel="noopener">WNBA.com schedule</a>.</p>'
    )
    return ('<section class="section" id="season-schedule"><p class="eyebrow">2026 season</p>'
            f'<h2>Schedule and results</h2>{dynamic("div", "team-season-schedule", "data/wnba/schedule-2026.json", updated, table)}</section>')


def history_csv(root, slot: dict) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow(('franchise', 'season', 'team_name', 'wins', 'losses', 'finish', 'playoffs', 'record_source'))
    for r in team_history(root, slot['full_name']):
        writer.writerow((slot['full_name'], r['season'], r.get('team_name') or '', r.get('wins') if r.get('wins') is not None else '',
                         r.get('losses') if r.get('losses') is not None else '', r.get('finish') or '', r.get('playoffs') or '',
                         r.get('record_source') or ''))
    return buffer.getvalue()


def schedule_csv(root, slot: dict) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow(('team', 'date_et', 'game', 'home_away', 'opponent', 'result', 'arena', 'series'))
    for g in team_schedule(root, slot['full_name']):
        writer.writerow((slot['full_name'], g['date'], g['type'], 'home' if g['home'] else 'away',
                         g['opponent'], g['result'], g['arena'], g['series']))
    return buffer.getvalue()
