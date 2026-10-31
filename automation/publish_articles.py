#!/usr/bin/env python3
"""Turn content/articles/<slug>/ into the news pages the site already uses.

A folder holds article.md and photo.jpg. This writes news/<slug>/index.html from
the shared article chrome, the root redirect, the hero and social images, and the
listings the last recap was added to. Running it again changes nothing.
"""
from __future__ import annotations

from datetime import date
import html
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'automation'))

import internal_links as links  # noqa: E402
import news_heroes  # noqa: E402
import rss_feed  # noqa: E402
import site_nav  # noqa: E402
import team_coverage  # noqa: E402

CONTENT = ROOT / 'content' / 'articles'
SHELL_PAGE = ROOT / 'news' / 'dream-valkyries-finals-game-1-recap' / 'index.html'
DISCLAIMER = '21+. Gamble responsibly. 1-800-GAMBLER.'
BETTING_RE = re.compile(r'betting odds|DraftKings|moneyline|Gamble responsibly', re.I)
SIZES = '(max-width: 900px) calc(94vw - 40px), 842px'
BROADCAST_STYLE = 'font-size:14px;color:#8a877f;margin:18px 0 0'
TRACKER_PATH = '/news/2026-wnba-finals-ratings-tracker/'


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def parse_front_matter(text: str) -> tuple[dict, str]:
    if not text.startswith('---'):
        raise ValueError('article.md must start with front matter')
    parts = text.split('---', 2)
    if len(parts) < 3:
        raise ValueError('article.md front matter is not closed')
    meta: dict = {}
    key = None
    for line in parts[1].splitlines():
        if not line.strip():
            continue
        stripped = line.strip()
        if stripped.startswith('- ') and key:
            meta.setdefault(key, [])
            if not isinstance(meta[key], list):
                raise ValueError(f'{key} mixes a value and a list')
            meta[key].append(stripped[2:].strip().strip('"').strip("'"))
            continue
        name, _, raw = line.partition(':')
        name = name.strip()
        raw = raw.strip()
        key = name
        if not raw:
            meta[name] = []
        elif raw.startswith('[') and raw.endswith(']'):
            meta[name] = [
                item.strip().strip('"').strip("'")
                for item in raw[1:-1].split(',')
                if item.strip()
            ]
        else:
            meta[name] = raw.strip('"').strip("'")
    return meta, parts[2].strip('\n')


def inline(text: str) -> str:
    def link(label: str, href: str) -> str:
        return (
            f'<a class="inline-link" href="{esc(href)}" target="_blank" '
            f'rel="{"nofollow noopener" if BETTING_HOST_RE.search(href) else "noopener"}">'
            f'{esc(label)}</a>'
        )

    parts = re.split(r'(!\[headshot:[^\]]+\]\(/images/players/[^)\s]+\)|\[[^\]]+\]\([^)]+\))', text)
    out = []
    for part in parts:
        shot = re.fullmatch(r'!\[headshot:([^\]]+)\]\((/images/players/[^)\s]+)\)', part)
        if shot:
            # Circle headshot next to a name in a data table: ![headshot:alt](/images/players/...).
            out.append(
                f'<img class="circle-headshot table-headshot" src="{esc(shot.group(2))}" alt="{esc(shot.group(1))}" '
                'width="32" height="32" loading="lazy" decoding="async" '
                'style="display:inline-block;width:32px;height:32px;max-width:32px;flex:0 0 32px;border-radius:50%;object-fit:cover;vertical-align:middle;margin-right:8px">'
            )
            continue
        match = re.fullmatch(r'\[([^\]]+)\]\(([^)]+)\)', part)
        if match:
            out.append(link(match.group(1), match.group(2)))
        else:
            out.append(esc(part))
    rendered = ''.join(out)
    return re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', rendered)


BETTING_HOST_RE = re.compile(r'//(?:[a-z0-9-]+\.)*(?:draftkings|kalshi|dunkelindex|fanduel|betmgm|caesars|polymarket)\.', re.I)
DYNAMIC_LINE_RE = re.compile(r'\{dynamic:([a-z0-9-]+)\}')
# A hand-checked, time-sensitive paragraph: "[dynamic:kind] text". Kept as written,
# marked so readers and checks know it changes (injuries, odds, ticket prices).
MANUAL_DYNAMIC_RE = re.compile(r'^\[dynamic:([a-z0-9-]+)\]\s+(.*)$', re.S)
TABLE_SEPARATOR_RE = re.compile(r'^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$')


def table_cells(line: str) -> list[str]:
    row = line.strip()
    if row.startswith('|'):
        row = row[1:]
    if row.endswith('|'):
        row = row[:-1]
    return [cell.strip() for cell in row.split('|')]


def table_html(rows: list[str]) -> str:
    """Render a pipe table (header row, --- separator, body rows) as a scrollable table."""
    header = table_cells(rows[0])
    body = [table_cells(row) for row in rows[2:]]
    head_html = ''.join(f'<th scope="col">{inline(cell)}</th>' for cell in header)
    body_rows = []
    for cells in body:
        cells = (cells + [''] * len(header))[:len(header)]
        body_rows.append('<tr>' + ''.join(f'<td>{inline(cell)}</td>' for cell in cells) + '</tr>')
    return (
        '<div class="table-wrap"><table>'
        f'<thead><tr>{head_html}</tr></thead>'
        f'<tbody>{"".join(body_rows)}</tbody>'
        '</table></div>'
    )


