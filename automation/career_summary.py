"""Unique career copy for players who are not on a current roster.

Season lines come from the player's stored file. Draft, college, and
international rows come only from data/wnba/career-extras.json, which is
filled from Basketball-Reference pages. Photos come from
data/wnba/licensed-photos.json, files already on the site.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import team_names

WORD_RE = re.compile(r"[A-Za-z0-9']+")
MARKERS = (
    'reportedly',
    'alleged',
    'allegedly',
    'rumor',
    'rumour',
    'rumored',
    'rumoured',
    'sources say',
    'it is believed',
    'widely regarded',
    'widely considered',
    'widely reported',
    'one of the best',
    'one of the greatest',
    'legendary',
    'iconic',
    'according to reports',
    'unconfirmed',
    'speculated',
    'speculation',
    'may have',
    'might have',
)
POSITIONS = {'G': 'guard', 'F': 'forward', 'C': 'center'}
COLLEGE_NOISE = {'university', 'college', 'of', 'the'}


def esc(value) -> str:
    return html.escape(str(value if value is not None else ''), quote=True)


def word_count(text: str) -> int:
    return len(WORD_RE.findall(re.sub(r'<[^>]+>', ' ', text or '')))


def marker_hits(text: str) -> list[str]:
    blob = re.sub(r'<[^>]+>', ' ', text or '').casefold()
    return [marker for marker in MARKERS if marker in blob]


def released(root: Path | None, slug: str) -> bool:
    """True when this player's career copy is allowed on the public page.

    A missing rollout file means every inactive player (used by the unit fixtures).
    The site file lists the slugs already reviewed for a published batch.
    """
    if root is None or not slug:
        return True
    path = Path(root) / 'data' / 'wnba' / 'career-rollout.json'
    if not path.is_file():
        return True
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return True
    slugs = data.get('slugs') if isinstance(data, dict) else None
    if not isinstance(slugs, list):
        return True
    return slug in slugs


def prose_link(href: str, label: str) -> str:
    return f'<a href="{esc(href)}" target="_blank" rel="noopener">{esc(label)}</a>'


def player_name(profile: dict) -> str:
    player = profile.get('player') or {}
    return (str(player.get('first_name') or '') + ' ' + str(player.get('last_name') or '')).strip()


def _team(row: dict) -> str:
    team = row.get('team') or {}
    raw = str(team.get('full_name') or team.get('name') or '').strip()
    if not raw:
        return 'a team that is not named on the row'
    return team_names.public_name(raw)


def _num(value) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return f'{float(value):.1f}'


def _games(value) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return str(int(value)) if int(value) == value else f'{value:.1f}'


def _rows(profile: dict, kind: int) -> list[dict]:
    rows = [
        row for row in profile.get('season_stats') or []
        if row.get('season_type') == kind and isinstance(row.get('season'), int)
    ]
    return sorted(rows, key=lambda row: (row['season'], _team(row)))


def _spans(rows: list[dict]) -> list[dict]:
    groups = []
    for row in rows:
        team = _team(row)
        year = row['season']
        if groups and groups[-1]['team'] == team and year == groups[-1]['end'] + 1:
            groups[-1]['end'] = year
        elif groups and groups[-1]['team'] == team and year == groups[-1]['end']:
            continue
        else:
            groups.append({'team': team, 'start': year, 'end': year})
    return groups


def _span_phrase(group: dict) -> str:
    if group['start'] == group['end']:
        when = f"in {group['start']}"
    else:
        when = f"from {group['start']} through {group['end']}"
    return f"the {group['team']} {when}"


def _line_bits(row: dict) -> str:
    bits = []
    for key, word in (('pts', 'points'), ('reb', 'rebounds'), ('ast', 'assists')):
        shown = _num(row.get(key))
        if shown is not None:
            bits.append(f'{shown} {word}')
    if not bits:
        return ''
    listed = bits[0] if len(bits) == 1 else ', '.join(bits[:-1]) + ' and ' + bits[-1]
    games = _games(row.get('games_played'))
    if games is not None:
        noun = 'game' if games == '1' else 'games'
        listed += f' in {games} {noun}'
    return listed


def _best(rows: list[dict]) -> dict | None:
    scored = [row for row in rows if _num(row.get('pts')) is not None]
    if not scored:
        return None

    def key(row):
        games = row.get('games_played')
        played = float(games) if isinstance(games, (int, float)) and not isinstance(games, bool) else 0
        return (float(row['pts']), played, row['season'])

    return max(scored, key=key)


def _best_sentence(name: str, row: dict, kind: str) -> str:
    """Kept for older callers. Editorial copy does not use this skeleton."""
    line = _line_bits(row)
    if not line:
        return ''
    comp = 'playoffs' if kind == 'playoff' else 'regular season'
    return f"{name} averaged {line} for the {_team(row)} in {row['season']} during the {comp}."


def _college_key(value: str) -> str:
    parts = re.sub(r'[^a-z0-9]+', ' ', str(value or '').casefold()).split()
    kept = [part for part in parts if part not in COLLEGE_NOISE]
    return ' '.join(kept or parts)


def profile_college(profile: dict) -> str:
    text = str((profile.get('player') or {}).get('college') or '').strip()
    if not text or not re.search(r'[A-Za-z]', text):
        return ''
    if re.fullmatch(r'\d+\s*(?:lbs?|kg)?', text, re.I):
        return ''
    return text


# Olympic tournaments as labeled on the international table. Anything else is omitted.
OLYMPICS = {
    'Athens 2004': (2004, 'Athens'),
    'Beijing 2008': (2008, 'Beijing'),
    'London 2012': (2012, 'London'),
    'Rio de Janeiro 2016': (2016, 'Rio de Janeiro'),
    'Tokyo 2020': (2020, 'Tokyo'),
    'Paris 2024': (2024, 'Paris'),
}
META_RE = re.compile(
    r'\b(?:rows?|stored|this page|on this page|database|line)\b',
    re.I,
)
_RANK_CACHE: dict | None = None


def _ordinal(number: int) -> str:
    if 10 <= number % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(number % 10, 'th')
    return f'{number}{suffix}'


def load_extras(root: Path | None) -> dict:
    if root is None:
        return {}
    path = Path(root) / 'data' / 'wnba' / 'career-extras.json'
    if not path.is_file():
        return {}
    last = None
    for _attempt in range(4):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            last = exc
            continue
        return data if isinstance(data, dict) else {}
    raise RuntimeError(f'career extras could not be read: {last}')


def load_photos(root: Path | None) -> dict:
    if root is None:
        return {}
    path = Path(root) / 'data' / 'wnba' / 'licensed-photos.json'
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def sentences_for(profile: dict, root: Path | None = None) -> list[str]:
    import career_prose
    extra = {}
    if root is not None:
        slug = str(profile.get('slug') or '')
        extra = load_extras(root).get(slug) or {}
    return career_prose.sentences(profile, extra, root)


def _medal_source(root: Path | None, slug: str) -> str:
    if root is None or not slug:
        return ''
    path = Path(root) / 'data' / 'wnba' / 'career-honors.json'
    if not path.is_file():
        return ''
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return ''
    block = data.get(slug) if isinstance(data, dict) else None
    if not isinstance(block, dict):
        return ''
    for row in block.get('olympics') or []:
        if not isinstance(row, dict):
            continue
        source = str(row.get('source') or '').strip()
        if 'olympedia.org' in source:
            return source
    return ''


def _medal_mentioned(profile: dict, root: Path | None) -> bool:
    if not _medal_source(root, str(profile.get('slug') or '')):
        return False
    blob = ' '.join(sentences_for(profile, root))
    return any(medal in blob for medal in ('Olympic gold', 'Olympic silver', 'Olympic bronze'))


def sources_line(profile: dict, root: Path | None = None) -> str:
    """One short credit line. Season numbers are ours. Draft and Olympic notes cite Basketball-Reference."""
    bits = ['Full Court Buckets season logs']
    extra = {}
    slug = ''
    if root is not None:
        slug = str(profile.get('slug') or '')
        extra = load_extras(root).get(slug) or {}
    if isinstance(extra, dict):
        bbref = str(extra.get('bbref') or '').strip()
        international = extra.get('international') if isinstance(extra.get('international'), dict) else None
        intl = str((international or {}).get('source') or '').strip()
        if bbref:
            bits.append(prose_link(bbref, 'Basketball-Reference'))
        elif intl:
            bits.append(prose_link(intl, 'Basketball-Reference'))
    if root is not None and slug and _medal_mentioned(profile, root):
        source = _medal_source(root, slug)
        if source:
            bits.append(prose_link(source, 'Olympedia'))
    return 'Sources: ' + '; '.join(bits) + '.'


def hero_plain(profile: dict, root: Path | None = None) -> str:
    found = sentences_for(profile, root)
    if not found:
        return ''
    return re.sub(r'<[^>]+>', '', found[0])


def photo_html(profile: dict, root: Path | None) -> str:
    if root is None:
        return ''
    slug = str(profile.get('slug') or '')
    spec = load_photos(root).get(slug)
    if not isinstance(spec, dict):
        return ''
    src = str(spec.get('src') or '')
    if not src.startswith('/images/'):
        return ''
    path = Path(root) / src.lstrip('/')
    if not path.is_file():
        return ''
    license_href = str(spec.get('license_href') or '').strip()
    license_name = str(spec.get('license') or '').strip()
    license_bit = esc(license_name or 'license')
    if license_href:
        license_bit = f'<a href="{esc(license_href)}" target="_blank" rel="noopener">{license_bit}</a>'
    author = str(spec.get('author') or 'photographer').replace('.', ',')
    caption = (
        f'Photo of {esc(player_name(profile))}: {esc(author)} / '
        f'<a href="{esc(spec.get("page") or "")}" target="_blank" rel="noopener">Wikimedia Commons</a> '
        f'({license_bit})'
    )
    width = int(spec.get('width') or 0)
    height = int(spec.get('height') or 0)
    dims = f' width="{width}" height="{height}"' if width and height else ''
    focal = str(spec.get('focal') or 'center 18%')
    return (
        f'<figure class="career-photo"><img src="{esc(src)}" alt="{esc(spec.get("alt") or player_name(profile))}"'
        f'{dims} style="object-position:{esc(focal)}" decoding="async" loading="lazy">'
        f'<figcaption>{caption}</figcaption></figure>'
    )


def section_html(profile: dict, root: Path | None = None, figure: str = '') -> str:
    found = sentences_for(profile, root)
    if not found:
        return ''
    paragraphs = ''.join(f'<p>{esc(sentence)}</p>' for sentence in found)
    photo = figure or photo_html(profile, root)
    copy = f'<div class="career-copy">{paragraphs}<p class="career-sources">{sources_line(profile, root)}</p></div>'
    body = f'<div class="career-layout">{photo}{copy}</div>' if photo else copy
    return (
        '<section class="section" id="career"><p class="eyebrow">Career</p>'
        f'<h2>Career summary</h2>{body}</section>'
    )


def sources_for(profile: dict, root: Path | None = None) -> list[dict]:
    slug = str(profile.get('slug') or '')
    sources = [{
        'label': 'Season lines stored for this profile',
        'url': f'/data/wnba/players/{slug}.json',
    }]
    extra = load_extras(root).get(slug) if root is not None and slug else None
    if isinstance(extra, dict):
        bbref = str(extra.get('bbref') or '').strip()
        if bbref:
            sources.append({'label': 'Basketball-Reference WNBA page', 'url': bbref})
        international = extra.get('international') if isinstance(extra.get('international'), dict) else None
        page = str((international or {}).get('source') or '').strip()
        if page:
            sources.append({'label': 'Basketball-Reference international table', 'url': page})
    photo = load_photos(root).get(slug) if root is not None and slug else None
    if isinstance(photo, dict) and photo.get('page'):
        sources.append({'label': 'Wikimedia Commons file', 'url': photo['page']})
    return sources


def write_sources(root: Path, profile: dict) -> None:
    slug = str(profile.get('slug') or '')
    if not slug:
        return
    path = Path(root) / 'data' / 'wnba' / 'career-sources' / f'{slug}.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {'slug': slug, 'sources': sources_for(profile, root)}
    path.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')


_SUMMARY_RE = re.compile(r'(<p class="answer-summary">)(.*?)(</p>)', re.S)
_CAREER_RE = re.compile(r'<section class="section" id="career">.*?</section>', re.S)


def patch_player_html(page: str, profile: dict, root: Path) -> str:
    """Replace the thin lead and insert the career section. Leave the header alone."""
    if 'http-equiv="refresh"' in page.lower():
        return page
    hero = esc(hero_plain(profile, root))
    if hero and _SUMMARY_RE.search(page):
        page = _SUMMARY_RE.sub(lambda match: match.group(1) + hero + match.group(3), page, count=1)
    figure = ''
    src_match = re.search(r'<figure class="career-photo">.*?</figure>', page, re.S)
    if src_match:
        figure = src_match.group(0)
    block = section_html(profile, root, figure=figure)
    if not block:
        return page
    if _CAREER_RE.search(page):
        return _CAREER_RE.sub(block, page, count=1)
    anchor = page.find('class="answer-summary"')
    if anchor < 0:
        anchor = page.find('<main')
    end = page.find('</section>', anchor)
    if end < 0:
        raise ValueError(f'{profile.get("slug")} has no section to follow')
    end += len('</section>')
    return page[:end] + block + page[end:]
