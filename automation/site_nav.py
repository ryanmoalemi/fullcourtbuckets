#!/usr/bin/env python3
"""The only main-menu source for fullcourtbuckets.com.

Every generator and hand-written page renders this module. Do not add a second
menu in a template. Submenu links are plain HTML; site_nav.js only toggles the
mobile panel.
"""
from __future__ import annotations

import html
import json
from pathlib import Path
import re

import internal_links as links
from link_graph import file_for_url, iter_html, page_url

HERE = Path(__file__).resolve().parent
CSS_TEXT = (HERE / 'site_nav.css').read_text(encoding='utf-8')
JS_TEXT = (HERE / 'site_nav.js').read_text(encoding='utf-8')

# Real profile pages only. There is no separate rookies or top-players hub.
FEATURED_PLAYERS = (
    'aja-wilson',
    'caitlin-clark',
    'angel-reese',
    'paige-bueckers',
    'breanna-stewart',
    'sabrina-ionescu',
)

STYLESHEET = '<link rel="stylesheet" href="/assets/site-nav.css">'
SCRIPT = '<script src="/assets/site-nav.js" defer></script>'
NAV_RE = re.compile(r'<nav\b([^>]*)>.*?</nav>', re.S)
MAIN_NAV_RE = re.compile(r'<nav\b[^>]*aria-label="Main"[^>]*>.*?</nav>', re.S)
FOOTER_RE = re.compile(r'<footer\b[^>]*>.*?</footer>', re.S)
# The footer already used on player pages. Do not restyle it.
FOOTER_HTML = (
    '<footer class="site-footer"><div class="wrap"><p><b>Full Court Buckets</b>. '
    'Independent WNBA news, analysis and commentary. Not affiliated with or endorsed by the WNBA.</p>'
    '<p class="footer-links"><a href="/wnba/">Players</a>'
    '<a href="/standings/">Standings</a>'
    '<a href="/about/">About</a>'
    '<a href="/contact/">Contact</a>'
    '<a href="/privacy/">Privacy Policy</a>'
    '<a href="/terms/">Terms of Use</a>'
    '<a href="/privacy/" onclick="if(window.googlefc&amp;&amp;googlefc.showRevocationMessage){googlefc.showRevocationMessage();return false;}">Privacy and cookie settings</a>'
    '<a href="/privacy/#us-state-privacy">Do not sell or share my personal information</a></p>'
    '<p>&copy; 2026 Full Court Buckets</p></div></footer>'
)
EM_DASH = '\u2014'


def esc(value) -> str:
    return html.escape('' if value is None else str(value), quote=True)


def page_path(href: str) -> str:
    href = (href or '').split('?', 1)[0]
    return href.split('#', 1)[0] or '/'


def is_current(href: str, current: str) -> bool:
    """Exact page match. Fragment links such as /#latest are not the page itself."""
    if '#' in (href or ''):
        return False
    return page_path(href) == (current or '/')


def _exists(root: Path, url: str, planned: set[str] | None) -> bool:
    path = page_path(url)
    if file_for_url(root, path) is not None:
        return True
    if not planned:
        return False
    rel = path.lstrip('/')
    key = 'index.html' if rel == '' else (rel + 'index.html' if path.endswith('/') else rel)
    return key in planned


def _player_names(root: Path) -> dict[str, str]:
    path = root / 'data' / 'wnba' / 'players-index.json'
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    names = {}
    for entry in data.get('players') or []:
        slug = entry.get('slug')
        name = str(entry.get('name') or '').strip()
        if slug and name:
            names[slug] = name
    return names


def planned_paths(root: Path, index: dict, linking: dict) -> set[str]:
    """Files this build will publish, plus static pages already on disk."""
    planned = {'index.html', 'wnba/index.html'}
    for entry in index.get('players') or []:
        slug = entry.get('slug') or ''
        if slug:
            planned.add(f'wnba/{slug}/index.html')
    for slot in linking['by_id'].values():
        planned.add(f'wnba/teams/{slot["slug"]}/index.html')
    for relative in (
        'standings/index.html',
        'about/index.html',
        'contact/index.html',
        'privacy/index.html',
        'terms/index.html',
        '404.html',
    ):
        if (root / relative).is_file():
            planned.add(relative)
    planned.add('news/index.html')
    for article in links.load_articles(root):
        slug = article.get('slug') or ''
        if slug:
            planned.add(f'news/{slug}/index.html')
    return planned


