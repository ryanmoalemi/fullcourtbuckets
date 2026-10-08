#!/usr/bin/env python3
"""16:9 lead photos for news articles.

Writes hero-1200.webp (1200x675) and, when the source is wide enough,
hero-2x.webp. Never upscales. The original file stays the listing image.
imageFocal is a CSS object-position. The default is "center 25%".
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image, ImageOps

import internal_links as links

ASPECT = 16 / 9
HERO_1X = (1200, 675)
# A second file is worth serving only when it is clearly sharper than 1200.
HERO_2X_MIN = 1440
HERO_2X_CAP = 2400
DEFAULT_FOCAL = 'center 25%'
WEBP_QUALITY = 76
# Face check on October 4, 2026. These shift the default window up so the
# player's face stays in the 16:9 frame. Other stories already fit at center 25%.
CHECKED_FOCALS = {
    'angel-reese-game-1-liberty': 'center 6%',
    'liberty-dream-semis-game-1-recap': 'center 18%',
    # Full-body free-throw photo. 47% keeps the hair and the ball; 25% cuts the ball.
    'aces-valkyries-semis-game-2-recap': 'center 47%',
    'aces-fever-series-breakdown': 'center 11%',
    # Portrait slab. center 40% keeps JuJu's face; 25% cuts into the label and head.
    'top-10-womens-college-basketball-cards-to-collect-2026': 'center 40%',
}
_FOCAL_WORD = r'(?:left|center|right|top|bottom|\d{1,3}(?:\.\d+)?%)'
FOCAL_RE = re.compile(rf'^{_FOCAL_WORD}(?:\s+{_FOCAL_WORD})?$', re.I)
OG_IMAGE_RE = re.compile(
    r'<meta\b[^>]*(?:property|name)="(?:og:image|twitter:image)"[^>]*>',
    re.I,
)
JSONLD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def parse_focal(value: str | None) -> tuple[float, float]:
    """CSS object-position as two fractions. Missing or invalid uses center 25%."""
    text = re.sub(r'\s+', ' ', (value or '').strip().lower())
    if not text or FOCAL_RE.fullmatch(text) is None:
        text = DEFAULT_FOCAL
    parts = text.split()
    if len(parts) == 1:
        token = parts[0]
        if token in ('top', 'bottom') or token.endswith('%'):
            parts = ['center', token]
        else:
            parts = [token, 'center']
    return _focal_axis(parts[0], 'x'), _focal_axis(parts[1], 'y')


def _focal_axis(token: str, axis: str) -> float:
    words = {
        'left': 0.0, 'right': 1.0,
        'top': 0.0, 'bottom': 1.0,
        'center': 0.5,
    }
    if token in words:
        return words[token]
    if token.endswith('%'):
        return min(1.0, max(0.0, float(token[:-1]) / 100))
    return 0.5 if axis == 'x' else 0.25


def format_focal(px: float, py: float) -> str:
    """CSS object-position. 50% on X is written as center."""
    def part(value: float, horizontal: bool) -> str:
        if horizontal and abs(value - 0.5) < 0.005:
            return 'center'
        return f'{int(round(value * 100))}%'

    return f'{part(px, True)} {part(py, False)}'


def cover_window(width: int, height: int, px: float, py: float) -> tuple[float, float, float, float]:
    """Source rectangle for object-fit: cover at this object-position."""
    if width < 1 or height < 1:
        raise ValueError('image has no pixels')
    if width / height > ASPECT:
        crop_h = float(height)
        crop_w = height * ASPECT
    else:
        crop_w = float(width)
        crop_h = width / ASPECT
    left = (width - crop_w) * px
    top = (height - crop_h) * py
    return left, top, crop_w, crop_h


def focal_keeping_face(width: int, height: int, face: tuple[float, float, float, float],
                       default: tuple[float, float] = (0.5, 0.25)) -> tuple[float, float]:
    """Move the default window only far enough to keep the face, with room for hair.

    face is (x, y, w, h) in source pixels. A face that already fits stays put.
    """
    px, py = default
    x, y, fw, fh = face
    if fw < 1 or fh < 1:
        return px, py
    face_top = y - 0.55 * fh
    face_bot = y + fh + 0.12 * fh
    face_left = x - 0.15 * fw
    face_right = x + fw + 0.15 * fw
    left, top, crop_w, crop_h = cover_window(width, height, px, py)
    if face_top >= top and face_bot <= top + crop_h and face_left >= left and face_right <= left + crop_w:
        return px, py
    if height - crop_h > 1:
        if face_top < top:
            top = face_top
        if face_bot > top + crop_h:
            top = face_bot - crop_h
        top = max(0.0, min(height - crop_h, top))
        py = top / (height - crop_h)
    if width - crop_w > 1:
        if face_left < left:
            left = face_left
        if face_right > left + crop_w:
            left = face_right - crop_w
        left = max(0.0, min(width - crop_w, left))
        px = left / (width - crop_w)
    return px, py


def snap_width(width: int) -> int:
    """Largest width <= width that divides evenly into a 16:9 frame."""
    snapped = width - (width % 16)
    return max(16, snapped)


def crop_image(image: Image.Image, focal: str) -> Image.Image:
    px, py = parse_focal(focal)
    width, height = image.size
    left, top, crop_w, crop_h = cover_window(width, height, px, py)
    box = (
        int(round(left)),
        int(round(top)),
        int(round(left + crop_w)),
        int(round(top + crop_h)),
    )
    box = (
        max(0, min(width - 1, box[0])),
        max(0, min(height - 1, box[1])),
        max(1, min(width, box[2])),
        max(1, min(height, box[3])),
    )
    if box[2] <= box[0] or box[3] <= box[1]:
        raise ValueError('crop missed the image')
    return image.crop(box)


def _resize(image: Image.Image, width: int) -> Image.Image:
    height = width * 9 // 16
    if image.size == (width, height):
        return image
    return image.resize((width, height), Image.Resampling.LANCZOS)


def _save(image: Image.Image, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    flat = image.convert('RGB')
    flat.save(dest, 'WEBP', quality=WEBP_QUALITY, method=6)


def load_rgb(path: Path) -> Image.Image:
    image = Image.open(path)
    image = ImageOps.exif_transpose(image)
    image.load()
    if image.mode != 'RGB':
        image = image.convert('RGB')
    return image


def source_path(root: Path, article: dict) -> Path | None:
    raw = str(article.get('imageSource') or article.get('image') or '').strip()
    if not raw or raw.startswith(('http://', 'https://')):
        return None
    path = (root / raw.lstrip('/')).resolve()
    if not path.is_file():
        return None
    return path


def hero_paths(source: Path) -> tuple[Path, Path]:
    return source.parent / 'hero-1200.webp', source.parent / 'hero-2x.webp'


def write_heroes(source: Path, focal: str) -> dict:
    """Crop source. Returns file paths and pixel sizes. Does not upscale."""
    image = load_rgb(source)
    cropped = crop_image(image, focal)
    crop_w = snap_width(min(cropped.size[0], cropped.size[1] * 16 // 9))
    one_path, two_path = hero_paths(source)
    small_path = source.parent / 'hero-16x9.webp'
    result = {'focal': focal if focal != DEFAULT_FOCAL else ''}
    if crop_w >= HERO_1X[0]:
        small_path.unlink(missing_ok=True)
        _save(_resize(cropped, HERO_1X[0]), one_path)
        result['imageHero'] = one_path
        result['imageHeroWidth'] = HERO_1X[0]
        result['imageHeroHeight'] = HERO_1X[1]
        if crop_w >= HERO_2X_MIN:
            two_w = min(crop_w, snap_width(HERO_2X_CAP))
            _save(_resize(cropped, two_w), two_path)
            result['imageHero2x'] = two_path
            result['imageHero2xWidth'] = two_w
            result['imageHero2xHeight'] = two_w * 9 // 16
        else:
            two_path.unlink(missing_ok=True)
            result['imageHero2x'] = None
    else:
        one_path.unlink(missing_ok=True)
        two_path.unlink(missing_ok=True)
        _save(_resize(cropped, crop_w), small_path)
        result['imageHero'] = small_path
        result['imageHeroWidth'] = crop_w
        result['imageHeroHeight'] = crop_w * 9 // 16
        result['imageHero2x'] = None
    return result


def _web_path(root: Path, file: Path) -> str:
    return '/' + file.resolve().relative_to(root.resolve()).as_posix()


def focal_for(article: dict) -> str:
    raw = str(article.get('imageFocal') or '').strip()
    if raw and FOCAL_RE.fullmatch(re.sub(r'\s+', ' ', raw)):
        return re.sub(r'\s+', ' ', raw.lower())
    slug = str(article.get('slug') or '')
    return CHECKED_FOCALS.get(slug, DEFAULT_FOCAL)


def ensure_article_hero(root: Path, article: dict) -> dict:
    """Write the hero files and set imageHero fields. Listing image stays put."""
    source = source_path(root, article)
    if source is None:
        return article
    if source.name in ('hero-1200.webp', 'hero-2x.webp', 'hero.webp'):
        return article
    focal = focal_for(article)
    written = write_heroes(source, focal)
    if not article.get('imageSource'):
        article['imageSource'] = '/' + source.resolve().relative_to(root.resolve()).as_posix()
    article['imageHero'] = _web_path(root, written['imageHero'])
    article['imageHeroWidth'] = written['imageHeroWidth']
    article['imageHeroHeight'] = written['imageHeroHeight']
    if written.get('imageHero2x'):
        article['imageHero2x'] = _web_path(root, written['imageHero2x'])
        article['imageHero2xWidth'] = written['imageHero2xWidth']
        article['imageHero2xHeight'] = written['imageHero2xHeight']
    else:
        article.pop('imageHero2x', None)
        article.pop('imageHero2xWidth', None)
        article.pop('imageHero2xHeight', None)
    if focal != DEFAULT_FOCAL:
        article['imageFocal'] = focal
    else:
        article.pop('imageFocal', None)
    return article


def _set_social_image(html: str, url: str) -> str:
    def meta(match: re.Match) -> str:
        tag = match.group(0)
        if 'content="' in tag:
            return re.sub(r'content="[^"]*"', f'content="{url}"', tag, count=1)
        return tag

    html = OG_IMAGE_RE.sub(meta, html)

    def schema(match: re.Match) -> str:
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            return match.group(0)
        if not _stamp_article_image(data, url):
            return match.group(0)
        payload = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
        return '<script type="application/ld+json">' + payload + '</script>'

    return JSONLD_RE.sub(schema, html)


def _stamp_article_image(node, url: str) -> bool:
    changed = False
    if isinstance(node, dict):
        kind = node.get('@type')
        kinds = kind if isinstance(kind, list) else [kind]
        if 'NewsArticle' in kinds or 'Article' in kinds:
            if node.get('image') != [url]:
                node['image'] = [url]
                changed = True
        for value in node.values():
            if _stamp_article_image(value, url):
                changed = True
    elif isinstance(node, list):
        for item in node:
            if _stamp_article_image(item, url):
                changed = True
    return changed


def apply_article_html(html: str, article: dict) -> str:
    """Install the shared lead CSS and point the lead photo at the hero."""
    html = links.ensure_byline(html)
    html = links.order_news_lead(html, article)
    hero = str(article.get('imageHero') or '').strip()
    if hero:
        html = _set_social_image(html, 'https://fullcourtbuckets.com' + hero)
    return html


def publish(root: Path) -> list[str]:
    """Rebuild every article hero and refresh the published lead markup."""
    path = root / 'articles.json'
    articles = json.loads(path.read_text(encoding='utf-8'))
    notes = []
    for article in articles:
        before = str(article.get('imageHero') or '')
        ensure_article_hero(root, article)
        hero = str(article.get('imageHero') or '')
        page = root / 'news' / article['slug'] / 'index.html'
        if page.is_file() and hero:
            html = page.read_text(encoding='utf-8')
            updated = apply_article_html(html, article)
            if updated != html:
                page.write_text(updated, encoding='utf-8')
            notes.append(
                f"{article['slug']}: {hero} {article.get('imageHeroWidth')}x{article.get('imageHeroHeight')}"
                + (f" + {article.get('imageHero2xWidth')}w" if article.get('imageHero2x') else '')
                + (f" focal {article.get('imageFocal')}" if article.get('imageFocal') else '')
            )
        elif before != hero:
            notes.append(f"{article['slug']}: hero {hero or 'missing'}")
    path.write_text(json.dumps(articles, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return notes


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    for note in publish(root):
        print(note)


if __name__ == '__main__':
    main()
