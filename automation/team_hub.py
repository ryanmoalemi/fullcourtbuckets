"""Teams hub at /wnba/teams/.

Facts are read from files already in the repo: data/wnba/teams.json,
api/wnba-standings, and the expansion guide at news/wnba-expansion-teams/.
Nothing here fills in a conference, record, city, or photo that those files do not support.
"""
from __future__ import annotations

import html
import json
from pathlib import Path
import re

import internal_links as links
import team_names

BASE = 'https://fullcourtbuckets.com'
HUB = '/wnba/teams/'
EM_DASH = '\u2014'

# Photos already published on the site, plus CC-licensed Wikimedia files saved
# under images/teams/ for clubs that had no photo in the repo yet.
VISUALS = {
    'atlanta-dream': {
        'src': '/images/articles/dream-mystics-game-1-howard-reese/jordin-canada-dream-2026.jpg',
        'alt': 'Jordin Canada of the Atlanta Dream at the free throw line',
        'width': 1600,
        'height': 1068,
        'author': 'John McClellan',
        'page': 'https://commons.wikimedia.org/wiki/File:260527_Lynx_Dream_JohnMc210_(55298398176).jpg',
        'license': 'CC BY-SA 4.0',
        'license_href': 'https://creativecommons.org/licenses/by-sa/4.0/',
    },
    'chicago-sky': {
        'src': '/images/teams/chicago-sky.jpg',
        'alt': 'Kamilla Cardoso of the Chicago Sky',
        'width': 1200,
        'height': 1200,
        'author': 'John McClellan',
        'page': 'https://commons.wikimedia.org/wiki/File:Kamilla_Cardoso_2025_(cropped).jpg',
        'license': 'CC BY-SA 2.0',
        'license_href': 'https://creativecommons.org/licenses/by-sa/2.0',
    },
    'connecticut-sun': {
        'src': '/images/teams/connecticut-sun.jpg',
        'alt': 'Jasmine Thomas of the Connecticut Sun',
        'width': 1200,
        'height': 800,
        'author': 'Lorie Shaull',
        'page': 'https://commons.wikimedia.org/wiki/File:2_Jasmine_Thomas.jpg',
        'license': 'CC BY-SA 4.0',
        'license_href': 'https://creativecommons.org/licenses/by-sa/4.0',
    },
    'dallas-wings': {
        'src': '/images/teams/dallas-wings.jpg',
        'alt': 'Dallas Wings players warming up before a game at College Park Center',
        'width': 1200,
        'height': 800,
        'author': 'Michael Barera',
        'page': 'https://commons.wikimedia.org/wiki/File:Minnesota_Lynx_vs._Dallas_Wings_June_2019_02_(Wings_warming_up).jpg',
        'license': 'CC BY-SA 4.0',
        'license_href': 'https://creativecommons.org/licenses/by-sa/4.0',
    },
    'golden-state-valkyries': {
        'src': '/images/articles/valkyries-wings-game-1-zandalasini/gabby-williams-valkyries-2026.jpg',
        'alt': 'Gabby Williams of the Golden State Valkyries',
        'width': 1000,
        'height': 1499,
        'author': 'John McClellan',
        'page': 'https://commons.wikimedia.org/wiki/File:260824_Lynx_Valkries_JohnMc300_(55486705669).jpg',
        'license': 'CC BY-SA 4.0',
        'license_href': 'https://creativecommons.org/licenses/by-sa/4.0/',
    },
    'indiana-fever': {
        'src': '/images/articles/aces-fever-game-1-aja-wilson-38/caitlin-clark-fever-2026.jpg',
        'alt': 'Caitlin Clark of the Indiana Fever bringing the ball up the floor',
        'width': 1600,
        'height': 1068,
        'author': 'John McClellan',
        'page': 'https://commons.wikimedia.org/wiki/File:Caitlin_Clark_Fever_2026.jpg',
        'license': 'CC BY-SA 4.0',
        'license_href': 'https://creativecommons.org/licenses/by-sa/4.0/',
    },
    'las-vegas-aces': {
        'src': '/images/articles/aces-fever-game-1-aja-wilson-38/aja-wilson-aces-2026.jpg',
        'alt': "A'ja Wilson of the Las Vegas Aces shooting over a Minnesota Lynx defender",
        'width': 1600,
        'height': 1067,
        'author': 'John McClellan',
        'page': 'https://commons.wikimedia.org/wiki/File:A%27ja_Wilson_vs._Napheesa_Collier_of_the_Minnesota_Lynx_(August_8,_2026).jpg',
        'license': 'CC BY-SA 4.0',
        'license_href': 'https://creativecommons.org/licenses/by-sa/4.0/',
    },
    'los-angeles-sparks': {
        'src': '/images/teams/los-angeles-sparks.jpg',
        'alt': 'Nneka Ogwumike of the Los Angeles Sparks',
        'width': 1200,
        'height': 1008,
        'author': 'John McClellan',
        'page': 'https://commons.wikimedia.org/wiki/File:Nneka_Ogwumike_(53062759824).jpg',
        'license': 'CC BY-SA 2.0',
        'license_href': 'https://creativecommons.org/licenses/by-sa/2.0',
    },
    'minnesota-lynx': {
        'src': '/images/teams/minnesota-lynx.jpg',
        'alt': 'Sylvia Fowles of the Minnesota Lynx',
        'width': 1200,
        'height': 800,
        'author': 'Lorie Shaull',
        'page': 'https://commons.wikimedia.org/wiki/File:Sylvia_Fowles_2019.jpg',
        'license': 'CC BY-SA 4.0',
        'license_href': 'https://creativecommons.org/licenses/by-sa/4.0',
    },
    'new-york-liberty': {
        'src': '/images/articles/liberty-lynx-game-1-full-recap/han-xu-liberty-barclays-2026.jpg',
        'alt': 'Han Xu of the New York Liberty at Barclays Center',
        'width': 1000,
        'height': 1500,
        'author': 'Nicholas A. Nichols',
        'page': 'https://commons.wikimedia.org/wiki/File:NIcNichols_EDITS-1.jpg',
        'license': 'CC BY 4.0',
        'license_href': 'https://creativecommons.org/licenses/by/4.0/',
    },
    'phoenix-mercury': {
        'src': '/images/teams/phoenix-mercury.jpg',
        'alt': 'Diana Taurasi of the Phoenix Mercury',
        'width': 1200,
        'height': 800,
        'author': 'John McClellan',
        'page': 'https://commons.wikimedia.org/wiki/File:Diana_Taurasi_2024.jpg',
        'license': 'CC BY-SA 2.0',
        'license_href': 'https://creativecommons.org/licenses/by-sa/2.0',
    },
    'portland-fire': {
        'src': '/images/articles/wnba-expansion-teams/moda-center.jpg',
        'alt': 'Exterior of the Moda Center arena in Portland, Oregon',
        'width': 1920,
        'height': 1440,
        'author': 'CrispyCream27',
        'page': 'https://commons.wikimedia.org/wiki/File:Modacenter2019.jpg',
        'license': 'CC BY-SA 4.0',
        'license_href': 'https://creativecommons.org/licenses/by-sa/4.0/',
    },
    'seattle-storm': {
        'src': '/images/teams/seattle-storm.jpg',
        'alt': 'Sue Bird of the Seattle Storm bringing the ball up the floor',
        'width': 1200,
        'height': 800,
        'author': 'Lorie Shaull',
        'page': 'https://commons.wikimedia.org/wiki/File:Seattle_Storm_Sue_Bird_(10),_photo_by_Lorie_Shaull.jpg',
        'license': 'CC BY-SA 4.0',
        'license_href': 'https://creativecommons.org/licenses/by-sa/4.0',
    },
    'toronto-tempo': {
        'src': '/images/articles/wnba-expansion-teams/tempo-aces-vancouver.jpg',
        'alt': 'Toronto Tempo players on court against the Las Vegas Aces in Vancouver',
        'width': 1542,
        'height': 2048,
        'author': 'Gold Broth',
        'page': 'https://commons.wikimedia.org/wiki/File:Tempo_v._Aces,_Cross_Canada_Series,_Vancouver_05.jpg',
        'license': 'CC BY 4.0',
        'license_href': 'https://creativecommons.org/licenses/by/4.0/',
    },
    'washington-mystics': {
        'src': '/images/teams/washington-mystics.jpg',
        'alt': 'Elena Delle Donne of the Washington Mystics',
        'width': 1200,
        'height': 800,
        'author': 'Lorie Shaull',
        'page': 'https://commons.wikimedia.org/wiki/File:Elena_Delle_Donne_(48369657691).jpg',
        'license': 'CC BY-SA 2.0',
        'license_href': 'https://creativecommons.org/licenses/by-sa/2.0',
    },
}