# Data notes (Ryan, Oct. 27, 2026): "Data through / Methods / Source / Download"
# paragraphs never sit between a heading and its table. The builder moves each one
# to a small muted caption directly below the next table in its section.
NOTE_RE = re.compile(r'^(?:\*\*)?(?:Data through|Methods(?: and sources)?:|Sources?:|Download \(CC0\):)', re.I)
KEY_FINDING_RE = re.compile(r'^(?:\*\*)?Key (?:finding|fact):(?:\*\*)?\s*', re.I)
NOTE_PARTS_RE = re.compile(r'(?=(?:Data through|Methods(?: and sources)?:|Sources?:|Download \(CC0\):))')


def note_text(text: str) -> str:
    """Order a data note as: Source. Data through. Methods. Download CSV (CC0)."""
    parts = [part.strip() for part in NOTE_PARTS_RE.split(text) if part.strip()]
    def rank(part: str) -> int:
        low = part.lower()
        if low.startswith('source'):
            return 0
        if low.startswith('data through'):
            return 1
        if low.startswith('method'):
            return 2
        if low.startswith('download'):
            return 3
        return 4
    out = []
    for part in sorted(parts, key=rank):
        if part.lower().startswith('download (cc0):'):
            link = part.split(':', 1)[1].strip()
            match = re.match(r'\[[^\]]*\]\(([^)]+)\)', link)
            part = f'[Download CSV (CC0)]({match.group(1)})' if match else 'Download (CC0): ' + link
        if part and part[-1] not in '.)!?':
            part += '.'
        out.append(part)
    return ' '.join(out)


def place_notes(blocks: list) -> list:
    """Attach each data note directly below a table in its section.

    A note goes under the next table in its section; if the section has no later
    table, under the section's last earlier table; if it has none, at section end.
    """
    sections: list[list] = [[]]
    for kind, value in blocks:
        if kind == 'h2':
            sections.append([])
        if kind == 'p' and isinstance(value, str):
            value = KEY_FINDING_RE.sub('', value)
            if NOTE_RE.match(value):
                kind, value = 'note', value.replace('**', '')
        sections[-1].append((kind, value))
    out: list = []
    for section in sections:
        notes: dict[int, list] = {}
        body = []
        tables = [i for i, (kind, _) in enumerate(section) if kind == 'table']
        for i, (kind, value) in enumerate(section):
            if kind != 'note':
                continue
            later = [t for t in tables if t > i]
            earlier = [t for t in tables if t < i]
            target = later[0] if later else (earlier[-1] if earlier else len(section))
            notes.setdefault(target, []).append(value)
        for i, block in enumerate(section):
            if block[0] != 'note':
                body.append(block)
            if i in notes:
                body.extend(('note', text) for text in notes[i])
        body.extend(('note', text) for text in notes.get(len(section), []))
        out.extend(body)
    return out


# In-body photo line (docs/style-guide.md): every photo is a 16:9 file, licensed and credited.
# !photo: /images/articles/<slug>/<name>.jpg | alt text | Photo: Author, LICENSE, via Wikimedia Commons | credit url | license url | focal
SUB_HEADING_CSS = ('<style class="sub-h-css">.article h3.sub-h3{margin:26px 0 10px;font:800 24px/1.1 Barlow,sans-serif;'
                   'color:#fff}.article h4.sub-h4{margin:18px 0 6px;font:700 18px/1.25 Barlow,sans-serif;color:#ff9800}</style>')
BODY_PHOTO_RE = re.compile(r'!photo:\s*(.+)')
ODD_RE = re.compile(r'^!odd:\s*(.+)$')


def ensure_body_photo_files(src: str, webp: str, root: Path | None = None) -> None:
    """Every in-body <picture> needs both files on disk: the webp source and the jpg <img> fallback.
    If one is missing, build it from the other; if neither exists, stop the build."""
    from PIL import Image
    root = root or ROOT
    jpg_path, webp_path = root / src.lstrip('/'), root / webp.lstrip('/')
    if jpg_path.is_file() and webp_path.is_file():
        return
    if not jpg_path.is_file() and not webp_path.is_file():
        raise SystemExit(f'in-body photo missing: {src} (and {webp})')
    if not jpg_path.is_file():
        with Image.open(webp_path) as im:
            im.convert('RGB').save(jpg_path, 'JPEG', quality=85, optimize=True, progressive=True)
    else:
        with Image.open(jpg_path) as im:
            im.convert('RGB').save(webp_path, 'WEBP', quality=82)


def body_photo_html(parts: list) -> str:
    src, alt, credit = parts[0], parts[1], parts[2]
    credit_url = parts[3] if len(parts) > 3 else ''
    license_url = parts[4] if len(parts) > 4 else ''
    focal = parts[5] if len(parts) > 5 and parts[5] else 'center 20%'
    webp = src.rsplit('.', 1)[0] + '.webp'
    ensure_body_photo_files(src, webp)
    return (
        f'<figure class="inline-photo body-photo"><picture><source srcset="{esc(webp)}" type="image/webp">'
        f'<img src="{esc(src)}" alt="{esc(alt)}" width="1600" height="900" loading="lazy" decoding="async" '
        f'style="object-position:{esc(focal)}"></picture>'
        f'<figcaption>{caption_html(credit, credit_url, license_url)}</figcaption></figure>'
    )


