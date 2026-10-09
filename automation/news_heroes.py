#!/usr/bin/env python3
"""16:9 lead photos for news articles.

Writes hero-1200.webp (1200x675) and, when the source is wide enough,
hero-2x.webp. Never upscales. The original file stays the listing image.
imageFocal is a CSS object-position. The default is "center 20%".
A missing focal is measured from the source photo (OpenCV Haar) so the face
stays inside the 16:9 lead and the 1.91:1 social crop. No face uses the default.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image, ImageOps

import internal_links as links

ASPECT = 16 / 9
HERO_1X = (1200, 675)
# Open Graph and Twitter large cards are 1.91:1. 1200x628 is that ratio.
OG_1X = (1200, 628)
OG_ASPECT = OG_1X[0] / OG_1X[1]
# A second file is worth serving only when it is clearly sharper than 1200.
HERO_2X_MIN = 1440
HERO_2X_CAP = 2400
DEFAULT_FOCAL = links.DEFAULT_IMAGE_FOCAL
WEBP_QUALITY = 76
_FOCAL_WORD = r'(?:left|center|right|top|bottom|\d{1,3}(?:\.\d+)?%)'
FOCAL_RE = re.compile(rf'^{_FOCAL_WORD}(?:\s+{_FOCAL_WORD})?$', re.I)
OG_IMAGE_RE = re.compile(
    r'<meta\b[^>]*(?:property|name)="(?:og:image|twitter:image)"[^>]*>',
    re.I,
)
JSONLD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def parse_focal(value: str | None) -> tuple[float, float]:
    """CSS object-position as two fractions. Missing or invalid uses center 20%."""
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
    return 0.5 if axis == 'x' else 0.20


def format_focal(px: float, py: float) -> str:
    """CSS object-position. 50% on X is written as center."""
    def part(value: float, horizontal: bool) -> str:
        if horizontal and abs(value - 0.5) < 0.005:
            return 'center'
        return f'{int(round(value * 100))}%'

    return f'{part(px, True)} {part(py, False)}'


def cover_window(width: int, height: int, px: float, py: float,
                 aspect: float = ASPECT) -> tuple[float, float, float, float]:
    """Source rectangle for object-fit: cover at this object-position."""
    if width < 1 or height < 1:
        raise ValueError('image has no pixels')
    if width / height > aspect:
        crop_h = float(height)
        crop_w = height * aspect
    else:
        crop_w = float(width)
        crop_h = width / aspect
    left = (width - crop_w) * px
    top = (height - crop_h) * py
    return left, top, crop_w, crop_h


def focal_keeping_face(width: int, height: int, face: tuple[float, float, float, float],
                       default: tuple[float, float] | None = None,
                       aspect: float = OG_ASPECT) -> tuple[float, float]:
    """Move the default window only far enough to keep the face, with room for hair.

    face is (x, y, w, h) in source pixels. A face that already fits stays put.
    aspect is the tightest crop this focal has to satisfy. A 16:9 lead is taller
    than 1.91:1, so a face kept in the social crop stays in the lead and in cards.
    """
    if default is None:
        default = parse_focal(DEFAULT_FOCAL)
    px, py = default
    x, y, fw, fh = face
    if fw < 1 or fh < 1:
        return px, py
    # One face-height above the box leaves room for hair on a tight 1.91 crop.
    face_top = y - 0.9 * fh
    face_bot = y + fh + 0.12 * fh
    face_left = x - 0.15 * fw
    face_right = x + fw + 0.15 * fw
    left, top, crop_w, crop_h = cover_window(width, height, px, py, aspect)
    if face_top >= top and face_bot <= top + crop_h and face_left >= left and face_right <= left + crop_w:
        return px, py
    if height - crop_h > 1:
        if face_top < top:
            top = face_top
        if face_bot > top + crop_h:
            top = face_bot - crop_h
        top = max(0.0, min(height - crop_h, top))
        py = top / (height - crop_h)
    left, top, crop_w, crop_h = cover_window(width, height, px, py, aspect)
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


def crop_image(image: Image.Image, focal: str, aspect: float = ASPECT) -> Image.Image:
    px, py = parse_focal(focal)
    width, height = image.size
    left, top, crop_w, crop_h = cover_window(width, height, px, py, aspect)
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


def _resize(image: Image.Image, width: int, height: int | None = None) -> Image.Image:
    if height is None:
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
    og_path, og_w, og_h = _write_og(image, focal, source)
    result['imageOg'] = og_path
    result['imageOgWidth'] = og_w
    result['imageOgHeight'] = og_h
    return result


def _write_og(image: Image.Image, focal: str, source: Path) -> tuple[Path, int, int]:
    """1.91:1 social crop. Does not upscale. Shares the lead focal point."""
    cropped = crop_image(image, focal, OG_ASPECT)
    crop_w = cropped.size[0]
    wide = source.parent / 'og-1200.webp'
    small = source.parent / 'og.webp'
    if crop_w >= OG_1X[0]:
        small.unlink(missing_ok=True)
        _save(_resize(cropped, OG_1X[0], OG_1X[1]), wide)
        return wide, OG_1X[0], OG_1X[1]
    snapped = max(2, crop_w - (crop_w % 2))
    height = max(1, int(round(snapped / OG_ASPECT)))
    wide.unlink(missing_ok=True)
    _save(_resize(cropped, snapped, height), small)
    return small, snapped, height


def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = aw * ah + bw * bh - inter
    return inter / union if union else 0.0


def detect_faces(image: Image.Image) -> list[tuple[int, int, int, int]]:
    """Haar faces in source pixels. Empty when OpenCV is not installed."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []
    rgb = np.asarray(image.convert('RGB'))
    height, width = rgb.shape[:2]
    scale = 900 / max(height, width) if max(height, width) > 900 else 1.0
    small = rgb
    if scale < 1:
        small = cv2.resize(rgb, (max(1, int(width * scale)), max(1, int(height * scale))), interpolation=cv2.INTER_AREA)
    gray = cv2.equalizeHist(cv2.cvtColor(small, cv2.COLOR_RGB2GRAY))
    sh, sw = gray.shape[:2]
    min_side = max(20, int(min(sw, sh) * 0.045))
    names = (
        'haarcascade_frontalface_default.xml',
        'haarcascade_frontalface_alt2.xml',
        'haarcascade_profileface.xml',
    )
    raw: list[tuple[int, int, int, int]] = []
    for name in names:
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + name)
        if cascade.empty():
            continue
        found = cascade.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=5, minSize=(min_side, min_side))
        for x, y, fw, fh in found:
            raw.append((int(x), int(y), int(fw), int(fh)))
    profile = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_profileface.xml')
    if not profile.empty():
        flipped = cv2.flip(gray, 1)
        found = profile.detectMultiScale(flipped, scaleFactor=1.08, minNeighbors=5, minSize=(min_side, min_side))
        for x, y, fw, fh in found:
            raw.append((int(sw - x - fw), int(y), int(fw), int(fh)))
    inv = 1 / scale
    boxes = []
    area = width * height
    for x, y, fw, fh in raw:
        x, y, fw, fh = int(x * inv), int(y * inv), int(fw * inv), int(fh * inv)
        if fw < 12 or fh < 12 or fw * fh < 0.002 * area or fw * fh > 0.4 * area:
            continue
        boxes.append((x, y, fw, fh))
    boxes.sort(key=lambda box: box[2] * box[3], reverse=True)
    kept: list[tuple[int, int, int, int]] = []
    for box in boxes:
        if all(_iou(box, other) < 0.35 for other in kept):
            kept.append(box)
    return kept


