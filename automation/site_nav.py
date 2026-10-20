#!/usr/bin/env python3
"""The only main-menu source for fullcourtbuckets.com.

Every generator and hand-written page renders this module. Do not add a second
menu in a template. Submenu links are plain HTML; site_nav.js only toggles the
mobile panel. News is one link to /news/. Do not put posts in the menu.
Couples is a news feature reached from the News page only. Never make it a
menu item, and never put it in player or stats navigation.
"""
from __future__ import annotations

import html
import json
from pathlib import Path
import re

import internal_links as links
import rss_feed
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
    '<a href="/how-we-make-full-court-buckets/">How we make Full Court Buckets</a>'
    '<a href="/contact/">Contact</a>'
    '<a href="/privacy/">Privacy Policy</a>'
    '<a href="/terms/">Terms of Use</a>'
    '<a href="/sitemap/">Site map</a>'
    '<a href="/privacy/" onclick="if(window.googlefc&amp;&amp;googlefc.showRevocationMessage){googlefc.showRevocationMessage();return false;}">Privacy and cookie settings</a>'
    '<a href="/privacy/#us-state-privacy">Do not sell or share my personal information</a>'
    f'{links.TIKTOK_FOOTER_LINK}</p>'
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
    if linking['by_id']:
        planned.add('wnba/teams/index.html')
    for slot in linking['by_id'].values():
        planned.add(f'wnba/teams/{slot["slug"]}/index.html')
    for relative in (
        'standings/index.html',
        'about/index.html',
        'how-we-make-full-court-buckets/index.html',
        'contact/index.html',
        'privacy/index.html',
        'terms/index.html',
        '404.html',
    ):
        if (root / relative).is_file():
            planned.add(relative)
    planned.add('news/index.html')
    planned.add(links.AUTHOR_PAGE)
    for article in links.load_articles(root):
        slug = article.get('slug') or ''
        if slug:
            planned.add(f'news/{slug}/index.html')
    return planned


def latest_playoffs_href(root: Path) -> str:
    """Newest playoff story. Empty when the postseason coverage is not on disk."""
    playoffs = []
    for article in links.load_articles(root):
        category = str(article.get('category') or '')
        if 'playoff' not in category.casefold():
            continue
        try:
            href = links.article_href(article)
        except ValueError:
            continue
        playoffs.append((str(article.get('date') or ''), href))
    if not playoffs:
        return ''
    playoffs.sort()
    return playoffs[-1][1]


def build_menu(root: Path, planned: set[str] | None = None) -> list[dict]:
    """Top-level menu. A link is included only when the target page exists."""
    def exists(url: str) -> bool:
        return _exists(root, url, planned)

    items: list[dict] = []
    if exists('/'):
        items.append({'label': 'Home', 'href': '/'})

    # One link. Posts stay on /news/ and are never added to this menu.
    # Couples is a news feature reached from /news/ only. Do not add it here.
    if exists('/news/'):
        items.append({'label': 'News', 'href': '/news/'})

    playoffs = latest_playoffs_href(root)
    if playoffs and exists(playoffs):
        items.append({'label': 'Playoffs', 'href': playoffs, 'highlight': True})

    if exists('/wnba/'):
        children = [{'label': 'Player index, A to Z', 'href': '/wnba/'}]
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
        if exists('/wnba/teams/'):
            parent = '/wnba/teams/'
        elif exists('/wnba/'):
            parent = '/wnba/#teams'
        else:
            parent = team_children[0]['href']
        items.append({'label': 'Teams', 'href': parent, 'children': team_children})

    if exists('/standings/'):
        items.append({'label': 'Standings', 'href': '/standings/'})

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
        highlight = ' site-nav-playoffs' if item.get('highlight') and not nested else ''
        if children and not nested:
            sub = _list(children, current, nested=True).replace('<ul>', f'<ul id="{esc(_submenu_id(item["label"]))}">', 1)
            parts.append(f'<li class="site-nav-branch{highlight}">{link}{_subtoggle(item["label"])}{sub}</li>')
        else:
            sub = _list(children, current, nested=True) if children else ''
            klass = f' class="{highlight.strip()}"' if highlight else ''
            parts.append(f'<li{klass}>{link}{sub}</li>')
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


