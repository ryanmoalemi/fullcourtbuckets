#!/usr/bin/env python3
"""Resize site images to their real display size (2x) and serve WebP.

Original pixels are only resampled and re-encoded. Nothing is generated,
cropped, or retouched. A per-file failure keeps that file and is logged.
The command always exits 0 so a later image cannot block publication.

Player portraits stay on the approved path the portrait checker hashes.
Full-size masters in portrait-masters/ and portrait-handoff/ are not rewritten.
robots.txt, sitemaps, and FAQ copy are not edited.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import traceback
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
RASTER = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.avif'}
SKIP_DIRS = {'portrait-masters', 'portrait-handoff', '.git'}
UNTOUCHED_FILES = {
    'robots.txt', 'sitemap.xml', 'pages-sitemap.xml', 'player-sitemap.xml',
}
LOG_PATH = ROOT / 'docs' / 'image-optimize.log'
ALT_PATH = ROOT / 'docs' / 'missing-alt.md'
ILLUSTRATIONS = ROOT / 'content' / 'player-illustrations.json'

# CSS display box times two. Contain (thumbnail) unless noted.
LOGO_BOX = (760, 507)  # 2x the 380px header slot; WebP lands near 69 KB
AUTHOR_PHOTO_BOX = (320, 320)  # author page paints at 160px
BYLINE_BOX = (80, 80)  # byline paints at 40px
COUPLES_BOX = (192, 192)  # 2x the 96px bubble
TEAM_BOX = (960, 480)
ARTICLE_BOX = (1688, 8000)  # 2x the 844px article column; do not upscale
# A multi-hundred-kilobyte JPEG next to its WebP is not a useful fallback.
FALLBACK_KEEP_BELOW = 100_000
REESE_BOX = (1960, 2800)  # 2x the card dialog
PORTRAIT_COVER = (732, 1140)  # 2x the desktop portrait column
PORTRAIT_MIN_SIDE = 1024  # keep the publisher from rejecting a later sync

IMG_TAG = re.compile(r'<img\b[^>]*>', re.I)
ATTR = re.compile(r'([^\s=/>]+)(?:\s*=\s*(".*?"|\'.*?\'|[^\s>]+))?', re.S)
FIGURE_IMG = re.compile(r'<figure\b[^>]*>\s*(?:<picture\b[^>]*>\s*(?:<source\b[^>]*>\s*)*)?<img\b', re.I)


class OptimizeError(Exception):
    pass


def web_path(root: Path, file: Path) -> str:
    return '/' + file.resolve().relative_to(root.resolve()).as_posix()


def versioned(root: Path, file: Path) -> str:
    digest = hashlib.sha256(file.read_bytes()).hexdigest()[:12]
    return f'{web_path(root, file)}?v={digest}'


def load_image(path: Path) -> Image.Image:
    image = Image.open(path)
    image = ImageOps.exif_transpose(image)
    image.load()
    if getattr(image, 'n_frames', 1) != 1:
        raise OptimizeError('animated images are left unchanged')
    if image.mode == 'P':
        image = image.convert('RGBA' if 'transparency' in image.info else 'RGB')
    elif image.mode not in ('RGB', 'RGBA'):
        image = image.convert('RGBA' if 'A' in image.getbands() else 'RGB')
    return image


def fit_size(size: tuple[int, int], box: tuple[int, int], *, cover: bool = False,
             min_side: int = 0) -> tuple[int, int]:
    """Return a new size that never upscales and never changes aspect ratio."""
    width, height = size
    if width < 1 or height < 1:
        raise OptimizeError('image has no pixels')
    if cover:
        scale = max(box[0] / width, box[1] / height)
    else:
        scale = min(box[0] / width, box[1] / height)
    scale = min(scale, 1.0)
    if min_side and min(width, height) >= min_side:
        scale = min(1.0, max(scale, min_side / min(width, height)))
    if scale >= 0.999:
        return width, height
    return max(1, int(round(width * scale))), max(1, int(round(height * scale)))


def display_box(rel: str) -> tuple[tuple[int, int], bool, int]:
    """(box, cover, min_side) for a repo-relative posix path."""
    name = Path(rel).name
    if rel in ('logo.png', 'logo.webp') or name == 'logo.png':
        return LOGO_BOX, False, 0
    if rel.startswith('images/authors/') and 'byline' in name:
        return BYLINE_BOX, False, 0
    if rel.startswith('images/authors/'):
        return AUTHOR_PHOTO_BOX, False, 0
    if rel.startswith('images/couples/'):
        return COUPLES_BOX, False, 0
    if rel.startswith('images/teams/'):
        return TEAM_BOX, False, 0
    if rel.startswith('images/reese-cards/'):
        return REESE_BOX, False, 0
    if rel.startswith('images/articles/') or name.startswith('team-usa-') or name.startswith('world-cup-'):
        return ARTICLE_BOX, False, 0
    if '/portrait.' in f'/{name}' or rel.startswith('images/players/'):
        return PORTRAIT_COVER, True, PORTRAIT_MIN_SIDE
    return ARTICLE_BOX, False, 0


def is_approved_portrait(rel: str) -> bool:
    return bool(re.fullmatch(r'images/players/[^/]+/portrait\.(png|webp|avif)', rel))


def quality_for(rel: str, opaque_png: bool) -> int:
    if rel.startswith('images/authors/'):
        return 90
    if rel in ('logo.png', 'logo.webp'):
        return 82
    if opaque_png and not is_approved_portrait(rel):
        return 85
    if is_approved_portrait(rel) or rel.startswith('images/players/'):
        return 78
    if rel.startswith('images/articles/') or Path(rel).name.startswith(('team-usa-', 'world-cup-')):
        return 62
    return 75


def save_webp(image: Image.Image, dest: Path, quality: int) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    image.save(dest, 'WEBP', quality=quality, method=6)


def save_fallback(image: Image.Image, dest: Path, quality: int) -> None:
    suffix = dest.suffix.lower()
    if suffix in ('.jpg', '.jpeg'):
        out = image.convert('RGB')
        out.save(dest, 'JPEG', quality=quality, optimize=True)
        return
    if suffix == '.png':
        # Opaque PNGs that are still huge after a normal save, including the
        # logo fallback, get a 256-color PNG. The WebP file stays truecolor.
        if 'A' not in image.getbands() and _png_bytes(image) > 400_000:
            reduced = image.convert('RGB').quantize(colors=256, method=Image.Quantize.FASTOCTREE)
            reduced.save(dest, 'PNG', optimize=True)
            return
        image.save(dest, 'PNG', optimize=True)
        return
    if suffix == '.webp':
        save_webp(image, dest, quality)
        return
    if suffix == '.gif':
        image.save(dest, 'GIF')
        return
    if suffix == '.avif':
        image.save(dest, 'AVIF', quality=quality)
        return
    raise OptimizeError(f'no encoder for {suffix}')


def _png_bytes(image: Image.Image) -> int:
    buffer = io.BytesIO()
    image.save(buffer, 'PNG', optimize=True)
    return buffer.tell()


def iter_rasters(root: Path):
    for path in root.rglob('*'):
        if not path.is_file() or path.suffix.lower() not in RASTER:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name in UNTOUCHED_FILES:
            continue
        yield path


def approved_sources(root: Path) -> set[str]:
    path = root / 'content' / 'player-illustrations.json'
    if not path.is_file():
        return set()
    manifest = json.loads(path.read_text(encoding='utf-8'))
    return {str(record.get('src') or '').split('?')[0] for record in manifest.get('portraits', [])}


def _drop_bulky_fallback(path: Path, webp_path: Path, src: str, rel: str,
                          log: list[str], moves: dict[str, Path]) -> bool:
    """Drop a fallback the browser will not fetch when WebP is smaller to ship."""
    if path.name == 'logo.png' or not path.exists() or path == webp_path:
        return False
    if path.stat().st_size <= FALLBACK_KEEP_BELOW:
        return False
    path.unlink()
    moves[src] = webp_path
    log.append(
        f'fallback dropped {rel}; serving {webp_path.name} ({webp_path.stat().st_size} bytes)'
    )
    return True


def optimize_file(root: Path, path: Path, log: list[str], moves: dict[str, Path],
                  approved: set[str]) -> bool:
    """Return True when the file bytes change. Never raises."""
    rel = path.relative_to(root).as_posix()
    src = '/' + rel
    try:
        image = load_image(path)
        box, cover, min_side = display_box(rel)
        approved_file = src in approved or is_approved_portrait(rel)
        new_size = fit_size(
            image.size, box, cover=cover,
            min_side=min_side if approved_file else 0,
        )
        opaque = 'A' not in image.getbands()
        quality = quality_for(rel, opaque and path.suffix.lower() == '.png')
        webp_path = path if path.suffix.lower() == '.webp' else path.with_suffix('.webp')
        already_fits = new_size == image.size
        # The hashed portrait file is what the browser must load. Do not add a
        # second file that a <picture> element would select instead.
        if approved_file and already_fits:
            return False
        if already_fits and path.suffix.lower() == '.webp':
            return False
        if already_fits and webp_path.is_file() and path.suffix.lower() != '.webp':
            if path.name == 'logo.png' and path.stat().st_size > 400_000 and 'A' not in image.getbands():
                reduced = image.convert('RGB').quantize(colors=256, method=Image.Quantize.FASTOCTREE)
                reduced.save(path, 'PNG', optimize=True)
                log.append(f'logo fallback quantized to {path.stat().st_size} bytes')
                return True
            return _drop_bulky_fallback(path, webp_path, src, rel, log, moves)
        resized = image if already_fits else image.resize(new_size, Image.Resampling.LANCZOS)
        if approved_file:
            target = path.with_suffix('.webp') if path.suffix.lower() == '.png' else path
            before = path.read_bytes()
            save_webp(resized, target, quality)
            check = load_image(target)
            alpha = check.convert('RGBA').getchannel('A').getextrema()
            if alpha[0] >= 255 or alpha[1] <= 0:
                if target == path:
                    target.write_bytes(before)
                else:
                    target.unlink(missing_ok=True)
                raise OptimizeError('portrait lost its real transparency; original kept')
            if target != path and path.exists():
                path.unlink()
                moves[src] = target
            _update_portrait_record(root, rel, target)
            log.append(f'portrait {rel} -> {target.relative_to(root).as_posix()} {check.size} {target.stat().st_size} bytes')
            return True
        if path.suffix.lower() != '.webp':
            save_webp(resized, webp_path, quality)
        if not already_fits:
            save_fallback(resized, path, quality)
        if path.suffix.lower() != '.webp' and path.exists():
            dropped = _drop_bulky_fallback(path, webp_path, src, rel, log, moves)
            if dropped:
                return True
        log.append(
            f'resized {rel} to {resized.size} ({path.stat().st_size} bytes) + {webp_path.name}'
        )
        return True
    except Exception as exc:
        log.append(f'KEPT {rel}: {exc}')
        return False


def _update_portrait_record(root: Path, old_rel: str, new_file: Path) -> None:
    path = root / 'content' / 'player-illustrations.json'
    if not path.is_file():
        return
    manifest = json.loads(path.read_text(encoding='utf-8'))
    old_src = '/' + old_rel
    new_src = web_path(root, new_file)
    image = load_image(new_file)
    digest = hashlib.sha256(new_file.read_bytes()).hexdigest()
    changed = False
    for record in manifest.get('portraits', []):
        src = str(record.get('src') or '')
        if src.split('?')[0] not in (old_src, new_src):
            continue
        record['src'] = new_src
        record['width'], record['height'] = image.size
        record['asset_sha256'] = digest
        settings = dict(record.get('export_settings') or {})
        settings.setdefault('source_width', image.size[0])
        settings.setdefault('source_height', image.size[1])
        settings['upscaled'] = False
        settings['reencoded'] = True
        settings['original_bytes_preserved'] = False
        settings['optimized_for_display'] = True
        record['export_settings'] = settings
        record['original_bytes_preserved'] = False
        changed = True
    if changed:
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _attrs(tag: str) -> list[tuple[str, str | None]]:
    body = tag[4:-1].strip()
    if body.endswith('/'):
        body = body[:-1]
    found = []
    for match in ATTR.finditer(body):
        name, value = match.group(1), match.group(2)
        if value is None:
            found.append((name, None))
        else:
            found.append((name, value))
    return found


def _attr_map(tag: str) -> dict[str, str | None]:
    return {name.lower(): value for name, value in _attrs(tag)}


def _unquote(value: str | None) -> str:
    if value is None:
        return ''
    if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
        return value[1:-1]
    return value


def _quote(value: str) -> str:
    return '"' + value.replace('"', '&quot;') + '"'


def _resolve_image(root: Path, src: str, moves: dict[str, Path]) -> Path | None:
    """Find the file a src should use, including a WebP stand-in for a removed original."""
    bare = src.split('#', 1)[0].split('?', 1)[0]
    if bare in moves:
        return moves[bare]
    file = _src_file(root, src)
    if file is not None:
        return file
    if not bare or bare.startswith(('http://', 'https://', 'data:', '//')):
        return None
    candidate = (root / bare.lstrip('/')).resolve().with_suffix('.webp')
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _src_file(root: Path, src: str) -> Path | None:
    bare = src.split('#', 1)[0].split('?', 1)[0]
    if not bare or bare.startswith(('http://', 'https://', 'data:', '//')):
        return None
    file = (root / bare.lstrip('/')).resolve()
    try:
        file.relative_to(root.resolve())
    except ValueError:
        return None
    return file if file.is_file() else None


def _rebuild_img(tag: str, *, width: int | None, height: int | None, src: str | None,
                 lcp: bool) -> str:
    attrs = []
    seen = set()
    for name, raw in _attrs(tag):
        key = name.lower()
        if key in ('width', 'height', 'loading', 'decoding', 'fetchpriority'):
            continue
        if key == 'src' and src is not None:
            attrs.append((name, _quote(src)))
            seen.add('src')
            continue
        if raw is None:
            attrs.append((name, None))
        else:
            attrs.append((name, raw))
        seen.add(key)
    if 'src' not in seen and src is not None:
        attrs.insert(0, ('src', _quote(src)))
    if width and height:
        attrs.append(('width', f'"{width}"'))
        attrs.append(('height', f'"{height}"'))
    attrs.append(('decoding', '"async"'))
    if lcp:
        attrs.append(('fetchpriority', '"high"'))
    else:
        attrs.append(('loading', '"lazy"'))
    parts = []
    for name, raw in attrs:
        parts.append(name if raw is None else f'{name}={raw}')
    return '<img ' + ' '.join(parts) + '>'


def _inside_picture(html: str, start: int) -> bool:
    window = html[max(0, start - 400):start].lower()
    return '<picture' in window and window.rfind('<picture') > window.rfind('</picture>')


def _lcp_positions(html: str) -> set[int]:
    """Byte offsets of the one hero image on this page, if it has one."""
    heroes = []
    for match in IMG_TAG.finditer(html):
        attrs = _attr_map(match.group(0))
        classes = _unquote(attrs.get('class'))
        ident = _unquote(attrs.get('id'))
        if 'feature-photo' in classes or ident == 'featured-image':
            heroes.append(match.start())
        elif 'player-illustration' in classes or 'hero-photo' in classes:
            heroes.append(match.start())
    if heroes:
        return {heroes[0]}
    figure = FIGURE_IMG.search(html)
    if figure:
        img_at = figure.group(0).lower().rfind('<img')
        return {figure.start() + img_at}
    for match in IMG_TAG.finditer(html):
        src = _unquote(_attr_map(match.group(0)).get('src'))
        if 'logo' in src:
            return {match.start()}
    return set()


def rewrite_html(root: Path, html: str, moves: dict[str, Path] | None = None,
                 approved: set[str] | None = None) -> tuple[str, list[str]]:
    """Return updated HTML and src values for <img> tags that have no alt attribute."""
    moves = moves or {}
    approved = approved or set()
    missing = []
    lcp_at = _lcp_positions(html)
    pieces = []
    cursor = 0
    for match in IMG_TAG.finditer(html):
        tag = match.group(0)
        attrs = _attr_map(tag)
        if 'alt' not in attrs:
            missing.append(_unquote(attrs.get('src')))
        src_raw = _unquote(attrs.get('src'))
        bare = src_raw.split('#', 1)[0].split('?', 1)[0]
        file = _resolve_image(root, src_raw, moves)
        width = height = None
        new_src = None
        webp = None
        if file is not None:
            try:
                image = load_image(file)
                width, height = image.size
            except Exception:
                width = height = None
            query = src_raw.split('?', 1)[1] if '?' in src_raw else ''
            query = f'?{query}' if query else ''
            if file.suffix.lower() in RASTER and any(part in SKIP_DIRS for part in file.parts):
                pass
            else:
                path = web_path(root, file)
                if bare in moves or query.startswith('?v=') or path != bare:
                    digest = hashlib.sha256(file.read_bytes()).hexdigest()[:12]
                    new_src = f'{path}?v={digest}' if (bare in moves or query.startswith('?v=')) else path
                else:
                    new_src = src_raw or path
                sibling = file.with_suffix('.webp')
                classes = _unquote(attrs.get('class'))
                approved_src = bare in approved or path in approved
                if (sibling.is_file() and sibling != file
                        and 'player-illustration' not in classes
                        and not approved_src
                        and not _inside_picture(html, match.start())):
                    webp = web_path(root, sibling)
        rebuilt = _rebuild_img(
            tag, width=width, height=height, src=new_src, lcp=match.start() in lcp_at,
        )
        if webp:
            rebuilt = f'<picture><source srcset="{webp}" type="image/webp">{rebuilt}</picture>'
        pieces.append(html[cursor:match.start()])
        pieces.append(rebuilt)
        cursor = match.end()
    pieces.append(html[cursor:])
    return ''.join(pieces), missing


def lock_logo_slot(html: str) -> str:
    """Keep the header logo box stable once width and height describe the real file."""
    return html.replace(
        '.brand img{display:block;width:235px;max-height:85px;object-fit:contain}',
        '.brand img{display:block;width:235px;height:85px;object-fit:contain;object-position:left center}',
    ).replace(
        '.brand img{width:380px;max-height:112px;object-fit:contain;object-position:left center}',
        '.brand img{width:380px;height:112px;object-fit:contain;object-position:left center}',
    ).replace(
        'header img{height:34px;vertical-align:middle;margin-right:22px}',
        'header img{height:34px;width:auto;vertical-align:middle;margin-right:22px}',
    )


def patch_homepage_script(html: str) -> str:
    """Keep the hero picture in sync when the homepage script swaps stories."""
    needle = 'photo.src = featured.image;\n        photo.alt = featured.imageAlt || featured.title || "";'
    insert = (
        'photo.src = featured.image;\n'
        '        photo.alt = featured.imageAlt || featured.title || "";\n'
        '        if (featured.imageWidth) { photo.width = featured.imageWidth; photo.height = featured.imageHeight; }\n'
        '        var heroSource = photo.parentNode && photo.parentNode.querySelector'
        ' ? photo.parentNode.querySelector("source[type=\\"image/webp\\"]") : null;\n'
        '        if (heroSource && featured.image) {\n'
        '          heroSource.srcset = String(featured.image).replace(/\\.(png|jpe?g)(\\?.*)?$/i, ".webp$2");\n'
        '        }'
    )
    if 'heroSource' not in html and needle in html:
        html = html.replace(needle, insert, 1)
    old_img = (
        '      var img = document.createElement("img");\n'
        '      img.alt = a.imageAlt || a.title || "WNBA story photo";\n'
        '      if (a.image) img.src = a.image;\n'
        '      card.querySelector(".article-visual").appendChild(img);'
    )
    new_img = (
        '      var img = document.createElement("img");\n'
        '      img.alt = a.imageAlt || a.title || "WNBA story photo";\n'
        '      img.decoding = "async";\n'
        '      img.loading = "lazy";\n'
        '      if (a.imageWidth) { img.width = a.imageWidth; img.height = a.imageHeight; }\n'
        '      if (a.image) img.src = a.image;\n'
        '      var visual = card.querySelector(".article-visual");\n'
        '      if (a.image && /\\.(png|jpe?g)$/i.test(String(a.image).split("?")[0])) {\n'
        '        var picture = document.createElement("picture");\n'
        '        var source = document.createElement("source");\n'
        '        source.type = "image/webp";\n'
        '        source.srcset = String(a.image).replace(/\\.(png|jpe?g)(\\?.*)?$/i, ".webp$2");\n'
        '        picture.appendChild(source);\n'
        '        picture.appendChild(img);\n'
        '        visual.appendChild(picture);\n'
        '      } else {\n'
        '        visual.appendChild(img);\n'
        '      }'
    )
    if 'source.type = "image/webp"' not in html and old_img in html:
        html = html.replace(old_img, new_img, 1)
    return html


LOCAL_IMAGE_URL = re.compile(
    r'(?<!:)(?P<path>/(?:images/|logo)[^"\'\s?)]+\.(?:png|jpe?g|webp|avif|gif))(?P<query>\?v=[0-9a-fA-F]+)?'
)


def repair_image_urls(root: Path) -> int:
    """Point leftover URLs at a WebP stand-in and refresh ?v= hashes."""
    changed = 0
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.suffix.lower() not in {'.html', '.json', '.css', '.js'}:
            continue
        if any(part in SKIP_DIRS or part == '.git' for part in path.parts):
            continue
        if path.name in UNTOUCHED_FILES:
            continue
        original = path.read_text(encoding='utf-8')

        def replace(match: re.Match) -> str:
            url = match.group('path')
            file = (root / url.lstrip('/')).resolve()
            try:
                file.relative_to(root.resolve())
            except ValueError:
                return match.group(0)
            target = file
            if not target.is_file():
                sibling = file.with_suffix('.webp')
                if sibling.is_file():
                    target = sibling
                else:
                    return match.group(0)
            new = '/' + target.relative_to(root.resolve()).as_posix()
            if match.group('query'):
                digest = hashlib.sha256(target.read_bytes()).hexdigest()[:12]
                return f'{new}?v={digest}'
            return new

        updated = LOCAL_IMAGE_URL.sub(replace, original)
        if updated != original:
            path.write_text(updated, encoding='utf-8')
            changed += 1
    return changed


def retarget_documents(root: Path, moves: dict[str, Path]) -> int:
    """Point existing URLs at the file that replaced a dropped original."""
    if not moves:
        return 0
    pairs = sorted(
        ((old, web_path(root, new)) for old, new in moves.items()),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    changed = 0
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.suffix.lower() not in {'.html', '.json', '.css', '.js'}:
            continue
        if any(part in SKIP_DIRS or part == '.git' for part in path.parts):
            continue
        if path.name in UNTOUCHED_FILES:
            continue
        original = path.read_text(encoding='utf-8')
        updated = original
        for old, new in pairs:
            updated = updated.replace(old, new)
        if updated != original:
            path.write_text(updated, encoding='utf-8')
            changed += 1
    return changed


def drop_unreferenced_root_copies(root: Path, log: list[str]) -> None:
    """Remove root copies that only duplicate a file already published under images/."""
    blobs = []
    for path in root.rglob('*'):
        if not path.is_file() or path.suffix.lower() not in {'.html', '.json', '.css', '.js', '.xml'}:
            continue
        if any(part in SKIP_DIRS or part == '.git' for part in path.parts):
            continue
        blobs.append(path.read_text(encoding='utf-8', errors='ignore'))
    blob = '\n'.join(blobs)
    published = set()
    images = root / 'images'
    if images.is_dir():
        published = {path.name for path in images.rglob('*') if path.is_file()}
    for path in list(root.iterdir()):
        if not path.is_file() or path.suffix.lower() not in RASTER:
            continue
        if path.name in ('logo.png', 'logo.webp') or path.name not in published:
            continue
        if re.search(rf'(?<![\w./-])/{re.escape(path.name)}(?![\w.-])', blob):
            continue
        path.unlink()
        log.append(f'removed unreferenced root image {path.name}')


def stamp_articles(root: Path) -> None:
    path = root / 'articles.json'
    if not path.is_file():
        return
    articles = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(articles, list):
        return
    for article in articles:
        image_src = str(article.get('image') or '')
        file = _resolve_image(root, image_src, {})
        if file is None:
            continue
        article['image'] = web_path(root, file)
        try:
            image = load_image(file)
        except Exception:
            continue
        article['imageWidth'], article['imageHeight'] = image.size
    path.write_text(json.dumps(articles, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_missing_alt(root: Path, pages: list[tuple[str, list[str]]]) -> None:
    alt_path = root / 'docs' / 'missing-alt.md'
    alt_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [(page, src) for page, srcs in pages for src in srcs]
    lines = [
        '# Images missing alt text',
        '',
        'No alt text was written or changed. Existing alt attributes were left as they are.',
        'Ryan can review anything listed here.',
        '',
    ]
    if not rows:
        lines.append('No `<img>` elements are missing an alt attribute.')
    else:
        lines.append(f'{len(rows)} `<img>` element(s) have no alt attribute.')
        lines.append('')
        for page, src in rows:
            lines.append(f'- `{page}` — `{src or "(no src)"}`')
    lines.append('')
    alt_path.write_text('\n'.join(lines), encoding='utf-8')


def optimize_tree(root: Path | None = None) -> dict:
    root = (root or ROOT).resolve()
    log: list[str] = []
    moves: dict[str, Path] = {}
    drop_unreferenced_root_copies(root, log)
    approved = approved_sources(root)
    changed = 0
    for path in sorted(iter_rasters(root), key=lambda item: item.as_posix()):
        if optimize_file(root, path, log, moves, approved):
            changed += 1
    retarget_documents(root, moves)
    repair_image_urls(root)
    approved = approved_sources(root)
    missing_pages = []
    html_changed = 0
    for path in sorted(root.rglob('*.html')):
        if any(part in SKIP_DIRS or part == '.git' for part in path.parts):
            continue
        if path.name in UNTOUCHED_FILES:
            continue
        original = path.read_text(encoding='utf-8')
        updated, missing = rewrite_html(root, original, moves, approved)
        updated = lock_logo_slot(updated)
        if path.name == 'index.html' and path.parent == root:
            updated = patch_homepage_script(updated)
        if missing:
            missing_pages.append((path.relative_to(root).as_posix(), missing))
        if updated != original:
            path.write_text(updated, encoding='utf-8')
            html_changed += 1
    stamp_articles(root)
    write_missing_alt(root, missing_pages)
    log_path = root / 'docs' / 'image-optimize.log'
    log_path.parent.mkdir(parents=True, exist_ok=True)
    summary = [
        f'files rewritten: {changed}',
        f'html files rewritten: {html_changed}',
        f'images missing alt: {sum(len(srcs) for _, srcs in missing_pages)}',
        '',
        *log,
    ]
    log_path.write_text('\n'.join(summary) + '\n', encoding='utf-8')
    return {'changed': changed, 'html': html_changed, 'log': log, 'missing': missing_pages}


def main() -> int:
    try:
        result = optimize_tree(ROOT)
    except Exception:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOG_PATH.write_text(traceback.format_exc(), encoding='utf-8')
        print('Image optimizer hit an unexpected error. Originals were left in place where the run stopped.', file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        return 0
    print(f'Optimized images. Files touched: {result["changed"]}. HTML files: {result["html"]}.')
    print(f'Log: {LOG_PATH.relative_to(ROOT)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
