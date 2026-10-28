"""Extra blocks for the 15 WNBA team pages.

Sources:
* api/wnba-standings for the record line (built by build_standings.py).
* data/wnba/team-facts.json, a snapshot of each club's WNBA.com team page
  (automation/fetch_team_facts.py), for team ranks and developmental tags.
* The players' own 2026 season lines in data/wnba/players.

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
    return str(load_facts(root).get('checked_at') or '')[:10]


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


CSV_FIELDS = ('team', 'number', 'player', 'position', 'developmental', 'ppg', 'rpg', 'apg', 'mpg', 'profile_url')


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
        f'Released under <a href="{CC0}" target="_blank" rel="noopener">CC0 1.0</a>: free to use with no permission needed.</p>'
        f'<p class="cite-this"><strong>Cite this:</strong> {esc(cite)}</p>'
    )
    return (
        '<section class="section" id="data-download"><p class="eyebrow">Data</p><h2>Download and cite</h2>'
        + dynamic('div', 'team-download', 'data/wnba/players', updated, body)
        + '</section>'
    )