def odds_html(rows: list[str]) -> str:
    """No. 1 odds bars for the Halloween Game 7 preview. CSS animates the fill."""
    cards = []
    for raw in rows:
        parts = [part.strip() for part in raw.split('|')]
        name = parts[0] if parts else ''
        pct = (parts[1] if len(parts) > 1 else '0').rstrip('%')
        detail = parts[2] if len(parts) > 2 else ''
        top = len(parts) > 3 and parts[3].lower() == 'top'
        try:
            width = max(0.0, min(100.0, float(pct)))
        except ValueError:
            width = 0.0
        cards.append(
            f'<div class="hw-odd{" hw-odd-top" if top else ""}">'
            f'<div class="hw-odd-name">{inline(name)}</div>'
            f'<div class="hw-odd-track"><span class="hw-odd-bar" style="--p:{width:.1f}"></span></div>'
            f'<div class="hw-odd-pct">{esc(pct)}%</div>'
            f'<div class="hw-odd-meta">{inline(detail)}</div>'
            f'</div>'
        )
    return '<div class="hw-lottery">' + ''.join(cards) + '</div>'


def body_html(markdown: str) -> str:
    blocks: list[str] = []
    paragraph: list[str] = []
    bullets: list[str] = []
    table: list[str] = []
    odds: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph:
            return
        text = ' '.join(part.strip() for part in paragraph).strip()
        paragraph.clear()
        if text:
            blocks.append(('p', text))

    def flush_bullets() -> None:
        if not bullets:
            return
        blocks.append(('ul', list(bullets)))
        bullets.clear()

    def flush_odds() -> None:
        if not odds:
            return
        blocks.append(('odds', list(odds)))
        odds.clear()

    def flush_table() -> None:
        if not table:
            return
        if len(table) >= 2 and TABLE_SEPARATOR_RE.match(table[1].strip()):
            blocks.append(('table', list(table)))
        else:
            # Not a real table (no separator row): keep the text as a paragraph.
            paragraph.extend(table)
            flush_paragraph()
        table.clear()

    for line in markdown.splitlines():
        if line.strip().startswith('|'):
            flush_paragraph()
            flush_bullets()
            flush_odds()
            table.append(line.strip())
            continue
        flush_table()
        odd = ODD_RE.match(line.strip())
        if odd:
            flush_paragraph()
            flush_bullets()
            odds.append(odd.group(1))
            continue
        flush_odds()
        if not line.strip():
            flush_paragraph()
            flush_bullets()
            continue
        dyn = DYNAMIC_LINE_RE.fullmatch(line.strip())
        if dyn:
            flush_paragraph()
            flush_bullets()
            blocks.append(('dynamic', dyn.group(1)))
            continue
        if line.startswith('## '):
            flush_paragraph()
            flush_bullets()
            blocks.append(('h2', line[3:].strip()))
            continue
        photo = BODY_PHOTO_RE.fullmatch(line.strip())
        if photo:
            flush_paragraph()
            flush_bullets()
            blocks.append(('photo', [x.strip() for x in photo.group(1).split('|')]))
            continue
        if line.startswith('### ') or line.startswith('#### '):
            flush_paragraph()
            flush_bullets()
            level = 'h4' if line.startswith('#### ') else 'h3'
            blocks.append((level, line.split(' ', 1)[1].strip()))
            continue
        if line.startswith('- '):
            flush_paragraph()
            bullets.append(line[2:].strip())
            continue
        paragraph.append(line.strip())
    flush_table()
    flush_paragraph()
    flush_bullets()
    flush_odds()
    blocks = place_notes(blocks)

    html_blocks = []
    first = True
    disclaimer = False
    for kind, value in blocks:
        if kind == 'h2':
            html_blocks.append(f'<h2 class="section-title">{esc(value)}</h2>')
            continue
        if kind == 'photo':
            html_blocks.append(body_photo_html(value))
            continue
        if kind == 'odds':
            html_blocks.append(odds_html(value))
            continue
        if kind in ('h3', 'h4'):
            if not any('sub-h-css' in b for b in html_blocks):
                html_blocks.append(SUB_HEADING_CSS)
            html_blocks.append(f'<{kind} class="sub-{kind}">{inline(value)}</{kind}>')
            continue
        if kind == 'ul':
            items = ''.join(f'<li>{inline(item)}</li>' for item in value)
            html_blocks.append(f'<ul>{items}</ul>')
            continue
        if kind == 'table':
            html_blocks.append(table_html(value))
            continue
        if kind == 'note':
            html_blocks.append(
                f'<p class="table-note" data-fcb-dynamic="data-note" data-fcb-source="manual" '
                f'data-fcb-updated="{date.today().isoformat()}">{inline(note_text(value))}</p><!--/fcb-dynamic-->')
            continue
        if kind == 'dynamic':
            # Body is filled by automation/dynamic_sections.py (same workflow run).
            html_blocks.append(
                f'<div data-fcb-dynamic="{esc(value)}" data-fcb-source="data/games data/finals-schedule.json" '
                f'data-fcb-updated=""></div><!--/fcb-dynamic-->')
            continue
        manual = MANUAL_DYNAMIC_RE.match(value) if kind == 'p' else None
        if manual:
            html_blocks.append(
                f'<p data-fcb-dynamic="{esc(manual.group(1))}" data-fcb-source="manual" '
                f'data-fcb-updated="{date.today().isoformat()}">{inline(manual.group(2))}</p><!--/fcb-dynamic-->')
            if BETTING_RE.search(value) and DISCLAIMER not in markdown and not disclaimer:
                html_blocks.append(f'<p>{esc(DISCLAIMER)}</p>')
                disclaimer = True
            continue
        if value.startswith('TV: ') and not first:
            # The closing broadcast line keeps its small grey style on every rebuild.
            html_blocks.append(f'<p class="broadcast-line" style="{BROADCAST_STYLE}">{inline(value)}</p>')
            continue
        html_blocks.append(f'<p{" class=\"lead\"" if first else ""}>{inline(value)}</p>')
        first = False
        if BETTING_RE.search(value) and DISCLAIMER not in markdown and not disclaimer:
            html_blocks.append(f'<p>{esc(DISCLAIMER)}</p>')
            disclaimer = True
    return '\n'.join(html_blocks)


