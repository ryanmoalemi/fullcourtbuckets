"""Open Graph / Twitter share images for every Full Court Buckets page.

Run after every page builder (fcb-wnba.yml, publish-articles.yml, the live
play-by-play loop). It is idempotent and safe to run repeatedly:

* Player pages get a 1200x630 card built from their licensed headshot
  (name, team, photo credit, wordmark). Players with no headshot get a branded
  fallback card with their name. Cards live in images/social/players/ and are
  rebuilt only when the inputs change (content/social-cards.json).
* News articles use their 1200x630 og-1200.jpg crop (news_heroes._write_og).
* Every other page gets the site default card images/social/fcb-default.jpg.
* Tags are only added where missing; existing og:image tags are kept. Added
  tags live between <!--fcb-social--> markers just before </head>. Page bodies
  are never touched.
"""
from __future__ import annotations

import hashlib
import html as htmlmod
import json
import re
import sys
from pathlib import Path

try:  # the live play-by-play loop runs --tags-only without Pillow
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:  # pragma: no cover
    Image = ImageDraw = ImageFont = ImageOps = None

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://fullcourtbuckets.com'
W, H = 1200, 630
CARD_VERSION = 'card-v1'
FONT_DIR = ROOT / 'assets' / 'fonts'
SOCIAL_DIR = ROOT / 'images' / 'social'
DEFAULT_CARD = SOCIAL_DIR / 'fcb-default.jpg'
MANIFEST = ROOT / 'content' / 'social-cards.json'
SKIP_DIRS = {'.git', '.github', 'automation', 'portrait-masters', 'portrait-handoff', 'node_modules', 'review'}
BG = (11, 11, 16)
PANEL = (20, 19, 25)
TEXT = (245, 243, 247)
MUTED = (177, 171, 185)
PINK = (255, 75, 177)
ORANGE = (255, 152, 98)
PURPLE = (185, 109, 245)
TWITTER_SITE = '@fullcourtbucket'
SOCIAL_TAG_RE = re.compile(r'<meta\b[^>]*\b(?:property|name)="(?:og|twitter):[^"]*"[^>]*>\n?', re.I)
DEFAULT_ALT = 'Full Court Buckets: WNBA stats, news and where to watch'
BLOCK_RE = re.compile(r'\n*<!--fcb-social-->.*?<!--/fcb-social-->\n*', re.S)
LICENSES = {
    'by-sa/4.0': 'CC BY-SA 4.0', 'by-sa/3.0': 'CC BY-SA 3.0', 'by-sa/2.5': 'CC BY-SA 2.5',
    'by-sa/2.0': 'CC BY-SA 2.0', 'by/4.0': 'CC BY 4.0', 'by/3.0': 'CC BY 3.0',
    'by/2.5': 'CC BY 2.5', 'by/2.0': 'CC BY 2.0', 'publicdomain': 'Public domain', 'cc0': 'CC0',
}


def font(name: str, size: int):
    return ImageFont.truetype(str(FONT_DIR / name), size)


