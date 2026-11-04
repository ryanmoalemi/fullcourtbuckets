"""Link the first plain-text WNBA player mention to Basketball-Reference.

Names and URLs come from data/wnba/bref-player-urls.json. That file only
contains URLs that returned HTTP 200. This module never invents a URL.

Headings, tables, existing links, and the related-stories aside are left
alone. A Full Court Buckets player link stays as it is. When that link is
the first mention, a later plain-text mention can still point at
Basketball-Reference so the player id is in the article text.
"""
from __future__ import annotations

import html
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAPPING = ROOT / 'data' / 'wnba' / 'bref-player-urls.json'
URL_RE = re.compile(
    r'https://www\.basketball-reference\.com/wnba/players/[a-z]/[a-z0-9]+\.html\Z'
)
HREF_RE = re.compile(r"""href\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
ARTICLE_RE = re.compile(r'(<article\b[^>]*>)(.*?)(</article>)', re.S | re.I)
BREF_HREF_RE = re.compile(
    r'href="(https://www\.basketball-reference\.com/wnba/players/[a-z]/[a-z0-9]+\.html)"'
)
APOS = r"(?:'|’|&#x27;|&#39;|&apos;|&#8217;)"
SKIP_TAGS = {
    'a', 'aside', 'button', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'script', 'style', 'table', 'td', 'textarea', 'th', 'title',
}
VOID_TAGS = {
    'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link',
    'meta', 'source', 'track', 'wbr',
}
LINKABLE_TAGS = {'p', 'li'}


def load_players(path: Path | None = None) -> dict[str, str]:
    """Official player name to a confirmed Basketball-Reference player URL."""
    path = path or MAPPING
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    raw = data.get('players') if isinstance(data, dict) and 'players' in data else data
    players: dict[str, str] = {}
    if not isinstance(raw, dict):
        return players
    for name, url in raw.items():
        clean = str(name or '').strip()
        target = str(url or '').strip()
        if ' ' not in clean or not URL_RE.fullmatch(target):
            continue
        players[clean] = target
    return players


def bref_link_count(page: str) -> int:
    return len(BREF_HREF_RE.findall(page))


def _fold(value: str) -> str:
    text = unicodedata.normalize('NFKD', value)
    text = ''.join(char for char in text if not unicodedata.combining(char))
    text = text.replace('\u2019', "'").replace('’', "'").replace('`', "'")
    return re.sub(r'\s+', ' ', text).strip().casefold()


def _key(value: str) -> str:
    return _fold(html.unescape(value))


def _phrase_body(phrase: str) -> str:
    parts = []
    for char in phrase:
        if char in {"'", '\u2019', '’'}:
            parts.append(APOS)
        else:
            parts.append(re.escape(char))
    return ''.join(parts)


def _phrases(players: dict[str, str]) -> tuple[re.Pattern | None, dict[str, str]]:
    """Longest-first matcher and a normalized-spelling lookup."""
    keys: dict[str, str] = {}
    phrases: list[str] = []

    seen: set[str] = set()

    def add(phrase: str, url: str) -> None:
        key = _key(phrase)
        if not key or ' ' not in key:
            return
        owner = keys.get(key)
        if owner is not None and owner != url:
            return
        if owner is None:
            keys[key] = url
        if phrase not in seen:
            seen.add(phrase)
            phrases.append(phrase)

    for name, url in players.items():
        add(name, url)
    for name, url in players.items():
        folded = _fold(name)
        if folded != name.casefold():
            add(folded, url)
        stripped = re.sub(r"['’\u2019`]", '', name)
        if stripped.casefold() != name.casefold():
            add(stripped, url)
    if not phrases:
        return None, keys
    phrases.sort(key=len, reverse=True)
    pattern = re.compile(
        r'(?<!\w)(?:' + '|'.join(_phrase_body(phrase) for phrase in phrases) + r')(?!\w)',
        re.I,
    )
    return pattern, keys


def _anchor(label: str, url: str) -> str:
    return (
        f'<a class="inline-link" href="{html.escape(url, quote=True)}" '
        f'target="_blank" rel="noopener">{label}</a>'
    )


def _read_tag(source: str, index: int) -> tuple[str, str, bool]:
    """Return the raw tag, its lowercase name, and whether it is a closing tag."""
    if source.startswith('<!--', index):
        end = source.find('-->', index + 4)
        end = len(source) if end < 0 else end + 3
        return source[index:end], '', False
    quote = ''
    cursor = index + 1
    while cursor < len(source):
        char = source[cursor]
        if quote:
            if char == quote:
                quote = ''
        elif char in {'"', "'"}:
            quote = char
        elif char == '>':
            cursor += 1
            break
        cursor += 1
    raw = source[index:cursor]
    match = re.match(r'</?\s*([a-zA-Z0-9]+)', raw)
    name = match.group(1).lower() if match else ''
    return raw, name, raw.startswith('</')


def _href(tag: str) -> str:
    match = HREF_RE.search(tag)
    if not match:
        return ''
    return html.unescape((match.group(1) if match.group(1) is not None else match.group(2)) or '').strip()


_DEFAULT: tuple[dict[str, str], re.Pattern | None, dict[str, str]] | None = None


def _default_matcher() -> tuple[dict[str, str], re.Pattern | None, dict[str, str]]:
    global _DEFAULT
    if _DEFAULT is None:
        players = load_players()
        pattern, keys = _phrases(players)
        _DEFAULT = (players, pattern, keys)
    return _DEFAULT


def link_html(source: str, players: dict[str, str] | None = None) -> str:
    """Link the first eligible mention of each mapped player."""
    if players is None:
        players, pattern, keys = _default_matcher()
    else:
        pattern, keys = _phrases(players)
    if pattern is None:
        return source
    known = set(players.values())
    used: set[str] = set()
    stack: list[str] = []
    out: list[str] = []
    index = 0
    length = len(source)

    def linkable() -> bool:
        if any(tag in SKIP_TAGS for tag in stack):
            return False
        return any(tag in LINKABLE_TAGS for tag in stack)

    def replace(match: re.Match) -> str:
        raw = match.group(0)
        url = keys.get(_key(raw))
        if not url or url in used or url not in known:
            return raw
        used.add(url)
        return _anchor(raw, url)

    while index < length:
        if source[index] != '<':
            end = source.find('<', index)
            if end < 0:
                end = length
            text = source[index:end]
            if linkable() and text:
                text = pattern.sub(replace, text)
            out.append(text)
            index = end
            continue
        raw, name, closing = _read_tag(source, index)
        if name and not closing and name not in VOID_TAGS:
            if name == 'a':
                target = _href(raw)
                if target in known:
                    used.add(target)
            stack.append(name)
        elif name and closing:
            for cursor in range(len(stack) - 1, -1, -1):
                if stack[cursor] == name:
                    del stack[cursor:]
                    break
        out.append(raw)
        index += len(raw)
    return ''.join(out)


def link_document(page: str, players: dict[str, str] | None = None) -> str:
    """Link inside the article body. Pages without an article are unchanged."""
    match = ARTICLE_RE.search(page)
    if not match:
        return page
    linked = link_html(match.group(2), players)
    if linked == match.group(2):
        return page
    return page[:match.start(2)] + linked + page[match.end(2):]


def apply_news_pages(root: Path | None = None, players: dict[str, str] | None = None) -> int:
    """Add links to published news articles. Returns how many links were added."""
    root = root or ROOT
    if players is None:
        players = load_players()
    added = 0
    for path in sorted((root / 'news').glob('*/index.html')):
        text = path.read_text(encoding='utf-8')
        updated = link_document(text, players)
        added += bref_link_count(updated) - bref_link_count(text)
        if updated != text:
            path.write_text(updated, encoding='utf-8')
    return added
