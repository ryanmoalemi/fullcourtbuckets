"""Link a player page to an FCB recap of her career-high game.

A link is added only when three records agree:
the player FAQ states a single-game career high with a full date,
a box score in data/games has that player, that date, and those points,
and an FCB article whose slug contains "recap" covers that game.
Season averages and games we have not logged are not called career highs.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MONTHS = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
}
POINTS_RE = re.compile(
    r'career[- ]high(?: is| of)? (\d+) points\b',
    re.I,
)
DATE_RE = re.compile(
    r'\b(January|February|March|April|May|June|July|August|September|October|November|December)'
    r' (\d{1,2}), (\d{4})\b',
    re.I,
)


def _load(path: Path, default):
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def _iso(month: str, day: str, year: str) -> str:
    try:
        return date(int(year), MONTHS[month.casefold()], int(day)).isoformat()
    except (KeyError, ValueError):
        return ''


def _faq_claims(root: Path) -> list[dict]:
    claims = []
    folder = root / 'data' / 'wnba' / 'faq'
    if not folder.is_dir():
        return claims
    for path in sorted(folder.glob('*.json')):
        doc = _load(path, {})
        if not isinstance(doc, dict):
            continue
        slug = str(doc.get('slug') or path.stem)
        name = str(doc.get('player_name') or '').strip()
        for item in doc.get('items') or []:
            if not isinstance(item, dict):
                continue
            answer = str(item.get('answer') or '')
            for points_match in POINTS_RE.finditer(answer):
                points = int(points_match.group(1))
                window = answer[points_match.start():points_match.start() + 180]
                dated = DATE_RE.search(window) or DATE_RE.search(answer)
                if not dated:
                    continue
                iso = _iso(dated.group(1), dated.group(2), dated.group(3))
                if not iso:
                    continue
                claims.append({
                    'slug': slug,
                    'name': name,
                    'points': points,
                    'iso': iso,
                    'label': f'{dated.group(1)} {int(dated.group(2))}, {dated.group(3)}',
                })
    return claims


def _recaps(root: Path) -> dict[str, str]:
    """Map a game id to one recap path. Player features that are not recaps stay out."""
    found: dict[str, str] = {}
    for article in _load(root / 'articles.json', []):
        if not isinstance(article, dict):
            continue
        slug = str(article.get('slug') or '')
        url = str(article.get('url') or '')
        if 'recap' not in slug or not url.startswith('/'):
            continue
        for key in ('gameId', 'espnGameId'):
            game_id = str(article.get(key) or '').strip()
            if game_id and game_id not in found:
                found[game_id] = url
    return found


def _box_hits(root: Path) -> list[dict]:
    hits = []
    folder = root / 'data' / 'games'
    if not folder.is_dir():
        return hits
    for path in sorted(folder.glob('*.json')):
        game = _load(path, {})
        if not isinstance(game, dict) or not isinstance(game.get('players'), list):
            continue
        game_ids = [str(game.get('espn_game_id') or ''), str(game.get('balldontlie_game_id') or '')]
        game_ids = [game_id for game_id in game_ids if game_id]
        day = str(game.get('date') or '')[:10]
        for row in game['players']:
            if not isinstance(row, dict) or row.get('did_not_play'):
                continue
            points = row.get('pts')
            if isinstance(points, bool) or not isinstance(points, (int, float)):
                continue
            hits.append({
                'name': str(row.get('name') or '').strip().casefold(),
                'points': int(points),
                'iso': day,
                'ids': game_ids,
            })
    return hits


def matching_games(root: Path | None = None) -> list[dict]:
    """Career-high games that our box score and an FCB recap both cover."""
    root = root or ROOT
    recaps = _recaps(root)
    boxes = _box_hits(root)
    found = []
    seen = set()
    for claim in _faq_claims(root):
        wanted = claim['name'].casefold()
        for box in boxes:
            if box['iso'] != claim['iso'] or box['points'] != claim['points']:
                continue
            if wanted and box['name'] != wanted:
                continue
            url = next((recaps[game_id] for game_id in box['ids'] if game_id in recaps), '')
            if not url:
                continue
            key = (claim['slug'], claim['iso'], claim['points'], url)
            if key in seen:
                continue
            seen.add(key)
            found.append({**claim, 'url': url})
    found.sort(key=lambda item: (item['slug'], -item['points'], item['iso']))
    return found


def note_html(slug: str, root: Path | None = None) -> str:
    """Paragraph for one player. Empty when no career-high game has a recap."""
    rows = [row for row in matching_games(root) if row['slug'] == slug]
    if not rows:
        return ''
    parts = []
    for row in rows:
        parts.append(
            '<p class="career-high-recap">Career-high game in our logs: '
            f'{row["points"]} points on {row["label"]}. '
            f'<a href="{row["url"]}">Full Court Buckets recap</a>.</p>'
        )
    return ''.join(parts)


def insert_note(html: str, note: str) -> str:
    """Put the recap link under the game log, or under the season table when there is no log."""
    if not note or 'career-high-recap' in html:
        return html
    for section_id in ('games', 'stats'):
        token = f'id="{section_id}"'
        start = html.find(token)
        if start < 0:
            continue
        open_at = html.rfind('<section', 0, start)
        if open_at < 0:
            continue
        close = html.find('</section>', start)
        if close < 0:
            continue
        return html[:close] + note + html[close:]
    return html