def _gradient_bar(img, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    d = ImageDraw.Draw(img)
    for x in range(x0, x1):
        t = (x - x0) / max(1, x1 - x0 - 1)
        a, b = (PINK, ORANGE) if t < .5 else (ORANGE, PURPLE)
        u = t * 2 if t < .5 else (t - .5) * 2
        d.line([(x, y0), (x, y1)], fill=tuple(int(a[i] + (b[i] - a[i]) * u) for i in range(3)))


def _fit(draw, text, fname, size, max_w, min_size=40):
    while size > min_size:
        f = font(fname, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 4
    return font(fname, min_size)


def _base():
    img = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(img)
    d.ellipse((-260, 300, 520, 1080), fill=(24, 16, 30))
    _gradient_bar(img, (0, 0, W, 10))
    return img


def _wordmark(img, x: int, y: int) -> None:
    d = ImageDraw.Draw(img)
    d.text((x, y), 'FULLCOURTBUCKETS.COM', font=font('BarlowCondensed-ExtraBold.ttf', 34), fill=TEXT)


def render_player(name: str, team: str, portrait: Path | None, credit: str):
    img = _base()
    d = ImageDraw.Draw(img)
    text_w = 640 if portrait else 1080
    if portrait:
        photo = ImageOps.fit(Image.open(portrait).convert('RGBA'), (500, 600), Image.LANCZOS, centering=(.5, .15))
        panel = Image.new('RGB', (500, 600), PANEL)
        panel.paste(photo, (0, 0), photo)
        img.paste(panel, (W - 540, 30))
        _gradient_bar(img, (W - 540, 624, W - 40, 630))
    d.text((60, 70), 'WNBA PLAYER PROFILE', font=font('Inter-Bold.ttf', 24), fill=ORANGE)
    parts = name.split(' ', 1)
    first, last = (parts[0], parts[1]) if len(parts) > 1 else ('', parts[0])
    y = 120
    if first:
        f1 = _fit(d, first, 'BarlowCondensed-ExtraBold.ttf', 96, text_w)
        d.text((60, y), first.upper(), font=f1, fill=TEXT)
        y += f1.size + 4
    f2 = _fit(d, last.upper(), 'BarlowCondensed-ExtraBold.ttf', 132, text_w)
    d.text((60, y), last.upper(), font=f2, fill=PINK)
    y += f2.size + 24
    if team:
        ft = _fit(d, team, 'Inter-Bold.ttf', 36, text_w, 24)
        d.text((60, y), team, font=ft, fill=MUTED)
    if not portrait:
        d.text((60, y + (60 if team else 0)), 'Stats, game logs and career record', font=font('Inter-Medium.ttf', 30), fill=MUTED)
    _wordmark(img, 60, H - 110)
    if credit:
        fc = _fit(d, credit, 'Inter-Medium.ttf', 18, text_w, 12)
        d.text((60, H - 56), credit, font=fc, fill=MUTED)
    return img


def render_default():
    img = _base()
    d = ImageDraw.Draw(img)
    d.text((60, 150), 'FULL COURT', font=font('BarlowCondensed-ExtraBold.ttf', 150), fill=TEXT)
    d.text((60, 300), 'BUCKETS', font=font('BarlowCondensed-ExtraBold.ttf', 150), fill=PINK)
    d.text((64, 470), "WNBA stats, news, play-by-play and where to watch", font=font('Inter-Medium.ttf', 34), fill=MUTED)
    _wordmark(img, 60, H - 90)
    logo = ROOT / 'logo.png'
    if logo.is_file():
        mark = Image.open(logo).convert('RGBA')
        mark.thumbnail((300, 300))
        img.paste(mark, (W - 60 - mark.width, 150), mark)
    return img


def _save(img, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, 'JPEG', quality=86, optimize=True, progressive=True)


def _vers(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def _jsonld(text: str) -> list:
    out = []
    for raw in re.findall(r'<script type="application/ld\+json">(.*?)</script>', text, re.S):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        nodes = data.get('@graph', [data]) if isinstance(data, dict) else data
        out.extend(n for n in nodes if isinstance(n, dict))
    return out


def player_info(text: str, slug: str, teams: list[str]) -> dict | None:
    for node in _jsonld(text):
        if node.get('@type') == 'Person' and str(node.get('@id', '')).endswith(f'/wnba/{slug}/#player'):
            info = {'name': node.get('name') or slug, 'team': '', 'portrait': None, 'credit': ''}
            m = re.search(r'class="answer-summary">(.*?)</p>', text, re.S)
            summary = htmlmod.unescape(re.sub('<[^>]+>', '', m.group(1))) if m else ''
            hits = sorted((summary.find(t), t) for t in teams if t in summary)
            if hits:
                info['team'] = hits[0][1]
            image = node.get('image') if isinstance(node.get('image'), dict) else {}
            src = str(image.get('contentUrl') or '').replace(BASE, '').split('?')[0]
            local = ROOT / src.lstrip('/') if src.startswith('/images/players/') else None
            if local and local.is_file():
                info['portrait'] = local
                author = re.sub(r'\s+via Wikimedia Commons$', '', str(image.get('creditText') or '')).strip()
                lic_url = str(image.get('license') or '')
                lic = next((v for k, v in LICENSES.items() if k in lic_url), '')
                if author:
                    info['credit'] = 'Photo: ' + author + (f', {lic}' if lic else '') + ', via Wikimedia Commons'
            return info
    return None


def refresh_article_og(root: Path = ROOT) -> list[str]:
    """Re-export any article social crop that is not exactly 1200x630."""
    sys.path.insert(0, str(root / 'automation'))
    import news_heroes as nh
    path = root / 'articles.json'
    articles = json.loads(path.read_text(encoding='utf-8'))
    fixed = []
    for a in articles:
        og = str(a.get('imageOg') or '')
        if not og or (a.get('imageOgWidth'), a.get('imageOgHeight')) == (W, H) and og.endswith('og-1200.jpg'):
            continue
        if a.get('slug') == '2026-wnba-finals-ratings-tracker':
            continue
        src = nh.source_path(root, a)
        if src is None:
            continue
        image = nh.load_rgb(src)
        out, w, h = nh._write_og(image, a.get('imageFocal') or nh.DEFAULT_FOCAL, src)
        a['imageOg'] = '/' + out.resolve().relative_to(root.resolve()).as_posix()
        a['imageOgWidth'], a['imageOgHeight'] = w, h
        page = root / 'news' / a['slug'] / 'index.html'
        if page.is_file():
            t = page.read_text(encoding='utf-8')
            u = nh._set_social_image(t, BASE + a['imageOg'])
            if u != t:
                page.write_text(u, encoding='utf-8')
        fixed.append(a['slug'])
    if fixed:
        path.write_text(json.dumps(articles, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return fixed


def _has(text: str, key: str) -> bool:
    return re.search(r'<meta\b[^>]*(?:property|name)="' + re.escape(key) + '"', text, re.I) is not None


def _existing_image(text: str) -> str:
    m = re.search(r'<meta\b[^>]*property="og:image"[^>]*content="([^"]*)"', text, re.I) or \
        re.search(r'<meta\b[^>]*content="([^"]*)"[^>]*property="og:image"', text, re.I)
    return htmlmod.unescape(m.group(1)) if m else ''


def _content(tag: str) -> str:
    m = re.search(r'content="([^"]*)"', tag)
    return htmlmod.unescape(m.group(1)) if m else ''


def _key(tag: str) -> str:
    return re.search(r'(?:property|name)="([^"]*)"', tag, re.I).group(1).lower()


def social_block(text: str, image: str, alt: str, width: int, height: int) -> str:
    if '</head>' not in text:
        return text
    head, sep, rest = text.partition('</head>')
    head = re.sub(r'\n*<!--/?fcb-social-->\n*', '\n', head)
    tags, seen = [], set()
    for t in SOCIAL_TAG_RE.findall(head):
        t = t.strip()
        k = _key(t)
        # og:image:* may repeat for multiple images; everything else is single-valued.
        if k in seen and not k.startswith('og:image'):
            continue
        if t not in tags:
            tags.append(t)
            seen.add(k)
    head = SOCIAL_TAG_RE.sub('', head)
    vals = {}
    for t in tags:
        vals.setdefault(_key(t), _content(t))

    def add(attr, key, val):
        if key not in seen and val not in ('', None):
            tags.append(f'<meta {attr}="{key}" content="{htmlmod.escape(str(val), quote=True)}">')
            seen.add(key)
            vals[key] = str(val)
    existing = vals.get('og:image', '')
    if existing:
        image = existing
    else:
        add('property', 'og:image', image)
        add('property', 'og:image:width', width)
        add('property', 'og:image:height', height)
        add('property', 'og:image:alt', alt)
    add('name', 'twitter:card', 'summary_large_image')
    add('name', 'twitter:site', TWITTER_SITE)
    add('name', 'twitter:title', vals.get('og:title') or _title(text))
    add('name', 'twitter:description', vals.get('og:description', ''))
    add('name', 'twitter:image', image)
    add('name', 'twitter:image:alt', vals.get('og:image:alt') or alt)
    order = ['og:title', 'og:description', 'og:url', 'og:type', 'og:site_name', 'og:image', 'og:image:width',
             'og:image:height', 'og:image:alt', 'twitter:card', 'twitter:site', 'twitter:title',
             'twitter:description', 'twitter:image', 'twitter:image:alt']
    tags.sort(key=lambda t: (order.index(_key(t)) if _key(t) in order else len(order), _key(t)))
    block = '<!--fcb-social-->' + ''.join(tags) + '<!--/fcb-social-->'
    m = re.search(r'<meta\s+charset=[^>]*>', head, re.I) or re.search(r'<head\b[^>]*>', head, re.I)
    if m:
        head = head[:m.end()] + '\n' + block + '\n' + head[m.end():].lstrip('\n')
    else:
        head = head + block + '\n'
    return head + sep + rest


def _title(text: str) -> str:
    m = re.search(r'<title>(.*?)</title>', text, re.S)
    return htmlmod.unescape(m.group(1)).strip() if m else 'Full Court Buckets'


def pages(root: Path):
    for p in sorted(root.rglob('*.html')):
        rel = p.relative_to(root)
        if rel.parts[0] in SKIP_DIRS:
            continue
        yield p


def default_image_url() -> str:
    """Sitewide default share image, versioned like run() writes it."""
    url = f'{BASE}/images/social/fcb-default.jpg'
    return f'{url}?v={_vers(DEFAULT_CARD)}' if DEFAULT_CARD.is_file() else url


def run(root: Path = ROOT, cards: bool = True) -> dict:
    stats = {'player_cards': 0, 'fallback_cards': 0, 'pages_updated': 0, 'articles_reexported': []}
    if cards:
        stats['articles_reexported'] = refresh_article_og(root)
    if cards or not DEFAULT_CARD.is_file():
        _save(render_default(), DEFAULT_CARD)
    default_url = f'{BASE}/images/social/fcb-default.jpg?v={_vers(DEFAULT_CARD)}'
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.is_file() else {}
    try:
        teams = [t['full_name'] for t in json.loads((root / 'data/wnba/season-teams.json').read_text())['current_teams'].values()]
    except Exception:
        teams = []
    articles = {}
    try:
        for a in json.loads((root / 'articles.json').read_text(encoding='utf-8')):
            if a.get('imageOg'):
                articles[f"/news/{a['slug']}/"] = a
    except Exception:
        pass
    for page in pages(root):
        text = page.read_text(encoding='utf-8', errors='replace')
        if '</head>' not in text or re.search(r'http-equiv="?refresh', text, re.I):
            continue
        rel = '/' + page.relative_to(root).as_posix().removesuffix('index.html')
        image, alt, w, h = default_url, DEFAULT_ALT, W, H
        m = re.fullmatch(r'/wnba/([a-z0-9-]+)/', rel)
        info = player_info(text, m.group(1), teams) if m else None
        if info:
            slug = m.group(1)
            out = SOCIAL_DIR / 'players' / f'{slug}.jpg'
            key = hashlib.sha256(json.dumps([CARD_VERSION, info['name'], info['team'], info['credit'],
                                             _vers(info['portrait']) if info['portrait'] else '']).encode()).hexdigest()[:16]
            if cards and (manifest.get(slug) != key or not out.is_file()):
                _save(render_player(info['name'], info['team'], info['portrait'], info['credit']), out)
                manifest[slug] = key
            if out.is_file():
                stats['player_cards' if info['portrait'] else 'fallback_cards'] += 1
                image = f'{BASE}/images/social/players/{slug}.jpg?v={_vers(out)}'
                alt = f"{info['name']}" + (f", {info['team']}" if info['team'] else '') + ' | WNBA player profile on Full Court Buckets'
        elif rel in articles:
            a = articles[rel]
            image = BASE + a['imageOg']
            w, h = a.get('imageOgWidth') or W, a.get('imageOgHeight') or H
            alt = a.get('imageAlt') or _title(text)
        updated = social_block(text, image, alt, w, h)
        if updated != text:
            page.write_text(updated, encoding='utf-8')
            stats['pages_updated'] += 1
    if cards:
        MANIFEST.write_text(json.dumps(dict(sorted(manifest.items())), indent=1) + '\n')
    return stats


if __name__ == '__main__':
    print(json.dumps(run(cards='--tags-only' not in sys.argv), indent=1))