def focal_for(meta: dict, existing: dict | None) -> str:
    raw = str(meta.get('focal_y') or '').strip()
    if not raw and existing and existing.get('imageFocal'):
        return str(existing['imageFocal'])
    if not raw:
        return 'center 20%'
    if re.fullmatch(r'\d{1,3}(?:\.\d+)?', raw):
        return f'center {raw}%'
    if re.fullmatch(r'\d{1,3}(?:\.\d+)?%', raw):
        return f'center {raw}'
    return raw


def caption_html(credit: str, credit_url: str, license_url: str) -> str:
    match = re.fullmatch(r'Photo: (.+), (.+), via Wikimedia Commons', credit.strip())
    if match and credit_url and license_url:
        author, license_name = match.group(1), match.group(2)
        return (
            'Photo: '
            f'<a class="inline-link" href="{esc(credit_url)}" target="_blank" rel="noopener">{esc(author)}</a>, '
            f'<a class="inline-link" href="{esc(license_url)}" target="_blank" rel="noopener">{esc(license_name)}</a>, via '
            f'<a class="inline-link" href="{esc(credit_url)}" target="_blank" rel="noopener">Wikimedia Commons</a>'
        )
    return esc(credit)


def load_articles() -> list:
    return json.loads((ROOT / 'articles.json').read_text(encoding='utf-8'))


def record_for(meta: dict, folder: Path, existing: dict | None) -> dict:
    slug = meta['slug']
    title = meta['title']
    article = dict(existing or {})
    article.update({
        'slug': slug,
        'url': f'/news/{slug}/',
        'title': meta.get('card_title') or title,
        'description': meta.get('description') or '',
        'category': meta.get('category') or 'news',
        'date': meta['date'],
        'imageAlt': meta.get('hero_alt') or title,
        'imageCredit': meta.get('photo_credit') or '',
        'teams': list(meta.get('teams') or []),
        'imageFocal': focal_for(meta, existing),
    })
    if str(meta.get('game_id') or '').strip():  # links score rows to this recap; no ESPN box-score line
        article['gameId'] = str(meta['game_id']).strip()
    if str(meta.get('preview_game_id') or '').strip():  # rail 'Next' links this preview before tip
        article['previewGameId'] = str(meta['preview_game_id']).strip()
    # The event day for a preview. Body copy can mention an earlier game.
    game_day = str(meta.get('game_date') or '').strip()[:10]
    if game_day:
        try:
            date.fromisoformat(game_day)
        except ValueError:
            raise SystemExit(f'{slug}: game_date {game_day!r} is not YYYY-MM-DD')
        article['gameDate'] = game_day
    return article


def images_ready(article: dict, photo: bytes) -> bool:
    source = str(article.get('imageSource') or '')
    hero = str(article.get('imageHero') or '')
    og = str(article.get('imageOg') or '')
    if not source or not hero or not og:
        return False
    source_path = ROOT / source.lstrip('/')
    if not source_path.is_file() or source_path.read_bytes() != photo:
        return False
    for key in ('imageHero', 'imageOg'):
        if not (ROOT / str(article[key]).lstrip('/')).is_file():
            return False
    if article.get('imageHero2x') and not (ROOT / str(article['imageHero2x']).lstrip('/')).is_file():
        return False
    return True


def write_images(article: dict, photo_path: Path, photo: bytes) -> None:
    slug = article['slug']
    dest_dir = ROOT / 'images' / 'articles' / slug
    dest_dir.mkdir(parents=True, exist_ok=True)
    source_name = Path(str(article.get('imageSource') or '')).name or 'photo.jpg'
    source = dest_dir / source_name
    if not source.is_file() or source.read_bytes() != photo:
        shutil.copyfile(photo_path, source)
    article['image'] = '/' + source.relative_to(ROOT).as_posix()
    article['imageSource'] = article['image']
    news_heroes.ensure_article_hero(ROOT, article)
    article['image'] = article['imageHero']
    article['imageWidth'] = article['imageHeroWidth']
    article['imageHeight'] = article['imageHeroHeight']


# Silhouettes for the Game 7 Halloween field. CSS moves them; the page has no animation script.
_BAT_SVG = (
    '<svg viewBox="0 0 128 52" aria-hidden="true" focusable="false">'
    '<path fill="#14060f" d="M64 30c-6-14-22-22-36-16 6 3 8 12 2 16C16 36 4 24 0 10c8 10 18 22 16 32'
    ' 12-4 24-12 32-20 4 10 12 16 16 16s12-6 16-16c8 8 20 16 32 20-2-10 8-22 16-32-4 14-16 26-30 20'
    '-6-4-4-13 2-16-14-6-30 2-36 16z"/>'
    '<circle cx="58" cy="32" r="1.8" fill="#ffe08a"/>'
    '<circle cx="70" cy="32" r="1.8" fill="#ffe08a"/>'
    '</svg>'
)
_PUMPKIN_SVG = (
    '<svg viewBox="0 0 64 72" aria-hidden="true" focusable="false">'
    '<path fill="#2f7d32" d="M34 4c4 1 7 6 5 10-3-1-5-1-7 1 1-4 0-9 2-11z"/>'
    '<ellipse cx="32" cy="40" rx="13" ry="22" fill="#ff9f1c"/>'
    '<ellipse cx="21" cy="40" rx="11" ry="20" fill="#f76707"/>'
    '<ellipse cx="43" cy="40" rx="11" ry="20" fill="#e8590c"/>'
    '<path fill="#2a0c00" d="M24 34l6 7-6 2zm16 0-6 7 6 2zM28 50c1 2 3 3 4 3s3-1 4-3c0 3-2 6-4 7s-4-4-4-7z"/>'
    '</svg>'
)


