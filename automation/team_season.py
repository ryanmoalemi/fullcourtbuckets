"""2026 season copy for team pages.

Every number comes from api/wnba-standings, the current roster's 2026 season
lines, or a sentence already published in articles.json. Photos are the
licensed files already used on the teams hub.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import internal_links as links
import team_hub
import team_names

SEASON_MARK = 'fcb-season-summary'
WORD_RE = re.compile(r"[A-Za-z0-9']+")

# Scores and series states quoted from articles.json titles or descriptions.
# The test fails if one of these strings is missing from that article.
COVERAGE = {
    'minnesota-lynx': [
        ('/news/liberty-lynx-game-1-full-recap/', 'Game 1 recap', '91-75'),
        ('/news/liberty-lynx-game-2-recap/', 'Game 2 recap', '87-71'),
    ],
    'golden-state-valkyries': [
        ('/news/valkyries-wings-game-1-zandalasini/', 'Wings Game 1', '104-80'),
        ('/news/valkyries-wings-game-2-recap/', 'Wings Game 2', '108-100'),
        ('/news/wings-valkyries-game-3-recap/', 'Wings Game 3', '77-73'),
        ('/news/aces-valkyries-semis-game-1-recap/', 'Aces Game 1', '71-60'),
        ('/news/aces-valkyries-semis-game-2-recap/', 'Aces Game 2', '83-81'),
        ('/news/semis-game-3-preview/', 'Game 3 preview', '2-0'),
    ],
    'las-vegas-aces': [
        ('/news/aces-fever-game-1-aja-wilson-38/', 'Fever Game 1', '102-85'),
        ('/news/fever-aces-game-2-recap/', 'Fever Game 2', '99-89'),
        ('/news/fever-aces-game-3-recap/', 'Fever Game 3', '94-83'),
        ('/news/aces-fever-series-breakdown/', 'series breakdown', '2-1'),
        ('/news/aces-valkyries-semis-game-1-recap/', 'Valkyries Game 1', '71-60'),
        ('/news/aces-valkyries-semis-game-2-recap/', 'Valkyries Game 2', '83-81'),
        ('/news/semis-game-3-preview/', 'Game 3 preview', '2-0'),
    ],
    'atlanta-dream': [
        ('/news/dream-mystics-game-1-howard-reese/', 'Mystics Game 1', '92-77'),
        ('/news/liberty-dream-semis-game-1-recap/', 'Liberty Game 1', '92-82'),
        ('/news/liberty-dream-semis-game-2-recap/', 'Liberty Game 2', '101-98'),
        ('/news/semis-game-3-preview/', 'Game 3 preview', '2-0'),
    ],
    'washington-mystics': [
        ('/news/dream-mystics-game-1-howard-reese/', 'Game 1 recap', '92-77'),
    ],
    'indiana-fever': [
        ('/news/aces-fever-game-1-aja-wilson-38/', 'Game 1', '102-85'),
        ('/news/fever-aces-game-2-recap/', 'Game 2', '99-89'),
        ('/news/fever-aces-game-3-recap/', 'Game 3', '94-83'),
        ('/news/aces-fever-series-breakdown/', 'series breakdown', '2-1'),
    ],
    'dallas-wings': [
        ('/news/valkyries-wings-game-1-zandalasini/', 'Game 1', '104-80'),
        ('/news/valkyries-wings-game-2-recap/', 'Game 2', '108-100'),
        ('/news/wings-valkyries-game-3-recap/', 'Game 3', '77-73'),
    ],
    'new-york-liberty': [
        ('/news/liberty-lynx-game-1-full-recap/', 'Lynx Game 1', '91-75'),
        ('/news/liberty-lynx-game-2-recap/', 'Lynx Game 2', '87-71'),
        ('/news/liberty-dream-semis-game-1-recap/', 'Dream Game 1', '92-82'),
        ('/news/liberty-dream-semis-game-2-recap/', 'Dream Game 2', '101-98'),
        ('/news/semis-game-3-preview/', 'Game 3 preview', '2-0'),
    ],
    'portland-fire': [
        ('/news/wnba-expansion-teams/', 'expansion story', '17-27'),
    ],
    'toronto-tempo': [
        ('/news/wnba-expansion-teams/', 'expansion story', '11-33'),
    ],
}


def esc(value) -> str:
    return html.escape(str(value if value is not None else ''), quote=True)


def word_count(text: str) -> int:
    plain = re.sub(r'<[^>]+>', ' ', text or '')
    return len(WORD_RE.findall(plain))


def prose_link(href: str, label: str) -> str:
    """In-article link. Opens in a new tab. Story-list cards stay in this tab."""
    return f'<a href="{esc(href)}" target="_blank" rel="noopener">{esc(label)}</a>'


def _ordinal(number: int) -> str:
    if 10 <= number % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(number % 10, 'th')
    return f'{number}{suffix}'


def _average(value) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return f'{value:.1f}'


def _roster_line(root: Path, slug: str) -> dict:
    path = root / 'data' / 'wnba' / 'players' / f'{slug}.json'
    if not path.is_file():
        return {}
    try:
        profile = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}
    rows = [
        row for row in profile.get('season_stats') or []
        if row.get('season') == 2026 and row.get('season_type') == 2
    ]
    if len(rows) != 1:
        rows = [row for row in rows if not (row.get('team') or {}).get('id')]
    if len(rows) != 1:
        return {}
    row = rows[0]
    return {
        'pts': _average(row.get('pts')),
        'reb': _average(row.get('reb')),
        'ast': _average(row.get('ast')),
        'min': _average(row.get('min')),
        'min_raw': row.get('min') if _average(row.get('min')) else None,
    }


def _leaders(root: Path, slot: dict) -> list[dict]:
    found = []
    for player in slot.get('players') or []:
        stats = _roster_line(root, player['slug'])
        if not stats:
            continue
        if stats.get('pts') is None and stats.get('reb') is None and stats.get('ast') is None:
            continue
        found.append({'name': player['name'], 'slug': player['slug'], **stats})
    return found


def _names(rows: list[dict]) -> str:
    return ', '.join(prose_link(f'/wnba/{row["slug"]}/', row['name']) for row in rows)


def _leader_sentence(name: str, leaders: list[dict]) -> str:
    parts = []
    for key, label in (('pts', 'scoring'), ('reb', 'rebounds'), ('ast', 'assists')):
        scored = [row for row in leaders if row.get(key) is not None]
        if not scored:
            continue
        best = max(float(row[key]) for row in scored)
        tied = [row for row in scored if float(row[key]) == best]
        unit = 'points' if key == 'pts' else 'rebounds' if key == 'reb' else 'assists'
        parts.append(f'{_names(tied)} in {label} at {tied[0][key]} {unit} per game')
    if not parts:
        return ''
    listed = parts[0] if len(parts) == 1 else ', '.join(parts[:-1]) + ', and ' + parts[-1]
    return f'On the current {name} roster, the 2026 regular-season leaders are {listed}.'


def _minutes_sentence(name: str, leaders: list[dict]) -> str:
    rows = [row for row in leaders if isinstance(row.get('min_raw'), (int, float)) and not isinstance(row.get('min_raw'), bool)]
    if not rows:
        return ''
    rows.sort(key=lambda row: (-float(row['min_raw']), row['name'].casefold()))
    top = rows[0]
    return (
        f'{prose_link("/wnba/" + top["slug"] + "/", top["name"])} played the most minutes '
        f'on the {name} at {top["min"]} per game.'
    )


def _split_sentence(name: str, standing: dict) -> str:
    home = str(standing.get('home') or '').strip()
    road = str(standing.get('road') or '').strip()
    last10 = str(standing.get('last10') or '').strip()
    streak = str(standing.get('streak') or '').strip()
    bits = []
    if home and road:
        bits.append(f'home {home} and road {road}')
    if last10:
        bits.append(f'a last-10 of {last10}')
    if streak:
        bits.append(f'a streak of {streak}')
    if not bits:
        return ''
    listed = bits[0] if len(bits) == 1 else ', '.join(bits[:-1]) + ', and ' + bits[-1]
    return f'The {name} standings line also shows {listed}.'


def _record_sentence(name: str, standing: dict, conference: str) -> str:
    wins = standing.get('wins')
    losses = standing.get('losses')
    rank = standing.get('conferenceRank')
    bits = [f'the {name} are {wins}-{losses}']
    if isinstance(rank, int) and not isinstance(rank, bool) and conference:
        bits.append(f'{_ordinal(rank)} in the {conference}')
    back = str(standing.get('gamesBack') or '').strip()
    if back and back not in {'0', '0.0', '0.00'}:
        unit = 'game' if back in {'1', '1.0'} else 'games'
        bits.append(f'{back} {unit} back')
    listed = bits[0] if len(bits) == 1 else ', '.join(bits[:-1]) + ', and ' + bits[-1]
    return f'On the standings checked October 1, 2026, {listed}.'


def _seed_sentence(name: str, standing: dict) -> str:
    seed = standing.get('playoffSeed')
    if isinstance(seed, int) and not isinstance(seed, bool) and 1 <= seed <= 8:
        return f'That record was the No. {seed} playoff seed for the {name}.'
    return f'The {name} finished outside the top eight playoff seeds on that standings file.'


def _playoff_html(slug: str, name: str) -> str:
    """Team-specific postseason sentences. Each one names the club."""
    link = prose_link
    if slug == 'minnesota-lynx':
        return (
            f'The No. 8 Liberty beat the {name} 91-75 in {link("/news/liberty-lynx-game-1-full-recap/", "Game 1")} '
            f'and closed that series with an 87-71 win in {link("/news/liberty-lynx-game-2-recap/", "Game 2")}.'
        )
    if slug == 'golden-state-valkyries':
        return (
            f'The {name} opened the first round with a 104-80 win, dropped Game 2 108-100 in overtime, '
            f'and closed the Wings out 77-73 to win the series 2-1. '
            f'In the semifinals they beat the Aces 71-60 and 83-81 and lead 2-0 heading into '
            f'{link("/news/semis-game-3-preview/", "Game 3")}.'
        )
    if slug == 'las-vegas-aces':
        return (
            f'The {name} beat the Fever 102-85, lost Game 2 99-89, and closed the series 94-83 for a 2-1 win. '
            f'In the semifinals the Valkyries beat Las Vegas 71-60 and 83-81, so the Aces trail 0-2 '
            f'going into {link("/news/semis-game-3-preview/", "Game 3")}.'
        )
    if slug == 'atlanta-dream':
        return (
            f'The {name} beat the Mystics 92-77 in the published {link("/news/dream-mystics-game-1-howard-reese/", "Game 1")} recap. '
            f'In the semifinals they beat the Liberty 92-82 and 101-98 in overtime and lead 2-0 '
            f'before {link("/news/semis-game-3-preview/", "Game 3")}.'
        )
    if slug == 'washington-mystics':
        return (
            f'The only {name} playoff story on the site is {link("/news/dream-mystics-game-1-howard-reese/", "Game 1")}, '
            f'a 92-77 loss to the Dream. Later games in that series are not in the story list.'
        )
    if slug == 'indiana-fever':
        return (
            f'The {name} lost Game 1 to the Aces 102-85, won Game 2 99-89, and lost Game 3 94-83. '
            f'The {link("/news/aces-fever-series-breakdown/", "series breakdown")} records that as a 2-1 Aces win.'
        )
    if slug == 'dallas-wings':
        return (
            f'The {name} lost Game 1 to the Valkyries 104-80, won Game 2 108-100 in overtime, '
            f'and lost Game 3 77-73. Golden State took the series 2-1.'
        )
    if slug == 'new-york-liberty':
        return (
            f'The {name} beat the Lynx 91-75 and 87-71 to sweep the first round. '
            f'In the semifinals the Dream beat New York 92-82 and 101-98 in overtime, so the Liberty trail 0-2 '
            f'before {link("/news/semis-game-3-preview/", "Game 3")}.'
        )
    if slug == 'portland-fire':
        return (
            f'The {link("/news/wnba-expansion-teams/", "expansion story")} says the {name} played their first games in May 2026, '
            f'finished 17-27, and did not make the playoffs.'
        )
    if slug == 'toronto-tempo':
        return (
            f'The {link("/news/wnba-expansion-teams/", "expansion story")} says the {name} played their first games in May 2026, '
            f'finished 11-33, and did not make the playoffs.'
        )
    return ''


def _coverage_line(slug: str) -> str:
    rows = COVERAGE.get(slug) or []
    if not rows:
        return ''
    links_html = ', '.join(prose_link(href, label) for href, label, _claim in rows)
    return f'Playoff and series coverage: {links_html}.'


def photo_html(slug: str) -> str:
    spec = team_hub.VISUALS.get(slug)
    if not spec:
        return ''
    focal = 'center center' if slug == 'portland-fire' else 'center 20%'
    caption = (
        f'Photo: {esc(spec["author"])} / '
        f'<a href="{esc(spec["page"])}" target="_blank" rel="noopener">Wikimedia Commons</a> '
        f'(<a href="{esc(spec["license_href"])}" target="_blank" rel="noopener">{esc(spec["license"])}</a>)'
    )
    return (
        f'<figure class="team-photo"><img src="{esc(spec["src"])}" alt="{esc(spec["alt"])}" '
        f'width="{int(spec["width"])}" height="{int(spec["height"])}" style="object-position:{focal}" '
        f'decoding="async" loading="lazy"><figcaption>{caption}</figcaption></figure>'
    )


def summary_paragraphs(root: Path, slot: dict, standing: dict | None) -> str:
    name = slot['full_name']
    slug = slot['slug']
    if not standing or not isinstance(standing.get('wins'), int) or not isinstance(standing.get('losses'), int):
        return ''
    conference = str(slot.get('conference') or '').strip()
    if not conference:
        label = str(standing.get('conference') or '').strip()
        conference = label if not label or label.endswith('Conference') else f'{label} Conference'
    elif not conference.endswith('Conference'):
        conference = f'{conference} Conference'
    leaders = _leaders(root, slot)
    sentences = [
        _record_sentence(name, standing, conference),
        _seed_sentence(name, standing),
        _split_sentence(name, standing),
        _leader_sentence(name, leaders),
        _minutes_sentence(name, leaders),
        _playoff_html(slug, name),
        _coverage_line(slug),
    ]
    body = ' '.join(part for part in sentences if part)
    count = word_count(body)
    if count < 100 or count > 200:
        raise ValueError(f'{slug} season summary is {count} words, expected 100-200')
    return f'<p class="season-summary">{body}</p>'


def season_section(root: Path, slot: dict, standing: dict | None) -> str:
    summary = summary_paragraphs(root, slot, standing)
    photo = photo_html(slot['slug'])
    if not summary and not photo:
        return ''
    return (
        f'<!-- {SEASON_MARK} -->'
        f'<section class="section" id="season-2026"><p class="eyebrow">2026 season</p>'
        f'<h2>Season summary</h2>{photo}{summary}</section>'
        f'<!-- /{SEASON_MARK} -->'
    )


def stories_section(root: Path, slot: dict) -> str:
    """Team stories, or the latest league stories when this club has none."""
    owned = links.team_news_html(root, slot['slug'])
    if owned:
        return owned
    name = slot.get('full_name') or slot.get('name') or 'this team'
    articles = links._ordered_articles(links.load_articles(root))[:4]
    items = []
    for article in articles:
        title = str(article.get('title') or '').strip()
        if not title:
            continue
        image = str(article.get('image') or '').strip()
        thumb = ''
        if image:
            alt = str(article.get('imageAlt') or title)
            thumb = (
                f'<img src="{esc(image)}" alt="{esc(alt)}"{links._image_dims(article)}'
                f' decoding="async" loading="lazy"{links.focal_style(article)}>'
            )
        items.append(
            '<li><a class="team-news-item" href="' + esc(links.article_href(article)) + '">'
            + thumb + '<span>' + esc(title) + '</span></a></li>'
        )
    if not items:
        return ''
    note = (
        f'<p>No story in the news list names the {esc(name)}, so these are the latest league stories.</p>'
    )
    return (
        '<section class="section" id="team-news"><p class="eyebrow">News</p><h2>Latest stories</h2>'
        + note + '<ul class="teammate-list">' + ''.join(items) + '</ul></section>'
    )


_SEASON_RE = re.compile(
    rf'<!-- {SEASON_MARK} -->.*?<!-- /{SEASON_MARK} -->',
    re.S,
)
_NEWS_RE = re.compile(r'<section class="section" id="team-news">.*?</section>', re.S)


def patch_team_html(page: str, root: Path, slot: dict, standing: dict | None) -> str:
    """Insert the season block and stories into an already published team page."""
    season = season_section(root, slot, standing)
    stories = stories_section(root, slot)
    if _SEASON_RE.search(page):
        page = _SEASON_RE.sub(season, page, count=1)
    else:
        start = page.find('<section class="directory-header">')
        end = page.find('</section>', start)
        if start < 0 or end < 0:
            raise ValueError(f'{slot.get("slug")} is missing a directory header')
        end += len('</section>')
        page = page[:end] + season + page[end:]
    if _NEWS_RE.search(page):
        page = _NEWS_RE.sub(stories, page, count=1)
    elif stories:
        marker = page.find('>All teams</a>')
        if marker < 0:
            raise ValueError(f'{slot.get("slug")} is missing the All teams link')
        paragraph = page.rfind('<p>', 0, marker)
        page = page[:paragraph] + stories + page[paragraph:]
    return page