# Article table says West or East. teams.json says Eastern Conference or Western Conference.
GROUP_ORDER = ('Eastern Conference', 'Western Conference')
EAST_LABELS = {'east', 'eastern', 'eastern conference'}
WEST_LABELS = {'west', 'western', 'western conference'}


def esc(value) -> str:
    return html.escape('' if value is None else str(value), quote=True)


def _plain(raw: str) -> str:
    text = re.sub(r'<[^>]+>', ' ', raw or '')
    text = html.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()


def expansion_facts(root: Path) -> dict[str, dict]:
    """Conference and 2026 record from the published expansion guide table. Empty when that page is absent."""
    path = root / 'news' / 'wnba-expansion-teams' / 'index.html'
    if not path.is_file():
        return {}
    text = path.read_text(encoding='utf-8')
    start = text.find('WNBA expansion teams 2026: quick facts')
    if start < 0:
        return {}
    end = text.find('</table>', start)
    table = text[start:end if end > start else start]
    header = re.search(r'<thead>\s*<tr>(.*?)</tr>\s*</thead>', table, re.S)
    if not header:
        return {}
    slugs = []
    for cell in re.findall(r'<th>(.*?)</th>', header.group(1), re.S):
        match = re.search(r'href="(/wnba/teams/[a-z0-9-]+/)"', cell)
        slugs.append(match.group(1).strip('/').split('/')[-1] if match else '')
    team_slugs = [slug for slug in slugs if slug]
    facts = {slug: {} for slug in team_slugs}
    if not facts:
        return {}
    for label_html, cells in re.findall(r'<tr><th>(.*?)</th>((?:<td>.*?</td>)+)</tr>', table, re.S):
        label = _plain(label_html).casefold()
        values = [_plain(cell) for cell in re.findall(r'<td>(.*?)</td>', cells, re.S)]
        if label not in {'conference', '2026 record'}:
            continue
        for slug, value in zip(team_slugs, values):
            if not slug or not value or EM_DASH in value:
                continue
            if label == 'conference':
                facts[slug]['conference'] = value
            else:
                facts[slug]['record'] = value
    return {slug: row for slug, row in facts.items() if row}


