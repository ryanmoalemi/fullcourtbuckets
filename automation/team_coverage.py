"""FCB stories that mention a current WNBA team, at the bottom of each team page.

The list is rebuilt from files already in the repo. articles.json and the
article body supply the stories. data/wnba/players-index.json supplies the
current roster. A nightly player build and an article rebuild both call this
module, so a new story or a roster change shows up without a hand-edited list.

A story matches when it does any of these:

- articles.json lists the team slug
- the story links to that team's page
- the story uses the team's full name
- the story uses the roster nickname, when that nickname is one distinctive word
- the story uses "the {Nickname}" when the nickname is a common word
  (Dream, Sun, Sky, Fire, Tempo)
- the story uses a current player's full name
- the story links to a current player's page

A surname alone does not match. "Gray" is not Allisha Gray. A link whose
visible text is only the surname still matches, because the href is the
player page. The site menu, footer, and the related-story aside are ignored,
so a nav link cannot put every story on every team.
"""
from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

import internal_links as links

PT = ZoneInfo('America/Los_Angeles')
VISIBLE_LIMIT = 20
SECTION_ID = 'team-coverage'
SECTION_RE = re.compile(
    r'<section class="section" id="team-coverage">.*?</section>',
    re.S,
)
ARTICLE_RE = re.compile(r'<article\b[^>]*>(.*)</article>', re.I | re.S)
ARTICLE_END_RE = re.compile(r'<aside\b[^>]*\bclass="[^"]*\barticle-end\b', re.I)
SCRIPT_RE = re.compile(r'<script\b[^>]*>.*?</script>', re.I | re.S)
STYLE_RE = re.compile(r'<style\b[^>]*>.*?</style>', re.I | re.S)
TAG_RE = re.compile(r'<[^>]+>')
PLAYER_HREF_RE = re.compile(
    r'''href=["'](?:https://fullcourtbuckets\.com)?/wnba/(?!teams/|assets/|couples/)([a-z0-9-]+)/["']''',
    re.I,
)
TEAM_HREF_RE = re.compile(
    r'''href=["'](?:https://fullcourtbuckets\.com)?/wnba/teams/([a-z0-9-]+)/["']''',
    re.I,
)
DATE_ONLY_RE = re.compile(r'\d{4}-\d{2}-\d{2}\Z')


def phrase_pattern(phrase: str, ignore_case: bool = False, block_following_team: bool = False) -> re.Pattern:
    parts = []
    for char in phrase:
        if char in {"'", '’'}:
            parts.append("(?:'|’)")
        else:
            parts.append(re.escape(char))
    suffix = r'(?!\s+[Tt]eam\b)' if block_following_team else ''
    flags = re.IGNORECASE if ignore_case else 0
    return re.compile(
        r'(?<![A-Za-z0-9])' + ''.join(parts) + suffix + r'(?![A-Za-z0-9])',
        flags,
    )


def _plain(fragment: str) -> str:
    text = SCRIPT_RE.sub(' ', fragment or '')
    text = STYLE_RE.sub(' ', text)
    text = TAG_RE.sub(' ', text)
    text = html.unescape(text)
    text = text.replace('’', "'").replace('‘', "'").replace('`', "'")
    return re.sub(r'\s+', ' ', text).strip()


def article_body(page: str) -> str:
    """Story copy only. Menu, footer, and the related-story aside stay out."""
    if not page or links.is_redirect_html(page):
        return ''
    match = ARTICLE_RE.search(page)
    if not match:
        return ''
    body = match.group(1)
    cut = ARTICLE_END_RE.search(body)
    if cut:
        body = body[:cut.start()]
    return SCRIPT_RE.sub(' ', body)


def format_pt(raw) -> tuple[str, str]:
    """Calendar date in Pacific Time, plus the visible label.

    A date with no clock is already the publish day and is not shifted.
    A timestamp is converted to America/Los_Angeles first.
    """
    text = str(raw or '').strip()
    if not text:
        return '', ''
    if DATE_ONLY_RE.fullmatch(text):
        when = dt.date.fromisoformat(text)
        return when.isoformat(), f'{when.strftime("%B")} {when.day}, {when.year} PT'
    try:
        parsed = dt.datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        return '', ''
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=PT)
    when = parsed.astimezone(PT).date()
    return when.isoformat(), f'{when.strftime("%B")} {when.day}, {when.year} PT'


