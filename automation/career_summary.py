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
        listed += f' in {games} games'
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
    line = _line_bits(row)
    if not line:
        return ''
    return (
        f"The highest points-per-game {kind} line stored for {name} is {line} "
        f"with the {_team(row)} in {row['season']}."
    )


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


def stat_sentences(profile: dict) -> list[str]:
    """Named sentences from the season rows already stored for this player."""
    name = player_name(profile)
    if not name:
        return []
    regular = _rows(profile, 2)
    playoffs = _rows(profile, 3)
    position = POSITIONS.get(str((profile.get('player') or {}).get('position') or '').strip(), '')
    who = f'{name}, a {position},' if position else name
    sentences = []
    if regular:
        years = sorted({row['season'] for row in regular})
        spans = _spans(regular)
        if len(years) == 1:
            span = f'in {years[0]}'
        else:
            span = f'from {years[0]} through {years[-1]}'
        parts = [_span_phrase(group) for group in spans]
        if len(parts) == 1:
            listed = parts[0]
        else:
            listed = ', '.join(parts[:-1]) + ', and ' + parts[-1]
        sentences.append(
            f'Regular-season rows for {who} on this page run {span} with {listed}.'
        )
        best = _best(regular)
        if best:
            sentences.append(_best_sentence(name, best, 'regular-season'))
    elif playoffs:
        sentences.append(f'{who} has no regular-season line stored on this page.')
    else:
        sentences.append(f'{who} has no season line stored on this page.')
    if playoffs:
        best = _best(playoffs)
        if best:
            sentences.append(_best_sentence(name, best, 'playoff'))
    college = profile_college(profile)
    if college:
        sentences.append(f'The college stored for {name} is {college}.')
    for sentence in sentences:
        if name not in sentence:
            raise ValueError(f'Career sentence is missing the player name: {sentence}')
        if word_count(sentence) >= 12 and name not in sentence:
            raise ValueError(sentence)
    return [sentence for sentence in sentences if sentence]


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


def extra_sentences(profile: dict, extra: dict) -> list[str]:
    """Sentences that cite Basketball-Reference fields already saved for this player."""
    name = player_name(profile)
    if not name or not isinstance(extra, dict):
        return []
    sentences = []
    draft = extra.get('draft') if isinstance(extra.get('draft'), dict) else None
    source = str(extra.get('bbref') or (draft or {}).get('source') or '').strip()
    if draft and source and isinstance(draft.get('year'), int) and isinstance(draft.get('overall'), int):
        team = str(draft.get('team') or '').strip()
        if team:
            linked = prose_link(source, 'Basketball-Reference')
            sentences.append(
                f'{linked} records {name} as the {_ordinal(draft["overall"])} overall pick, '
                f'taken by the {team} in the {draft["year"]} WNBA draft.'
            )
    bbref_college = str((extra.get('college') or {}).get('name') or '').strip() if isinstance(extra.get('college'), dict) else ''
    stored = profile_college(profile)
    if bbref_college and source:
        linked = prose_link(source, 'Basketball-Reference')
        if stored and _college_key(stored) == _college_key(bbref_college):
            sentences.append(f'{linked} lists the same college for {name}: {stored}.')
        elif not stored:
            sentences.append(f'{linked} lists {bbref_college} as the college for {name}.')
    international = extra.get('international') if isinstance(extra.get('international'), dict) else None
    rows = (international or {}).get('rows') if international else None
    page = str((international or {}).get('source') or '').strip()
    if page and isinstance(rows, list) and rows:
        teams = []
        leagues = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            team = str(row.get('team') or '').strip()
            league = str(row.get('league') or '').strip()
            if team and team not in teams:
                teams.append(team)
            if league and league not in leagues:
                leagues.append(league)
        if teams:
            linked = prose_link(page, 'Basketball-Reference')
            team_list = ', '.join(teams[:8])
            league_list = ', '.join(leagues[:8])
            extra_teams = ''
            if len(teams) > 8:
                extra_teams = f' and {len(teams) - 8} more teams'
            noun = 'row' if len(rows) == 1 else 'rows'
            sentences.append(
                f'{linked} lists {len(rows)} international season {noun} for {name} '
                f'with {team_list}{extra_teams}'
                + (f', in {league_list}.' if league_list else '.')
            )
    for sentence in sentences:
        plain = re.sub(r'<[^>]+>', '', sentence)
        if name not in plain:
            raise ValueError(f'Extra sentence is missing the player name: {plain}')
    return sentences


def sentences_for(profile: dict, root: Path | None = None) -> list[str]:
    extra = {}
    if root is not None:
        slug = str(profile.get('slug') or '')
        extra = load_extras(root).get(slug) or {}
    found = stat_sentences(profile) + extra_sentences(profile, extra)
    blob = ' '.join(re.sub(r'<[^>]+>', ' ', sentence) for sentence in found).casefold()
    for marker in MARKERS:
        if marker in blob:
            raise ValueError(f'Unverified-claim marker in {profile.get("slug")}: {marker}')
    return found


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


def section_html(profile: dict, root: Path | None = None) -> str:
    found = sentences_for(profile, root)
    if not found:
        return ''
    paragraphs = ''.join(
        f'<p>{sentence}</p>' if '<a ' in sentence else f'<p>{esc(sentence)}</p>'
        for sentence in found
    )
    photo = photo_html(profile, root)
    body = f'<div class="career-layout">{photo}<div class="career-copy">{paragraphs}</div></div>' if photo else paragraphs
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
    block = section_html(profile, root)
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