LOGO_HTML = (
    '<a class="site-brand" href="/" aria-label="Full Court Buckets home">'
    '<picture><source srcset="/logo.svg" type="image/svg+xml"><source srcset="/logo-c.webp" type="image/webp">'
    '<img src="/logo-c.png" alt="Full Court Buckets" width="480" height="416" decoding="async">'
    '</picture></a>'
)
TAGLINE_HTML = (
    '<p class="site-tagline"><span>WNBA News · Analysis · Commentary</span>'
    '<span>Independent WNBA news and analysis</span></p>'
)
OLD_SEARCH_HTML = (
    '<div class="site-search">'
    '<button type="button" class="site-search-toggle" aria-expanded="false" aria-controls="site-search-panel">'
    '<span class="site-search-icon" aria-hidden="true"></span>'
    '<span class="site-search-label">Search</span></button>'
    '<div class="site-search-panel" id="site-search-panel" hidden>'
    '<form role="search">'
    '<label class="site-search-field">Search Full Court Buckets'
    '<input type="search" name="q" placeholder="Players, teams, stories" autocomplete="off"></label>'
    '</form>'
    '<p class="site-search-status" role="status"></p>'
    '<ul class="site-search-results"></ul>'
    '</div>'
    '<template id="site-search-item"><li><a><span class="site-search-title"></span><span class="site-search-kind"></span></a></li></template>'
    '</div>'
)
# Header search. Results, groups and highlights are cloned from these templates (no innerHTML).
SEARCH_HTML = (
    '<div class="site-search">'
    '<button type="button" class="site-search-toggle" aria-expanded="false" aria-controls="site-search-panel" aria-keyshortcuts="/">'
    '<span class="site-search-icon" aria-hidden="true"></span>'
    '<span class="site-search-label">Search</span></button>'
    '<div class="site-search-panel" id="site-search-panel" hidden>'
    '<form role="search" action="/search/">'
    '<label class="site-search-field">Search Full Court Buckets'
    '<input type="search" name="q" placeholder="Players, teams, owners, stories" autocomplete="off" spellcheck="false"'
    ' role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="site-search-list"></label>'
    '</form>'
    '<p class="site-search-status" role="status"></p>'
    '<p class="ss-dym" hidden>Did you mean <a href="/search/"></a>?</p>'
    '<ul class="site-search-results" id="site-search-list" role="listbox"></ul>'
    '<a class="ss-all" href="/search/" hidden>See all results</a>'
    '</div>'
    '<template id="site-search-item"><li class="ss-item" role="option"><a class="ss-link">'
    '<span class="ss-thumb"><img alt="" width="48" height="27" loading="lazy" decoding="async"></span>'
    '<span class="ss-text"><span class="site-search-title"></span><span class="ss-snippet"></span>'
    '<span class="site-search-kind"></span></span></a></li></template>'
    '<template id="site-search-group"><li class="ss-group" role="presentation"></li></template>'
    '<template id="site-search-mark"><mark></mark></template>'
    '</div>'
)


def upgrade_search_markup(page_html: str) -> str:
    """Swap the old header search block for the current one."""
    return page_html.replace(OLD_SEARCH_HTML, SEARCH_HTML)


def render_header(menu: list[dict], current: str, show_tagline: bool | None = None) -> str:
    """One 60px bar for every template. The tagline is homepage-only and hidden on phones."""
    if show_tagline is None:
        show_tagline = page_path(current) == '/'
    tagline = TAGLINE_HTML if show_tagline else ''
    return (
        '<header class="site-header"><div class="site-bar">'
        f'{LOGO_HTML}<div class="site-tools">{SEARCH_HTML}{render(menu, current)}'
        f'</div></div>{tagline}</header>'
    )


def _element_end(html: str, start: int, tag: str) -> int | None:
    """End offset of the element that starts at `start`, counting nested copies of the same tag."""
    lower = html.lower()
    open_token = f'<{tag}'
    close_token = f'</{tag}>'
    if not lower.startswith(open_token, start):
        return None
    depth = 0
    i = start
    while i < len(html):
        opened = lower.find(open_token, i)
        closed = lower.find(close_token, i)
        if closed < 0:
            return None
        if opened != -1 and opened < closed:
            depth += 1
            i = opened + len(open_token)
        else:
            depth -= 1
            i = closed + len(close_token)
            if depth == 0:
                return i
    return None


def _drop_div_touching(html: str, class_name: str, *, before_header: bool) -> str:
    """Remove a chrome div that sits directly against the site header."""
    token = f'<div class="{class_name}">'
    start = 0
    while True:
        at = html.find(token, start)
        if at < 0:
            return html
        end = _element_end(html, at, 'div')
        if end is None:
            return html
        if before_header and html[end:].lstrip().lower().startswith('<header'):
            return html[:at] + html[end:].lstrip()
        if not before_header and html[:at].rstrip().lower().endswith('</header>'):
            return html[:at].rstrip() + html[end:]
        start = at + len(token)


def replace_site_header(page_html: str, menu: list[dict], current: str) -> str:
    """Swap whatever header this template used for the shared bar. Leave the Now ticker in place."""
    if 'http-equiv="refresh"' in page_html.lower():
        return page_html
    header = render_header(menu, current)
    page_html = _drop_div_touching(page_html, 'brand-line', before_header=True)
    page_html = _drop_div_touching(page_html, 'utility', before_header=True)
    start = page_html.lower().find('<header')
    if start < 0:
        if '<body>' in page_html:
            return page_html.replace('<body>', '<body>' + header, 1)
        if '<body' in page_html.lower():
            end = page_html.lower().find('>', page_html.lower().find('<body')) + 1
            return page_html[:end] + header + page_html[end:]
        return header + page_html
    end = _element_end(page_html, start, 'header')
    if end is None:
        return page_html
    page_html = page_html[:start] + header + page_html[end:]
    return _drop_div_touching(page_html, 'tagline', before_header=False)


