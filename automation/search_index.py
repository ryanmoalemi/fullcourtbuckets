"""Static site search index, built from every published page on disk.

Crawls each indexable ``index.html`` (skips noindex pages, redirect stubs and
embeds), so any page a generator or the publisher writes is searchable on the
next build. Writes ``/search-index.json`` and small thumbnails under
``/images/search-thumbs/``.

Item keys are short to keep the lazy-loaded index small:
  t title, u url, k type, d date (YYYY-MM-DD), s snippet, w keywords,
  b body words, i thumbnail, c 1 = circle (person)
"""
from __future__ import annotations

import hashlib
import html as htmllib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THUMB_DIR = 'images/search-thumbs'
THUMB_PX = 96
SKIP_PREFIXES = ('review/', 'portrait-', 'docs/', 'content/', 'data/', 'automation/', 'assets/',
                 'images/', 'api/', 'projects/', '.')
SITE_SUFFIX_RE = re.compile(r'\s*[|\u2013\u2014-]\s*Full Court Buckets\s*$', re.I)
STOP = set('''a an and are as at be been but by for from has have he her his in into is it its of on or our
she that the their them there they this to was were will with you your we not no than then so if about
after before over up out all more most also can just who what when where which while how why one two
three new last first per vs said says game games season player players team teams wnba page full court
buckets fcb'''.split())

TYPE_ORDER = ['Article', 'Player', 'Team', 'Owner', 'Tracker', 'Data', 'Game', 'Couple', 'Person', 'Page']


def _meta(page: str, attr: str, name: str) -> str:
    m = re.search(r'<meta\b[^>]*\b%s\s*=\s*["\']%s["\'][^>]*>' % (attr, re.escape(name)), page, re.I)
    if not m:
        return ''
    c = re.search(r'\bcontent\s*=\s*"([^"]*)"|\bcontent\s*=\s*\'([^\']*)\'', m.group(0), re.I)
    return htmllib.unescape((c.group(1) or c.group(2) or '') if c else '').strip()


def _strip(fragment: str) -> str:
    fragment = re.sub(r'<(script|style|template|svg|noscript)\b.*?</\1>', ' ', fragment, flags=re.I | re.S)
    fragment = re.sub(r'<[^>]+>', ' ', fragment)
    return re.sub(r'\s+', ' ', htmllib.unescape(fragment)).strip()


def _main_region(page: str) -> str:
    m = re.search(r'<main\b.*?</main>', page, re.I | re.S)
    if m:
        return m.group(0)
    body = re.search(r'<body\b.*?</body>', page, re.I | re.S)
    region = body.group(0) if body else page
    return re.sub(r'<(header|footer|nav)\b.*?</\1>', ' ', region, flags=re.I | re.S)


def _type_for(url: str, page: str) -> str:
    if url.startswith('/wnba/owners/'):
        return 'Owner'
    if url.startswith('/wnba/where-to-watch/'):
        return 'Data'
    if 'tracker' in url:
        return 'Tracker'
    if url.startswith('/news/'):
        return 'Article'
    if url.startswith('/wnba/teams/'):
        return 'Team'
    if url.startswith('/wnba/couples/') or 'relatives' in url:
        return 'Couple'
    if url.startswith('/wnba/finals/') or 'play-by-play' in url:
        return 'Game'
    if url.startswith('/authors/'):
        return 'Person'
    if 'player-illustration' in page or re.search(r'"@type"\s*:\s*"Person"', page) and url.count('/') == 3 and url.startswith('/wnba/'):
        return 'Player'
    if url.startswith(('/standings/', '/wnba/viewership', '/wnba/')) or '<table' in page:
        return 'Data'
    return 'Page'


def _image_for(page: str, kind: str) -> str:
    if kind == 'Player':
        m = re.search(r'<img\b[^>]*class="[^"]*player-illustration[^"]*"[^>]*\bsrc="([^"]+)"', page)
        if m:
            return m.group(1)
    og = _meta(page, 'property', 'og:image')
    if og:
        return re.sub(r'^https?://(www\.)?fullcourtbuckets\.com', '', og)
    for m in re.finditer(r'<img\b[^>]*\bsrc="(/images/[^"]+)"', _main_region(page)):
        return m.group(1)
    return ''


