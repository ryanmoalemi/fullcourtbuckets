#!/usr/bin/env python3
"""Contextual internal links derived from roster and story copy already in the repo.

Used by build_players.py so the next rebuild keeps the same links. Only emits an
href when the target page is known. Article links use the first mention of a
name that is already written in the copy.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from analytics import GA4_TAG
from link_graph import file_for_url, normalize_href
import homepage_rail
import team_names

# Official Full Court Buckets profile. rel="me" marks it as this site's account.
TIKTOK_URL = 'https://www.tiktok.com/@fullcourtbuckets'
TIKTOK_ICON_SVG = (
    '<svg class="tiktok-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'width="16" height="16" aria-hidden="true" focusable="false">'
    '<path fill="currentColor" d="M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 '
    '1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 '
    '5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19'
    '-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 '
    '1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 '
    '1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03'
    '-.01-8.05.02-12.07z"/></svg>'
)
TIKTOK_FOOTER_LINK = (
    f'<a class="footer-tiktok" href="{TIKTOK_URL}" target="_blank" rel="noopener me">'
    f'{TIKTOK_ICON_SVG}Follow us</a>'
)
ABOUT_TIKTOK_HTML = (
    '<p>Follow Full Court Buckets on TikTok at '
    f'<a href="{TIKTOK_URL}" target="_blank" rel="noopener me">@fullcourtbuckets</a> '
    'for WNBA news, analysis and commentary.</p>'
)
AUTHOR_TIKTOK_HTML = (
    '<p>Full Court Buckets on TikTok: '
    f'<a href="{TIKTOK_URL}" target="_blank" rel="noopener me">@fullcourtbuckets</a>.</p>'
)

MAX_PLAYER_LINKS = 8
AMBIGUOUS_NICKNAMES = {
    'sun', 'sky', 'dream', 'fire', 'tempo', 'stars', 'east', 'west', 'usa',
    'tbd', 'coop', 'spoon', 'team',
}
TAG = re.compile(r'(<[^>]+>)')
REGION = re.compile(r'(<(?:p|li)\b[^>]*>)(.*?)(</(?:p|li)>)', re.I | re.S)
ARTICLE = re.compile(r'(<article\b[^>]*>)(.*?)(</article>)', re.I | re.S)
MAIN = re.compile(r'(<main\b[^>]*>)(.*?)(</main>)', re.I | re.S)


def esc(value):
    return html.escape('' if value is None else str(value), quote=True)


def team_slug(name: str) -> str:
    text = str(name or '').casefold().replace("'", '').replace('’', '')
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', text or ''):
        raise ValueError('Unsafe team slug.')
    return text


class Budget:
    def __init__(self, left=MAX_PLAYER_LINKS):
        self.left = left

    def take(self):
        if self.left <= 0:
            return False
        self.left -= 1
        return True


def catalog_from_index(index: dict) -> dict:
    """Current rosters only. A team page exists when at least one active player lists it."""
    teams = {}
    for entry in index.get('players') or []:
        if entry.get('active_in_provider_feed') is not True:
            continue
        team = entry.get('current_team') or {}
        if not isinstance(team, dict):
            continue
        tid = team.get('id')
        team = team_names.apply(team)
        full = str(team.get('full_name') or '').strip()
        if isinstance(tid, bool) or not isinstance(tid, int) or not full:
            continue
        slot = teams.get(tid)
        if slot is None:
            slot = {
                'id': tid,
                'full_name': full,
                'name': str(team.get('name') or full).strip() or full,
                'conference': str(team.get('conference') or '').strip(),
                'slug': team_names.pinned_slug(tid) or team_slug(full),
                'players': [],
            }
            teams[tid] = slot
        elif slot['full_name'] != full:
            raise ValueError(f'Team {tid} has two names.')
        slot['players'].append({
            'id': entry.get('id'),
            'slug': entry['slug'],
            'name': entry['name'],
        })
    seen = {}
    for slot in teams.values():
        if slot['slug'] in seen:
            raise ValueError('Two teams share a page address.')
        seen[slot['slug']] = slot['id']
        slot['players'].sort(key=lambda p: p['name'].casefold())
    by_name = {slot['full_name']: slot for slot in teams.values()}
    if len(by_name) != len(teams):
        raise ValueError('Two current teams share a full name.')
    for slot in teams.values():
        nick = slot['name']
        if nick and nick.casefold() != slot['full_name'].casefold():
            by_name.setdefault(nick, slot)
    return {'by_id': teams, 'by_name': by_name}


def team_href(slot: dict) -> str:
    return f'/wnba/teams/{slot["slug"]}/'


def link_target_attrs(href: str) -> str:
    """Off-site links open in a new tab. On-site links stay in this tab."""
    value = (href or '').strip()
    lowered = value.casefold()
    if lowered.startswith(('mailto:', 'tel:')):
        return ' target="_blank" rel="noopener"'
    if lowered.startswith(('http://', 'https://', '//')):
        rest = value.split('//', 1)[-1]
        host = rest.split('/')[0].split('@')[-1].split(':')[0].casefold()
        if host not in {'fullcourtbuckets.com', 'www.fullcourtbuckets.com'}:
            return ' target="_blank" rel="noopener"'
    return ''


def inline_link(label: str, href: str) -> str:
    return f'<a class="inline-link" href="{esc(href)}"{link_target_attrs(href)}>{esc(label)}</a>'


def linked_team_name(name: str, linking: dict | None, budget: Budget | None):
    """Return HTML for a team name. Links only when a current team page exists and budget remains."""
    plain = esc(name)
    if not linking or budget is None:
        return plain
    slot = linking['by_name'].get(name)
    if not slot or not budget.take():
        return plain
    return inline_link(name, team_href(slot))


def article_phrases(index: dict, linking: dict) -> list[tuple[str, str]]:
    """Phrases that can be linked from story copy. Ambiguous or single-token names are left as text."""
    phrases = []
    counts = {}
    for entry in index.get('players') or []:
        name = str(entry.get('name') or '').strip()
        counts[name.casefold()] = counts.get(name.casefold(), 0) + 1
    for entry in index.get('players') or []:
        name = str(entry.get('name') or '').strip()
        if ' ' not in name or counts[name.casefold()] != 1:
            continue
        phrases.append((name, f'/wnba/{entry["slug"]}/'))
    nick_counts = {}
    for slot in linking['by_id'].values():
        nick_counts[slot['name'].casefold()] = nick_counts.get(slot['name'].casefold(), 0) + 1
    for slot in linking['by_id'].values():
        url = team_href(slot)
        full = slot['full_name']
        if ' ' in full:
            phrases.append((full, url))
        nick = slot['name']
        if (
            nick
            and nick.casefold() != full.casefold()
            and len(nick) >= 4
            and ' ' not in nick
            and nick.casefold() not in AMBIGUOUS_NICKNAMES
            and nick_counts[nick.casefold()] == 1
        ):
            phrases.append((nick, url))
    compiled = []
    for phrase, url in phrases:
        parts = []
        for char in phrase:
            if char in {"'", '’'}:
                parts.append(r"(?:'|’|&#x27;|&#39;|&apos;)")
            else:
                parts.append(re.escape(char))
        pattern = re.compile('(?<![A-Za-z0-9])' + ''.join(parts) + '(?![A-Za-z0-9])')
        compiled.append((url, pattern))
    return compiled


def _link_plain(text: str, compiled, used: set[str], new_tab: bool = False) -> str:
    pieces = []
    rest = text
    while rest:
        best = None
        for url, pattern in compiled:
            if url in used:
                continue
            match = pattern.search(rest)
            if not match:
                continue
            found = (match.start(), match.end(), match.group(0), url)
            if best is None or found[0] < best[0] or (found[0] == best[0] and found[1] - found[0] > best[1] - best[0]):
                best = found
        if best is None:
            pieces.append(rest)
            break
        start, end, raw, url = best
        pieces.append(rest[:start])
        attrs = ' target="_blank" rel="noopener"' if new_tab else ''
        pieces.append(f'<a class="inline-link" href="{url}"{attrs}>{raw}</a>')
        used.add(url)
        rest = rest[end:]
    return ''.join(pieces)


def _link_fragment(fragment: str, compiled, used: set[str], new_tab: bool = False) -> str:
    parts = TAG.split(fragment)
    out = []
    in_anchor = 0
    skip = 0
    for part in parts:
        if part.startswith('<'):
            low = part.lower()
            if low.startswith('<a ') or low.startswith('<a>'):
                href = re.search(r'href=["\']([^"\']+)', part, re.I)
                if href:
                    target = normalize_href(href.group(1), '/')
                    if target:
                        used.add(target)
                in_anchor += 1
            elif low.startswith('</a'):
                in_anchor = max(0, in_anchor - 1)
            elif low.startswith('<script'):
                skip += 1
            elif low.startswith('</script'):
                skip = max(0, skip - 1)
            elif low.startswith('<style'):
                skip += 1
            elif low.startswith('</style'):
                skip = max(0, skip - 1)
            out.append(part)
        elif in_anchor or skip:
            out.append(part)
        else:
            out.append(_link_plain(part, compiled, used, new_tab=new_tab))
    return ''.join(out)


def link_copy(html_text: str, compiled, scope: str = 'article') -> str:
    """Link the first body mention inside p and li. Existing anchors count as the first mention."""
    pattern = ARTICLE if scope == 'article' else MAIN
    match = pattern.search(html_text)
    if not match:
        return html_text
    used: set[str] = set()
    # Story prose keeps the new-tab pattern. Hub and terms copy stays in this tab.
    new_tab = scope == 'article'

    def region(found: re.Match) -> str:
        return found.group(1) + _link_fragment(found.group(2), compiled, used, new_tab=new_tab) + found.group(3)

    inner = REGION.sub(region, match.group(2))
    return html_text[:match.start(2)] + inner + html_text[match.end(2):]


def ensure_footer_hubs(text: str) -> str:
    """Add crawlable Players, Standings, and TikTok links in an existing footer link row."""
    match = re.search(r'<p class="footer-links">.*?</p>', text, re.S)
    if not match:
        return text
    block = match.group(0)
    extra = ''
    if 'href="/wnba/"' not in block and "href='/wnba/'" not in block:
        extra += '<a href="/wnba/">Players</a>'
    if 'href="/standings/"' not in block and "href='/standings/'" not in block:
        extra += '<a href="/standings/">Standings</a>'
    if extra:
        open_end = block.find('>') + 1
        block = block[:open_end] + extra + block[open_end:]
    if TIKTOK_URL not in block:
        block = block.replace('</p>', TIKTOK_FOOTER_LINK + '</p>', 1)
    if block == match.group(0):
        return text
    return text[:match.start()] + block + text[match.end():]


def _format_date(iso: str) -> str:
    year, month, day = (int(part) for part in str(iso).split('-')[:3])
    when = dt.date(year, month, day)
    return f'{when.strftime("%B")} {when.day}, {when.year}'


def _image_dims(article: dict) -> str:
    width, height = article.get('imageWidth'), article.get('imageHeight')
    if not width or not height:
        return ''
    return f' width="{int(width)}" height="{int(height)}"'


MORE_STORY_LIMIT = 8
FULL_STORY_CARDS = 3


# 85-83, 101-98, 2-0. The hyphen is a line-break point, so the score sits in one span.
SCORE_RE = re.compile(r'(?<!\d)\d{1,3}-\d{1,3}(?!\d)')
_HEADING_RE = re.compile(r'(<h[1-3]\b[^>]*>)(.*?)(</h[1-3]>)', re.S | re.I)


def glue_scores(fragment: str) -> str:
    """Keep a score together. Tags are left alone so a URL cannot be rewritten."""
    parts = re.split(r'(<[^>]+>)', fragment)
    out = []
    skip = 0
    for part in parts:
        if part.startswith('<'):
            if re.match(r'<span\b[^>]*\bclass="[^"]*\bscore\b', part, re.I):
                skip += 1
            elif part.lower().startswith('</span') and skip:
                skip -= 1
            out.append(part)
            continue
        if skip:
            out.append(part)
            continue
        out.append(SCORE_RE.sub(
            lambda match: f'<span class="score" style="white-space:nowrap">{match.group(0)}</span>',
            part,
        ))
    return ''.join(out)


def glue_headline_scores(html: str) -> str:
    """Article titles and other headings. Body copy can still break at a hyphen."""
    return _HEADING_RE.sub(
        lambda match: match.group(1) + glue_scores(match.group(2)) + match.group(3),
        html,
    )


def _story_card(article: dict, compact: bool = False) -> str:
    title = article['title']
    image = article.get('image') or ''
    alt = article.get('imageAlt') or title
    klass = 'article-card is-compact' if compact else 'article-card'
    return (
        f'<a class="{klass}" href="{esc(article_href(article))}">'
        f'<div class="article-visual"><img src="{esc(image)}" alt="{esc(alt)}"{_image_dims(article)}'
        f' decoding="async" loading="lazy"{focal_style(article)}></div>'
        f'<div class="article-copy"><div class="cat">{esc(article.get("category") or "")}</div>'
        f'<h3>{glue_scores(esc(title))}</h3><p>{esc(article.get("description") or "")}</p>'
        f'<div class="date">{esc(_format_date(article["date"]))}</div></div></a>'
    )


def _more_story_cards(articles: list) -> str:
    """Three full cards, then compact rows. Eight stories after the feature."""
    rest = articles[1:1 + MORE_STORY_LIMIT]
    return ''.join(
        _story_card(article, compact=index >= FULL_STORY_CARDS)
        for index, article in enumerate(rest)
    )


def _replace_marker(text: str, name: str, inner: str) -> str:
    pattern = re.compile(rf'<!-- {name}:start -->.*?<!-- {name}:end -->', re.S)
    block = f'<!-- {name}:start -->{inner}<!-- {name}:end -->'
    if pattern.search(text):
        return pattern.sub(lambda _: block, text, count=1)
    return text


HUBS = (
    '<!-- fcb-hubs:start --><section class="section" id="site-hubs">'
    '<div class="section-head"><h2 class="section-title">Players and standings</h2></div>'
    '<div class="coverage-grid">'
    '<a class="coverage-card" href="/standings/"><b>Standings</b>'
    '<p>Current WNBA standings and where each team sits in the playoff race.</p></a>'
    '<a class="coverage-card" href="/wnba/"><b>Players</b>'
    '<p>Season statistics and profiles for WNBA players, past and present.</p></a>'
    '</div></section><!-- fcb-hubs:end -->'
)


MATCHUP_IMAGE = '/images/articles/2026-wnba-finals-ratings-tracker/matchup-1200.webp'
MATCHUP_ALT = 'Angel Reese of the Atlanta Dream in a white number 5 jersey looks up'


def _featured_source(article: dict) -> dict:
    """The pending-counts sheet is not the homepage hero. Use the matchup photo."""
    source = dict(article or {})
    image = str(source.get('image') or '')
    if not image:
        return source
    tracker = source.get('slug') == '2026-wnba-finals-ratings-tracker'
    pending = image.endswith('/ratings-sheet.webp') or image.endswith('/social-card.webp')
    if not tracker and not pending:
        return source
    if pending or not image.endswith('/matchup-1200.webp'):
        source['image'] = MATCHUP_IMAGE
        source['imageWidth'] = 1200
        source['imageHeight'] = 675
    alt = str(source.get('imageAlt') or '')
    if not alt or 'pending' in alt.lower():
        source['imageAlt'] = MATCHUP_ALT
    source['imageFocal'] = 'center center'
    return source


def _featured_photo(article: dict) -> str:
    """Lead image for the homepage hero. Empty when the story has no image."""
    source = _featured_source(article)
    image = str(source.get('image') or '').strip()
    if not image:
        return ''
    alt = str(source.get('imageAlt') or source.get('title') or '')
    return (
        f'<img class="feature-photo" id="featured-image" src="{esc(image)}" alt="{esc(alt)}"'
        f'{_image_dims(source)} decoding="async" fetchpriority="high"{focal_style(source)}>'
    )


def _featured_credit(article: dict) -> str:
    credit = str((article or {}).get('imageCredit') or '').strip()
    return f'<span class="feature-credit" id="featured-credit">{esc(credit)}</span>'


def _homepage_feature_card(article: dict) -> str:
    """Homepage lead. Same post card the other stories use. No credit on the card."""
    card = _story_card(_featured_source(article))
    return card.replace('<a class="article-card"', '<a class="article-card" id="featured-story"', 1)


def _apply_featured_media(text: str, article: dict) -> str:
    """Replace the featured slot with the standard post card."""
    card = _homepage_feature_card(article)
    updated, count = re.subn(
        r'<a\b[^>]*\bid="featured-story"[^>]*>.*?</a>',
        lambda _match: card,
        text,
        count=1,
        flags=re.S,
    )
    return updated if count else text


def _place_hubs(text: str) -> str:
    """Players and standings sits above the story list, not after it."""
    text = re.sub(r'<!-- fcb-hubs:start -->.*?<!-- fcb-hubs:end -->', '', text, count=1, flags=re.S)
    needle = '<section class="section" id="more-stories">'
    if needle in text:
        return text.replace(needle, HUBS + needle, 1)
    fallback = '<section class="section"><div class="section-head"><h2 class="section-title">What We Cover</h2>'
    if fallback in text:
        return text.replace(fallback, HUBS + fallback, 1)
    return text


def _ensure_all_news(text: str) -> str:
    if 'class="all-news"' in text:
        return text
    old = (
        '<section class="section" id="more-stories">'
        '<div class="section-head"><h2 class="section-title">More Stories</h2></div>'
    )
    new = (
        '<section class="section" id="more-stories">'
        '<div class="section-head"><h2 class="section-title">More Stories</h2>'
        '<a class="all-news" href="/news/">All news</a></div>'
    )
    if old in text:
        return text.replace(old, new, 1)
    return text


TICKER_MAX_AGE = dt.timedelta(hours=48)
_TICKER_RE = re.compile(r'<div class="ticker\b[^>]*>.*?</div></div></div>', re.S)
_WEEKDAYS = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
_MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')


def _article_day(article: dict) -> str:
    return str(article.get('date') or '')[:10]


def _noon(day: dt.date) -> dt.datetime:
    return dt.datetime(day.year, day.month, day.day, 12, 0, tzinfo=ZoneInfo('America/Los_Angeles'))


def _is_game_result(article: dict) -> bool:
    if str(article.get('espnGameId') or '').strip():
        return True
    return bool(re.search(r'\b\d{2,3}\s*-\s*\d{2,3}\b', str(article.get('title') or '')))


def _short_club(name: str) -> str:
    parts = name.split()
    return parts[-1] if parts else name


def _pt_clock(tip: str) -> str:
    match = re.search(r'(\d{1,2}:\d{2})\s*([ap])\.?m\.?\s*PT', tip, re.I)
    if not match:
        return ''
    hour, minute = match.group(1).split(':')
    suffix = 'AM' if match.group(2).lower() == 'a' else 'PM'
    return f'{int(hour)}:{minute} {suffix} PT'


def _slash_network(network: str) -> str:
    return network.replace(' and ', '/').replace(', ', '/')


def _schedule_items() -> list[dict]:
    """Upcoming Finals games from the shared tracker rows."""
    import citation

    items = []
    for row in citation.FINALS_TRACKER_ROWS:
        game, date_text, matchup, network, tip = row[:5]
        status = row[-1]
        if status != 'Scheduled':
            continue
        found = re.search(r'([A-Z][a-z]{2})\.?\s+(\d{1,2}),\s+(\d{4})', date_text)
        teams = matchup.split(',', 1)[0]
        clock = _pt_clock(tip)
        if not found or ' at ' not in teams or not clock:
            continue
        month = _MONTHS.index(found.group(1)) + 1
        day = dt.date(int(found.group(3)), month, int(found.group(2)))
        hour_text, suffix = clock.split(' ')[0], clock.split(' ')[1]
        hour, minute = (int(part) for part in hour_text.split(':'))
        if suffix == 'PM' and hour != 12:
            hour += 12
        if suffix == 'AM' and hour == 12:
            hour = 0
        moment = dt.datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZoneInfo('America/Los_Angeles'))
        away, home = teams.split(' at ', 1)
        text = (
            f'WNBA Finals Game {game}: {_short_club(away)} at {_short_club(home)}, '
            f'{_WEEKDAYS[day.weekday()]} {_MONTHS[day.month - 1]} {day.day}, {clock}, {_slash_network(network)}'
        )
        text = FINALS_TICKER_TEXT.get(str(game), text)
        items.append({'date': day.isoformat(), 'moment': moment, 'text': text, 'kind': 'schedule'})
    return items


# Hand-written Now lines for Finals games, matching the article tickers (absolute dates, series status).
FINALS_TICKER_TEXT = {
    '2': 'WNBA Finals Game 2: Dream at Valkyries, Mon Oct 19, 2026, 5 p.m. PT, Chase Center. Valkyries lead 1-0.',
}
# A scheduled game stays the Now line until about three hours after tip-off, then the next game takes over.
GAME_WINDOW = dt.timedelta(hours=3)


def _next_finals_item(now: dt.datetime) -> dict | None:
    fresh = [item for item in _schedule_items() if item['moment'] >= now - GAME_WINDOW]
    fresh.sort(key=lambda item: item['moment'])
    return fresh[0] if fresh else None


def _article_ticker(article: dict) -> dict | None:
    raw = _article_day(article)
    try:
        day = dt.date.fromisoformat(raw)
    except ValueError:
        return None
    title = re.sub(r'\s+', ' ', str(article.get('title') or '')).strip()
    if not title:
        return None
    return {'date': raw, 'moment': _noon(day), 'text': title, 'kind': 'article'}


def choose_ticker(articles: list, now: dt.datetime | None = None) -> dict | None:
    """Newest game result, or the next Finals game when no result is newer.

    The line is hidden when that item is more than 48 hours old.
    """
    moment = now or dt.datetime.now(ZoneInfo('America/Los_Angeles'))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=ZoneInfo('America/Los_Angeles'))
    ordered = [article for article in articles or [] if isinstance(article, dict) and _article_day(article)]
    ordered.sort(key=_article_day, reverse=True)
    if not ordered:
        return None
    newest = ordered[0]
    schedule = _next_finals_item(moment)
    result = _article_ticker(newest) if _is_game_result(newest) else None
    result_fresh = result is not None and result['moment'] >= moment - TICKER_MAX_AGE
    game_day = schedule is not None and schedule['date'] <= moment.date().isoformat()
    # The next game takes over on game day; before that a fresh result stays up.
    if schedule and (result is None or game_day or not result_fresh):
        item = schedule
    elif result:
        item = result
    else:
        item = _article_ticker(newest)
    if item is None or item['moment'] < moment - TICKER_MAX_AGE:
        return None
    if item['date'] < _article_day(newest):
        item = dict(item)
        item['date'] = _article_day(newest)
    return item


def apply_ticker(html: str, articles: list, now: dt.datetime | None = None) -> str:
    """The Now line is one shared sitewide value (data/now-ticker.json); see site_nav.apply_now_bar."""
    import site_nav
    if 'site-header' in html:
        return site_nav.apply_now_bar(html)
    if 'id="latest"' not in html:
        return html
    item = choose_ticker(articles, now)
    if item is None:
        return _TICKER_RE.sub('', html, count=1)
    block = (
        f'<div class="ticker" data-item-date="{esc(item["date"])}">'
        '<div class="shell"><div class="ticker-label">Now</div>'
        f'<div class="ticker-text">{esc(item["text"])}</div></div></div>'
    )
    if _TICKER_RE.search(html):
        first = True

        def replace(_match: re.Match) -> str:
            nonlocal first
            if first:
                first = False
                return block
            return ''

        return _TICKER_RE.sub(replace, html)
    if '</header>' in html:
        return html.replace('</header>', '</header>\n' + block, 1)
    return html


def apply_homepage(text: str, articles: list, rail_html: str | None = None) -> str:
    """Crawlable story and hub links. Leaves the small test homepage untouched."""
    text = ensure_site_organization_same_as(text)
    if 'id="latest"' not in text or 'id="older-stories"' not in text:
        return text
    text = ensure_footer_hubs(text)
    text = _place_hubs(text)
    text = _ensure_all_news(text)
    ordered = sorted(articles, key=lambda article: article.get('date') or '', reverse=True)
    if ordered:
        featured = ordered[0]
        text = re.sub(
            r'(<a class="feature feature-link" id="featured-story" href=")[^"]*(")',
            lambda match: match.group(1) + article_href(featured) + match.group(2),
            text,
            count=1,
        )
        text = _apply_featured_media(text, featured)
        text = re.sub(
            r'(<h1 id="featured-title">).*?(</h1>)',
            lambda m: m.group(1) + glue_scores(esc(featured['title'])) + m.group(2),
            text,
            count=1,
        )
        text = re.sub(r'(<p id="featured-dek">).*?(</p>)', lambda m: m.group(1) + esc(featured.get('description') or '') + m.group(2), text, count=1)
        meta = f'{featured.get("category") or ""} · {_format_date(featured["date"])}'
        text = re.sub(r'(<div class="meta" id="featured-meta">).*?(</div>)', lambda m: m.group(1) + esc(meta) + m.group(2), text, count=1)
        cards = _more_story_cards(ordered)
        if '<!-- fcb-stories:start -->' in text:
            text = _replace_marker(text, 'fcb-stories', cards)
        else:
            text = text.replace(
                '<div class="story-list" id="older-stories"></div>',
                '<div class="story-list" id="older-stories"><!-- fcb-stories:start -->' + cards + '<!-- fcb-stories:end --></div>',
                1,
            )
        text = text.replace('id="more-stories" hidden', 'id="more-stories"', 1)
    old = 'articles.slice(1).forEach(function (a) {'
    guard = 'if (!list.querySelector("a.article-card")) articles.slice(1).forEach(function (a) {'
    if old in text and guard not in text:
        text = text.replace(old, guard, 1)
    text = text.replace('link.href = "/" + featured.slug + "/";', 'link.href = articlePath(featured);')
    text = text.replace('card.href = "/" + a.slug + "/";', 'card.href = articlePath(a);')
    text = text.replace('    link.target = "_blank";\n    link.rel = "noopener";\n', '')
    text = text.replace('      card.target = "_blank";\n      card.rel = "noopener";\n', '')
    helper = 'function articlePath(a){return (a.url && a.url.charAt(0)==="/") ? a.url : ("/news/" + a.slug + "/");}'
    if 'function articlePath(' not in text:
        text = text.replace('fetch("/articles.json")', helper + '\n  fetch("/articles.json")', 1)
    if rail_html:
        text = homepage_rail.apply_rail(text, rail_html)
    return apply_ticker(text, articles)


def _pct(value) -> str:
    try:
        return f'{float(value):.3f}'.replace('0.', '.', 1) if float(value) < 1 else f'{float(value):.3f}'
    except (TypeError, ValueError):
        return ''


def _long_date(raw) -> str:
    text = str(raw or '').strip()
    if not text:
        return ''
    try:
        if 'T' in text or text.endswith('Z'):
            moment = dt.datetime.fromisoformat(text.replace('Z', '+00:00'))
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=dt.timezone.utc)
            day = moment.astimezone(ZoneInfo('America/Los_Angeles')).date()
        else:
            day = dt.date.fromisoformat(text[:10])
    except (ValueError, TypeError):
        return ''
    return f'{day.strftime("%B")} {day.day}, {day.year}'


def standings_sentence(standings: dict) -> str:
    """One sentence from the published table. No record is guessed."""
    teams = [team for team in (standings.get('teams') or []) if isinstance(team, dict)]
    leader = next((team for team in teams if team.get('rank') == 1), None)
    name = str((leader or {}).get('name') or '').strip()
    if not name:
        return ''
    wins, losses = leader.get('wins'), leader.get('losses')
    if isinstance(wins, bool) or isinstance(losses, bool) or not isinstance(wins, int) or not isinstance(losses, int):
        return ''
    return f'The {name} lead the WNBA standings at {wins}-{losses}.'


def _iso_day(raw) -> str:
    """Pacific calendar day for a timestamp. Date-only values stay as written."""
    text = str(raw or '').strip()
    if not text:
        return ''
    try:
        if 'T' in text or text.endswith('Z'):
            moment = dt.datetime.fromisoformat(text.replace('Z', '+00:00'))
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=dt.timezone.utc)
            return moment.astimezone(ZoneInfo('America/Los_Angeles')).date().isoformat()
        return dt.date.fromisoformat(text[:10]).isoformat()
    except (ValueError, TypeError):
        return ''


def regular_season_is_final(standings: dict) -> bool:
    """True once every team has finished the same full regular-season schedule."""
    teams = [team for team in (standings.get('teams') or []) if isinstance(team, dict)]
    played = []
    for team in teams:
        wins, losses = team.get('wins'), team.get('losses')
        if isinstance(wins, bool) or isinstance(losses, bool) or not isinstance(wins, int) or not isinstance(losses, int):
            return False
        played.append(wins + losses)
    return len(played) >= 12 and len(set(played)) == 1 and played[0] >= 40


def standings_title(standings: dict) -> str:
    year = standings.get('season') or ''
    if regular_season_is_final(standings) and year:
        return f'Final {year} regular-season standings'
    return 'WNBA Standings'


def stamp_webpage_modified(text: str, day: str) -> str:
    """JSON-LD dateModified follows the data date, not the time the HTML was built."""
    if not day:
        return text

    def repl(match):
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            return match.group(0)
        nodes = data.get('@graph') if isinstance(data, dict) else None
        if not isinstance(nodes, list):
            nodes = [data] if isinstance(data, dict) else []
        for node in nodes:
            if isinstance(node, dict) and node.get('@type') == 'WebPage':
                node['dateModified'] = day
        encoded = json.dumps(data, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
        return '<script type="application/ld+json">' + encoded + '</script>'

    return re.sub(r'<script type="application/ld\+json">(.*?)</script>', repl, text, count=1, flags=re.S)


def apply_standings_freshness(text: str, standings: dict) -> str:
    """Replace the JS placeholder date with the date stored in the standings file."""
    sentence = standings_sentence(standings)
    when = _long_date(standings.get('updatedAt'))
    parts = [part for part in (sentence, f'Updated {when}.' if when else '') if part]
    if parts:
        block = '<p class="support" id="standings-updated">' + esc(' '.join(parts)) + '</p>'
        if 'id="standings-updated"' in text:
            text = re.sub(r'<p class="support" id="standings-updated">.*?</p>', lambda _: block, text, count=1)
        else:
            old = '<p class="support">Updated automatically throughout the season.</p>'
            if old in text:
                text = text.replace(old, block, 1)
    title = standings_title(standings)
    text = re.sub(
        r'<h1>(?:WNBA Standings|Final \d{4} regular-season standings)</h1>',
        f'<h1>{esc(title)}</h1>',
        text,
        count=1,
    )
    # One heading and one Updated line. The support sentence carries the date.
    text = re.sub(r'<p class="subhead">.*?</p>', '', text, count=1, flags=re.S)
    text = re.sub(r'<div class="last-updated">.*?</div>', '', text, count=1, flags=re.S)
    text = re.sub(r'<span id="updatedAt">.*?</span>', '', text, count=1, flags=re.S)
    text = re.sub(
        r'<h2>[^<]*WNBA Standings</h2>',
        '',
        text,
        count=1,
    )
    return stamp_webpage_modified(text, _iso_day(standings.get('updatedAt')))


def apply_standings(text: str, linking: dict, standings: dict) -> str:
    text = ensure_footer_hubs(text)
    by_name = {}
    for slot in linking['by_id'].values():
        href = team_href(slot)
        by_name[slot['full_name']] = href
        nick = slot.get('name') or ''
        if nick and nick.casefold() != slot['full_name'].casefold():
            by_name.setdefault(nick, href)
    payload = json.dumps(by_name, ensure_ascii=False, separators=(',', ':'))
    script = (
        '/* fcb-team-pages:start */\nconst teamPages = ' + payload + ';\n'
        'function teamNameHtml(name) {\n'
        "  var href = teamPages[name];\n"
        "  var safe = String(name).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');\n"
        "  if (!href) return '<span class=\"team-name\">' + safe + '</span>';\n"
        "  return '<a class=\"team-name\" href=\"' + href + '\">' + safe + '</a>';\n"
        '}\n/* fcb-team-pages:end */'
    )
    if '/* fcb-team-pages:start */' in text:
        text = re.sub(
            r'\n*/\* fcb-team-pages:start \*/.*?/\* fcb-team-pages:end \*/\n*',
            lambda _: '\n' + script + '\n',
            text,
            count=1,
            flags=re.S,
        )
    else:
        text = text.replace(
            "const standingsUrl = '/api/wnba-standings';",
            "const standingsUrl = '/api/wnba-standings';\n" + script,
            1,
        )
    old_span = "'<span class=\"team-name\">' + team.name + '</span>'"
    new_span = 'teamNameHtml(team.name)'
    if old_span in text:
        text = text.replace(old_span, new_span)

    def row(team, wide):
        raw = str(team.get('name') or '')
        name = team_names.public_name(raw)
        href = by_name.get(raw) or by_name.get(name)
        label = f'<a class="team-name" href="{esc(href)}">{esc(name)}</a>' if href else f'<span class="team-name">{esc(name)}</span>'
        rank = team.get('conferenceRank') if not wide and team.get('conferenceRank') not in (None, '') else team.get('rank')
        games_back = team.get('gamesBack')
        if not wide and team.get('conferenceGamesBack') not in (None, ''):
            games_back = team.get('conferenceGamesBack')
        badge = str(team.get('abbreviation') or name.split()[-1][:3]).upper()
        cells = (
            f'<td><span class="rank">{esc(rank)}</span></td>'
            f'<td><div class="team-cell"><span class="team-badge">{esc(badge)}</span>{label}</div></td>'
            f'<td>{esc(team.get("wins"))}</td><td>{esc(team.get("losses"))}</td>'
            f'<td class="percent">{esc(_pct(team.get("pct")))}</td><td>{esc(games_back)}</td>'
        )
        if wide:
            cells += (
                f'<td>{esc(team.get("home"))}</td><td>{esc(team.get("road"))}</td>'
                f'<td>{esc(team.get("streak"))}</td><td>{esc(team.get("last10"))}</td>'
            )
        klass = ' class="playoff-row"' if wide and isinstance(team.get('rank'), int) and team['rank'] <= 8 else ''
        html_row = f'<tr{klass}>{cells}</tr>'
        if wide and team.get('rank') == 8:
            html_row += '<tr class="playoff-line"><td colspan="10">Playoff Line</td></tr>'
        return html_row

    listed = standings.get('teams') or []

    def conference_rows(name):
        rows = [team for team in listed if team.get('conference') == name]
        return sorted(
            rows,
            key=lambda team: (
                team.get('conferenceRank') if isinstance(team.get('conferenceRank'), int) else 99,
                str(team.get('name') or ''),
            ),
        )

    text = re.sub(
        r'<tbody id="standingsBody">.*?</tbody>',
        '<tbody id="standingsBody">' + ''.join(row(team, True) for team in listed) + '</tbody>',
        text,
        count=1,
        flags=re.S,
    )
    text = re.sub(
        r'<tbody id="eastStandings">.*?</tbody>',
        '<tbody id="eastStandings">' + ''.join(row(team, False) for team in conference_rows('Eastern')) + '</tbody>',
        text,
        count=1,
        flags=re.S,
    )
    text = re.sub(
        r'<tbody id="westStandings">.*?</tbody>',
        '<tbody id="westStandings">' + ''.join(row(team, False) for team in conference_rows('Western')) + '</tbody>',
        text,
        count=1,
        flags=re.S,
    )
    blocks = []
    for slot in sorted(linking['by_id'].values(), key=lambda item: item['full_name'].casefold()):
        players = ''.join(
            f'<li><a class="inline-link" href="/wnba/{esc(player["slug"])}/">{esc(player["name"])}</a></li>'
            for player in slot['players']
        )
        blocks.append(
            f'<h3><a href="{esc(team_href(slot))}">{esc(slot["full_name"])}</a></h3><ul>{players}</ul>'
        )
    roster = (
        '<section class="explainer" id="rosters"><h3>Current rosters</h3>'
        '<p>Players listed on each current roster.</p>'
        + ''.join(blocks) + '</section>'
    )
    wrapped = f'<!-- fcb-rosters:start -->{roster}<!-- fcb-rosters:end -->'
    if '<!-- fcb-rosters:start -->' in text:
        text = _replace_marker(text, 'fcb-rosters', roster)
    else:
        text = text.replace('</div>\n</main>', '</div>\n' + wrapped + '\n</main>', 1)
        if wrapped not in text:
            text = text.replace('</main>', wrapped + '</main>', 1)
    return apply_standings_freshness(text, standings)


def ensure_sitemap(text: str, urls: list[str], base: str) -> str:
    """Add current team URLs and drop team locations that are no longer published."""
    if '</urlset>' not in text:
        return text
    wanted = {base + url for url in urls}
    team_prefix = base + '/wnba/teams/'

    def keep(match: re.Match) -> str:
        block = match.group(0)
        loc_match = re.search(r'<loc>\s*([^<]+?)\s*</loc>', block)
        if not loc_match:
            return block
        loc = loc_match.group(1).strip()
        if loc.startswith(team_prefix) and loc not in wanted:
            return ''
        return block

    text = re.sub(r'[ \t]*<url\b[^>]*>.*?</url>[ \t]*\r?\n?', keep, text, flags=re.S)
    for url in urls:
        loc = base + url
        if re.search(rf'<loc>\s*{re.escape(loc)}\s*</loc>', text):
            continue
        block = (
            '  <url>\n'
            f'    <loc>{loc}</loc>\n'
            '    <lastmod>2026-09-29</lastmod>\n'
            '    <changefreq>weekly</changefreq>\n'
            '    <priority>0.7</priority>\n'
            '  </url>\n'
        )
        text = text.replace('</urlset>', block + '</urlset>', 1)
    return text


def apply_known_page_links(text: str, relative: str) -> str:
    """A few hub words already written on static pages. No new claims."""
    text = ensure_footer_hubs(text)
    if relative == 'about/index.html':
        if 'Follow Full Court Buckets on TikTok at ' not in text:
            marker = (
                '<p><a href="/authors/ryan-moalemi/">Ryan Moalemi</a> runs Full Court Buckets. '
                'He comes up with the stories, edits every one, and uses AI tools to help draft them. '
                '<a href="/how-we-make-full-court-buckets/">Here\'s how that works.</a></p>'
            )
            if marker in text:
                text = text.replace(marker, marker + ABOUT_TIKTOK_HTML, 1)
            elif '</main>' in text:
                text = text.replace('</main>', ABOUT_TIKTOK_HTML + '</main>', 1)
        if '<b>Players:</b>' in text:
            text = text.replace(
                '<b>Players:</b>',
                '<b><a href="/wnba/">Players</a>:</b>',
                1,
            )
        if '<b>Standings:</b>' in text:
            text = text.replace(
                '<b>Standings:</b>',
                '<b><a href="/standings/">Standings</a>:</b>',
                1,
            )
    if relative == 'terms/index.html':
        compiled = [
            ('/wnba/', re.compile(r'(?<![A-Za-z0-9])player profiles(?![A-Za-z0-9])')),
            ('/standings/', re.compile(r'(?<![A-Za-z0-9])standings(?![A-Za-z0-9])')),
        ]
        text = link_copy(text, compiled, scope='main')
    return text


def verify_hrefs(root: Path, pages: dict[str, str]) -> None:
    """Raise if a generated contextual href does not match a real file."""
    blob = '\n'.join(value for value in pages.values() if isinstance(value, str))
    hrefs = re.findall(
        r'<a class="(?:inline-link|team-name|coverage-card|article-card|team-card-link)" href="(/[^"]+|https?://[^"]+)"',
        blob,
    )
    for href in hrefs:
        target = normalize_href(href, '/')
        if not target:
            continue
        relative = target.lstrip('/')
        leaf = target.rstrip('/').split('/')[-1]
        if target.endswith('/'):
            key = (relative + 'index.html') if relative else 'index.html'
        else:
            key = relative if '.' in leaf else relative + '/index.html'
        if key in pages or file_for_url(root, target) is not None:
            continue
        raise ValueError(f'Link target does not exist: {href}')


def load_articles(root: Path) -> list:
    path = root / 'articles.json'
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding='utf-8'))
    return data if isinstance(data, list) else []


BASE = 'https://fullcourtbuckets.com'
NEWS_HUB = '/news/'
ARTICLE_SLUG = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*\Z')
NEWS_INTRO = 'WNBA game recaps, roster notes, and other league stories from Full Court Buckets, each with a date and a one-line summary.'
# After the story cards on /news/ only. Couples is a news feature, not a menu item.
COUPLES_FEATURE_HTML = '<p class="couples-feature"><a href="/wnba/couples/">WNBA couples</a></p>'
COUPLES_FEATURE_CSS = (
    '.couples-feature{margin:22px 0 0}'
    '.couples-feature a{color:#ff9800;font-weight:700;text-decoration:underline;'
    'display:inline-flex;align-items:center;min-height:44px}'
)
AUTHOR_NAME = 'Ryan Moalemi'
AUTHOR_PATH = '/authors/ryan-moalemi/'
AUTHOR_PAGE = 'authors/ryan-moalemi/index.html'
AUTHOR_URL = BASE + AUTHOR_PATH
AUTHOR_PHOTO = '/images/authors/ryan-moalemi-photo.jpg'
BYLINE_PHOTO = '/images/authors/ryan-moalemi-photo-byline.jpg'


def versioned_image(path: str) -> str:
    """Same ?v= cache bust portraits use, so a replaced photo is not stuck in cache."""
    file = Path(__file__).resolve().parents[1] / path.lstrip('/')
    if not file.is_file():
        return path
    digest = hashlib.sha256(file.read_bytes()).hexdigest()[:12]
    return f'{path}?v={digest}'


AUTHOR_IMAGE = versioned_image(AUTHOR_PHOTO)
AUTHOR_IMAGE_URL = BASE + AUTHOR_IMAGE
BYLINE_IMAGE = versioned_image(BYLINE_PHOTO)
# One line for Person JSON-LD. Visible bio paragraphs stay separate.
AUTHOR_DESCRIPTION = (
    'Ryan Moalemi has been writing internet content since 2001. '
    'He found the WNBA in 2026 because of Angel Reese and covers the league for Full Court Buckets.'
)
AUTHOR_META = (
    'Ryan Moalemi has been writing internet content since 2001. '
    'He covers the WNBA for Full Court Buckets.'
)
AUTHOR_BIO = (
    (
        "Hi, I'm Ryan Moalemi. I've been writing internet content since 2001. "
        'I found the WNBA in 2026 because of Angel Reese, she is the reason I fell in love with the league. '
        'Now I enjoy watching a number of other players and teams. '
        "I support the WNBA and the positive effect the league is having on women's sports."
    ),
    (
        'My goal for Full Court Buckets is to cover the WNBA thoughtfully and fairly, '
        'with genuine respect for every player in the league. '
        'I hope our coverage highlights their talent, gives their stories the attention they deserve, '
        'and inspires more people to become fans.'
    ),
)
GENERATED_LISTING_PAGES = {'news/index.html', AUTHOR_PAGE}
BYLINE_HTML = (
    '<a class="byline" href="/authors/ryan-moalemi/">'
    f'<picture><source srcset="/images/authors/ryan-moalemi-photo-byline.webp" type="image/webp">'
    f'<img src="{BYLINE_IMAGE}" alt="Ryan Moalemi" width="80" height="80" decoding="async" loading="lazy"></picture>'
    '<span>By Ryan Moalemi</span></a>'
)
BYLINE_CSS = (
    '.article .byline{display:flex;align-items:center;gap:10px;margin:0 0 18px;color:#d4d0ca;'
    'font:600 15px/1.3 Inter,system-ui,sans-serif;letter-spacing:0;text-transform:none;text-decoration:none}'
    '.article .byline img{width:40px;height:40px;max-width:40px;border-radius:50%;object-fit:cover;'
    'border:1px solid var(--line,#2b2930);flex:0 0 40px;background:#111}'
    '.article .byline:hover{color:var(--orange,#ff9800)}'
    '@media(max-width:900px){.article .byline{font-size:14px;margin-bottom:16px}}'
)
BYLINE_RE = re.compile(r'<a class="byline" href="/authors/ryan-moalemi/">.*?</a>', re.S)
# Headline, then the byline and date, then the lead photo and credit, then the hook.
# The photo is the article column, never the viewport, at a fixed 16:9 crop.
# The previous block broke the photo out to 100vw. Replace it wherever it is still inline.
OLD_LEAD_CSS = (
    '.article figure.lead-photo{margin:0 0 14px}'
    '.article figure.lead-photo img{width:100%;height:auto}'
    '.article figure.lead-photo figcaption{margin-top:6px;font-size:12px;line-height:1.4}'
    '.article .byline-row{display:flex;flex-wrap:wrap;align-items:center;gap:8px 14px;margin:0 0 16px}'
    '.article .byline-row .byline{margin:0}'
    '.article .article-date{color:#a29f99;font:600 13px/1.3 Inter,system-ui,sans-serif}'
    '@media(max-width:900px){'
    '.article-wrap{padding-top:8px}'
    '.article{padding-top:12px}'
    '.article h1{font-size:28px;line-height:1.05;letter-spacing:-.5px;margin-bottom:8px}'
    '.meta-row{margin-bottom:8px}'
    '.breadcrumbs{margin-bottom:8px}'
    '.article figure.lead-photo{width:100vw;max-width:100vw;margin-left:calc(50% - 50vw);'
    'margin-right:calc(50% - 50vw)}'
    '.article figure.lead-photo figcaption{padding:0 16px}'
    '.article .byline-row .byline{margin-bottom:0;font-size:14px}'
    '}'
)
NEWS_LEAD_CSS = Path(__file__).resolve().parents[1] / 'assets' / 'news-lead.css'


def load_lead_css() -> str:
    """The shared lead stylesheet, minified so it can sit in the article <style> block."""
    text = NEWS_LEAD_CSS.read_text(encoding='utf-8')
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\s*([{}:;,])\s*', r'\1', text)
    return text.strip()


LEAD_CSS = load_lead_css()
LEAD_FIGURE_RE = re.compile(r'<figure\b[^>]*>.*?</figure>', re.S)
BYLINE_ROW_RE = re.compile(r'<div class="byline-row">.*?</div>', re.S)
ARTICLE_DATE_RE = re.compile(r'<time class="article-date"[^>]*>.*?</time>', re.S)
_DATE_MONTHS = (
    'January|February|March|April|May|June|July|August|September|October|November|December'
)
META_DATE_RE = re.compile(
    r'<span>((?:Published\s+)?(?:' + _DATE_MONTHS + r')\s+\d{1,2},\s+\d{4})</span>'
)
META_ROW_RE = re.compile(r'<div class="meta-row">.*?</div>', re.S)
HOW_PAGE = '/how-we-make-full-court-buckets/'
HOW_MADE_CSS = (
    '.article .how-made{margin:22px 0 0;color:#a29f99;font-size:13px;line-height:1.55}'
    '.article .how-made a{color:#d4d0ca;text-decoration:underline}'
)
HOW_MADE_RE = re.compile(r'<p class="how-made">.*?</p>', re.S)
# Older post that covers the same game as the kept recap. Both URLs redirect there.
RETIRED_NEWS = {
    'liberty-lynx-game-1-ionescu-stewart': '/news/liberty-lynx-game-1-full-recap/',
}
AUTHOR_META_RE = re.compile(r'<meta\b[^>]*\bname="author"[^>]*>', re.I)
JSONLD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
CANONICAL_RE = re.compile(r'<link\b[^>]*rel="canonical"[^>]*>', re.I)
OG_URL_RE = re.compile(r'<meta\b[^>]*property="og:url"[^>]*>', re.I)


def article_slug(article: dict) -> str:
    slug = str((article or {}).get('slug') or '').strip().strip('/')
    if not ARTICLE_SLUG.fullmatch(slug):
        raise ValueError(f'Article slug is not a single path segment: {slug!r}')
    return slug


def article_href(article: dict) -> str:
    """Public path for a post. The slug is unchanged; the category is always /news/."""
    return f'/news/{article_slug(article)}/'


def article_absolute(article: dict) -> str:
    return BASE + article_href(article)


def _slot_for_slug(root: Path, team_slug: str) -> dict:
    path = root / 'data' / 'wnba' / 'players-index.json'
    if not path.is_file():
        return {'slug': team_slug, 'full_name': '', 'name': ''}
    index = json.loads(path.read_text(encoding='utf-8'))
    for slot in catalog_from_index(index)['by_id'].values():
        if slot['slug'] == team_slug:
            return slot
    return {'slug': team_slug, 'full_name': '', 'name': ''}


def article_mentions_team(article: dict, slot: dict) -> bool:
    """True when articles.json names this team in teams, the title, or the description."""
    if slot.get('slug') and slot['slug'] in (article.get('teams') or []):
        return True
    blob = f"{article.get('title') or ''} {article.get('description') or ''}"
    names = []
    for key in ('full_name', 'name'):
        text = str(slot.get(key) or '').strip()
        if text and text not in names:
            names.append(text)
    for name in names:
        if re.search(rf'(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])', blob):
            return True
    return False


def team_news_html(root: Path, team_slug: str) -> str:
    """Newest stories that mention this team. Empty when none do. Same-tab links."""
    slot = _slot_for_slug(root, team_slug)
    items = []
    for article in _ordered_articles(load_articles(root)):
        if not article_mentions_team(article, slot):
            continue
        title = str(article.get('title') or '').strip()
        if not title:
            continue
        image = str(article.get('image') or '').strip()
        thumb = ''
        if image:
            alt = str(article.get('imageAlt') or title)
            thumb = (
                f'<img src="{esc(image)}" alt="{esc(alt)}"{_image_dims(article)}'
                f' decoding="async" loading="lazy"{focal_style(article)}>'
            )
        items.append(
            '<li><a class="team-news-item" href="' + esc(article_href(article)) + '">'
            + thumb + '<span>' + esc(title) + '</span></a></li>'
        )
    if not items:
        return ''
    return (
        '<section class="section" id="team-news"><p class="eyebrow">News</p><h2>Latest stories</h2>'
        '<ul class="teammate-list">' + ''.join(items) + '</ul></section>'
    )


def is_redirect_html(text: str) -> bool:
    lowered = text.lower()
    return 'http-equiv="refresh"' in lowered or "http-equiv='refresh'" in lowered


def ensure_article_urls(root: Path) -> list:
    """Store /news/<slug>/ on every articles.json entry. The slug itself stays put."""
    path = root / 'articles.json'
    articles = load_articles(root)
    normalized = []
    changed = False
    for article in articles:
        href = article_href(article)
        ordered = {}
        for key in ('slug', 'url', 'title', 'description', 'category', 'date', 'image', 'imageAlt'):
            if key == 'url':
                ordered['url'] = href
            elif key in article:
                ordered[key] = article[key]
        for key, value in article.items():
            if key not in ordered:
                ordered[key] = value
        if ordered != article:
            changed = True
        normalized.append(ordered)
    if changed and path.is_file():
        path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return normalized


def _ordered_articles(articles: list) -> list:
    return sorted(articles, key=lambda article: article.get('date') or '', reverse=True)


def _breadcrumb_data(crumbs: list[tuple[str, str]]) -> dict:
    return {
        '@context': 'https://schema.org',
        '@type': 'BreadcrumbList',
        'itemListElement': [
            {'@type': 'ListItem', 'position': index, 'name': name, 'item': item}
            for index, (name, item) in enumerate(crumbs, 1)
        ],
    }


def _has_type(data, name: str) -> bool:
    if isinstance(data, dict):
        kind = data.get('@type')
        if kind == name or (isinstance(kind, list) and name in kind):
            return True
        return any(_has_type(value, name) for value in data.values())
    if isinstance(data, list):
        return any(_has_type(item, name) for item in data)
    return False


def _article_node(data):
    if isinstance(data, dict):
        kind = data.get('@type')
        names = kind if isinstance(kind, list) else [kind]
        if any(name in ('NewsArticle', 'Article', 'BlogPosting') for name in names):
            return data
        for value in data.values():
            found = _article_node(value)
            if found is not None:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _article_node(item)
            if found is not None:
                return found
    return None


def _jsonld(data: dict) -> str:
    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + '</script>'


def _stamp_org_same_as(node) -> bool:
    """Add TikTok to the site Organization node. Leave Person profiles alone."""
    changed = False
    if isinstance(node, dict):
        kind = node.get('@type')
        names = kind if isinstance(kind, list) else [kind]
        if 'Organization' in names and node.get('@id') == BASE + '/#organization':
            current = node.get('sameAs')
            if current is None:
                node['sameAs'] = [TIKTOK_URL]
                changed = True
            elif isinstance(current, str):
                if current != TIKTOK_URL:
                    node['sameAs'] = [current, TIKTOK_URL]
                    changed = True
            elif isinstance(current, list) and TIKTOK_URL not in current:
                current.append(TIKTOK_URL)
                changed = True
        for value in node.values():
            if _stamp_org_same_as(value):
                changed = True
    elif isinstance(node, list):
        for item in node:
            if _stamp_org_same_as(item):
                changed = True
    return changed


def ensure_site_organization_same_as(html: str) -> str:
    """Put the official TikTok URL on the homepage Organization block."""
    def sub(match: re.Match) -> str:
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            return match.group(0)
        if not _stamp_org_same_as(data):
            return match.group(0)
        payload = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
        return '<script type="application/ld+json">' + payload + '</script>'

    return JSONLD_RE.sub(sub, html)


def cap_meta(text, limit: int = 155) -> str:
    """Trim a meta description at a word boundary."""
    cleaned = re.sub(r'\s+', ' ', '' if text is None else str(text)).strip()
    if len(cleaned) <= limit:
        return cleaned
    clipped = cleaned[:limit + 1]
    if ' ' in clipped:
        clipped = clipped.rsplit(' ', 1)[0]
    return clipped.rstrip(' ,;:') or cleaned[:limit].rstrip()


def _set_meta_content(html: str, pattern: re.Pattern, content: str) -> str:
    safe = esc(content)

    def sub(match: re.Match) -> str:
        tag = match.group(0)
        if re.search(r'content="', tag, re.I):
            return re.sub(r'content="[^"]*"', f'content="{safe}"', tag, count=1)
        return tag

    return pattern.sub(sub, html, count=1)


DESC_NAME_RE = re.compile(r'<meta\b[^>]*\bname="description"[^>]*>', re.I)
OG_DESC_RE = re.compile(r'<meta\b[^>]*\bproperty="og:description"[^>]*>', re.I)
TW_DESC_RE = re.compile(r'<meta\b[^>]*\bname="twitter:description"[^>]*>', re.I)


def _upsert_meta(html: str, absolute: str, description: str | None = None) -> str:
    canonical = f'<link rel="canonical" href="{esc(absolute)}">'
    og_url = f'<meta property="og:url" content="{esc(absolute)}">'
    if CANONICAL_RE.search(html):
        html = CANONICAL_RE.sub(canonical, html, count=1)
    elif '</head>' in html:
        html = html.replace('</head>', canonical + '</head>', 1)
    if OG_URL_RE.search(html):
        html = OG_URL_RE.sub(og_url, html, count=1)
    elif '</head>' in html:
        html = html.replace('</head>', og_url + '</head>', 1)
    if 'property="og:type"' not in html and '</head>' in html:
        html = html.replace('</head>', '<meta property="og:type" content="article"></head>', 1)
    if description:
        trimmed = cap_meta(description, 160)
        html = _set_meta_content(html, DESC_NAME_RE, trimmed)
        html = _set_meta_content(html, OG_DESC_RE, trimmed)
        html = _set_meta_content(html, TW_DESC_RE, trimmed)
    return html


def _upsert_article_schema(html: str, article: dict, absolute: str) -> str:
    found = False

    def sub(match: re.Match) -> str:
        nonlocal found
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            return match.group(0)
        if _has_type(data, 'BreadcrumbList'):
            return ''
        node = _article_node(data)
        if node is None:
            return match.group(0)
        found = True
        node['url'] = absolute
        node['mainEntityOfPage'] = {'@type': 'WebPage', '@id': absolute}
        node['author'] = article_author()
        description = cap_meta(article.get('description') or '', 160)
        if description:
            node['description'] = description
        modified = str(article.get('dateModified') or '').strip()
        if modified:
            node['dateModified'] = modified
        return _jsonld(data)

    html = JSONLD_RE.sub(sub, html)
    if not found:
        image = str(article.get('image') or '')
        if image.startswith('/'):
            image = BASE + image
        created = {
            '@context': 'https://schema.org',
            '@type': 'NewsArticle',
            'headline': article.get('title') or '',
            'description': cap_meta(article.get('description') or '', 160),
            'url': absolute,
            'mainEntityOfPage': {'@type': 'WebPage', '@id': absolute},
            'datePublished': article.get('date') or '',
            'author': article_author(),
            'publisher': {
                '@type': 'Organization',
                'name': 'Full Court Buckets',
                'logo': {'@type': 'ImageObject', 'url': BASE + '/logo.png'},
            },
        }
        modified = str(article.get('dateModified') or '').strip()
        if modified:
            created['dateModified'] = modified
        if image:
            created['image'] = [image]
        html = html.replace('</head>', _jsonld(created) + '</head>', 1)
    crumbs = _breadcrumb_data([
        ('Home', BASE + '/'),
        ('News', BASE + NEWS_HUB),
        (str(article.get('title') or ''), absolute),
    ])
    return html.replace('</head>', _jsonld(crumbs) + '</head>', 1)


def _visible_breadcrumb(title: str) -> str:
    return (
        '<nav class="breadcrumbs" aria-label="Breadcrumb">'
        '<a href="/">Home</a>'
        '<span aria-hidden="true">/</span>'
        f'<a href="{NEWS_HUB}">News</a>'
        '<span aria-hidden="true">/</span>'
        f'<span>{esc(title)}</span></nav>'
    )


def _insert_visible_breadcrumb(html: str, title: str) -> str:
    crumb = _visible_breadcrumb(title)
    html = re.sub(r'<nav class="breadcrumbs" aria-label="Breadcrumb">.*?</nav>', '', html, count=1, flags=re.S)
    marker = '<article'
    index = html.find(marker)
    if index == -1:
        return html
    if '.breadcrumbs{' not in html:
        css = '.breadcrumbs{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 16px;color:#a29f99;font-size:13px;font-weight:600}.breadcrumbs a{color:#d4d0ca;text-decoration:underline}'
        if '</style>' in html:
            html = html.replace('</style>', css + '</style>', 1)
        elif '</head>' in html:
            html = html.replace('</head>', '<style>' + css + '</style></head>', 1)
        index = html.find(marker)
    return html[:index] + crumb + html[index:]


def rewrite_legacy_article_urls(text: str, articles: list) -> str:
    """Point root post URLs at /news/<slug>/. Image folders that contain the slug stay put."""
    for article in articles:
        try:
            slug = article_slug(article)
        except ValueError:
            continue
        new = article_href(article)
        old_abs = f'{BASE}/{slug}/'
        new_abs = BASE + new
        text = text.replace(old_abs, new_abs)
        text = text.replace(f'href="/{slug}/"', f'href="{new}"')
        text = text.replace(f"href='/{slug}/'", f"href='{new}'")
    return text.replace('href="/#latest">News', 'href="/news/">News')


def read_article_source(root: Path, slug: str) -> str:
    candidates = (root / 'news' / slug / 'index.html', root / slug / 'index.html')
    for path in candidates:
        if not path.is_file():
            continue
        text = path.read_text(encoding='utf-8')
        if is_redirect_html(text):
            continue
        return text
    raise FileNotFoundError(f'No article HTML for {slug}')


def box_score_html(game_id: str) -> str:
    """Game source line: our own play-by-play/game page only, never ESPN (Ryan's rule)."""
    import strip_espn_stats
    url = strip_espn_stats.game_pages().get(str(game_id).strip())
    return f'<p class="box-score">Play-by-play: <a href="{esc(url)}">Full Court Buckets game page</a>.</p>' if url else ''


def ensure_box_score(html_text: str, article: dict) -> str:
    import strip_espn_stats
    html_text = strip_espn_stats.clean(html_text)
    game_id = str((article or {}).get('gameId') or (article or {}).get('espnGameId') or '').strip()
    snippet = box_score_html(game_id) if game_id.isdigit() else ''
    if not snippet or snippet in html_text:
        return html_text
    if '<p class="how-made">' in html_text:
        # A game page published after the story: its link still belongs above the disclosure.
        return html_text.replace('<p class="how-made">', snippet + '<p class="how-made">', 1)
    if '<p class="brand-sign">' in html_text:
        return html_text.replace('<p class="brand-sign">', snippet + '<p class="brand-sign">', 1)
    if '</article>' in html_text:
        return html_text.replace('</article>', snippet + '</article>', 1)
    return html_text


def article_author() -> dict:
    """Person credited on every news post. Publisher stays the organization."""
    return {'@type': 'Person', 'name': AUTHOR_NAME, 'url': AUTHOR_URL}


def author_person() -> dict:
    """Profile markup. jobTitle stays the generic Editor label."""
    return {
        '@context': 'https://schema.org',
        '@type': 'Person',
        'name': AUTHOR_NAME,
        'url': AUTHOR_URL,
        'image': AUTHOR_IMAGE_URL,
        'jobTitle': 'Editor',
        'description': AUTHOR_DESCRIPTION,
        'worksFor': {
            '@type': 'Organization',
            'name': 'Full Court Buckets',
            'url': BASE + '/',
        },
    }


def ensure_author_meta(html: str) -> str:
    tag = f'<meta name="author" content="{esc(AUTHOR_NAME)}">'
    if AUTHOR_META_RE.search(html):
        return AUTHOR_META_RE.sub(tag, html, count=1)
    if '</head>' in html:
        return html.replace('</head>', tag + '</head>', 1)
    return html + tag


def _figure_classes(figure: str) -> set[str]:
    match = re.match(r'<figure\b([^>]*)>', figure, re.I)
    if not match:
        return set()
    classes = re.search(r'class="([^"]*)"', match.group(1))
    return set(classes.group(1).split()) if classes else set()


def _add_figure_class(figure: str, name: str) -> str:
    """Add one class on the opening tag. An empty class attribute is replaced."""
    if name in _figure_classes(figure):
        return figure

    def repl(match: re.Match) -> str:
        existing = match.group(2).strip()
        merged = f'{existing} {name}'.strip() if existing else name
        return f'{match.group(1)}{merged}"'

    updated, count = re.subn(
        r'(<figure\b[^>]*\bclass=")([^"]*)"',
        repl,
        figure,
        count=1,
        flags=re.I,
    )
    if count:
        return updated
    return re.sub(r'<figure\b', f'<figure class="{name}"', figure, count=1, flags=re.I)


# Screenshots and charts keep their pixels. card photos in a list stay on the card rule.
NO_CROP_CLASSES = frozenset({'no-crop', 'screenshot', 'chart', 'stat-board'})
_FIGURE_OPEN_RE = re.compile(r'<figure\b[^>]*>', re.I)
_DROP_FIGURE_STYLE = frozenset({'max-width', 'width', 'margin', 'margin-left', 'margin-right'})


def _is_lead_figure(figure: str) -> bool:
    """The story photo, not a chart or a later card in a list."""
    if '<img' not in figure.lower():
        return False
    classes = _figure_classes(figure)
    if 'chart' in classes:
        return False
    return 'lead' in classes or 'lead-photo' in classes or 'fetchpriority="high"' in figure


_FOCAL_WORD = r'(?:left|center|right|top|bottom|\d{1,3}(?:\.\d+)?%)'
_FOCAL_RE = re.compile(rf'^{_FOCAL_WORD}(?:\s+{_FOCAL_WORD})?$', re.I)
LEAD_SIZES = '(max-width: 900px) calc(94vw - 40px), 842px'
# object-fit: cover defaults to the center and cuts off heads in portrait photos.
# 20% keeps the face in frame when a post has no measured focal point.
DEFAULT_IMAGE_FOCAL = 'center 20%'


def lead_focal(article: dict | None) -> str:
    """Per-article object-position. The default keeps faces in the top of a portrait."""
    raw = re.sub(r'\s+', ' ', str((article or {}).get('imageFocal') or '').strip())
    if raw and _FOCAL_RE.fullmatch(raw):
        return raw.lower()
    return DEFAULT_IMAGE_FOCAL


def focal_style(article: dict | None) -> str:
    """Inline object-position so a card crop uses this post's focal point."""
    return f' style="object-position:{esc(lead_focal(article))}"'


def _upsert_attr(tag: str, name: str, value: str) -> str:
    pattern = re.compile(rf'\b{name}=("|\')(.*?)\1', re.I)
    replacement = f'{name}="{value}"'
    if pattern.search(tag):
        return pattern.sub(replacement, tag, count=1)
    return tag[:-1] + f' {replacement}' + tag[-1]


def _upsert_style_prop(tag: str, prop: str, value: str) -> str:
    decl = f'{prop}:{value}'
    style = re.search(r'\bstyle=("|\')(.*?)\1', tag)
    if style is None:
        return tag[:-1] + f' style="{decl}"' + tag[-1]
    body = style.group(2).strip()
    if re.search(rf'(?:^|;)\s*{re.escape(prop)}\s*:', body):
        body = re.sub(rf'{re.escape(prop)}\s*:\s*[^;]+', decl, body)
    else:
        body = body.rstrip(';') + ';' + decl
    quote = style.group(1)
    return tag[:style.start()] + f'style={quote}{body}{quote}' + tag[style.end():]


def _lead_asset(article: dict | None) -> tuple[str, int, int, str] | None:
    """Hero file when one has been cropped. Otherwise leave the img src alone."""
    if not article:
        return None
    hero = str(article.get('imageHero') or '').strip()
    if not hero:
        return None
    width = int(article.get('imageHeroWidth') or 1200)
    height = int(article.get('imageHeroHeight') or 675)
    two = str(article.get('imageHero2x') or '').strip()
    two_w = article.get('imageHero2xWidth')
    if two and two_w:
        srcset = f'{hero} {width}w, {two} {int(two_w)}w'
    else:
        srcset = f'{hero} {width}w'
    return hero, width, height, srcset


def _mark_lead_figure(figure: str, article: dict | None = None) -> str:
    """Column-width 16:9 lead. Keep width and height. Hero is eager and high priority."""
    classes = _figure_classes(figure)
    if 'lead-photo' not in classes:
        if classes:
            figure = re.sub(
                r'(<figure\b[^>]*class=")',
                r'\1lead-photo ',
                figure,
                count=1,
            )
        else:
            figure = figure.replace('<figure', '<figure class="lead-photo"', 1)
    asset = _lead_asset(article)
    focal = lead_focal(article)

    def _source(match: re.Match) -> str:
        tag = match.group(0)
        if asset is None:
            return tag
        _src, _width, _height, srcset = asset
        tag = _upsert_attr(tag, 'srcset', srcset)
        tag = _upsert_attr(tag, 'sizes', LEAD_SIZES)
        if 'type=' not in tag.lower():
            tag = _upsert_attr(tag, 'type', 'image/webp')
        return tag

    figure = re.sub(r'<source\b[^>]*>', _source, figure, count=1)

    def _hero(img: re.Match) -> str:
        tag = re.sub(r'\sloading=(["\']).*?\1', '', img.group(0))
        if 'fetchpriority=' not in tag.lower():
            tag = tag.replace('<img', '<img fetchpriority="high"', 1)
        tag = _upsert_style_prop(tag, 'object-position', focal)
        if asset is not None:
            src, width, height, srcset = asset
            tag = _upsert_attr(tag, 'src', src)
            tag = _upsert_attr(tag, 'srcset', srcset)
            tag = _upsert_attr(tag, 'sizes', LEAD_SIZES)
            tag = _upsert_attr(tag, 'width', str(width))
            tag = _upsert_attr(tag, 'height', str(height))
        return tag

    return re.sub(r'<img\b[^>]*>', _hero, figure, count=1)


def _img_focal(img: str, focals: dict[str, str]) -> str:
    """Per-image object-position. A named override wins, then a value already on the img."""
    src = re.search(r'\bsrc="([^"]+)"', img)
    name = src.group(1).rsplit('/', 1)[-1] if src else ''
    named = re.sub(r'\s+', ' ', str(focals.get(name) or '').strip())
    if named and _FOCAL_RE.fullmatch(named):
        return named.lower()
    existing = re.search(r'object-position\s*:\s*([^;"]+)', img)
    if existing:
        raw = re.sub(r'\s+', ' ', existing.group(1).strip())
        if _FOCAL_RE.fullmatch(raw):
            return raw.lower()
    return DEFAULT_IMAGE_FOCAL


def _set_img_focal(figure: str, focal: str) -> str:
    def repl(match: re.Match) -> str:
        return _upsert_style_prop(match.group(0), 'object-position', focal)

    return re.sub(r'<img\b[^>]*>', repl, figure, count=1)


def _relax_body_figure(figure: str) -> str:
    """Drop a narrow max-width so the 16:9 photo fills the column like the lead."""
    open_tag = _FIGURE_OPEN_RE.match(figure)
    if open_tag is None:
        return figure
    tag = open_tag.group(0)
    style = re.search(r'\bstyle=("|\')(.*?)\1', tag)
    if style is None:
        return figure
    kept = []
    for decl in style.group(2).split(';'):
        decl = decl.strip()
        if not decl or ':' not in decl:
            continue
        prop = decl.split(':', 1)[0].strip().lower()
        if prop in _DROP_FIGURE_STYLE:
            continue
        kept.append(decl)
    if kept:
        replacement = f'style="{";".join(kept)}"'
        tag = tag[:style.start()] + replacement + tag[style.end():]
    else:
        tag = tag[:style.start()] + tag[style.end():]
        tag = re.sub(r'\s{2,}', ' ', tag)
        tag = tag.replace(' >', '>')
    return tag + figure[open_tag.end():]


def apply_body_photos(html: str, focals: dict[str, str] | None = None,
                      no_crop_files: set[str] | None = None) -> str:
    """16:9 body photos with a focal point. Screenshots and charts are not cropped.

    Lead photos and list-article card photos are left alone. A figure marked
    screenshot, chart, stat-board, or no-crop keeps its pixels and only gets
    the shared no-crop class. no_crop_files names files that are screenshots
    even when the figure has no class yet. focals maps a filename to an
    object-position; an object-position already on the img is kept otherwise.
    """
    focals = focals or {}
    names = no_crop_files or set()

    def repl(match: re.Match) -> str:
        figure = match.group(0)
        classes = _figure_classes(figure)
        if 'lead-photo' in classes or 'card' in classes:
            return figure
        img = re.search(r'<img\b[^>]*>', figure, re.I)
        src_name = ''
        if img:
            src = re.search(r'\bsrc="([^"]+)"', img.group(0))
            src_name = src.group(1).rsplit('/', 1)[-1] if src else ''
        if src_name in names or classes & NO_CROP_CLASSES:
            figure = _add_figure_class(figure, 'no-crop')
            if src_name in names:
                figure = _add_figure_class(figure, 'screenshot')
            return figure
        if img is None:
            return figure
        figure = _add_figure_class(figure, 'body-photo')
        figure = _relax_body_figure(figure)
        img = re.search(r'<img\b[^>]*>', figure, re.I)
        return _set_img_focal(figure, _img_focal(img.group(0), focals))

    return LEAD_FIGURE_RE.sub(repl, html)


# End of the inlined lead block. install_lead_css uses it to refresh an older copy.
_LEAD_BLOCK_END = '.article .byline-row .byline{margin-bottom:0;font-size:14px;}}'


def install_lead_css(html: str) -> str:
    """Put the shared 16:9 column rules on the page. Drop the old full-bleed block."""
    if OLD_LEAD_CSS in html:
        html = html.replace(OLD_LEAD_CSS, LEAD_CSS)
    start = html.find('.article figure.lead-photo{')
    if start >= 0:
        end = html.find(_LEAD_BLOCK_END, start)
        if end > start:
            end += len(_LEAD_BLOCK_END)
            if html[start:end] != LEAD_CSS:
                return html[:start] + LEAD_CSS + html[end:]
            return html
    if '</style>' in html:
        return html.replace('</style>', LEAD_CSS + '</style>', 1)
    if '</head>' in html:
        return html.replace('</head>', '<style>' + LEAD_CSS + '</style></head>', 1)
    return html


def _article_date_tag(text: str) -> str:
    shown = text.strip()
    bare = re.sub(r'^Published\s+', '', shown)
    try:
        parsed = dt.datetime.strptime(bare, '%B %d, %Y')
        iso = f' datetime="{parsed.strftime("%Y-%m-%d")}"'
    except ValueError:
        iso = ''
    return f'<time class="article-date"{iso}>{html.escape(shown)}</time>'


def _pull_article_date(article: str) -> tuple[str, str]:
    """Take the date off the kicker so it sits with the byline. Keep the category."""
    existing = ARTICLE_DATE_RE.search(article)
    kept = ''
    if existing:
        kept = re.sub(r'<[^>]+>', '', existing.group(0))
        article = ARTICLE_DATE_RE.sub('', article)
    meta = META_ROW_RE.search(article)
    if meta is None:
        return article, kept
    date = META_DATE_RE.search(meta.group(0))
    if date is None:
        return article, kept
    inner = meta.group(0)[len('<div class="meta-row">'):-len('</div>')]
    found = META_DATE_RE.search(inner)
    inner = inner[:found.start()] + inner[found.end():]
    inner = re.sub(r'(?:<span class="divider"></span>)+', '<span class="divider"></span>', inner)
    inner = re.sub(r'^(?:<span class="divider"></span>)+', '', inner)
    inner = re.sub(r'(?:<span class="divider"></span>)+$', '', inner)
    article = article[:meta.start()] + f'<div class="meta-row">{inner}</div>' + article[meta.end():]
    return article, date.group(1)


QUICK_CITE_RE = re.compile(r'<aside class="fcb-quick-cite".*?</aside>', re.S)
LEAD_PHOTO_RE = re.compile(r'<figure\b[^>]*\blead-photo\b[^>]*>.*?</figure>', re.S)
# An archive note stays with the byline, above the photo.
_ARCHIVE_NOTE_RE = re.compile(
    r'\s*<p>This preview was published before the games?\..*?</p>',
    re.S,
)


def _splice_block(html: str, at: int, block: str) -> str:
    """Insert a block on its own line without stacking blank lines on repeat."""
    head = html[:at].rstrip('\n')
    tail = html[at:].lstrip('\n')
    parts = [part for part in (head, block, tail) if part]
    return '\n'.join(parts)


# This slug is the attendance database. Nightly assembly must not rebuild that page.
# Data-first articles: the data table sits directly under the byline, so they carry no lead photo.
DATA_FIRST_ARTICLE_SLUGS = frozenset({'valkyries-dream-finals-game-4-first-half'})
FROZEN_ARTICLE_SLUGS = frozenset({'2026-wnba-finals-ratings-tracker'}) | DATA_FIRST_ARTICLE_SLUGS


def _is_ratings_tracker_page(html: str, article: dict | None) -> bool:
    """Ratings lead order applies only while the page is still the ratings tracker.

    The attendance database keeps this slug. Its markup must not be reordered.
    """
    if 'fcb-attendance' in html:
        return False
    if isinstance(article, dict) and article.get('slug') == '2026-wnba-finals-ratings-tracker':
        return True
    return 'class="fcb-tracker-update"' in html and 'id="finals-ratings-tracker"' in html


def _pull_block(pattern: re.Pattern, text: str) -> tuple[str, str]:
    match = pattern.search(text)
    if not match:
        return '', text
    return match.group(0).strip(), text[:match.start()] + text[match.end():]


TRACKER_MATCHUP_RE = re.compile(r'<figure\b[^>]*\btracker-matchup\b[^>]*>.*?</figure>', re.S)
TRACKER_STAT_RE = re.compile(r'<p class="tracker-stat">.*?</p>', re.S)
TRACKER_NOTE_RE = re.compile(r'<p class="tracker-note">.*?</p>', re.S)
TRACKER_TOOLS_RE = re.compile(r'<nav class="tracker-tools".*?</nav>', re.S)
TRACKER_AVERAGES_RE = re.compile(r'<section class="tracker-averages".*?</section>', re.S)
TRACKER_SHEET_BLOCK_RE = re.compile(
    r'<section class="tracker-sheet-block"[^>]*>.*?</section>',
    re.S,
)
TRACKER_TABLE_RE = re.compile(
    r'<div class="fcb-table-wrap tracker-sheet"[^>]*>.*?</table></div>',
    re.S,
)
TRACKER_CALLOUT_RE = re.compile(r'<aside class="fcb-tracker-update".*?</aside>', re.S)
_OLD_RATINGS_SHEET_RE = re.compile(
    r'<div class="fcb-table-wrap"[^>]*>.*?>Overnight rating<.*?</table></div>',
    re.S,
)

TRACKER_COMPACT_CSS = (
    '<style id="tracker-compact-css">'
    '.article .tracker-stat{margin:0 0 8px;color:#f5f3ef;font-size:17px;line-height:1.35}'
    '.article p.tracker-note,.article p.tracker-credit{margin:4px 0 10px;color:#a5a19b;font-size:12px;line-height:1.4}'
    '.article .tracker-tools{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 12px}'
    '.article .tracker-tools a,.article .tracker-tools button{appearance:none;margin:0;font:600 13px/1 Inter,system-ui,sans-serif;color:#f5f3ef;background:#141418;border:1px solid #2b2930;border-radius:3px;padding:6px 10px;cursor:pointer;text-decoration:none}'
    '.article .tracker-averages{margin:0 0 14px}'
    '.article .tracker-averages h2{margin:0 0 2px;font:800 15px/1.2 Barlow,sans-serif;letter-spacing:0}'
    '.article .tracker-averages p{margin:0;font-size:15px;line-height:1.35}'
    '.article h2.section-title{margin:16px 0 8px;font-size:22px;line-height:1.15;letter-spacing:-.3px}'
    '.article table.tracker-compact{width:max-content;min-width:100%;margin:0;font-size:14px;line-height:1.15}'
    '.article table.tracker-compact th,.article table.tracker-compact td{padding:4px 8px;white-space:nowrap;vertical-align:middle}'
    '.article .fcb-table-wrap.tracker-sheet{overflow-x:auto;margin:0 0 4px}'
    '.article .tracker-sheet-block{margin:0 0 8px}'
    '.article .tracker-sheet-block h2.section-title{margin:2px 0 6px}'
    '</style>'
)
TRACKER_COMPACT_JS = (
    '<script id="tracker-compact-js">'
    "document.querySelectorAll('.fcb-tracker-cite').forEach(function(button){"
    "button.addEventListener('click',function(){"
    "var text=button.getAttribute('data-citation')||'';"
    "var label=button.textContent;"
    "var done=function(){button.textContent='Copied';setTimeout(function(){button.textContent=label;},1600);};"
    "if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(text).then(done,done);return;}"
    "done();});});"
    '</script>'
)


def install_tracker_compact(html: str) -> str:
    """Page-local compact table rules. Shared citation.css stays as other pages use it."""
    needle = '<link rel="stylesheet" href="/assets/citation.css">'
    if 'id="tracker-compact-css"' not in html and needle in html:
        html = html.replace(needle, needle + TRACKER_COMPACT_CSS, 1)
    if 'id="tracker-compact-js"' not in html and '</body>' in html:
        html = html.replace('</body>', TRACKER_COMPACT_JS + '</body>', 1)
    return html


def _drop_old_ratings_sheet(article: str) -> str:
    """Remove a leftover nine-column sheet and a heading that is no longer the compact label."""
    article = re.sub(
        r'<h2\b[^>]*\bid="finals-ratings-tracker"[^>]*>.*?</h2>',
        '',
        article,
        count=1,
        flags=re.S,
    )
    return _OLD_RATINGS_SHEET_RE.sub('', article, count=1)


def order_ratings_tracker(html: str) -> str:
    """Fast facts under the byline, then Cite / CSV / Embed, then the compact sheet.

    A released Finals audience is the tracker-stat line. When that line is present,
    it and the game table move above the fast facts. A pending line stays off the page.
    The update callout stays with the sources, just before the how-made line.
    A stray lead photo or the old matchup figure is removed. The tall nine-column
    sheet is removed once the compact table is on the page.
    """
    start = html.find('<article')
    end = html.rfind('</article>')
    if start < 0 or end < 0:
        return install_tracker_compact(html)
    article = LEAD_PHOTO_RE.sub('', html[start:end])
    article = TRACKER_MATCHUP_RE.sub('', article)
    _lead, article = _pull_block(re.compile(r'<p class="lead">.*?</p>', re.S), article)
    stat, article = _pull_block(TRACKER_STAT_RE, article)
    if stat and 'ratings pending' in stat:
        stat = ''
    sheet, article = _pull_block(TRACKER_SHEET_BLOCK_RE, article)
    if sheet:
        article = _drop_old_ratings_sheet(article)
    else:
        table, article = _pull_block(TRACKER_TABLE_RE, article)
        if table:
            article = _drop_old_ratings_sheet(article)
        note, article = _pull_block(TRACKER_NOTE_RE, article)
        sheet = '\n'.join(part for part in (table, note) if part)
    tools, article = _pull_block(TRACKER_TOOLS_RE, article)
    averages, article = _pull_block(TRACKER_AVERAGES_RE, article)
    cite, article = _pull_block(QUICK_CITE_RE, article)
    callout, article = _pull_block(TRACKER_CALLOUT_RE, article)
    h1 = article.find('</h1>')
    if h1 < 0:
        return install_tracker_compact(html)
    row = BYLINE_ROW_RE.search(article)
    insert_at = row.end() if row and row.start() > h1 else h1 + len('</h1>')
    if stat:
        parts = (stat, sheet, cite, averages, tools)
    else:
        parts = (cite, averages, tools, sheet)
    block = '\n'.join(part for part in parts if part)
    article = article[:insert_at].rstrip() + '\n' + block + '\n' + article[insert_at:].lstrip()
    if callout:
        how = article.find('class="how-made"')
        if how > 0:
            article = article[:how].rstrip() + '\n' + callout + '\n' + article[how:]
        else:
            article = article.rstrip() + '\n' + callout + '\n'
    return install_tracker_compact(html[:start] + article + html[end:])


def place_quick_cite(html: str) -> str:
    """Fast-facts box follows the lead photo. The byline stays under the H1.

    The ratings tracker keeps its own order: fast facts, tools, then the compact sheet.
    A released audience moves the latest-game line and the sheet above the facts.
    """
    if _is_ratings_tracker_page(html, None):
        return order_ratings_tracker(html)
    match = QUICK_CITE_RE.search(html)
    if not match:
        return html
    block = match.group(0).strip()
    start, end = match.span()
    head = html[:start].rstrip('\n')
    tail = html[end:].lstrip('\n')
    html = f'{head}\n{tail}' if head and tail else head + tail
    figure = LEAD_PHOTO_RE.search(html)
    if figure:
        return _splice_block(html, figure.end(), block)
    byline = BYLINE_ROW_RE.search(html)
    if byline:
        return _splice_block(html, byline.end(), block)
    h1 = html.find('</h1>')
    if h1 < 0:
        return block + html
    return _splice_block(html, h1 + len('</h1>'), block)


_DATA_TABLE_OPEN_RE = re.compile(r'<([a-z][a-z0-9]*)\b[^>]*\bdata-fcb-data-table\b[^>]*>', re.I)


def _data_table_end(fragment: str) -> int | None:
    """Offset just past the element marked data-fcb-data-table, or None."""
    opened = _DATA_TABLE_OPEN_RE.search(fragment)
    if not opened:
        return None
    tag = opened.group(1).lower()
    token = re.compile(rf'<(/?){tag}\b[^>]*>', re.I)
    depth = 0
    for match in token.finditer(fragment, opened.start()):
        depth += -1 if match.group(1) else 1
        if depth == 0:
            return match.end()
    return None


def order_news_lead(html: str, article: dict | None = None) -> str:
    """Headline, byline and date, lead photo and credit, quick-cite, then the hook.

    The ratings tracker is the exception: fast facts follow the byline, then the journalist tools, then the compact ratings table. A released audience moves the latest-game line and that table above the facts. The matchup photo stays off the body.
    On every other article the byline sits directly under the H1 and above the hero.
    A fast-facts box, when the page has one, follows the hero. An archive note
    stays immediately under the byline, still above the photo.

    The lead matches the article column, uses a 16:9 crop, keeps width and height,
    uses fetchpriority="high", and is not lazy-loaded. imageFocal sets object-position.
    Later photos use the same 16:9 crop unless the figure is a screenshot or chart.
    """
    if _is_ratings_tracker_page(html, article):
        return order_ratings_tracker(html)
    meta = article
    start = html.find('<article')
    end = html.rfind('</article>')
    if start < 0 or end < 0:
        return html
    article = html[start:end]
    lead = None
    fallback = None
    for match in LEAD_FIGURE_RE.finditer(article):
        figure = match.group(0)
        if '<img' not in figure.lower() or _figure_classes(figure) & NO_CROP_CLASSES:
            continue
        if fallback is None:
            fallback = match
        if _is_lead_figure(figure):
            lead = match
            break
    if lead is None:
        lead = fallback
    if lead is None:
        return place_quick_cite(html)
    figure = _mark_lead_figure(lead.group(0), meta)
    article = article[:lead.start()] + article[lead.end():]
    byline = BYLINE_RE.search(article)
    byline_html = byline.group(0) if byline else ''
    if byline:
        article = article[:byline.start()] + article[byline.end():]
    article, date_text = _pull_article_date(article)
    article = BYLINE_ROW_RE.sub('', article)
    date_html = _article_date_tag(date_text) if date_text else ''
    row = ''
    if byline_html or date_html:
        row = f'<div class="byline-row">{byline_html}{date_html}</div>'
    h1 = article.find('</h1>')
    if h1 < 0:
        return html
    rest = article[h1 + len('</h1>'):]
    note = _ARCHIVE_NOTE_RE.match(rest)
    note_html = note.group(0) if note else ''
    if note:
        rest = rest[note.end():]
    table_end = _data_table_end(rest)
    if table_end is not None:
        # Data pages: the table comes straight after the byline; the lead photo follows it.
        article = article[:h1 + len('</h1>')] + row + note_html + rest[:table_end] + figure + rest[table_end:]
    else:
        article = article[:h1 + len('</h1>')] + row + note_html + figure + rest
    html = html[:start] + article + html[end:]
    html = apply_body_photos(html)
    return place_quick_cite(install_lead_css(html))


def ensure_byline(html: str) -> str:
    """Put the linked byline on the post. Same tab, since it stays on this site."""
    if '.article .byline{' not in html:
        if '</style>' in html:
            html = html.replace('</style>', BYLINE_CSS + '</style>', 1)
        elif '</head>' in html:
            html = html.replace('</head>', '<style>' + BYLINE_CSS + '</style></head>', 1)
    if BYLINE_RE.search(html):
        return BYLINE_RE.sub(BYLINE_HTML, html, count=1)
    if '</h1>' in html:
        return html.replace('</h1>', '</h1>' + BYLINE_HTML, 1)
    marker = '<article'
    index = html.find(marker)
    if index == -1:
        return html + BYLINE_HTML
    end = html.find('>', index)
    return html[:end + 1] + BYLINE_HTML + html[end + 1:]


AUTHOR_HOW_LABEL = 'How we make Full Court Buckets content'


def _author_bio_html() -> str:
    """Intro, the media line, then the how-we-make link. The TikTok line closes the page.

    The media line lives here so a nightly rebuild cannot drop it. A one-off
    patch of the published HTML does not survive render_author_page.
    """
    import citation
    parts = [
        '<!-- TODO: add a LinkedIn sameAs link for Ryan Moalemi when the profile URL is available. -->',
    ]
    for sentence in AUTHOR_BIO:
        text = esc(sentence).replace(
            'Angel Reese',
            '<a href="/wnba/angel-reese/">Angel Reese</a>',
        )
        parts.append(f'<p>{text}</p>')
    parts.append(citation.media_line_html())
    parts.append(f'<p><a href="{HOW_PAGE}">{AUTHOR_HOW_LABEL}</a></p>')
    return '\n'.join(parts)


def _author_closing_html() -> str:
    return AUTHOR_TIKTOK_HTML


def _collection_teaser(root: Path | None) -> str:
    if root is None or not (root / 'data' / 'reese-cards.json').is_file():
        return ''
    import build_reese_cards
    return build_reese_cards.author_teaser(root)


def render_author_page(articles: list, root: Path | None = None) -> str:
    """Author archive. The article list is the same newest-first feed as /news/."""
    ordered = _ordered_articles(articles)
    crumbs = {
        '@context': 'https://schema.org',
        '@type': 'BreadcrumbList',
        'itemListElement': [
            {'@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': BASE + '/'},
            {'@type': 'ListItem', 'position': 2, 'name': AUTHOR_NAME, 'item': AUTHOR_URL},
        ],
    }
    cards = ''.join(_news_list_item(article) for article in ordered)
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
{GA4_TAG}
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-6621195315204235" crossorigin="anonymous"></script>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(AUTHOR_NAME)} | Full Court Buckets</title>
<meta name="description" content="{esc(AUTHOR_META)}">
<meta name="author" content="{esc(AUTHOR_NAME)}">
<meta name="robots" content="index,follow,max-image-preview:large">
<link rel="canonical" href="{AUTHOR_URL}">
<link rel="icon" href="/favicon.svg">
<meta property="og:type" content="profile">
<meta property="og:title" content="{esc(AUTHOR_NAME)}">
<meta property="og:description" content="{esc(AUTHOR_META)}">
<meta property="og:url" content="{AUTHOR_URL}">
<meta property="og:image" content="{AUTHOR_IMAGE_URL}">
<meta property="og:site_name" content="Full Court Buckets">
{_jsonld(author_person())}
{_jsonld(crumbs)}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@600;700;800&amp;family=Inter:wght@400;600;700&amp;display=swap" rel="stylesheet">
<style>
body{{margin:0;background:#050506;color:#f5f3ef;font:16px/1.6 Inter,system-ui,sans-serif}}
a{{color:inherit}}img{{max-width:100%;display:block}}
.shell{{width:min(980px,94vw);margin:0 auto}}
header{{border-bottom:1px solid #2b2930;background:#050506}}
header .shell{{display:flex;align-items:center;gap:24px;min-height:84px}}
header img{{width:220px;height:auto}}
main{{padding:28px 0 72px}}
h1{{margin:18px 0 8px;font:800 56px/1 Barlow,sans-serif;letter-spacing:-1px}}
h2{{margin:28px 0 8px;font:800 32px/1.1 Barlow,sans-serif}}
.bio p{{margin:0 0 14px;color:#e8e3df;max-width:40rem}}
.bio a{{color:#ff9800;text-decoration:underline}}
.author-photo{{width:160px;height:160px;border-radius:50%;object-fit:cover;margin:12px 0 18px;border:1px solid #2b2930;background:#111}}
.breadcrumbs{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;color:#a29f99;font-size:13px;font-weight:600}}
.breadcrumbs a{{color:#d4d0ca;text-decoration:underline}}
.news-list{{list-style:none;margin:18px 0 0;padding:0;display:grid;gap:14px}}
.news-item{{display:grid;grid-template-columns:180px minmax(0,1fr);gap:16px;align-items:center;background:rgba(10,10,12,.96);border:1px solid #2b2930;padding:12px;text-decoration:none}}
.news-item img{{width:180px;height:120px;object-fit:cover;object-position:{DEFAULT_IMAGE_FOCAL};background:#111;border-radius:0}}
.news-copy time{{color:#ff9800;font-size:12px;font-weight:800;letter-spacing:.04em}}
.news-copy h2{{margin:4px 0 6px;font:800 28px/1.1 Barlow,sans-serif}}
.news-copy p{{margin:0;color:#a5a19b;font-size:15px;line-height:1.45}}
.collection-teaser{{display:grid;grid-template-columns:120px minmax(0,1fr);gap:16px;align-items:center;margin:8px 0 4px;padding:12px;background:#121016;border:1px solid #3a3428;text-decoration:none}}
.collection-teaser img{{width:120px;height:160px;object-fit:contain;background:#0a090d}}
.collection-teaser b{{display:block;font:800 28px/1.1 Barlow,sans-serif}}
.collection-teaser p{{margin:6px 0 0;color:#a5a19b}}
@media(max-width:700px){{h1{{font-size:40px}}.author-photo{{width:120px;height:120px}}.news-item{{grid-template-columns:1fr}}.news-item img{{width:100%;height:180px}}.collection-teaser{{grid-template-columns:88px 1fr}}.collection-teaser img{{width:88px;height:118px}}}}
</style>
<link rel="stylesheet" href="/assets/citation.css">
</head>
<body>
<header><div class="shell"><a href="/"><img src="/logo-light.png" alt="Full Court Buckets" width="480" height="416"></a><nav aria-label="Main"><a href="/">Home</a></nav></div></header>
<main class="shell">
<nav class="breadcrumbs" aria-label="Breadcrumb"><a href="/">Home</a><span aria-hidden="true">/</span><span>{esc(AUTHOR_NAME)}</span></nav>
<h1>{esc(AUTHOR_NAME)}</h1>
<img class="author-photo" src="{AUTHOR_IMAGE}" alt="{esc(AUTHOR_NAME)}" width="320" height="320">
<div class="bio">
{_author_bio_html()}
</div>
{_collection_teaser(root)}
<h2>Stories</h2>
<ol class="news-list">{cards}</ol>
<div class="bio">
{_author_closing_html()}
</div>
</main>
<script src="/assets/citation.js" defer></script>
</body>
</html>
'''


# Figcaption under a stat-board chart in a new article. Published posts stay as written.
STAT_BOARD_CAPTION = 'gathered and verified by Full Court Buckets'


def stat_board_caption(lead: str = '') -> str:
    """Caption for a future article's stat board. It does not name a stats feed."""
    source = f'Source: Full Court Buckets game data, {STAT_BOARD_CAPTION}.'
    text = (lead or '').strip()
    if not text:
        return source
    if not text.endswith('.'):
        text += '.'
    return f'{text} {source}'


HOW_MADE_PAGE = '/how-we-make-full-court-buckets/'
HOW_MADE_LINK = f'<a href="{HOW_MADE_PAGE}" target="_blank" rel="noopener">How we make Full Court Buckets</a>'
HOW_MADE_RECAP = (
    'How this story was made: Full Court Buckets articles are written by Ryan Moalemi, sometimes with AI assistance, and every stat is checked against official WNBA box scores and the sources cited in the story.'
)
HOW_MADE_RECAP_BOX_ONLY = (
    'How this story was made: Full Court Buckets articles are written by Ryan Moalemi, sometimes with AI assistance, and every stat is checked against official WNBA box scores and the sources cited in the story.'
)
HOW_MADE_OTHER = (
    'How this story was made: Full Court Buckets articles are written by Ryan Moalemi, sometimes with AI assistance, and every stat is checked against official WNBA box scores and the sources cited in the story.'
)
HOW_MADE_OTHER_UNLINKED = (
    'How this story was made: Full Court Buckets articles are written by Ryan Moalemi, sometimes with AI assistance, and every stat is checked against official WNBA box scores and the sources cited in the story.'
)
HOW_MADE_RYAN = (
    'How this story was made: Full Court Buckets articles are written by Ryan Moalemi, sometimes with AI assistance, and every stat is checked against official WNBA box scores and the sources cited in the story.'
)
HOW_MADE_RYAN_UNLINKED = (
    'How this story was made: Full Court Buckets articles are written by Ryan Moalemi, sometimes with AI assistance, and every stat is checked against official WNBA box scores and the sources cited in the story.'
)
HOW_MADE_RE = re.compile(r'<p class="how-made">.*?</p>', re.S)
_OWN_HOSTS = frozenset({'fullcourtbuckets.com', 'www.fullcourtbuckets.com'})


class DisclosureError(RuntimeError):
    """The disclosure names a source the page does not actually link."""


def outbound_source_links(html_text: str) -> list[str]:
    """External links in the article, above the disclosure. Site links do not count."""
    text = html_text or ''
    start = text.find('<article')
    if start >= 0:
        text = text[start:]
    cut = text.find('class="how-made"')
    if cut >= 0:
        text = text[:cut]
    found = []
    for href in re.findall(r'href="([^"]+)"', text):
        if href.startswith(('#', '/', 'mailto:')):
            continue
        host = (urlsplit(href).hostname or '').lower()
        if not host or host in _OWN_HOSTS:
            continue
        found.append(href)
    return found


def how_made_sentence(html_text: str, article: dict | None) -> str:
    """Name sources only when this page links them above the disclosure."""
    linked = bool(outbound_source_links(html_text))
    if (article or {}).get('authorWrote'):
        return HOW_MADE_RYAN if linked else HOW_MADE_RYAN_UNLINKED
    if story_uses_box_score(html_text, article):
        return HOW_MADE_RECAP if linked else HOW_MADE_RECAP_BOX_ONLY
    return HOW_MADE_OTHER if linked else HOW_MADE_OTHER_UNLINKED


def assert_disclosure_matches_sources(html_text: str) -> None:
    """Fail when the footer says sources are linked above and none are."""
    match = HOW_MADE_RE.search(html_text or '')
    if match is None:
        return
    disclosure = match.group(0)
    if 'sources linked above' in disclosure and not outbound_source_links(html_text):
        raise DisclosureError(
            'Disclosure says sources are linked above, but this page has no outbound source links.'
        )
    claimed = 'official FIBA' in disclosure or 'USA Basketball announcements' in disclosure
    if claimed and not any(
        host in href.casefold()
        for href in outbound_source_links(html_text)
        for host in ('fiba.basketball', 'usab.com')
    ):
        raise DisclosureError(
            'Disclosure names official FIBA or USA Basketball announcements, and this page does not link them.'
        )


def story_uses_box_score(html_text: str, article: dict | None) -> bool:
    """Recaps name an ESPN game id or print a box-score line. Other posts do not."""
    game_id = str((article or {}).get('espnGameId') or '').strip()
    if game_id.isdigit():
        return True
    return 'class="box-score"' in (html_text or '')


def how_made_html(html_text: str, article: dict | None) -> str:
    sentence = how_made_sentence(html_text, article)
    snippet = f'<p class="how-made">{sentence} {HOW_MADE_LINK}</p>'
    if HOW_MADE_RE.search(html_text or ''):
        preview = HOW_MADE_RE.sub(snippet, html_text, count=1)
    else:
        preview = (html_text or '') + snippet
    assert_disclosure_matches_sources(preview)
    return snippet


def ensure_how_made(html_text: str, article: dict | None = None) -> str:
    """Disclosure at the end of a post. The box score, when there is one, stays above it."""
    if '.article .how-made{' not in html_text:
        if '</style>' in html_text:
            html_text = html_text.replace('</style>', HOW_MADE_CSS + '</style>', 1)
        elif '</head>' in html_text:
            html_text = html_text.replace('</head>', '<style>' + HOW_MADE_CSS + '</style></head>', 1)
    snippet = how_made_html(html_text, article)
    if HOW_MADE_RE.search(html_text):
        return HOW_MADE_RE.sub(snippet, html_text, count=1)
    box = re.search(r'<p class="box-score">.*?</p>', html_text, re.S)
    if box and story_uses_box_score(html_text, article):
        end = box.end()
        return html_text[:end] + snippet + html_text[end:]
    if '<p class="brand-sign">' in html_text:
        return html_text.replace('<p class="brand-sign">', snippet + '<p class="brand-sign">', 1)
    if '</article>' in html_text:
        return html_text.replace('</article>', snippet + '</article>', 1)
    return html_text + snippet


NOTE_BLOCK_RE = re.compile(r'<p class="(?:source-note|checked)">.*?</p>', re.S)


def order_article_sections(html_text: str) -> str:
    """Move source notes and the last-checked line to the source list.

    The disclosure stays last when it says the sources are linked above.
    Photo captions stay with their figures.
    """
    start = html_text.find('<article')
    end = html_text.rfind('</article>')
    if start < 0 or end < 0:
        return html_text
    article = html_text[start:end]
    notes = NOTE_BLOCK_RE.findall(article)
    if not notes:
        return html_text
    stripped = NOTE_BLOCK_RE.sub('', article)
    sources = stripped.find('<h2 class="section-title">Sources</h2>')
    how = stripped.find('<p class="how-made">')
    box = stripped.find('<p class="box-score">')
    if sources >= 0:
        at = sources
    elif how >= 0:
        at = how
    elif box >= 0:
        at = box
    else:
        at = len(stripped)
    moved = stripped[:at] + ''.join(notes) + stripped[at:]
    return html_text[:start] + moved + html_text[end:]


ARTICLE_END_RE = re.compile(r'<aside class="article-end">.*?</aside>', re.S)
ARTICLE_END_CSS = (
    '.article-end{margin:28px 0 0;display:grid;gap:22px}'
    '.article-end h2{margin:0 0 10px;font:800 22px/1 Barlow,sans-serif;letter-spacing:-.3px}'
    '.article-end h2:after{content:"";display:block;width:48px;height:3px;margin-top:8px;'
    'background:linear-gradient(90deg,#7d35ff,#f10091,#ff9800)}'
    '.article-end ul{list-style:none;margin:0;padding:0}'
    '.article-end li+li{margin-top:8px}'
    '.article-end a{color:#f5f3ef;font-weight:700}'
    '.article-players ul{display:flex;flex-wrap:wrap;gap:8px}'
    '.article-players li{margin:0}'
    '.article-players a{display:inline-flex;align-items:center;min-height:44px;padding:0 12px;'
    'border:1px solid #2b2930;background:#141218}'
)
PLAYER_HREF_RE = re.compile(r'href="(/wnba/(?!teams/)[a-z0-9-]+/)"')


def _article_teams(article: dict) -> frozenset:
    return frozenset(str(team) for team in (article.get('teams') or []) if team)


def series_articles(article: dict, articles: list, limit: int = 4) -> list:
    """Other posts from the same matchup. A multi-series preview covers each pair."""
    mine = _article_teams(article)
    if len(mine) < 2:
        return []
    found = []
    for other in articles:
        if other.get('slug') == article.get('slug'):
            continue
        theirs = _article_teams(other)
        if len(theirs) < 2:
            continue
        if mine == theirs or (len(mine) == 2 and mine < theirs) or (len(theirs) == 2 and theirs < mine):
            found.append(other)
    if len(mine) > 2:
        groups = {}
        for other in found:
            groups.setdefault(_article_teams(other), []).append(other)
        lists = [
            sorted(group, key=lambda item: item.get('date') or '', reverse=True)
            for group in groups.values()
        ]
        picked = []
        while len(picked) < limit and any(lists):
            for group in lists:
                if group and len(picked) < limit:
                    picked.append(group.pop(0))
        return picked
    found.sort(key=lambda item: item.get('date') or '', reverse=True)
    return found[:limit]


def _latest_news(article: dict, articles: list, skip: set[str], limit: int = 3) -> list:
    rows = []
    ordered = sorted(articles, key=lambda item: item.get('date') or '', reverse=True)
    for other in ordered:
        slug = str(other.get('slug') or '')
        if not slug or slug == article.get('slug') or slug in skip:
            continue
        rows.append(other)
        if len(rows) >= limit:
            break
    return rows


def _player_names(root: Path) -> dict[str, str]:
    path = root / 'data' / 'wnba' / 'players-index.json'
    if not path.is_file():
        return {}
    index = json.loads(path.read_text(encoding='utf-8'))
    names = {}
    for entry in index.get('players') or []:
        slug = str(entry.get('slug') or '').strip()
        name = str(entry.get('name') or '').strip()
        if slug and name:
            names[slug] = name
    return names


def _mentioned_players(html_text: str, root: Path) -> list[tuple[str, str]]:
    article = html_text
    start = article.find('<article')
    if start >= 0:
        article = article[start:]
    cut = article.find('class="how-made"')
    if cut >= 0:
        article = article[:cut]
    names = _player_names(root)
    found = []
    seen = set()
    for href in PLAYER_HREF_RE.findall(article):
        slug = href.strip('/').split('/')[-1]
        if slug in seen or slug not in names:
            continue
        seen.add(slug)
        found.append((names[slug], href))
    return found


def _story_links(rows: list) -> str:
    items = ''.join(
        f'<li><a href="{esc(article_href(article))}">{esc(article.get("title") or "")}</a></li>'
        for article in rows
    )
    return f'<ul>{items}</ul>' if items else ''


def article_end_html(html_text: str, root: Path, article: dict, articles: list) -> str:
    """Series stories, three latest posts, and the players named in the article."""
    series = series_articles(article, articles)
    latest = _latest_news(article, articles, {str(item.get('slug') or '') for item in series})
    players = _mentioned_players(html_text, root)
    parts = ['<aside class="article-end">']
    if series:
        parts.append(
            '<section class="article-series"><h2>More from this series</h2>'
            + _story_links(series) + '</section>'
        )
    if latest:
        parts.append(
            '<section class="article-latest"><h2>Latest news</h2>'
            + _story_links(latest) + '</section>'
        )
    if players:
        chips = ''.join(
            f'<li><a href="{esc(href)}" target="_blank" rel="noopener">{esc(name)}</a></li>'
            for name, href in players
        )
        parts.append(
            '<section class="article-players"><h2>Players in this story</h2>'
            f'<ul>{chips}</ul></section>'
        )
    parts.append('</aside>')
    if len(parts) == 2:
        return ''
    return ''.join(parts)


def ensure_article_end(html_text: str, root: Path, article: dict, articles: list) -> str:
    """Build-time related links at the end of a post. Re-running replaces the block."""
    if '.article-end{' not in html_text:
        if '</style>' in html_text:
            html_text = html_text.replace('</style>', ARTICLE_END_CSS + '</style>', 1)
        elif '</head>' in html_text:
            html_text = html_text.replace('</head>', '<style>' + ARTICLE_END_CSS + '</style></head>', 1)
    cleaned = ARTICLE_END_RE.sub('', html_text)
    block = article_end_html(cleaned, root, article, articles)
    if not block:
        return cleaned
    match = HOW_MADE_RE.search(cleaned)
    if match:
        end = match.end()
        return cleaned[:end] + block + cleaned[end:]
    if '</article>' in cleaned:
        return cleaned.replace('</article>', block + '</article>', 1)
    return cleaned + block


def prepare_article_page(root: Path, article: dict, articles: list | None = None) -> str:
    slug = article_slug(article)
    html_text = read_article_source(root, slug)
    if slug in FROZEN_ARTICLE_SLUGS:
        return html_text
    html_text = rewrite_legacy_article_urls(html_text, articles if articles is not None else [article])
    import news_heroes
    # Crop first: the og/twitter meta and schema below read the paths this writes.
    social_before = str(article.get('imageOg') or article.get('imageHero') or '').strip()
    news_heroes.ensure_article_hero(root, article)
    social_after = str(article.get('imageOg') or article.get('imageHero') or '').strip()
    absolute = article_absolute(article)
    html_text = _upsert_meta(html_text, absolute, article.get('description'))
    html_text = ensure_author_meta(html_text)
    html_text = _upsert_article_schema(html_text, article, absolute)
    html_text = _insert_visible_breadcrumb(html_text, str(article.get('title') or ''))
    html_text = ensure_box_score(html_text, article)
    html_text = ensure_how_made(html_text, article)
    html_text = ensure_byline(html_text)
    html_text = order_article_sections(html_text)
    html_text = order_news_lead(html_text, article)
    html_text = ensure_article_end(html_text, root, article, articles if articles is not None else [article])
    html_text = glue_headline_scores(html_text)
    if social_after and social_after != social_before:
        # A re-crop renamed the social card; og:image, twitter:image and schema follow it.
        html_text = news_heroes._set_social_image(html_text, BASE + social_after)
    return html_text


# Published at /players/<slug>/ before profiles moved to /wnba/<slug>/.
# This is only the floor for URLs that already existed. The generator also emits a
# stub for every current /wnba/<slug>/ page. Two of these names never received a
# profile and still redirect to the player index.
LEGACY_PLAYER_SLUGS = (
    'aja-wilson', 'aliyah-boston', 'allisha-gray', 'angel-reese', 'arike-ogunbowale',
    'becky-hammon', 'breanna-stewart', 'caitlin-clark', 'cecilia-zandalasini', 'chelsea-gray',
    'courtney-vandersloot', 'dewanna-bonner', 'gabby-williams', 'han-xu', 'jackie-young',
    'jessica-shepard', 'jewell-loyd', 'jonquel-jones', 'jordin-canada', 'kahleah-copper',
    'kara-lawson', 'kayla-mcbride', 'kayla-thornton', 'kelsey-mitchell', 'kelsey-plum',
    'kiki-iriafen', 'kitija-laksa', 'leonie-fiebich', 'maddy-siegrist', 'napheesa-collier',
    'natasha-howard', 'nia-brodie', 'olivia-miles', 'paige-bueckers', 'pauline-astier',
    'raven-johnson', 'rhyne-howard', 'sabrina-ionescu', 'shakira-austin', 'sonia-citron',
    'stephanie-white', 'tiffany-hayes', 'veronica-burton',
)
# Folders under /wnba/ that are not player profiles.
# viewership-attendance is an evergreen guide. Counting it as a player made the
# updater require a /players/viewership-attendance/ redirect and fail the suite
# on 0b40a3d (Oct. 13, 2026).
WNBA_NON_PLAYER_DIRS = frozenset({'teams', 'assets', 'couples', 'viewership-attendance', 'owners', 'where-to-watch', 'finals'})


def permanent_redirect(target: str) -> str:
    """HTML permanent redirect. GitHub Pages cannot send HTTP 301."""
    safe = esc(target)
    return (
        '<!doctype html>\n'
        '<html lang="en">\n'
        '<head>\n'
        '<meta charset="utf-8">\n'
        '<title>Redirect</title>\n'
        f'<link rel="canonical" href="{safe}">\n'
        '<meta name="robots" content="noindex">\n'
        f'<meta http-equiv="refresh" content="0; url={safe}">\n'
        f'<script>location.replace("{safe}");</script>\n'
        '</head>\n'
        '<body>\n'
        f'<p><a href="{safe}">This page has moved.</a></p>\n'
        '</body>\n'
        '</html>\n'
    )


def wnba_player_slugs(root: Path | None = None, files: dict | None = None) -> set[str]:
    """Slugs that publish a /wnba/<slug>/ page, on disk or in this build's output."""
    found: set[str] = set()

    def add(slug: str) -> None:
        if slug in WNBA_NON_PLAYER_DIRS or not ARTICLE_SLUG.fullmatch(slug):
            return
        found.add(slug)

    if files:
        for relative in files:
            match = re.fullmatch(r'wnba/([^/]+)/index\.html', str(relative))
            if match:
                add(match.group(1))
    if root is not None:
        wnba = Path(root) / 'wnba'
        if wnba.is_dir():
            for child in wnba.iterdir():
                if child.is_dir() and (child / 'index.html').is_file():
                    add(child.name)
    return found


def legacy_player_redirect_files(published_slugs: set) -> dict:
    """Old /players/ URLs.

    Every slug with a /wnba/<slug>/ page gets a matching stub. A historical
    /players/ slug that still has no profile goes to the player index.
    """
    pages = {'players/index.html': permanent_redirect(BASE + '/wnba/')}
    profiles = set(published_slugs)
    for slug in sorted(profiles | set(LEGACY_PLAYER_SLUGS)):
        if not ARTICLE_SLUG.fullmatch(slug):
            continue
        route = f'/wnba/{slug}/' if slug in profiles else '/wnba/'
        pages[f'players/{slug}/index.html'] = permanent_redirect(BASE + route)
    return pages


def redirect_stub(article: dict) -> str:
    """GitHub Pages has no server redirects. The old root URL refreshes to /news/<slug>/."""
    return permanent_redirect(article_absolute(article))


def _news_list_item(article: dict) -> str:
    title = str(article.get('title') or '')
    summary = str(article.get('description') or '')
    image = str(article.get('image') or '')
    alt = str(article.get('imageAlt') or title)
    when = str(article.get('date') or '')
    label = _format_date(when) if when else ''
    dims = _image_dims(article)
    thumb = (
        f'<img src="{esc(image)}" alt="{esc(alt)}"{dims} decoding="async" loading="lazy"{focal_style(article)}>'
        if image else ''
    )
    return (
        '<li><a class="news-item" href="' + esc(article_href(article)) + '">'
        + thumb
        + '<span class="news-copy"><time datetime="' + esc(when) + '">' + esc(label) + '</time>'
        + '<h2>' + glue_scores(esc(title)) + '</h2><p>' + esc(summary) + '</p></span></a></li>'
    )


def render_news_hub(articles: list) -> str:
    ordered = _ordered_articles(articles)
    items = []
    for index, article in enumerate(ordered, 1):
        items.append({
            '@type': 'ListItem',
            'position': index,
            'url': article_absolute(article),
            'name': article.get('title') or '',
        })
    structured = {
        '@context': 'https://schema.org',
        '@graph': [
            {
                '@type': 'CollectionPage',
                'name': 'WNBA news',
                'url': BASE + NEWS_HUB,
                'description': NEWS_INTRO,
                'isPartOf': {'@type': 'WebSite', 'name': 'Full Court Buckets', 'url': BASE + '/'},
                'mainEntity': {
                    '@type': 'ItemList',
                    'itemListOrder': 'https://schema.org/ItemListOrderDescending',
                    'numberOfItems': len(items),
                    'itemListElement': items,
                },
            },
            _breadcrumb_data([('Home', BASE + '/'), ('News', BASE + NEWS_HUB)]),
        ],
    }
    cards = ''.join(_news_list_item(article) for article in ordered)
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
{GA4_TAG}
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-6621195315204235" crossorigin="anonymous"></script>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>WNBA news | Full Court Buckets</title>
<meta name="description" content="{esc(NEWS_INTRO)}">
<meta name="robots" content="index,follow,max-image-preview:large">
<link rel="canonical" href="{BASE}{NEWS_HUB}">
<link rel="icon" href="/favicon.svg">
<meta property="og:type" content="website">
<meta property="og:title" content="WNBA news">
<meta property="og:description" content="{esc(NEWS_INTRO)}">
<meta property="og:url" content="{BASE}{NEWS_HUB}">
<meta property="og:site_name" content="Full Court Buckets">
{_jsonld(structured)}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@600;700;800&amp;family=Inter:wght@400;600;700&amp;display=swap" rel="stylesheet">
<style>
body{{margin:0;background:#050506;color:#f5f3ef;font:16px/1.6 Inter,system-ui,sans-serif}}
a{{color:inherit}}img{{max-width:100%;display:block}}
.shell{{width:min(980px,94vw);margin:0 auto}}
header{{border-bottom:1px solid #2b2930;background:#050506}}
header .shell{{display:flex;align-items:center;gap:24px;min-height:84px}}
header img{{width:220px;height:auto}}
main{{padding:28px 0 72px}}
h1{{margin:18px 0 8px;font:800 56px/1 Barlow,sans-serif;letter-spacing:-1px}}
.intro{{margin:0 0 8px;color:#d0ccc6;max-width:40rem}}
.breadcrumbs{{display:flex;gap:8px;align-items:center;color:#a29f99;font-size:13px;font-weight:600}}
.breadcrumbs a{{color:#d4d0ca;text-decoration:underline}}
.news-list{{list-style:none;margin:28px 0 0;padding:0;display:grid;gap:14px}}
.news-item{{display:grid;grid-template-columns:180px minmax(0,1fr);gap:16px;align-items:center;background:rgba(10,10,12,.96);border:1px solid #2b2930;padding:12px;text-decoration:none}}
.news-item img{{width:180px;height:120px;object-fit:cover;object-position:{DEFAULT_IMAGE_FOCAL};background:#111}}
.news-copy time{{color:#ff9800;font-size:12px;font-weight:800;letter-spacing:.04em}}
.news-copy h2{{margin:4px 0 6px;font:800 28px/1.1 Barlow,sans-serif}}
.news-copy p{{margin:0;color:#a5a19b;font-size:15px;line-height:1.45}}
{COUPLES_FEATURE_CSS}
@media(max-width:700px){{h1{{font-size:40px}}.news-item{{grid-template-columns:1fr}}.news-item img{{width:100%;height:180px}}}}
</style>
</head>
<body>
<header><div class="shell"><a href="/"><img src="/logo-light.png" alt="Full Court Buckets" width="480" height="416"></a><nav aria-label="Main"><a href="/">Home</a></nav></div></header>
<main class="shell">
<nav class="breadcrumbs" aria-label="Breadcrumb"><a href="/">Home</a><span aria-hidden="true">/</span><span>News</span></nav>
<h1>WNBA news</h1>
<p class="intro">{esc(NEWS_INTRO)}</p>
<ol class="news-list">{cards}</ol>
{COUPLES_FEATURE_HTML}
</main>
</body>
</html>
'''


def assemble_news_pages(root: Path) -> dict[str, str]:
    """Article HTML at news/<slug>/, redirect stubs at the old root paths, and the /news/ hub."""
    articles = ensure_article_urls(root)
    before = json.dumps(articles, ensure_ascii=False, sort_keys=True)
    pages = {}
    live = set()
    for article in articles:
        slug = article_slug(article)
        live.add(slug)
        pages[f'news/{slug}/index.html'] = prepare_article_page(root, article, articles)
        pages[f'{slug}/index.html'] = redirect_stub(article)
    path = root / 'articles.json'
    if path.is_file() and json.dumps(articles, ensure_ascii=False, sort_keys=True) != before:
        # prepare_article_page re-crops heroes and social cards and can rename them
        # (hero-16x9 -> hero-1200, og.jpg -> og-1200.jpg). Persist the new paths so
        # articles.json, the page markup and the files on disk agree.
        path.write_text(json.dumps(articles, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for slug, href in RETIRED_NEWS.items():
        if slug in live:
            continue
        target = BASE + href
        pages[f'news/{slug}/index.html'] = permanent_redirect(target)
        pages[f'{slug}/index.html'] = permanent_redirect(target)
    pages['news/index.html'] = render_news_hub(articles)
    pages[AUTHOR_PAGE] = render_author_page(articles, root)
    return pages


def _drop_sitemap_loc(text: str, loc: str) -> str:
    return re.sub(
        r'\s*<url>\s*<loc>\s*' + re.escape(loc) + r'\s*</loc>.*?</url>',
        '',
        text,
        count=1,
        flags=re.S,
    )


def sync_news_sitemap(text: str, articles: list) -> str:
    """New post URLs and /news/ stay. Old root post URLs and retired duplicates go."""
    if '</urlset>' not in text:
        return text
    live = set()
    for article in articles:
        try:
            live.add(article_slug(article))
        except ValueError:
            continue
    for slug in RETIRED_NEWS:
        if slug in live:
            continue
        text = _drop_sitemap_loc(text, f'{BASE}/news/{slug}/')
        text = _drop_sitemap_loc(text, f'{BASE}/{slug}/')
    for article in articles:
        try:
            slug = article_slug(article)
        except ValueError:
            continue
        old = f'{BASE}/{slug}/'
        new = article_absolute(article)
        text = re.sub(rf'(<loc>\s*){re.escape(old)}(\s*</loc>)', rf'\1{new}\2', text)
        if new not in text:
            lastmod = str(article.get('date') or '2026-09-29')
            block = (
                '  <url>\n'
                f'    <loc>{new}</loc>\n'
                f'    <lastmod>{lastmod}</lastmod>\n'
                '    <changefreq>weekly</changefreq>\n'
                '    <priority>0.8</priority>\n'
                '  </url>\n'
            )
            text = text.replace('</urlset>', block + '</urlset>', 1)
    hub = BASE + NEWS_HUB
    if not re.search(rf'<loc>\s*{re.escape(hub)}\s*</loc>', text):
        block = (
            '  <url>\n'
            f'    <loc>{hub}</loc>\n'
            '    <lastmod>2026-09-29</lastmod>\n'
            '    <changefreq>weekly</changefreq>\n'
            '    <priority>0.8</priority>\n'
            '  </url>\n'
        )
        text = text.replace('</urlset>', block + '</urlset>', 1)
    if not re.search(rf'<loc>\s*{re.escape(AUTHOR_URL)}\s*</loc>', text):
        block = (
            '  <url>\n'
            f'    <loc>{AUTHOR_URL}</loc>\n'
            '    <lastmod>2026-10-02</lastmod>\n'
            '    <changefreq>weekly</changefreq>\n'
            '    <priority>0.6</priority>\n'
            '  </url>\n'
        )
        text = text.replace('</urlset>', block + '</urlset>', 1)
    how = BASE + HOW_PAGE
    if not re.search(rf'<loc>\s*{re.escape(how)}\s*</loc>', text):
        block = (
            '  <url>\n'
            f'    <loc>{how}</loc>\n'
            '    <lastmod>2026-10-02</lastmod>\n'
            '    <changefreq>monthly</changefreq>\n'
            '    <priority>0.5</priority>\n'
            '  </url>\n'
        )
        text = text.replace('</urlset>', block + '</urlset>', 1)
    return text


def legacy_post_link_pattern(articles: list) -> re.Pattern:
    slugs = []
    for article in articles:
        try:
            slugs.append(re.escape(article_slug(article)))
        except ValueError:
            continue
    if not slugs:
        return re.compile(r'(?!x)x')
    group = '|'.join(slugs)
    return re.compile(
        rf'''(?:(?:href|content)\s*=\s*["'](?:https://fullcourtbuckets\.com)?/(?:{group})/["']'''
        rf'''|<loc>\s*https://fullcourtbuckets\.com/(?:{group})/\s*</loc>)''',
        re.I,
    )