def build_search_index(root: Path) -> dict:
    """Every indexable page on disk (see search_index.py)."""
    import search_index
    return search_index.build(root)


def search_index_document(root: Path, pending: dict | None = None) -> str:
    """Compact JSON the header search lazy-loads from /search-index.json.

    pending: pages a generator is about to write ({relative path: html})."""
    import search_index
    search_index.write_search_page(root)
    return search_index.document(root, pending=pending)


def normalize(nav_html: str) -> str:
    return re.sub(r' aria-current="page"', '', nav_html)


def extract_main_nav(page_html: str) -> list[str]:
    return MAIN_NAV_RE.findall(page_html)


PINTEREST_VERIFY_TAG = (
    '<meta name="p:domain_verify" content="31768ba4e5e82ef772093f8a448d1884"/>'
)


def ensure_pinterest_verify(page_html: str) -> str:
    if 'name="p:domain_verify"' in page_html or '</head>' not in page_html:
        return page_html
    return page_html.replace('</head>', PINTEREST_VERIFY_TAG + '</head>', 1)


ICON_LINKS = (
    '<link rel="icon" href="/favicon.ico" sizes="48x48">'
    '<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png">'
    '<link rel="apple-touch-icon" href="/apple-touch-icon.png">'
    '<link rel="manifest" href="/site.webmanifest">'
)


def ensure_icons(page_html: str) -> str:
    if '/site.webmanifest' in page_html or '</head>' not in page_html:
        return page_html
    return page_html.replace('</head>', ICON_LINKS + '</head>', 1)


FONTS_LINK = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
              '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
              '<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@500;600;700;800'
              '&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">')


def ensure_fonts(page_html: str) -> str:
    """The shared header is set in Barlow/Inter; every page must load them."""
    if 'family=Barlow:' in page_html or '</head>' not in page_html:
        return page_html
    return page_html.replace('</head>', FONTS_LINK + '</head>', 1)


def ensure_assets(page_html: str) -> str:
    page_html = ensure_fonts(page_html)
    page_html = rss_feed.ensure_link(page_html)
    page_html = ensure_pinterest_verify(page_html)
    if '/assets/site-nav.css' not in page_html:
        if '</head>' in page_html:
            page_html = page_html.replace('</head>', STYLESHEET + '</head>', 1)
        else:
            page_html = STYLESHEET + page_html
    if '/assets/site-nav.js' not in page_html and '</body>' in page_html:
        page_html = page_html.replace('</body>', SCRIPT + '</body>', 1)
    page_html = page_html.replace('nav{display:none}', 'nav:not(.site-nav){display:none}')
    page_html = apply_now_bar(page_html)
    page_html = ensure_icons(page_html)
    page_html = upgrade_search_markup(page_html)
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
    """Put the shared header on the page. Leave the on-page section nav alone."""
    page_html = replace_site_header(page_html, menu, current)
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


# ---- Sitewide Now bar: one shared value from data/now-ticker.json ----
import datetime as _dt
import html as _html
import json as _json

NOW_PATH = Path(__file__).resolve().parents[1] / 'data' / 'now-ticker.json'
NOW_RE = re.compile(r'<div class="ticker\b[^>]*>.*?</div></div></div>', re.S)


def load_now() -> dict:
    return _json.loads(NOW_PATH.read_text(encoding='utf-8'))


def now_item(now: _dt.datetime | None = None) -> dict:
    """The current item, or the evergreen fallback once it has expired."""
    data = load_now()
    moment = now or _dt.datetime.now(_dt.timezone.utc)
    if moment >= _dt.datetime.fromisoformat(data['expires']):
        fb = dict(data['fallback'])
        fb.setdefault('date', data.get('date', ''))
        fb['expired'] = True
        return fb
    return data


def now_bar_html(now: _dt.datetime | None = None) -> str:
    data = load_now()
    item = now_item(now)
    e = lambda v: _html.escape(str(v), quote=True)
    fb = data['fallback']
    return (
        f'<div class="ticker fcb-now" data-item-date="{e(data.get("date", ""))}" data-expires="{e(data["expires"])}" '
        f'data-fallback-text="{e(fb["text"])}" data-fallback-url="{e(fb["url"])}">'
        '<div class="shell ticker-shell"><div class="ticker-label">Now</div>'
        f'<div class="ticker-text"><a href="{e(item["url"])}">{e(item["text"])}</a></div></div></div>'
    )


def apply_now_bar(page_html: str, now: _dt.datetime | None = None) -> str:
    """Remove any page-specific ticker and put the shared one right after the site header."""
    if 'site-header' not in page_html:
        return page_html
    stripped = NOW_RE.sub('', page_html)
    end = stripped.find('</header>', stripped.find('site-header'))
    if end < 0:
        return page_html
    end += len('</header>')
    return stripped[:end] + now_bar_html(now) + stripped[end:]
