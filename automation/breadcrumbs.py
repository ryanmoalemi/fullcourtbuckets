"""Visible breadcrumbs + BreadcrumbList JSON-LD on every indexable FCB page.

Owner standing rule: every page has SEO meta, compact visible breadcrumbs above
the H1, matching BreadcrumbList JSON-LD, one H1 and descriptive H2/H3s.

This pass runs after every builder (before social_meta.py) and only fills gaps:

* Page has BreadcrumbList JSON-LD but no visible trail -> render the trail
  from the JSON-LD directly above the H1 (so both always agree).
* Page has a visible trail but no JSON-LD -> add JSON-LD built from it.
* Page has neither -> derive the trail from the URL path, add both.
* Play-by-play pages get Home > WNBA > 2026 Finals > Game N > Play-by-play.
* The homepage gets a compact H1 when it has none (no breadcrumb on Home).

    python automation/breadcrumbs.py           # fix pages
    python automation/breadcrumbs.py --check   # report gaps, exit 1 if any
"""
from __future__ import annotations

import html as htmlmod
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://fullcourtbuckets.com'
SKIP_DIRS = {'.git', '.github', 'automation', 'data', 'portrait-masters', 'portrait-handoff', 'node_modules',
             'review', 'api', 'docs', 'content', 'assets', 'images', 'projects'}
JSONLD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
VISIBLE_RE = re.compile(r'<(nav|div|ol|p)\b[^>]*class="[^"]*\bbreadcrumbs?\b[^"]*"[^>]*>(.*?)</\1>', re.S | re.I)
H1_RE = re.compile(r'<h1[\s>]', re.I)
NOINDEX_RE = re.compile(r'<meta name="robots" content="[^"]*noindex', re.I)
REDIRECT_RE = re.compile(r'http-equiv="?refresh', re.I)
HOME_H1 = 'WNBA news, stats, scores and play-by-play'
FINALS_HUB = '/news/wnba-finals-2026-schedule-dream-valkyries/'
LABELS = {
    '/news/': 'News', '/wnba/': 'WNBA', '/wnba/teams/': 'Teams', '/standings/': 'Standings',
    '/authors/': 'Authors', '/sitemap/': 'Site map', '/search/': 'Search',
}
CSS = ('.breadcrumbs{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:0 0 10px;'
       'font-size:13px;line-height:1.3}.breadcrumbs a{text-decoration:underline}'
       '.home-h1{font-size:15px;font-weight:700;letter-spacing:.4px;margin:12px 0 10px;text-transform:uppercase}')


def esc(s: str) -> str:
    return htmlmod.escape(str(s), quote=True)


def is_indexable(text: str) -> bool:
    return '</head>' in text and not NOINDEX_RE.search(text) and not REDIRECT_RE.search(text)


def iter_pages(root: Path):
    for p in sorted(root.rglob('index.html')):
        rel = p.relative_to(root)
        if rel.parts and rel.parts[0] in SKIP_DIRS:
            continue
        yield p, '/' + rel.as_posix().removesuffix('index.html')


def _walk(node, kind):
    if isinstance(node, dict):
        t = node.get('@type')
        if t == kind or (isinstance(t, list) and kind in t):
            yield node
        for v in node.values():
            yield from _walk(v, kind)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v, kind)


def jsonld_blocks(text: str) -> list:
    out = []
    for raw in JSONLD_RE.findall(text):
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError:
            out.append(None)
    return out


def jsonld_trail(text: str) -> list[tuple[str, str]] | None:
    for data in jsonld_blocks(text):
        for node in _walk(data, 'BreadcrumbList'):
            items = sorted(node.get('itemListElement') or [], key=lambda i: int(i.get('position', 0)))
            trail = []
            for i in items:
                item = i.get('item')
                if isinstance(item, dict):
                    item = item.get('@id') or item.get('url')
                trail.append((str(i.get('name') or ''), str(item or '')))
            return trail
    return None