def _is_halloween(meta: dict) -> bool:
    return str(meta.get('theme') or '') == 'halloween'


def halloween_kicker_html() -> str:
    """Eyebrow above the headline so the moving background reads as Halloween."""
    icon = f'<span class="hw-kicker-ico" aria-hidden="true">{_PUMPKIN_SVG}</span>'
    return f'<p class="hw-kicker">{icon}<span>Halloween Finals 2026</span>{icon}</p>'


def halloween_orbit_html() -> str:
    """Short motion band directly above the hero photo. The photo itself is unchanged."""
    embers = '<span class="hw-embers">' + ('<i></i>' * 8) + '</span>'
    return (
        '<div class="hw-orbit" aria-hidden="true"><span class="hw-orbit-fog"></span>'
        f'{embers}'
        f'<span class="hw-pumpkin hw-orbit-pumpkin">{_PUMPKIN_SVG}</span>'
        f'<span class="hw-pumpkin hw-orbit-pumpkin hw-orbit-pumpkin-b">{_PUMPKIN_SVG}</span>'
        f'<span class="hw-bat hw-orbit-bat"><span class="hw-bat-path">{_BAT_SVG}</span></span>'
        f'<span class="hw-bat hw-orbit-bat hw-orbit-bat-b"><span class="hw-bat-path">{_BAT_SVG}</span></span>'
        '</div>'
    )


def halloween_field_html() -> str:
    """Fixed page background: fog, embers, bats and pumpkins behind the article."""
    bats = ''.join(
        f'<span class="hw-bat hw-bat-{i}"><span class="hw-bat-path">{_BAT_SVG}</span></span>'
        for i in range(1, 8)
    )
    pumpkins = ''.join(
        f'<span class="hw-pumpkin hw-pumpkin-{i}">{_PUMPKIN_SVG}</span>'
        for i in range(1, 7)
    )
    spots = (
        (4, 11, 1), (11, 15, 4), (18, 9, 2), (27, 13, 7), (35, 10, 3),
        (44, 16, 6), (52, 12, 2), (61, 14, 8), (69, 9, 5), (77, 13, 1),
        (85, 11, 6), (93, 15, 3), (8, 18, 9), (48, 8, 4), (72, 17, 7), (22, 12, 5),
    )
    embers = ''.join(
        f'<i style="left:{left}%;animation-duration:{dur}s;animation-delay:-{delay}s"></i>'
        for left, dur, delay in spots
    )
    return (
        '<div class="hw-field" aria-hidden="true">'
        '<span class="hw-field-fog"></span><span class="hw-field-fog hw-field-fog-b"></span>'
        f'<span class="hw-field-embers">{embers}</span>{bats}{pumpkins}</div>'
    )


def figure_html(article: dict, meta: dict) -> str:
    hero = article['imageHero']
    srcset = f'{hero} {article["imageHeroWidth"]}w'
    if article.get('imageHero2x'):
        srcset += f', {article["imageHero2x"]} {article["imageHero2xWidth"]}w'
    focal = article.get('imageFocal') or 'center 20%'
    caption = caption_html(
        str(meta.get('photo_credit') or article.get('imageCredit') or ''),
        str(meta.get('photo_credit_url') or ''),
        str(meta.get('license_url') or ''),
    )
    layer = ''
    orbit = ''
    open_hero = ''
    close_hero = ''
    if _is_halloween(meta):
        orbit = halloween_orbit_html()
        open_hero = '<div class="hw-hero">'
        close_hero = '</div>'
        layer = (
            '<div class="hw-sky" aria-hidden="true"><span class="hw-fog"></span>'
            '<span class="hw-embers">' + ('<i></i>' * 14) + '</span>'
            '<span class="hw-lantern"><span class="hw-stem"></span><span class="hw-face"></span></span>'
            '</div>'
        )
    return (
        f'<figure class="lead-photo">{orbit}{open_hero}<picture><source srcset="{esc(srcset)}" type="image/webp" '
        f'sizes="{SIZES}"></source><img src="{esc(hero)}" alt="{esc(article["imageAlt"])}" '
        f'style="object-position:{esc(focal)}" srcset="{esc(srcset)}" sizes="{SIZES}" '
        f'width="{article["imageHeroWidth"]}" height="{article["imageHeroHeight"]}" '
        f'decoding="async" fetchpriority="high"></picture>'
        f'{layer}{close_hero}<figcaption>{caption}</figcaption></figure>'
    )