def _thumb(root: Path, src: str, circle: bool, used: set) -> str:
    """96px webp thumbnail (square crop from the top for people, 16:9 otherwise)."""
    if not src.startswith('/'):
        return ''
    path = root / src.split('?')[0].lstrip('/')
    if not path.is_file():
        return ''
    key = hashlib.sha1(f'{src.split("?")[0]}|{path.stat().st_size}|{circle}'.encode()).hexdigest()[:16]
    rel = f'{THUMB_DIR}/{key}.webp'
    used.add(rel)
    out = root / rel
    if out.is_file():
        return '/' + rel
    try:
        from PIL import Image
    except ImportError:
        return src
    try:
        with Image.open(path) as im:
            im = im.convert('RGBA')
            w, h = im.size
            if circle:
                side = min(w, h)
                box = ((w - side) // 2, 0, (w - side) // 2 + side, side)
                size = (THUMB_PX, THUMB_PX)
            else:
                th = int(w * 9 / 16)
                if th <= h:
                    top = int((h - th) * 0.2)
                    box = (0, top, w, top + th)
                else:
                    tw = int(h * 16 / 9)
                    box = ((w - tw) // 2, 0, (w - tw) // 2 + tw, h)
                size = (THUMB_PX * 16 // 9, THUMB_PX)
            im = im.crop(box).resize(size, Image.LANCZOS)
            bg = Image.new('RGBA', im.size, (255, 255, 255, 255))
            bg.alpha_composite(im)
            out.parent.mkdir(parents=True, exist_ok=True)
            bg.convert('RGB').save(out, 'WEBP', quality=72, method=6)
    except Exception:
        used.discard(rel)
        return ''
    return '/' + rel


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9'’]*", text.lower())


def _date(page: str) -> str:
    for pat in (r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})', r'article:published_time"\s+content="(\d{4}-\d{2}-\d{2})',
                r'"dateModified"\s*:\s*"(\d{4}-\d{2}-\d{2})'):
        m = re.search(pat, page)
        if m:
            return m.group(1)
    return ''


def page_entry(root: Path, rel: str, page: str, used: set) -> dict | None:
    head = page[:20000]
    if re.search(r'<meta\b[^>]*name="robots"[^>]*noindex', head, re.I) or 'http-equiv="refresh"' in head.lower():
        return None
    url = '/' + rel[:-len('index.html')]
    title_m = re.search(r'<title>(.*?)</title>', page, re.I | re.S)
    h1_m = re.search(r'<h1\b[^>]*>(.*?)</h1>', page, re.I | re.S)
    title = _strip(h1_m.group(1)) if h1_m else ''
    if not title or len(title) > 140:
        title = SITE_SUFFIX_RE.sub('', htmllib.unescape(_strip(title_m.group(1)))) if title_m else ''
    if url == '/':
        title = 'Full Court Buckets home'
    if not title:
        return None
    kind = _type_for(url, page)
    desc = _meta(page, 'name', 'description') or _meta(page, 'property', 'og:description')
    main = _main_region(page)
    heads = ' '.join(_strip(h) for h in re.findall(r'<h[23]\b[^>]*>(.*?)</h[23]>', main, re.I | re.S))
    kw = _meta(page, 'name', 'keywords')
    keywords = ' '.join(dict.fromkeys(w for w in _words(kw + ' ' + heads + ' ' + url.replace('/', ' ').replace('-', ' '))
                                      if w not in STOP and len(w) > 1))[:300]
    counts = Counter(w for w in _words(_strip(main)) if w not in STOP and len(w) > 2 and not w.isdigit())
    title_words = set(_words(title)) | set(keywords.split())
    body = ' '.join(w for w, _ in counts.most_common(70) if w not in title_words)[:400]
    item = {'t': title, 'u': url, 'k': kind}
    d = _date(page) if kind in ('Article', 'Tracker', 'Game', 'Owner', 'Couple', 'Data') else ''
    if d:
        item['d'] = d
    snippet = desc or _strip(main)[:200]
    if len(snippet) > 170:
        snippet = snippet[:167].rsplit(' ', 1)[0] + '…'
    item['s'] = snippet
    if keywords:
        item['w'] = keywords
    if body:
        item['b'] = body
    circle = kind in ('Player', 'Person', 'Owner') and url.count('/') >= 3
    img = _image_for(page, kind)
    if img:
        thumb = _thumb(root, img, circle, used)
        if thumb:
            item['i'] = thumb
            if circle:
                item['c'] = 1
    return item


def iter_pages(root: Path):
    for path in sorted(root.rglob('index.html')):
        rel = path.relative_to(root).as_posix()
        if rel.startswith(SKIP_PREFIXES) or '/embed/' in rel or rel.startswith('search/'):
            continue
        yield rel, path


def build(root: Path = ROOT, prune: bool = False, pending: dict | None = None) -> dict:
    """pending: {relative path: html} a generator is about to write; wins over disk."""
    used: set = set()
    items, seen = [], set()
    pending = {str(k): v for k, v in (pending or {}).items()
               if str(k).endswith('index.html') and isinstance(v, str)}
    rels = {rel: path for rel, path in iter_pages(root)}
    for rel in pending:
        if (rel == 'index.html' or rel.endswith('/index.html')) and not rel.startswith(SKIP_PREFIXES) \
                and '/embed/' not in rel and not rel.startswith('search/'):
            rels.setdefault(rel, root / rel)
    for rel in sorted(rels):
        if rel in pending:
            page = pending[rel]
        else:
            try:
                page = rels[rel].read_text(encoding='utf-8')
            except (OSError, UnicodeDecodeError):
                continue
        entry = page_entry(root, rel, page, used)
        if entry and entry['u'] not in seen:
            seen.add(entry['u'])
            items.append(entry)
    rank = {k: i for i, k in enumerate(TYPE_ORDER)}
    items.sort(key=lambda it: (rank.get(it['k'], 99), it['t'].casefold()))
    if prune:
        thumbs = root / THUMB_DIR
        if thumbs.is_dir():
            for f in thumbs.glob('*.webp'):
                if f'{THUMB_DIR}/{f.name}' not in used:
                    f.unlink()
    return {'v': 2, 'items': items}


def document(root: Path = ROOT, prune: bool = False, pending: dict | None = None) -> str:
    return json.dumps(build(root, prune, pending), separators=(',', ':'), ensure_ascii=False) + '\n'


def write(root: Path = ROOT) -> Path:
    write_search_page(root)
    out = root / 'search-index.json'
    text = document(root, prune=True)
    if not out.is_file() or out.read_text(encoding='utf-8') != text:
        out.write_text(text, encoding='utf-8')
    return out


SEARCH_MAIN = (
    '<main id="search-page">'
    '<h1>Search</h1>'
    '<form id="sp-form" class="sp-form" role="search" action="/search/">'
    '<label class="visually-hidden" for="sp-q" style="position:absolute;left:-9999px">Search Full Court Buckets</label>'
    '<input id="sp-q" type="search" name="q" placeholder="Players, teams, owners, stories" autocomplete="off" spellcheck="false">'
    '<button type="submit">Search</button></form>'
    '<p id="sp-status" class="sp-status" role="status"></p>'
    '<p id="sp-dym" class="ss-dym" hidden>Did you mean <a href="/search/"></a>?</p>'
    '<ul id="sp-results" class="sp-results"></ul>'
    '<noscript><p>Search needs JavaScript. Browse the <a href="/sitemap/">sitemap</a> instead.</p></noscript>'
    '</main>'
)


def write_search_page(root: Path = ROOT) -> Path | None:
    """/search/?q= results page, built on the about page shell (same header, footer, Now bar)."""
    shell_path = root / 'about' / 'index.html'
    if not shell_path.is_file():
        return None
    page = shell_path.read_text(encoding='utf-8')
    page = re.sub(r'<title>.*?</title>', '<title>Search | Full Court Buckets</title>', page, count=1, flags=re.S)
    page = re.sub(r'<meta name="description"[^>]*>',
                  '<meta name="description" content="Search Full Court Buckets players, teams, owners, trackers and stories.">', page, count=1)
    page = re.sub(r'<link rel="canonical"[^>]*>', '<link rel="canonical" href="https://fullcourtbuckets.com/search/">', page, count=1)
    page = re.sub(r'<meta name="robots"[^>]*>', '', page)
    page = page.replace('</head>', '<meta name="robots" content="noindex,follow"></head>', 1)
    page = re.sub(r'<script type="application/ld\+json">.*?</script>', '', page, flags=re.S)
    import social_meta
    page = social_meta.BLOCK_RE.sub('', page)
    page = re.sub(r'<meta property="og:[^>]*>|<meta name="twitter:[^>]*>', '', page)
    # Keep the PR #327 share tags (the about shell's block was stripped above).
    page = social_meta.social_block(page, social_meta.default_image_url(), social_meta.DEFAULT_ALT,
                                    social_meta.W, social_meta.H)
    page = re.sub(r'<main\b.*?</main>', lambda _m: SEARCH_MAIN, page, count=1, flags=re.S)
    page = page.replace(' aria-current="page"', '')
    out = root / 'search' / 'index.html'
    out.parent.mkdir(exist_ok=True)
    if not out.is_file() or out.read_text(encoding='utf-8') != page:
        out.write_text(page, encoding='utf-8')
    return out


if __name__ == '__main__':
    write_search_page(ROOT)
    p = write(ROOT)
    data = json.loads(p.read_text(encoding='utf-8'))
    print(f'{p}: {len(data["items"])} items, {p.stat().st_size} bytes',
          dict(Counter(i['k'] for i in data['items'])))