def standings_index(root: Path) -> tuple[dict[str, str], str]:
    """First saved row for each team name, plus the file date. Later duplicate rows are ignored."""
    path = root / 'api' / 'wnba-standings'
    if not path.is_file():
        return {}, ''
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    found = {}
    for team in data.get('teams') or []:
        if not isinstance(team, dict):
            continue
        name = team_names.public_name(str(team.get('name') or '').strip())
        wins, losses = team.get('wins'), team.get('losses')
        if not name or name in found:
            continue
        if isinstance(wins, bool) or isinstance(losses, bool):
            continue
        if not isinstance(wins, int) or not isinstance(losses, int):
            continue
        found[name] = f'{wins}-{losses}'
    return found, links._long_date(data.get('updatedAt'))


def cities_by_id(root: Path) -> dict[int, str]:
    path = root / 'data' / 'wnba' / 'teams.json'
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    cities = {}
    for team in data.get('teams') or []:
        if not isinstance(team, dict):
            continue
        team = team_names.apply(team)
        raw = team.get('id')
        city = str(team.get('city') or '').strip()
        if isinstance(raw, bool) or not isinstance(raw, int) or not city:
            continue
        cities[raw] = city
    return cities


def conference_group(label: str) -> str:
    key = (label or '').strip().casefold()
    if key in EAST_LABELS:
        return 'Eastern Conference'
    if key in WEST_LABELS:
        return 'Western Conference'
    return ''


def conference_label(slot: dict, extra: dict) -> str:
    stored = str(slot.get('conference') or '').strip()
    if stored:
        return stored
    return str((extra or {}).get('conference') or '').strip()


def record_line(slot: dict, extra: dict, records: dict[str, str], standings_date: str) -> str:
    published = str((extra or {}).get('record') or '').strip()
    if published:
        return f'2026 record: {published}.'
    saved = records.get(slot['full_name'])
    if not saved:
        return ''
    if standings_date:
        return f'{saved} as of {standings_date}.'
    return f'{saved}.'


def card_facts(slot: dict, extra: dict, records: dict[str, str], standings_date: str) -> list[str]:
    facts = []
    conference = conference_label(slot, extra)
    if conference:
        facts.append(conference if conference.endswith('.') else conference + '.')
    record = record_line(slot, extra, records, standings_date)
    if record:
        facts.append(record)
    elif slot.get('players'):
        count = len(slot['players'])
        noun = 'player' if count == 1 else 'players'
        facts.append(f'{count} {noun} on the current roster.')
    for fact in facts:
        if EM_DASH in fact:
            raise ValueError('Team fact contains an em dash.')
    return facts[:2]


def intro(slots: list[dict]) -> str:
    count = len(slots)
    names = {slot['slug'] for slot in slots}
    sentence = f'{count} WNBA teams have a roster here'
    if {'portland-fire', 'toronto-tempo'} <= names:
        sentence += ', including the Portland Fire and the Toronto Tempo'
    sentence += '.'
    if EM_DASH in sentence:
        raise ValueError('Teams intro contains an em dash.')
    return sentence