def apply_page_theme(page: str, meta: dict) -> str:
    """Link a per-article stylesheet and mark the body. Other pages are untouched."""
    slug = str(meta.get('slug') or '')
    src = CONTENT / slug / 'page.css'
    if not src.is_file():
        return page
    dest = ROOT / 'news' / slug / 'page.css'
    dest.parent.mkdir(parents=True, exist_ok=True)
    css = src.read_text(encoding='utf-8')
    if not dest.is_file() or dest.read_text(encoding='utf-8') != css:
        dest.write_text(css, encoding='utf-8')
    href = f'/news/{slug}/page.css'
    if href not in page:
        page = page.replace('</head>', f'<link rel="stylesheet" href="{href}">\n</head>', 1)
    if _is_halloween(meta) and 'class="fcb-halloween"' not in page:
        page = page.replace('<body>', '<body class="fcb-halloween">', 1)
    if _is_halloween(meta) and 'class="hw-field"' not in page:
        page = page.replace(
            '<body class="fcb-halloween">',
            '<body class="fcb-halloween">' + halloween_field_html(),
            1,
        )
    return page


def archive_note_html(meta: dict) -> str:
    """Preview archive note under the byline once the game is played (front matter recap_url).

    Kept in the source so a rebuild of the preview never drops it.
    """
    url = str(meta.get('recap_url') or '').strip()
    if not url:
        return ''
    return (
        '<p>This preview was published before the game. For the result, read our '
        f'<a href="{esc(url)}">game recap</a>. '
        f'<a href="{TRACKER_PATH}">2026 WNBA Finals ratings tracker</a>.</p>'
    )


def top_link_html(meta: dict) -> str:
    """Optional one-line link under the byline (front matter top_link_text + top_link_url)."""
    text, url = str(meta.get('top_link_text') or '').strip(), str(meta.get('top_link_url') or '').strip()
    if not (text and url):
        return ''
    return f'<p class="top-link"><a href="{esc(url)}">{esc(text)} &rarr;</a></p>'


def render_page(meta: dict, markdown: str, article: dict, articles: list) -> str:
    slug = article['slug']
    dest = ROOT / 'news' / slug / 'index.html'
    existed = dest.is_file()
    if existed:
        page = dest.read_text(encoding='utf-8')
    else:
        page = SHELL_PAGE.read_text(encoding='utf-8')
        page = page.replace('dream-valkyries-finals-game-1-recap', slug)
    title = meta['title']
    social = meta.get('social_title') or title
    description = article.get('description') or ''
    when = links._format_date(article['date'])
    stamp = article['date']
    # A date-only `updated` value is the visible byline date. Timestamp notes on other posts stay unused.
    updated_raw = str(meta.get('updated') or '').strip()
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', updated_raw):
        when = 'Updated ' + links._format_date(updated_raw)
        stamp = updated_raw
    body = body_html(markdown)
    if str(meta.get('data_table_first') or '').strip().lower() in ('true', 'yes', '1'):
        # Ryan's news exception: headline, byline, 16:9 lead photo, one-line opening, then this table.
        body = body.replace('<div class="table-wrap">', '<div class="table-wrap" data-fcb-data-table>', 1)
    linked = bool(meta.get('photo_credit_url') or meta.get('license_url'))
    sentence = links.HOW_MADE_OTHER if linked else links.HOW_MADE_OTHER_UNLINKED
    how = f'<p class="how-made">{sentence} {links.HOW_MADE_LINK}</p>'
    kicker = halloween_kicker_html() if _is_halloween(meta) else ''
    article_html = (
        '<article class="article">'
        f'{kicker}'
        f'<div class="meta-row"><span class="cat">{esc(article["category"])}</span>'
        '<span class="divider"></span><span>Full Court Buckets</span></div>'
        f'<h1>{esc(title)}</h1>'
        f'<div class="byline-row">{links.BYLINE_HTML}'
        f'<time class="article-date" datetime="{esc(stamp)}">{esc(when)}</time></div>'
        f'{archive_note_html(meta)}{top_link_html(meta)}{figure_html(article, meta)}{body}{how}'
        '<p class="brand-sign">Full Court Buckets &middot; WNBA News. Analysis. Commentary.</p>'
        '</article>'
    )
    article_html = links.glue_headline_scores(article_html)
    page = re.sub(r'<article class="article">.*?</article>', article_html, page, count=1, flags=re.S)
    page = links.ensure_article_end(page, ROOT, article, articles)
    page = set_title(page, str(meta.get('seo_title') or title), social, description, article)
    ticker = str(meta.get('ticker') or '').strip()
    if ticker or not existed:
        # A new story must not keep the shell page's score in the Now bar.
        ticker_text = ticker or 'WNBA news, analysis and commentary.'
        page = re.sub(
            r'(<div class="ticker-text">)(.*?)(</div>)',
            lambda match: match.group(1) + esc(ticker_text) + match.group(3),
            page,
            count=1,
            flags=re.S,
        )
    page = re.sub(
        r'(<nav class="breadcrumbs"[^>]*>.*)(<span>)(.*?)(</span></nav>)',
        lambda match: match.group(1) + match.group(2) + esc(title) + match.group(4),
        page,
        count=1,
        flags=re.S,
    )
    return apply_page_theme(page, meta)