def choose_face(boxes: list[tuple[int, int, int, int]], height: int,
                width: int = 0) -> tuple[int, int, int, int] | None:
    """Highest substantial face. Boxes glued to the side edge are partial detections."""
    if width:
        boxes = [box for box in boxes if box[0] > width * 0.04 and box[0] + box[2] < width * 0.96]
    if not boxes:
        return None
    largest_area = max(box[2] * box[3] for box in boxes)

    def center_y(box: tuple[int, int, int, int]) -> float:
        return box[1] + box[3] / 2

    candidates = [
        box for box in boxes
        if box[2] * box[3] >= 0.4 * largest_area and center_y(box) < height * 0.62
    ]
    pool = candidates or boxes
    return min(pool, key=lambda box: (center_y(box), -(box[2] * box[3])))


def suggest_focal(image: Image.Image) -> str:
    """Face-safe object-position. No detection, or no face, uses center 20%."""
    face = choose_face(detect_faces(image), image.size[1], image.size[0])
    if face is None:
        return DEFAULT_FOCAL
    px, py = focal_keeping_face(image.size[0], image.size[1], face)
    return format_focal(px, py)


def _web_path(root: Path, file: Path) -> str:
    return '/' + file.resolve().relative_to(root.resolve()).as_posix()


def focal_for(article: dict, image: Image.Image | None = None) -> str:
    """Stored object-position, or a face measurement, or center 20%."""
    raw = re.sub(r'\s+', ' ', str(article.get('imageFocal') or '').strip())
    if raw and FOCAL_RE.fullmatch(raw):
        return raw.lower()
    if image is not None:
        return suggest_focal(image)
    return DEFAULT_FOCAL


def ensure_article_hero(root: Path, article: dict) -> dict:
    """Write the hero and social crops. Listing image stays put.

    A post with no imageFocal is measured once and the result is stored, including
    the center 20% fallback, so a later build does not move the crop.
    """
    source = source_path(root, article)
    if source is None:
        return article
    if source.name in ('hero-1200.webp', 'hero-2x.webp', 'hero.webp', 'hero-16x9.webp', 'og-1200.webp', 'og.webp'):
        return article
    image = load_rgb(source)
    focal = focal_for(article, image)
    article['imageFocal'] = focal
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
    if written.get('imageOg'):
        article['imageOg'] = _web_path(root, written['imageOg'])
        article['imageOgWidth'] = written['imageOgWidth']
        article['imageOgHeight'] = written['imageOgHeight']
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
    social = str(article.get('imageOg') or article.get('imageHero') or '').strip()
    if social:
        html = _set_social_image(html, links.BASE + social)
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
