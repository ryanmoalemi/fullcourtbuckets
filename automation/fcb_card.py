"""Shared summary card for one team or one player.

The classes live in automation/site_nav.css, so every page that loads
/assets/site-nav.css can use them. Article photos stay 16:9. Headshots stay circles.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_PHOTO_SLUGS: set[str] | None = None

# "played 41 games at 6.3 points, 3.9 rebounds and 1.1 assists per game (18.6 minutes, ...)."
_STAT_RE = re.compile(
    r'^<p><a\b[^>]*href="/wnba/([a-z0-9-]+)/"[^>]*>(.*?)</a> '
    r'played (?:all but one game: |all )?(?P<games>\d+)(?: games?)?(?:, at | at )'
    r'(?P<pts>[\d.]+) points, (?P<reb>[\d.]+) rebounds and (?P<ast>[\d.]+) assists'
    r'(?: per game)? \((?P<extra>[^)]+)\)\. (?P<rest>.*)</p>$',
    re.S,
)
_PLAYER_P_RE = re.compile(
    r'^<p><a\b[^>]*href="/wnba/([a-z0-9-]+)/"[^>]*>(.*?)</a>(?P<rest> .*)</p>$',
    re.S,
)
_P_RE = re.compile(r'<p(?: class="(?P<cls>[^"]*)")?>(?P<body>.*?)</p>', re.S)


def _photo_slugs() -> set[str]:
    global _PHOTO_SLUGS
    if _PHOTO_SLUGS is None:
        path = ROOT / 'content' / 'player-photographs.json'
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            data = {}
        _PHOTO_SLUGS = {str(slug) for slug in (data.get('slugs') or [])}
    return _PHOTO_SLUGS


def _initials(name: str) -> str:
    plain = re.sub(r'<[^>]+>', '', name)
    plain = plain.replace('&#x27;', "'").replace('&amp;', '&')
    parts = [part for part in plain.split() if part[:1].isalpha()]
    if not parts:
        return '?'
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else '')).upper()


def _face(slug: str, name: str) -> str:
    rel = f'/images/players/{slug}/portrait.webp'
    if slug in _photo_slugs() and (ROOT / rel.lstrip('/')).is_file():
        return (
            f'<img class="face" src="{rel}" alt="" width="80" height="80" '
            'loading="lazy" decoding="async">'
        )
    return f'<span class="av" aria-hidden="true">{_initials(name)}</span>'


def _tiles(games: str, pts: str, reb: str, ast: str) -> str:
    cells = (
        stat_tile(pts, 'PTS/G')
        + stat_tile(reb, 'REB/G')
        + stat_tile(ast, 'AST/G')
        + stat_tile(games, 'Games')
    )
    return stat_tiles(cells)


def card_open(extra: str = '') -> str:
    classes = 'fcb-card'
    if extra:
        classes += ' ' + extra.strip()
    return f'<div class="{classes}">'


def card_close() -> str:
    return '</div>'


def stat_tile(value: str, label: str, extra: str = '') -> str:
    classes = 'stat-tile'
    if extra:
        classes += ' ' + extra.strip()
    return f'<div class="{classes}"><b>{value}</b><span>{label}</span></div>'


def stat_tiles(inner: str, extra: str = '') -> str:
    classes = 'stat-tiles'
    if extra:
        classes += ' ' + extra.strip()
    return f'<div class="{classes}">{inner}</div>'


def card_credit(inner: str) -> str:
    return f'<p class="card-credit">{inner}</p>'


def section_note(inner: str) -> str:
    return f'<p class="section-note table-note">{inner}</p>'


def _card(slug: str, name: str, tiles: str, extra: str, body: str) -> str:
    extra_html = f'<p class="early-line">{extra}</p>' if extra else ''
    return (
        card_open()
        + '<div class="card-body">'
        + f'<div class="card-head">{_face(slug, name)}'
        + f'<h3><a href="/wnba/{slug}/">{name}</a></h3></div>'
        + tiles
        + extra_html
        + f'<p>{body}</p>'
        + '</div>'
        + card_close()
    )


def wrap_player_stat_cards(html: str) -> str:
    """Turn a player stat paragraph into a summary card. The numbers stay. The rest of the sentence stays."""

    def repl(match: re.Match) -> str:
        cls = match.group('cls') or ''
        if cls and cls != 'lead':
            return match.group(0)
        paragraph = f'<p>{match.group("body")}</p>'
        stat = _STAT_RE.match(paragraph)
        if stat and stat.group(1) not in ('teams', 'owners'):
            prefix = ''
            lead = paragraph[:stat.start('games')]
            if 'all but one game' in lead:
                prefix = 'Played all but one game. '
            elif 'played all ' in lead:
                prefix = f'Played all {stat.group("games")} games. '
            return _card(
                stat.group(1),
                stat.group(2),
                _tiles(stat.group('games'), stat.group('pts'), stat.group('reb'), stat.group('ast')),
                stat.group('extra') + '.',
                prefix + stat.group('rest'),
            )
        player = _PLAYER_P_RE.match(paragraph)
        body = match.group('body')
        if (
            player
            and player.group(1) not in ('teams', 'owners')
            and 'points' in body
            and ('rebounds' in body or 'points per game' in body)
        ):
            slug, name, rest = player.group(1), player.group(2), player.group('rest')
            return _card(slug, name, '', '', name_link(slug, name) + rest)
        return match.group(0)

    return _P_RE.sub(repl, html)


def name_link(slug: str, name: str) -> str:
    return f'<a class="inline-link" href="/wnba/{slug}/">{name}</a>'