def build_menu(root: Path, planned: set[str] | None = None) -> list[dict]:
    """Top-level menu. A link is included only when the target page exists."""
    def exists(url: str) -> bool:
        return _exists(root, url, planned)

    items: list[dict] = []
    if exists('/'):
        items.append({'label': 'Home', 'href': '/'})

    if exists('/wnba/'):
        children = [{'label': 'Player index, A to Z', 'href': '/wnba/'}]
        if exists('/wnba/couples/'):
            children.append({'label': 'Couples', 'href': '/wnba/couples/'})
        names = _player_names(root)
        for slug in FEATURED_PLAYERS:
            href = f'/wnba/{slug}/'
            label = names.get(slug)
            if label and exists(href):
                children.append({'label': label, 'href': href})
        items.append({'label': 'Players', 'href': '/wnba/', 'children': children})

    index_path = root / 'data' / 'wnba' / 'players-index.json'
    team_children = []
    if index_path.is_file():
        index = json.loads(index_path.read_text(encoding='utf-8'))
        linking = links.catalog_from_index(index)
        for slot in sorted(linking['by_id'].values(), key=lambda slot: slot['full_name'].casefold()):
            href = links.team_href(slot)
            if exists(href):
                team_children.append({'label': slot['full_name'], 'href': href})
    if team_children:
        parent = '/wnba/#teams' if exists('/wnba/') else team_children[0]['href']
        items.append({'label': 'Teams', 'href': parent, 'children': team_children})

    if exists('/standings/'):
        items.append({'label': 'Standings', 'href': '/standings/'})

    news_children = []
    articles = sorted(
        links.load_articles(root),
        key=lambda article: article.get('date') or '',
        reverse=True,
    )
    for article in articles:
        slug = article.get('slug') or ''
        title = str(article.get('title') or '').strip()
        href = links.article_href(article)
        if slug and title and exists(href):
            news_children.append({'label': title, 'href': href})
    if exists('/news/') or news_children:
        parent = '/news/' if exists('/news/') else news_children[0]['href']
        items.append({'label': 'News', 'href': parent, 'children': news_children})

    if exists('/about/'):
        children = []
        if exists('/contact/'):
            children.append({'label': 'Contact', 'href': '/contact/'})
        items.append({'label': 'About', 'href': '/about/', 'children': children})
    elif exists('/contact/'):
        items.append({'label': 'Contact', 'href': '/contact/'})

    for label in iter_labels(items):
        if EM_DASH in label:
            raise ValueError('Menu label contains an em dash.')
    return items


def iter_labels(items: list[dict]):
    for item in items:
        yield item['label']
        yield from iter_labels(item.get('children') or [])


def iter_hrefs(items: list[dict]):
    for item in items:
        yield item['href']
        yield from iter_hrefs(item.get('children') or [])


