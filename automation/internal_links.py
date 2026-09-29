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

from link_graph import file_for_url, normalize_href

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
                'slug': team_slug(full),
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
        extra += '<a href="/wnba/" target="_blank" rel="noopener">Players</a>'
    if 'href="/standings/"' not in block and "href='/standings/'" not in block:
        extra += '<a href="/standings/" target="_blank" rel="noopener">Standings</a>'
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
    slug = article['slug']
    title = article['title']
    image = article.get('image') or ''
    alt = article.get('imageAlt') or title
    return (
        f'<a class="article-card" href="/{esc(slug)}/" target="_blank" rel="noopener">'
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
            lambda match: match.group(1) + '/' + featured['slug'] + '/' + match.group(2),
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
    return text


def _pct(value) -> str:
    try:
        return f'{float(value):.3f}'.replace('0.', '.', 1) if float(value) < 1 else f'{float(value):.3f}'
    except (TypeError, ValueError):
        return ''


def apply_standings(text: str, linking: dict, standings: dict) -> str:
    text = ensure_footer_hubs(text)
    by_name = {slot['full_name']: team_href(slot) for slot in linking['by_id'].values()}
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
        name = str(team.get('name') or '')
        href = by_name.get(name)
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
    return text


def ensure_sitemap(text: str, urls: list[str], base: str) -> str:
    if '</urlset>' not in text:
        return text
    for url in urls:
        loc = base + url
        if loc in text:
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
        r'<a class="(?:inline-link|team-name|coverage-card|article-card)" href="(/[^"]+|https?://[^"]+)"',
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