def visible_trail(text: str) -> list[tuple[str, str]] | None:
    m = VISIBLE_RE.search(text)
    if not m:
        return None
    trail = []
    for a in re.finditer(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>|<span(?![^>]*aria-hidden)[^>]*>(.*?)</span>', m.group(2), re.S):
        href, label, plain = a.group(1), a.group(2), a.group(3)
        name = htmlmod.unescape(re.sub(r'<[^>]+>', '', label if href else plain or '')).strip()
        if not name or name in {'/', '›', '>', '»'}:
            continue
        trail.append((name, (BASE + href if href and href.startswith('/') else href) or ''))
    return trail or None


def _h1_text(text: str) -> str:
    m = re.search(r'<h1[^>]*>(.*?)</h1>', text, re.S | re.I)
    return re.sub(r'\s+', ' ', htmlmod.unescape(re.sub(r'<[^>]+>', ' ', m.group(1)))).strip() if m else ''


def _page_ok(root: Path, rel: str) -> bool:
    p = root / rel.lstrip('/') / 'index.html'
    return p.is_file() and is_indexable(p.read_text(encoding='utf-8', errors='replace'))


def pbp_trail(year: int | str, game: int | str, root: Path = ROOT) -> list[tuple[str, str]]:
    """Home > WNBA > 2026 Finals > Game N > Play-by-play (levels without a live page are skipped)."""
    trail = [('Home', BASE + '/'), ('WNBA', BASE + '/wnba/')]
    if _page_ok(root, FINALS_HUB):
        trail.append((f'{year} Finals', BASE + FINALS_HUB))
    recap = None
    try:
        for a in json.loads((root / 'articles.json').read_text(encoding='utf-8')):
            if re.search(rf'finals-game-{game}-recap$', a.get('slug', '')):
                recap = f"/news/{a['slug']}/"
                break
    except Exception:
        pass
    if recap and _page_ok(root, recap):
        trail.append((f'Game {game}', BASE + recap))
    trail.append(('Play-by-play' if len(trail) > 3 else f'Game {game} play-by-play',
                  f'{BASE}/wnba/finals/{year}/game-{game}/play-by-play/'))
    return trail


def path_trail(root: Path, rel: str, text: str) -> list[tuple[str, str]]:
    m = re.fullmatch(r'/wnba/finals/(\d{4})/game-(\d+)/play-by-play/', rel)
    if m:
        return pbp_trail(m.group(1), m.group(2), root)
    trail = [('Home', BASE + '/')]
    parts = [p for p in rel.strip('/').split('/') if p]
    for i in range(1, len(parts)):
        sub = '/' + '/'.join(parts[:i]) + '/'
        if _page_ok(root, sub):
            trail.append((LABELS.get(sub, parts[i - 1].replace('-', ' ').title()), BASE + sub))
    trail.append((LABELS.get(rel) or _h1_text(text) or parts[-1].replace('-', ' ').title(), BASE + rel))
    return trail


def jsonld_for(trail: list[tuple[str, str]]) -> str:
    data = {'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': i, 'name': n, 'item': u} for i, (n, u) in enumerate(trail, 1)]}
    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + '</script>'


def visible_for(trail: list[tuple[str, str]]) -> str:
    bits = []
    for i, (name, url) in enumerate(trail):
        if i == len(trail) - 1:
            bits.append(f'<span aria-current="page">{esc(name)}</span>')
        else:
            bits.append(f'<a href="{esc(url.removeprefix(BASE) or "/")}">{esc(name)}</a>')
    return ('<nav class="breadcrumbs" aria-label="Breadcrumb">'
            + '<span aria-hidden="true">/</span>'.join(bits) + '</nav>')


def _add_css(text: str) -> str:
    if 'fcb-crumb-css' in text:
        return text
    return text.replace('</head>', f'<style id="fcb-crumb-css">{CSS}</style></head>', 1)


def _replace_jsonld_trail(text: str, trail) -> str:
    """Swap any existing BreadcrumbList (standalone or inside @graph) for `trail`."""
    new = json.loads(jsonld_for(trail)[len('<script type="application/ld+json">'):-len('</script>')])

    def sub(m):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            return m.group(0)
        if isinstance(data, dict) and data.get('@type') == 'BreadcrumbList':
            return jsonld_for(trail)
        if isinstance(data, dict) and isinstance(data.get('@graph'), list):
            g = data['@graph']
            for i, n in enumerate(g):
                if isinstance(n, dict) and n.get('@type') == 'BreadcrumbList':
                    g[i] = {k: v for k, v in new.items() if k != '@context'}
                    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + '</script>'
        return m.group(0)
    return JSONLD_RE.sub(sub, text)


def fix(text: str, rel: str, root: Path = ROOT) -> str:
    if not is_indexable(text):
        return text
    if rel == '/':
        if not H1_RE.search(text) and '<main' in text:
            i = text.index('>', text.index('<main')) + 1
            text = _add_css(text[:i] + f'<h1 class="home-h1">{esc(HOME_H1)}</h1>' + text[i:])
        return text
    is_pbp = re.fullmatch(r'/wnba/finals/\d{4}/game-\d+/play-by-play/', rel) is not None
    jl, vis = jsonld_trail(text), visible_trail(text)
    if is_pbp:
        want = path_trail(root, rel, text)
        if jl != want:
            text = _replace_jsonld_trail(text, want) if jl else text.replace('</head>', jsonld_for(want) + '</head>', 1)
        if vis != want:
            text = VISIBLE_RE.sub('', text, count=1) if vis else text
            vis = None
        jl = want
    if jl is None:
        trail = [(n, u or (BASE + rel if i == len(vis) - 1 else u)) for i, (n, u) in enumerate(vis)] if vis else None
        if not trail or any(not u for _, u in trail):
            trail = path_trail(root, rel, text)
        text = text.replace('</head>', jsonld_for(trail) + '</head>', 1)
        jl = trail
    if vis is None:
        m = H1_RE.search(text)
        if m:
            text = _add_css(text)
            m = H1_RE.search(text)
            text = text[:m.start()] + visible_for(jl) + text[m.start():]
    return text


def run(root: Path = ROOT, check: bool = False) -> list[str]:
    changed = []
    for p, rel in iter_pages(root):
        text = p.read_text(encoding='utf-8', errors='replace')
        new = fix(text, rel, root)
        if new != text:
            changed.append(rel)
            if not check:
                p.write_text(new, encoding='utf-8')
    return changed


if __name__ == '__main__':
    check = '--check' in sys.argv
    out = run(check=check)
    print(('needs breadcrumbs/H1: ' if check else 'updated: ') + str(len(out)))
    for r in out:
        print(' ', r)
    sys.exit(1 if check and out else 0)