def _submenu_id(label: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', label.casefold()).strip('-') or 'section'
    return f'site-nav-sub-{slug}'


def _subtoggle(label: str) -> str:
    """Separate 44px control. The parent item stays an ordinary link."""
    return (
        f'<button type="button" class="site-nav-subtoggle" aria-expanded="false" '
        f'aria-controls="{esc(_submenu_id(label))}" data-section="{esc(label)}">'
        '<span class="site-nav-chevron" aria-hidden="true"></span>'
        f'<span class="site-nav-subtoggle-label">Show {esc(label)} menu</span>'
        '</button>'
    )


def _list(items: list[dict], current: str, nested: bool = False) -> str:
    parts = []
    for item in items:
        current_attr = ' aria-current="page"' if is_current(item['href'], current) else ''
        children = item.get('children') or []
        # Site chrome stays in this tab. New tabs are for article-body links only.
        link = f'<a href="{esc(item["href"])}"{current_attr}>{esc(item["label"])}</a>'
        if children and not nested:
            sub = _list(children, current, nested=True).replace('<ul>', f'<ul id="{esc(_submenu_id(item["label"]))}">', 1)
            parts.append(f'<li class="site-nav-branch">{link}{_subtoggle(item["label"])}{sub}</li>')
        else:
            sub = _list(children, current, nested=True) if children else ''
            parts.append(f'<li>{link}{sub}</li>')
    return '<ul>' + ''.join(parts) + '</ul>'


def render(menu: list[dict], current: str) -> str:
    """Server-rendered menu. The button only toggles; it does not create links."""
    inner = _list(menu, current or '/').replace('<ul>', '<ul id="site-nav-menu">', 1)
    return (
        '<nav class="site-nav" aria-label="Main">'
        '<button type="button" class="site-nav-toggle" aria-expanded="false" aria-controls="site-nav-menu">'
        '<span class="site-nav-bars" aria-hidden="true"></span>'
        '<span class="site-nav-toggle-label">Menu</span>'
        '</button>'
        f'{inner}'
        '</nav>'
    )


def normalize(nav_html: str) -> str:
    return re.sub(r' aria-current="page"', '', nav_html)


def extract_main_nav(page_html: str) -> list[str]:
    return MAIN_NAV_RE.findall(page_html)


def ensure_assets(page_html: str) -> str:
    if '/assets/site-nav.css' not in page_html:
        if '</head>' in page_html:
            page_html = page_html.replace('</head>', STYLESHEET + '</head>', 1)
        else:
            page_html = STYLESHEET + page_html
    if '/assets/site-nav.js' not in page_html and '</body>' in page_html:
        page_html = page_html.replace('</body>', SCRIPT + '</body>', 1)
    page_html = page_html.replace('nav{display:none}', 'nav:not(.site-nav){display:none}')
    return page_html


def footer_html(include_standings: bool = True) -> str:
    """Same footer everywhere. The standings link is omitted only when that page is absent."""
    if include_standings:
        return FOOTER_HTML
    return FOOTER_HTML.replace('<a href="/standings/">Standings</a>', '', 1)


def install_footer(page_html: str) -> str:
    """Replace whatever footer is on the page with the shared one. Add it if missing."""
    if FOOTER_RE.search(page_html):
        return FOOTER_RE.sub(FOOTER_HTML, page_html, count=1)
    if '</body>' in page_html:
        return page_html.replace('</body>', FOOTER_HTML + '</body>', 1)
    return page_html + FOOTER_HTML


_ANCHOR_RE = re.compile(r'<a\b[^>]*>', re.I)
_CHROME_REGION_RE = re.compile(
    r'<(header|footer|nav)\b[^>]*>.*?</\1>'
    r'|<(div|p)\b[^>]*\bclass\s*=\s*(["\'])[^"\']*\b(?:breadcrumb|breadcrumbs)\b[^"\']*\3[^>]*>.*?</\2>',
    re.I | re.S,
)
_SCRIPT_OR_STYLE_RE = re.compile(r'(<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>)', re.I | re.S)
_INTERNAL_HOSTS = {'fullcourtbuckets.com', 'www.fullcourtbuckets.com'}


def _is_internal_href(href: str) -> bool:
    """Same-site chrome links. Off-site links may still open in a new tab."""
    value = (href or '').strip()
    if value.startswith(('#', '/')) or value == '':
        return True
    lowered = value.casefold()
    if lowered.startswith(('mailto:', 'tel:', 'javascript:')):
        return False
    if lowered.startswith(('http://', 'https://', '//')):
        host = value.split('/')[2].split('@')[-1].split(':')[0].casefold() if '//' in value else ''
        return host in _INTERNAL_HOSTS
    return True


def _strip_new_tab(tag: str) -> str:
    href = re.search(r'\bhref\s*=\s*(["\'])([^"\']*)\1', tag, re.I)
    if href and not _is_internal_href(href.group(2)):
        return tag
    if not re.search(r'\btarget\s*=\s*(["\']?)_blank\1', tag, re.I):
        return tag
    tag = re.sub(r'\s+target\s*=\s*(["\']?)_blank\1', '', tag, count=1, flags=re.I)
    tag = re.sub(r'\s+rel\s*=\s*(["\'])noopener(?:\s+noreferrer)?\1', '', tag, count=1, flags=re.I)
    return tag


def strip_chrome_new_tabs(page_html: str) -> str:
    """Nav, header, footer, and breadcrumbs stay in this tab.

    A post-publish pass added target=_blank to site chrome. Article-body links
    are outside these regions and keep the new-tab behavior.
    """
    def region(match: re.Match) -> str:
        parts = _SCRIPT_OR_STYLE_RE.split(match.group(0))
        cleaned = []
        for part in parts:
            lowered = part[:7].casefold()
            if lowered.startswith('<script') or lowered.startswith('<style'):
                cleaned.append(part)
            else:
                cleaned.append(_ANCHOR_RE.sub(lambda anchor: _strip_new_tab(anchor.group(0)), part))
        return ''.join(cleaned)

    return _CHROME_REGION_RE.sub(region, page_html)


def install(page_html: str, current: str, menu: list[dict]) -> str:
    """Replace the first main nav. Leave the on-page section nav alone."""
    rendered = render(menu, current)
    replaced = False

    def sub(match: re.Match) -> str:
        nonlocal replaced
        if replaced:
            return match.group(0)
        attrs = match.group(1)
        if 'section-nav' in attrs or 'On this page' in attrs:
            return match.group(0)
        replaced = True
        return rendered

    page_html = NAV_RE.sub(sub, page_html)
    if not replaced:
        if '</header>' in page_html:
            page_html = page_html.replace('</header>', rendered + '</header>', 1)
        elif '<body>' in page_html:
            page_html = page_html.replace('<body>', '<body>' + rendered, 1)
        else:
            page_html = rendered + page_html
    return strip_chrome_new_tabs(install_footer(ensure_assets(page_html)))


def install_tree(root: Path, menu: list[dict], skip: set[str]) -> dict[str, str]:
    """Refresh every HTML page that this build is not already rewriting."""
    updates = {}
    for path in iter_html(root):
        rel = path.relative_to(root).as_posix()
        if rel in skip:
            continue
        original = path.read_text(encoding='utf-8')
        updated = install(original, page_url(path.relative_to(root)), menu)
        if updated != original:
            updates[rel] = updated
    return updates
