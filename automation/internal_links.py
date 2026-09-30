#!/usr/bin/env python3
"""Contextual internal links derived from roster and story copy already in the repo.

Used by build_players.py so the next rebuild keeps the same links. Only emits an
href when the target page is known. Article links use the first mention of a
name that is already written in the copy.
"""
from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from analytics import GA4_TAG
from link_graph import file_for_url, normalize_href
import team_names

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


def inline_link(label: str, href: str) -> str:
    return f'<a class="inline-link" href="{esc(href)}" target="_blank" rel="noopener">{esc(label)}</a>'


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


def _link_plain(text: str, compiled, used: set[str]) -> str:
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
        pieces.append(f'<a class="inline-link" href="{url}" target="_blank" rel="noopener">{raw}</a>')
        used.add(url)
        rest = rest[end:]
    return ''.join(pieces)


def _link_fragment(fragment: str, compiled, used: set[str]) -> str:
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
            out.append(_link_plain(part, compiled, used))
    return ''.join(out)


def link_copy(html_text: str, compiled, scope: str = 'article') -> str:
    """Link the first body mention inside p and li. Existing anchors count as the first mention."""
    pattern = ARTICLE if scope == 'article' else MAIN
    match = pattern.search(html_text)
    if not match:
        return html_text
    used: set[str] = set()

    def region(found: re.Match) -> str:
        return found.group(1) + _link_fragment(found.group(2), compiled, used) + found.group(3)

    inner = REGION.sub(region, match.group(2))
    return html_text[:match.start(2)] + inner + html_text[match.end(2):]


def ensure_footer_hubs(text: str) -> str:
    """Add crawlable Players and Standings links in an existing footer link row."""
    match = re.search(r'<p class="footer-links">.*?</p>', text, re.S)
    if not match:
        return text
    block = match.group(0)
    extra = ''
    if 'href="/wnba/"' not in block and "href='/wnba/'" not in block:
        extra += '<a href="/wnba/">Players</a>'
    if 'href="/standings/"' not in block and "href='/standings/'" not in block:
        extra += '<a href="/standings/">Standings</a>'
    if not extra:
        return text
    open_end = block.find('>') + 1
    updated = block[:open_end] + extra + block[open_end:]
    return text[:match.start()] + updated + text[match.end():]


def _format_date(iso: str) -> str:
    year, month, day = (int(part) for part in str(iso).split('-')[:3])
    when = dt.date(year, month, day)
    return f'{when.strftime("%B")} {when.day}, {when.year}'


def _story_card(article: dict) -> str:
    title = article['title']
    image = article.get('image') or ''
    alt = article.get('imageAlt') or title
    return (
        f'<a class="article-card" href="{esc(article_href(article))}" target="_blank" rel="noopener">'
        f'<div class="article-visual"><img src="{esc(image)}" alt="{esc(alt)}"></div>'
        f'<div class="article-copy"><div class="cat">{esc(article.get("category") or "")}</div>'
        f'<h3>{esc(title)}</h3><p>{esc(article.get("description") or "")}</p>'
        f'<div class="date">{esc(_format_date(article["date"]))}</div></div></a>'
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
    '<a class="coverage-card" href="/standings/" target="_blank" rel="noopener"><b>Standings</b>'
    '<p>Current WNBA standings and where each team sits in the playoff race.</p></a>'
    '<a class="coverage-card" href="/wnba/" target="_blank" rel="noopener"><b>Players</b>'
    '<p>Season statistics and profiles for WNBA players, past and present.</p></a>'
    '</div></section><!-- fcb-hubs:end -->'
)