def _sort_key(article: dict, index: int) -> tuple:
    raw = str(article.get('date') or '').strip()
    iso, _label = format_pt(raw)
    instant = iso
    if 'T' in raw:
        try:
            parsed = dt.datetime.fromisoformat(raw.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=PT)
            instant = parsed.astimezone(PT).isoformat()
        except ValueError:
            instant = raw
    return (iso, instant, -index)


def load_corpus(root: Path) -> list[dict]:
    """Published stories, newest first, one row per slug."""
    rows = []
    for index, article in enumerate(links.load_articles(root)):
        if not isinstance(article, dict):
            continue
        try:
            slug = links.article_slug(article)
        except ValueError:
            continue
        title = _plain(str(article.get('title') or ''))
        if not title:
            continue
        path = root / 'news' / slug / 'index.html'
        page = path.read_text(encoding='utf-8') if path.is_file() else ''
        if page and links.is_redirect_html(page):
            continue
        if not path.is_file():
            continue
        body = article_body(page)
        description = _plain(str(article.get('description') or ''))
        rows.append({
            'article': article,
            'slug': slug,
            'index': index,
            'body': body,
            'plain': _plain(f'{title} {description} {_plain(body)}'),
            'sort': _sort_key(article, index),
        })
    rows.sort(key=lambda row: row['sort'], reverse=True)
    kept = []
    seen = set()
    for row in rows:
        if row['slug'] in seen:
            continue
        seen.add(row['slug'])
        kept.append(row)
    return kept


def _linking_for(root: Path, slot: dict, linking: dict | None) -> dict:
    if linking is not None:
        return linking
    path = Path(root) / 'data' / 'wnba' / 'players-index.json'
    if path.is_file():
        try:
            index = json.loads(path.read_text(encoding='utf-8'))
            return links.catalog_from_index(index)
        except (OSError, json.JSONDecodeError, ValueError):
            pass
    return {'by_id': {slot.get('id', 0): slot}}


def team_patterns(slot: dict, linking: dict) -> list[re.Pattern]:
    """Full name, plus the roster nickname when it will not hit ordinary words."""
    patterns = []
    full = str(slot.get('full_name') or '').strip()
    if full:
        patterns.append(phrase_pattern(full, ignore_case=True))
    nick = str(slot.get('name') or '').strip()
    if not nick or nick.casefold() == full.casefold():
        return patterns
    counts: dict[str, int] = {}
    for other in linking.get('by_id', {}).values():
        key = str(other.get('name') or '').casefold()
        if key:
            counts[key] = counts.get(key, 0) + 1
    ambiguous = (
        nick.casefold() in links.AMBIGUOUS_NICKNAMES
        or len(nick) < 4
        or ' ' in nick
        or counts.get(nick.casefold(), 0) != 1
    )
    if ambiguous:
        phrases = [f'the {nick}', f'The {nick}']
    else:
        phrases = [nick]
    for phrase in phrases:
        patterns.append(phrase_pattern(phrase, ignore_case=False, block_following_team=True))
    return patterns


def player_matchers(slot: dict) -> tuple[list[re.Pattern], set[str]]:
    """Full names only. A one-word name is not used as text."""
    patterns = []
    slugs = set()
    seen = set()
    for player in slot.get('players') or []:
        slug = str(player.get('slug') or '').strip()
        name = str(player.get('name') or '').strip()
        if slug:
            slugs.add(slug)
        if ' ' not in name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        patterns.append(phrase_pattern(name, ignore_case=True))
        stripped = name.replace("'", '').replace('’', '')
        if ' ' in stripped and stripped.casefold() not in seen:
            seen.add(stripped.casefold())
            patterns.append(phrase_pattern(stripped, ignore_case=True))
    return patterns, slugs


