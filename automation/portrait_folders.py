#!/usr/bin/env python3
"""Approved image in images/players/<slug>/portrait.ext -> automatic mapping.

Reads original bytes only. Never resizes, recompresses, stretches or generates art.
Only place owner-approved artwork in these publishing folders, never drafts.
"""
from __future__ import annotations
import copy
import hashlib
import io
import json
from pathlib import Path
import re
from PIL import Image

SLUG = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*\Z')
FORMATS = {'.png': 'PNG', '.webp': 'WEBP', '.avif': 'AVIF'}
MANAGER = 'approved-player-folder-v1'


def matches_player_path(src: str, slug: str) -> bool:
    if not isinstance(src, str) or not isinstance(slug, str) or not SLUG.fullmatch(slug):
        return False
    return bool(re.fullmatch(r'/images/players/' + re.escape(slug) +
                            r'(?:-[a-z0-9._-]+|/portrait)\.(?:png|webp|avif)', src))


def record_for(root: Path, file: Path, prior: dict | None = None) -> dict:
    slug = file.parent.name
    if (not SLUG.fullmatch(slug) or file.parent.is_symlink() or file.is_symlink()
            or not file.resolve().is_relative_to((root/'images/players').resolve())):
        raise ValueError('Unsafe player image folder')
    profile_file = root/'data/wnba/players'/f'{slug}.json'
    if not profile_file.is_file():
        raise ValueError(f'Unknown player folder: {slug}')
    profile = json.loads(profile_file.read_text())
    player = profile['player']
    if profile['slug'] != slug or type(player['id']) is not int:
        raise ValueError(f'Invalid player record: {slug}')
    raw = file.read_bytes()
    if not 0 < len(raw) <= 12_000_000:
        raise ValueError(f'{slug}: image must be nonempty and at most 12 MB')
    digest = hashlib.sha256(raw).hexdigest()
    try:
        image = Image.open(io.BytesIO(raw))
        if image.width * image.height > 25_000_000 or getattr(image, 'n_frames', 1) != 1:
            raise ValueError('Use a still image under 25 megapixels')
        image.load()
        width, height = image.size
        alpha = image.convert('RGBA').getchannel('A').getextrema()
        if image.format != FORMATS[file.suffix]:
            raise ValueError('Image extension does not match its file format')
    except Exception as exc:
        raise ValueError(f'{slug}: invalid image: {exc}') from exc
    if alpha[0] == 255 or alpha[1] == 0:
        raise ValueError(f'{slug}: use visible artwork with actual transparency')
    if not (640 <= width <= 10000 and 650 <= height <= 10000):
        raise ValueError(f'{slug}: undersized portrait; upload the original, not a thumbnail')

    # A previously approved full-quality export can move folders unchanged.
    # Its recorded master dimensions remain valid because its bytes are identical.
    same = (prior is not None and prior.get('player_id') == player['id']
            and prior.get('asset_sha256') == digest)
    settings = copy.deepcopy(prior.get('export_settings', {})) if same else {}
    if not settings:
        if min(width, height) < 1024:
            raise ValueError(f'{slug}: new uploads need an original of at least 1024px per side')
        settings = {'format': image.format, 'width': width, 'height': height,
                    'source_width': width, 'source_height': height, 'upscaled': False,
                    'original_bytes_preserved': True, 'reencoded': False}
    record = copy.deepcopy(prior) if same else {}
    name = ' '.join(str(player.get(k) or '').strip() for k in ('first_name', 'last_name')).strip()
    record.update(player_id=player['id'], slug=slug, player_name=name, approved=True,
                  kind='illustration', src='/' + file.relative_to(root).as_posix(),
                  width=width, height=height, asset_sha256=digest,
                  quality_standard='fcb-portrait-640x650-v2', managed_by=MANAGER,
                  original_bytes_preserved=True, export_settings=settings)
    if not same:
        record['source'] = ('Owner-approved illustration uploaded to the player publishing folder. '
                            'Original bytes retained without resizing or recompression.')
        record['display'] = ('Existing compact desktop/mobile template. Proportional shoulder crop; '
                             'names and statistics remain HTML. No square card or visible caption.')
    return record


def sync(root: Path) -> int:
    """Derive the implementation manifest; users never edit it per image."""
    root = root.resolve()
    folder_root = root/'images/players'
    if not folder_root.is_dir():
        return 0
    manifest_path = root/'content/player-illustrations.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {'schema_version': 1, 'portraits': []}
    old = manifest['portraits']
    known = {r['slug']: r for r in old}
    found = {}
    for folder in sorted(folder_root.iterdir()):
        if not folder.is_dir():
            continue
        files = [folder/('portrait' + ext) for ext in FORMATS if (folder/('portrait' + ext)).exists()]
        if not files:
            continue
        if len(files) != 1:
            raise ValueError(f'{folder.name}: keep exactly one portrait.png, portrait.webp or portrait.avif')
        found[folder.name] = record_for(root, files[0], known.get(folder.name))
    records = [found.pop(r['slug'], r) for r in old
               if r.get('managed_by') != MANAGER or r['slug'] in found]
    records.extend(found.values())
    ids = [r['player_id'] for r in records]
    slugs = [r['slug'] for r in records]
    hashes = [r['asset_sha256'] for r in records if r.get('asset_sha256')]
    if len(ids) != len(set(ids)) or len(slugs) != len(set(slugs)) or len(hashes) != len(set(hashes)):
        raise ValueError('Duplicate player mapping or identical image assigned to different players')
    if old != records:
        manifest['portraits'] = records
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = manifest_path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
        temporary.replace(manifest_path)
    count = sum(r.get('managed_by') == MANAGER for r in records)
    print(f'Player folders: {count} approved originals mapped automatically; image files unchanged.')
    return count


if __name__ == '__main__':
    sync(Path(__file__).resolve().parents[1])