def _credit(spec: dict) -> str:
    return (
        '<p class="team-card-credit">Photo: '
        f'{esc(spec["author"])} / '
        f'<a href="{esc(spec["page"])}" target="_blank" rel="noopener">Wikimedia Commons</a> '
        f'(<a href="{esc(spec["license_href"])}" target="_blank" rel="noopener">{esc(spec["license"])}</a>)'
        '</p>'
    )


def _card(slot: dict, city: str, facts: list[str]) -> str:
    href = links.team_href(slot)
    spec = VISUALS.get(slot['slug'])
    image = ''
    credit = ''
    if spec:
        image = (
            f'<img src="{esc(spec["src"])}" alt="{esc(spec["alt"])}" '
            f'width="{int(spec["width"])}" height="{int(spec["height"])}">'
        )
        credit = _credit(spec)
    city_html = f'<span class="eyebrow">{esc(city)}</span>' if city else ''
    fact_html = ''.join(f'<p>{esc(fact)}</p>' for fact in facts)
    return (
        '<li class="team-card">'
        f'<a class="team-card-link" href="{esc(href)}" target="_blank" rel="noopener">'
        f'{image}<span class="team-card-body">{city_html}<h3>{esc(slot["full_name"])}</h3>{fact_html}</span>'
        '</a>'
        f'{credit}</li>'
    )


def grouped(slots: list[dict], extras: dict, records: dict[str, str], standings_date: str, cities: dict[int, str]):
    buckets = {name: [] for name in GROUP_ORDER}
    loose = []
    for slot in slots:
        extra = extras.get(slot['slug']) or {}
        label = conference_label(slot, extra)
        group = conference_group(label)
        entry = {
            'slot': slot,
            'city': cities.get(slot['id'], ''),
            'facts': card_facts(slot, extra, records, standings_date),
            'group': group,
        }
        if group in buckets:
            buckets[group].append(entry)
        else:
            loose.append(entry)
    ordered = []
    for name in GROUP_ORDER:
        rows = sorted(buckets[name], key=lambda row: row['slot']['full_name'].casefold())
        if rows:
            ordered.append((name, rows))
    if loose:
        ordered.append(('', sorted(loose, key=lambda row: row['slot']['full_name'].casefold())))
    return ordered


def hub_parts(root: Path, linking: dict) -> tuple[str, dict, str, str]:
    """Body HTML, JSON-LD, title, and meta description."""
    slots = sorted(linking['by_id'].values(), key=lambda slot: slot['full_name'].casefold())
    extras = expansion_facts(root)
    records, standings_date = standings_index(root)
    cities = cities_by_id(root)
    sections = []
    listed = []
    for heading, rows in grouped(slots, extras, records, standings_date, cities):
        cards = ''.join(_card(row['slot'], row['city'], row['facts']) for row in rows)
        title = f'<h2>{esc(heading)}</h2>' if heading else ''
        sections.append(f'<section class="team-group">{title}<ul class="team-grid">{cards}</ul></section>')
        listed.extend(row['slot'] for row in rows)
    lead = intro(slots)
    body = (
        '<nav class="breadcrumbs" aria-label="Breadcrumb">'
        '<a href="/">Home</a><span aria-hidden="true">/</span>'
        '<a href="/wnba/">WNBA</a><span aria-hidden="true">/</span>'
        '<span>Teams</span></nav>'
        '<section class="directory-header"><p class="eyebrow">WNBA teams</p>'
        '<h1>WNBA teams</h1>'
        f'<p>{esc(lead)}</p></section>'
        + ''.join(sections)
    )
    items = []
    for position, slot in enumerate(listed, start=1):
        items.append({
            '@type': 'ListItem',
            'position': position,
            'name': slot['full_name'],
            'url': BASE + links.team_href(slot),
        })
    structured = {
        '@context': 'https://schema.org',
        '@graph': [
            {
                '@type': 'BreadcrumbList',
                'itemListElement': [
                    {'@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': BASE + '/'},
                    {'@type': 'ListItem', 'position': 2, 'name': 'WNBA', 'item': BASE + '/wnba/'},
                    {'@type': 'ListItem', 'position': 3, 'name': 'Teams', 'item': BASE + HUB},
                ],
            },
            {
                '@type': 'ItemList',
                'name': 'WNBA teams',
                'numberOfItems': len(items),
                'itemListElement': items,
            },
        ],
    }
    title = 'WNBA Teams | Full Court Buckets'
    if {'portland-fire', 'toronto-tempo'} <= {slot['slug'] for slot in slots}:
        description = (
            f'All {len(slots)} WNBA teams with a current roster, including the Portland Fire and Toronto Tempo, '
            'with conference and record.'
        )
    else:
        description = f'All {len(slots)} WNBA teams with a current roster, with conference and record.'
    return body, structured, title, description