def mentions(row: dict, slot: dict, linking: dict) -> bool:
    article = row.get('article') or {}
    slug = str(slot.get('slug') or '')
    listed = article.get('teams') or []
    if slug and slug in listed:
        return True
    body = row.get('body') or ''
    if slug and slug in TEAM_HREF_RE.findall(body):
        return True
    plain = row.get('plain') or ''
    for pattern in team_patterns(slot, linking):
        if pattern.search(plain):
            return True
    patterns, slugs = player_matchers(slot)
    linked = set(PLAYER_HREF_RE.findall(body))
    if linked & slugs:
        return True
    for pattern in patterns:
        if pattern.search(plain):
            return True
    return False


def matching_articles(root: Path, slot: dict, linking: dict | None = None, corpus: list | None = None) -> list[dict]:
    rows = corpus if corpus is not None else load_corpus(root)
    catalog = _linking_for(root, slot, linking)
    return [row['article'] for row in rows if mentions(row, slot, catalog)]


def _item(article: dict) -> str:
    title = str(article.get('title') or '').strip()
    href = links.article_href(article)
    title_html = links.glue_scores(links.esc(title))
    iso, label = format_pt(article.get('date'))
    when = f'<time datetime="{links.esc(iso)}">{links.esc(label)}</time>' if iso else ''
    return f'<li><a href="{links.esc(href)}">{title_html}</a>{when}</li>'


def _list(articles: list, start: int | None = None) -> str:
    start_attr = f' start="{int(start)}"' if start else ''
    items = ''.join(_item(article) for article in articles)
    return f'<ol class="team-coverage-list"{start_attr}>{items}</ol>'


def section_html(root: Path, slot: dict, linking: dict | None = None, corpus: list | None = None) -> str:
    """The coverage block, or '' when nothing mentions this team."""
    articles = matching_articles(root, slot, linking, corpus)
    if not articles:
        return ''
    name = str(slot.get('full_name') or slot.get('name') or '').strip()
    heading = f'Full Court Buckets coverage of the {name}'
    visible = articles[:VISIBLE_LIMIT]
    extra = articles[VISIBLE_LIMIT:]
    more = ''
    if extra:
        more = (
            '<details class="team-coverage-more"><summary>More</summary>'
            + _list(extra, VISIBLE_LIMIT + 1)
            + '</details>'
        )
    return (
        f'<section class="section" id="{SECTION_ID}">'
        f'<h2>{links.esc(heading)}</h2>'
        + _list(visible)
        + more
        + '</section>'
    )


def apply_html(page: str, root: Path, slot: dict, linking: dict | None = None, corpus: list | None = None) -> str:
    """Insert or replace the block at the bottom of a team page. Drop it when empty."""
    if not page or links.is_redirect_html(page):
        return page
    section = section_html(root, slot, linking, corpus)
    existing = SECTION_RE.search(page)
    if existing:
        if not section:
            return page[:existing.start()] + page[existing.end():]
        if existing.group(0) == section:
            return page
        return page[:existing.start()] + section + page[existing.end():]
    if not section:
        return page
    marker = page.rfind('>All players</a>')
    if marker >= 0:
        end = page.find('</p>', marker)
        if end >= 0:
            end += len('</p>')
            return page[:end] + section + page[end:]
    footer = page.find('<footer')
    if footer >= 0:
        return page[:footer] + section + page[footer:]
    if '</main>' in page:
        return page.replace('</main>', section + '</main>', 1)
    return page + section


def refresh(root: Path) -> int:
    """Rewrite each current team page from the roster and stories on disk."""
    root = Path(root)
    index_path = root / 'data' / 'wnba' / 'players-index.json'
    if not index_path.is_file():
        return 0
    index = json.loads(index_path.read_text(encoding='utf-8'))
    linking = links.catalog_from_index(index)
    corpus = load_corpus(root)
    changes = 0
    for slot in linking['by_id'].values():
        path = root / 'wnba' / 'teams' / slot['slug'] / 'index.html'
        if not path.is_file():
            continue
        original = path.read_text(encoding='utf-8')
        updated = apply_html(original, root, slot, linking, corpus)
        if updated == original:
            continue
        path.write_text(updated, encoding='utf-8')
        changes += 1
    return changes