def apply_homepage(text: str, articles: list) -> str:
    """Crawlable story and hub links. Leaves the small test homepage untouched."""
    if 'id="latest"' not in text or 'id="older-stories"' not in text:
        return text
    text = ensure_footer_hubs(text)
    if '<!-- fcb-hubs:start -->' not in text:
        needle = '<section class="section"><div class="section-head"><h2 class="section-title">What We Cover</h2>'
        if needle in text:
            text = text.replace(needle, HUBS + needle, 1)
    ordered = sorted(articles, key=lambda article: article.get('date') or '', reverse=True)
    if ordered:
        featured = ordered[0]
        text = re.sub(
            r'(<a class="feature feature-link" id="featured-story" href=")[^"]*(")',
            lambda match: match.group(1) + article_href(featured) + match.group(2),
            text,
            count=1,
        )
        text = re.sub(r'(<h1 id="featured-title">).*?(</h1>)', lambda m: m.group(1) + esc(featured['title']) + m.group(2), text, count=1)
        text = re.sub(r'(<p id="featured-dek">).*?(</p>)', lambda m: m.group(1) + esc(featured.get('description') or '') + m.group(2), text, count=1)
        meta = f'{featured.get("category") or ""} · {_format_date(featured["date"])}'
        text = re.sub(r'(<div class="meta" id="featured-meta">).*?(</div>)', lambda m: m.group(1) + esc(meta) + m.group(2), text, count=1)
        cards = ''.join(_story_card(article) for article in ordered[1:])
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
    helper = 'function articlePath(a){return (a.url && a.url.charAt(0)==="/") ? a.url : ("/news/" + a.slug + "/");}'
    if 'function articlePath(' not in text:
        text = text.replace('fetch("/articles.json")', helper + '\n  fetch("/articles.json")', 1)
    return text


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
    if when:
        text = re.sub(
            r'(<span id="updatedAt">).*?(</span>)',
            lambda match: match.group(1) + 'Updated: ' + esc(when) + match.group(2),
            text,
            count=1,
        )
    return text


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
        "  return '<a class=\"team-name\" href=\"' + href + '\" target=\"_blank\" rel=\"noopener\">' + safe + '</a>';\n"
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
        label = f'<a class="team-name" href="{esc(href)}" target="_blank" rel="noopener">{esc(name)}</a>' if href else f'<span class="team-name">{esc(name)}</span>'
        cells = (
            f'<td><span class="rank">{esc(team.get("rank"))}</span></td>'
            f'<td><div class="team-cell"><span class="team-badge">{esc(name.split()[-1][:3].upper())}</span>{label}</div></td>'
            f'<td>{esc(team.get("wins"))}</td><td>{esc(team.get("losses"))}</td>'
            f'<td class="percent">{esc(_pct(team.get("pct")))}</td><td>{esc(team.get("gamesBack"))}</td>'
        )
        if wide:
            cells += (
                f'<td>{esc(team.get("home"))}</td><td>{esc(team.get("road"))}</td>'
                f'<td>{esc(team.get("streak"))}</td><td>{esc(team.get("last10"))}</td>'
            )
        line = ''
        if wide and team.get('rank') == 8:
            line = '<tr class="playoff-line"><td colspan="10">Playoff Line</td></tr>'
        klass = ' class="playoff-row"' if wide and isinstance(team.get('rank'), int) and team['rank'] <= 8 else ''
        return line + f'<tr{klass}>{cells}</tr>'

    listed = standings.get('teams') or []
    text = re.sub(
        r'<tbody id="standingsBody">.*?</tbody>',
        '<tbody id="standingsBody">' + ''.join(row(team, True) for team in listed) + '</tbody>',
        text,
        count=1,
        flags=re.S,
    )
    text = re.sub(
        r'<tbody id="eastStandings">.*?</tbody>',
        '<tbody id="eastStandings">' + ''.join(row(team, False) for team in listed if team.get('conference') == 'Eastern') + '</tbody>',
        text,
        count=1,
        flags=re.S,
    )
    text = re.sub(
        r'<tbody id="westStandings">.*?</tbody>',
        '<tbody id="westStandings">' + ''.join(row(team, False) for team in listed if team.get('conference') == 'Western') + '</tbody>',
        text,
        count=1,
        flags=re.S,
    )
    blocks = []
    for slot in sorted(linking['by_id'].values(), key=lambda item: item['full_name'].casefold()):
        players = ''.join(
            f'<li><a class="inline-link" href="/wnba/{esc(player["slug"])}/" target="_blank" rel="noopener">{esc(player["name"])}</a></li>'
            for player in slot['players']
        )
        blocks.append(
            f'<h3><a href="{esc(team_href(slot))}" target="_blank" rel="noopener">{esc(slot["full_name"])}</a></h3><ul>{players}</ul>'
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
        if '<b>Players:</b>' in text:
            text = text.replace(
                '<b>Players:</b>',
                '<b><a href="/wnba/" target="_blank" rel="noopener">Players</a>:</b>',
                1,
            )
        if '<b>Standings:</b>' in text:
            text = text.replace(
                '<b>Standings:</b>',
                '<b><a href="/standings/" target="_blank" rel="noopener">Standings</a>:</b>',
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
NEWS_INTRO = 'Recaps, notes, and other WNBA stories from Full Court Buckets.'
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


def team_news_html(root: Path, team_slug: str) -> str:
    """Newest stories tagged for this team. Empty when the team has none."""
    items = []
    for article in _ordered_articles(load_articles(root)):
        teams = article.get('teams') or []
        if team_slug not in teams:
            continue
        title = str(article.get('title') or '').strip()
        if not title:
            continue
        items.append('<li>' + inline_link(title, article_href(article)) + '</li>')
    if not items:
        return ''
    return (
        '<section class="section" id="team-news"><p class="eyebrow">News</p><h2>Stories</h2>'
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


def _upsert_meta(html: str, absolute: str) -> str:
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
            'description': article.get('description') or '',
            'url': absolute,
            'mainEntityOfPage': {'@type': 'WebPage', '@id': absolute},
            'datePublished': article.get('date') or '',
            'author': {'@type': 'Organization', 'name': 'Full Court Buckets', 'url': BASE + '/'},
            'publisher': {
                '@type': 'Organization',
                'name': 'Full Court Buckets',
                'logo': {'@type': 'ImageObject', 'url': BASE + '/logo.png'},
            },
        }
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


def prepare_article_page(root: Path, article: dict, articles: list | None = None) -> str:
    slug = article_slug(article)
    html_text = read_article_source(root, slug)
    html_text = rewrite_legacy_article_urls(html_text, articles if articles is not None else [article])
    absolute = article_absolute(article)
    html_text = _upsert_meta(html_text, absolute)
    html_text = _upsert_article_schema(html_text, article, absolute)
    html_text = _insert_visible_breadcrumb(html_text, str(article.get('title') or ''))
    return html_text


# Published at /players/<slug>/ before profiles moved to /wnba/<slug>/.
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


def legacy_player_redirect_files(published_slugs: set) -> dict:
    """Old /players/ URLs. A slug with no /wnba/ profile goes to the player index."""
    pages = {'players/index.html': permanent_redirect(BASE + '/wnba/')}
    for slug in LEGACY_PLAYER_SLUGS:
        route = f'/wnba/{slug}/' if slug in published_slugs else '/wnba/'
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
    thumb = f'<img src="{esc(image)}" alt="{esc(alt)}">' if image else ''
    return (
        '<li><a class="news-item" href="' + esc(article_href(article)) + '" target="_blank" rel="noopener">'
        + thumb
        + '<span class="news-copy"><time datetime="' + esc(when) + '">' + esc(label) + '</time>'
        + '<h2>' + esc(title) + '</h2><p>' + esc(summary) + '</p></span></a></li>'
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
.news-item img{{width:180px;height:120px;object-fit:cover;background:#111}}
.news-copy time{{color:#ff9800;font-size:12px;font-weight:800;letter-spacing:.04em}}
.news-copy h2{{margin:4px 0 6px;font:800 28px/1.1 Barlow,sans-serif}}
.news-copy p{{margin:0;color:#a5a19b;font-size:15px;line-height:1.45}}
@media(max-width:700px){{h1{{font-size:40px}}.news-item{{grid-template-columns:1fr}}.news-item img{{width:100%;height:180px}}}}
</style>
</head>
<body>
<header><div class="shell"><a href="/"><img src="/logo.png" alt="Full Court Buckets"></a><nav aria-label="Main"><a href="/">Home</a></nav></div></header>
<main class="shell">
<nav class="breadcrumbs" aria-label="Breadcrumb"><a href="/">Home</a><span aria-hidden="true">/</span><span>News</span></nav>
<h1>WNBA news</h1>
<p class="intro">{esc(NEWS_INTRO)}</p>
<ol class="news-list">{cards}</ol>
</main>
</body>
</html>
'''


def assemble_news_pages(root: Path) -> dict[str, str]:
    """Article HTML at news/<slug>/, redirect stubs at the old root paths, and the /news/ hub."""
    articles = ensure_article_urls(root)
    pages = {}
    for article in articles:
        slug = article_slug(article)
        pages[f'news/{slug}/index.html'] = prepare_article_page(root, article, articles)
        pages[f'{slug}/index.html'] = redirect_stub(article)
    pages['news/index.html'] = render_news_hub(articles)
    return pages


def sync_news_sitemap(text: str, articles: list) -> str:
    """New post URLs and /news/ stay. Old root post URLs go."""
    if '</urlset>' not in text:
        return text
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