def set_title(page: str, title: str, social: str, description: str, article: dict) -> str:
    slug = article['slug']
    canonical = f'https://fullcourtbuckets.com/news/{slug}/'
    og_image = links.BASE + article['imageOg']
    page = re.sub(r'<title>.*?</title>', f'<title>{esc(title)} | Full Court Buckets</title>', page, count=1)

    def meta(attr: str, value: str, prop: str) -> None:
        nonlocal page
        pattern = rf'(<meta {prop}="{attr}" content=").*?(">)'
        page = re.sub(pattern, lambda match: match.group(1) + esc(value) + match.group(2), page, count=1)

    meta('description', description, 'name')
    meta('og:title', social, 'property')
    meta('og:description', description, 'property')
    meta('og:url', canonical, 'property')
    meta('og:image', og_image, 'property')
    meta('twitter:title', social, 'name')
    meta('twitter:description', description, 'name')
    meta('twitter:image', og_image, 'name')
    meta('article:published_time', article['date'], 'property')
    page = re.sub(
        r'(<link rel="canonical" href=").*?(">)',
        lambda match: match.group(1) + esc(canonical) + match.group(2),
        page,
        count=1,
    )
    schema = {
        '@context': 'https://schema.org',
        '@type': 'NewsArticle',
        'headline': social,
        'description': description,
        'image': [og_image],
        'datePublished': article['date'],
        'dateModified': article['date'],
        'author': {
            '@type': 'Person',
            'name': 'Ryan Moalemi',
            'url': 'https://fullcourtbuckets.com/authors/ryan-moalemi/',
        },
        'publisher': {
            '@type': 'Organization',
            'name': 'Full Court Buckets',
            'logo': {'@type': 'ImageObject', 'url': 'https://fullcourtbuckets.com/logo.png'},
        },
        'mainEntityOfPage': {'@type': 'WebPage', '@id': canonical},
        'url': canonical,
    }
    replacement = '<script type="application/ld+json">' + json.dumps(schema, ensure_ascii=False) + '</script>'
    page = re.sub(
        r'<script type="application/ld\+json">\{"@context": "https://schema.org", "@type": "NewsArticle".*?</script>',
        lambda _: replacement,
        page,
        count=1,
    )
    page = re.sub(
        r'("itemListElement": \[{"@type": "ListItem", "position": 1, "name": "Home".*?"position": 3, "name": ").*?(", "item": )',
        lambda match: match.group(1) + json.dumps(social, ensure_ascii=False)[1:-1] + match.group(2),
        page,
        count=1,
    )
    return page


def write_if_changed(path: Path, text: str) -> bool:
    if path.is_file() and path.read_text(encoding='utf-8') == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return True


def redirect_html(slug: str) -> str:
    return links.permanent_redirect(f'https://fullcourtbuckets.com/news/{slug}/')


def upsert_record(articles: list, article: dict) -> tuple[list, bool]:
    for index, other in enumerate(articles):
        if other.get('slug') == article['slug']:
            merged = dict(other)
            merged.update(article)
            changed = merged != other
            articles[index] = merged
            return articles, changed
    date = article.get('date') or ''
    index = len(articles)
    for cursor, other in enumerate(articles):
        if (other.get('date') or '') <= date:
            index = cursor
            break
    articles.insert(index, article)
    return articles, True


def save_articles(articles: list) -> None:
    text = json.dumps(articles, ensure_ascii=False, indent=2) + '\n'
    write_if_changed(ROOT / 'articles.json', text)


def prepend_news_list(path: Path, item_html: str, article: dict) -> None:
    text = path.read_text(encoding='utf-8')
    href = links.article_href(article)
    if href in text.split('class="news-list">', 1)[-1][:8000] and f'href="{href}"' in text:
        marker = 'class="news-list">'
        # Already listed. Replace the existing item when the card changed.
        pattern = re.compile(
            r'<li><a class="news-item" href="' + re.escape(href) + r'">.*?</li>',
            re.S,
        )
        updated = pattern.sub(lambda _: item_html, text, count=1)
        write_if_changed(path, updated)
        return
    marker = 'class="news-list">'
    if marker not in text:
        raise SystemExit(f'news list missing in {path}')
    text = text.replace(marker, marker + item_html, 1)

    def bump(match: re.Match) -> str:
        raw = match.group(1)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return match.group(0)
        changed = False

        def visit(node) -> None:
            nonlocal changed
            if isinstance(node, dict):
                main = node.get('mainEntity') if node.get('@type') == 'CollectionPage' else None
                if isinstance(main, dict) and main.get('@type') == 'ItemList':
                    elements = list(main.get('itemListElement') or [])
                    url = links.article_absolute(article)
                    if not any(isinstance(el, dict) and el.get('url') == url for el in elements):
                        elements.insert(0, {
                            '@type': 'ListItem',
                            'position': 1,
                            'url': url,
                            'name': article['title'],
                        })
                        for position, element in enumerate(elements, 1):
                            if isinstance(element, dict):
                                element['position'] = position
                        main['numberOfItems'] = len(elements)
                        main['itemListElement'] = elements
                        changed = True
                for value in node.values():
                    visit(value)
            elif isinstance(node, list):
                for value in node:
                    visit(value)

        visit(data)
        if not changed:
            return match.group(0)
        return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + '</script>'

    text = re.sub(r'<script type="application/ld\+json">(.*?)</script>', bump, text, flags=re.S)
    write_if_changed(path, text)


def update_homepage(articles: list) -> None:
    path = ROOT / 'index.html'
    text = path.read_text(encoding='utf-8')
    featured = links._story_card(articles[0]).replace(
        '<a class="article-card"',
        '<a class="article-card" id="featured-story"',
        1,
    )
    text = re.sub(
        r'<a class="article-card" id="featured-story" href=".*?">.*?</a>',
        lambda _: featured,
        text,
        count=1,
        flags=re.S,
    )
    text = links._replace_marker(text, 'fcb-stories', links._more_story_cards(articles))
    # Keep the homepage Now line in step with the newest story, as the nightly build does.
    text = links.apply_ticker(text, articles)
    write_if_changed(path, text)


def update_latest(article: dict, articles: list) -> None:
    href = links.article_href(article)
    title = esc(article['title'])
    item = f'<li><a href="{href}">{title}</a></li>'
    lead = articles[0].get('slug') == article['slug']
    for path in (ROOT / 'news').glob('*/index.html'):
        if path.parent.name == article['slug']:
            continue
        text = path.read_text(encoding='utf-8')
        match = re.search(
            r'(<section class="article-latest"><h2>Latest news</h2><ul>)(.*?)(</ul></section>)',
            text,
        )
        if not match:
            continue
        block = match.group(2)
        if href in block:
            updated = re.sub(
                r'(<li><a href="' + re.escape(href) + r'">).*?(</a></li>)',
                lambda found: found.group(1) + title + found.group(2),
                block,
                count=1,
            )
        elif lead:
            kept = re.findall(r'<li>.*?</li>', block)
            updated = item + ''.join(kept[:2])
        else:
            continue
        if updated == block:
            continue
        path.write_text(text[:match.start(2)] + updated + text[match.end(2):], encoding='utf-8')


def update_sitemap_html(article: dict) -> None:
    path = ROOT / 'sitemap' / 'index.html'
    text = path.read_text(encoding='utf-8')
    href = links.article_href(article)
    item = f'<li><a href="{href}">{esc(article["title"])}</a></li>'
    if href in text:
        text = re.sub(
            r'(<li><a href="' + re.escape(href) + r'">).*?(</a></li>)',
            lambda match: match.group(1) + esc(article['title']) + match.group(2),
            text,
            count=1,
        )
    else:
        marker = 'id="sitemap-news"><h2>News</h2><ul class="sitemap-list">'
        if marker not in text:
            raise SystemExit('html sitemap news list missing')
        text = text.replace(marker, marker + item, 1)
    write_if_changed(path, text)


def sync_feeds(articles: list) -> None:
    write_if_changed(ROOT / 'feed.xml', rss_feed.feed_document(ROOT))
    for name in ('sitemap.xml', 'pages-sitemap.xml'):
        path = ROOT / name
        if path.is_file():
            write_if_changed(path, links.sync_news_sitemap(path.read_text(encoding='utf-8'), articles))
    write_if_changed(ROOT / 'search-index.json', site_nav.search_index_document(ROOT))


def publish_folder(folder: Path, articles: list) -> list:
    meta, markdown = parse_front_matter((folder / 'article.md').read_text(encoding='utf-8'))
    slug = str(meta.get('slug') or folder.name)
    if slug != folder.name:
        raise SystemExit(f'{folder.name}: front matter slug is {slug}')
    meta['slug'] = slug
    for required in ('title', 'date', 'description', 'hero_alt', 'photo_credit'):
        if not str(meta.get(required) or '').strip():
            raise SystemExit(f'{slug}: missing {required}')
    photo_path = folder / 'photo.jpg'
    if not photo_path.is_file():
        raise SystemExit(f'{slug}: photo.jpg is missing')
    photo = photo_path.read_bytes()
    from PIL import Image  # every post photo is a true 16:9 file (test_photo_aspect)
    with Image.open(photo_path) as im:
        ratio = im.size[0] / im.size[1]
    if not 1.74 <= ratio <= 1.80:
        raise SystemExit(f'{slug}: photo.jpg is {ratio:.3f}:1; it must be 16:9. '
                         f'Run python3 automation/crop_16x9.py {photo_path} and check heads by eye.')
    existing = next((item for item in articles if item.get('slug') == slug), None)
    is_new = existing is None
    article = record_for(meta, folder, existing)
    requested_focal = str(meta.get('focal_y') or '').strip()
    focal_changed = bool(requested_focal) and (existing or {}).get('imageFocal') != article.get('imageFocal')
    if not (existing and images_ready(existing, photo) and not focal_changed):
        write_images(article, photo_path, photo)
    articles, record_changed = upsert_record(articles, article)
    # The record now in the list is the one listings and the article end should see.
    article = next(item for item in articles if item.get('slug') == slug)
    page = render_page(meta, markdown, article, articles)
    page = site_nav.apply_now_bar(site_nav.ensure_fonts(page))
    import strip_espn_stats
    page = strip_espn_stats.clean(page)  # never credit ESPN for game stats  # keep the shared Now bar + fonts on rebuild
    page_changed = write_if_changed(ROOT / 'news' / slug / 'index.html', page)
    write_if_changed(ROOT / slug / 'index.html', redirect_html(slug))
    if not (is_new or record_changed or page_changed):
        return articles
    save_articles(articles)
    if is_new or record_changed:
        item = links._news_list_item(article)
        prepend_news_list(ROOT / 'news' / 'index.html', item, article)
        prepend_news_list(ROOT / 'authors' / 'ryan-moalemi' / 'index.html', item, article)
        window = {item.get('slug') for item in articles[:1 + links.MORE_STORY_LIMIT]}
        if is_new or slug in window:
            update_homepage(articles)
        update_sitemap_html(article)
        update_latest(article, articles)
        sync_feeds(articles)
    if is_new or page_changed or record_changed:
        team_coverage.refresh(ROOT)
    return articles


def main() -> None:
    folders = sorted(path for path in CONTENT.glob('*/') if (path / 'article.md').is_file())
    if not folders:
        return
    articles = load_articles()
    for folder in folders:
        articles = publish_folder(folder, articles)
    save_articles(articles)


if __name__ == '__main__':
    main()
