#!/usr/bin/env python3
"""Splice reviewed season and career copy into published HTML.

Does not rebuild pages, so the shared header and nav stay as they are.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import build_couples
import build_players as builder
import career_summary
import internal_links
import research_careers
import team_hub
import team_season

ROOT = Path(__file__).resolve().parents[1]
ROLLOUT = ROOT / 'data' / 'wnba' / 'career-rollout.json'
PHOTOS = ROOT / 'data' / 'wnba' / 'licensed-photos.json'
BATCH = 50

LICENSE_HREFS = {
    'CC BY-SA 4.0': 'https://creativecommons.org/licenses/by-sa/4.0/',
    'CC BY-SA 2.0': 'https://creativecommons.org/licenses/by-sa/2.0/',
    'CC BY 4.0': 'https://creativecommons.org/licenses/by/4.0/',
    'CC BY 2.0': 'https://creativecommons.org/licenses/by/2.0/',
    'CC0': 'https://creativecommons.org/publicdomain/zero/1.0/',
}


def _load_json(path: Path, default):
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def _image_size(path: Path) -> tuple[int, int]:
    from PIL import Image
    with Image.open(path) as image:
        return image.size


def _license_href(name: str, page: str) -> str:
    return LICENSE_HREFS.get(name.strip(), page)


def write_licensed_photos() -> dict:
    index = _load_json(ROOT / 'data' / 'wnba' / 'players-index.json', {})
    active = {
        entry['slug']: entry.get('active_in_provider_feed') is True
        for entry in index.get('players') or []
    }
    names = {entry['name']: entry['slug'] for entry in index.get('players') or []}
    names.update(build_couples.load_slugs(ROOT))
    photos = {}
    for couple in build_couples.load_couples(ROOT):
        for side, key in (('a', 'photo_a'), ('b', 'photo_b')):
            person = str(couple.get(side) or '').strip()
            raw = str(couple.get(key) or '').strip()
            slug = names.get(person)
            if not person or not raw or not slug or active.get(slug, True) or slug in photos:
                continue
            page, author, license_name = [part.strip() for part in raw.split('|', 2)]
            file_slug = build_couples.slugify(person)
            path = ROOT / 'images' / 'couples' / f'{file_slug}.jpg'
            if not path.is_file():
                path = ROOT / 'images' / 'couples' / f'{file_slug}.webp'
            if not path.is_file():
                continue
            width, height = _image_size(path)
            photos[slug] = {
                'src': '/' + str(path.relative_to(ROOT)).replace('\\', '/'),
                'alt': person,
                'width': width,
                'height': height,
                'author': author,
                'page': page,
                'license': license_name,
                'license_href': _license_href(license_name, page),
                'focal': 'center 18%',
            }
    for slug, spec in team_hub.VISUALS.items():
        alt = str(spec.get('alt') or '')
        if ' of the ' not in alt:
            continue
        person = alt.split(' of the ', 1)[0].strip()
        player_slug = names.get(person)
        if not player_slug or active.get(player_slug, True) or player_slug in photos:
            continue
        src = str(spec.get('src') or '')
        if not src.startswith('/images/') or not (ROOT / src.lstrip('/')).is_file():
            continue
        photos[player_slug] = {
            'src': src,
            'alt': alt,
            'width': int(spec['width']),
            'height': int(spec['height']),
            'author': spec['author'],
            'page': spec['page'],
            'license': spec['license'],
            'license_href': spec['license_href'],
            'focal': 'center 20%',
        }
    if 'marta-xargay' not in photos:
        raise SystemExit('Marta Xargay photo was not added from the couples set.')
    PHOTOS.write_text(json.dumps(photos, indent=2) + '\n', encoding='utf-8')
    return photos


def ensure_rollout(extra: int = 0) -> tuple[list[str], list[str]]:
    """Return (released slugs, slugs added this call). extra adds the next batch."""
    current = _load_json(ROLLOUT, {'slugs': []})
    slugs = [slug for slug in current.get('slugs') or [] if isinstance(slug, str)]
    if extra <= 0 and slugs:
        return slugs, []
    ranked = [row['slug'] for row in research_careers.inactive_players()]
    have = set(slugs)
    added_slugs: list[str] = []
    for slug in ranked:
        if slug in have:
            continue
        page = ROOT / 'wnba' / slug / 'index.html'
        if not page.is_file():
            continue
        text = page.read_text(encoding='utf-8', errors='replace')
        if 'http-equiv="refresh"' in text.lower():
            continue
        slugs.append(slug)
        added_slugs.append(slug)
        have.add(slug)
        if extra and len(added_slugs) >= extra:
            break
        if not current.get('slugs') and len(added_slugs) >= BATCH:
            break
    ROLLOUT.parent.mkdir(parents=True, exist_ok=True)
    ROLLOUT.write_text(json.dumps({'slugs': slugs}, indent=2) + '\n', encoding='utf-8')
    return slugs, added_slugs


def _team_facts(page: str) -> str:
    """Season copy and story titles, ignoring image markup another pass may wrap."""
    season = re.search(r'<p class="season-summary">(.*?)</p>', page, re.S)
    news = re.search(r'<section class="section" id="team-news">(.*?)</section>', page, re.S)
    chunks = []
    if season:
        chunks.append(re.sub(r'<[^>]+>', '', season.group(1)))
    if news:
        chunks.append(re.sub(r'<[^>]+>', ' ', news.group(1)))
    return re.sub(r'\s+', ' ', ' '.join(chunks)).strip()


def patch_teams() -> list[str]:
    index = _load_json(ROOT / 'data' / 'wnba' / 'players-index.json', {})
    linking = internal_links.catalog_from_index(index)
    table = builder.load_standings_by_name(ROOT)
    done = []
    for slot in sorted(linking['by_id'].values(), key=lambda item: item['slug']):
        path = ROOT / 'wnba' / 'teams' / slot['slug'] / 'index.html'
        standing = table.get(slot['full_name']) or table.get(slot.get('name') or '')
        page = path.read_text(encoding='utf-8')
        updated = team_season.patch_team_html(page, ROOT, slot, standing)
        if _team_facts(page) != _team_facts(updated):
            path.write_text(updated, encoding='utf-8')
        done.append(slot['slug'])
    return done


def patch_players(slugs: list[str]) -> tuple[list[str], list[str]]:
    patched = []
    skipped = []
    for slug in slugs:
        path = ROOT / 'wnba' / slug / 'index.html'
        profile_path = ROOT / 'data' / 'wnba' / 'players' / f'{slug}.json'
        if not path.is_file() or not profile_path.is_file():
            skipped.append(f'{slug}: missing page or profile')
            continue
        page = path.read_text(encoding='utf-8')
        if 'http-equiv="refresh"' in page.lower():
            skipped.append(f'{slug}: redirect stub, left unchanged')
            continue
        profile = json.loads(profile_path.read_text(encoding='utf-8'))
        updated = career_summary.patch_player_html(page, profile, ROOT)
        if 'id="career"' not in updated:
            skipped.append(f'{slug}: no career section produced')
            continue
        path.write_text(updated, encoding='utf-8')
        career_summary.write_sources(ROOT, profile)
        patched.append(slug)
    return patched, skipped


def main() -> None:
    import sys
    extra = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    photos = write_licensed_photos()
    if extra:
        _slugs, added = ensure_rollout(extra)
    else:
        slugs, added = ensure_rollout(0)
        if not slugs:
            _slugs, added = ensure_rollout(BATCH)
    teams = patch_teams()
    patched, skipped = patch_players(added)
    print(f'teams {len(teams)} photos {len(photos)} players {len(patched)} skipped {len(skipped)}')
    for line in skipped:
        print('skip', line)


if __name__ == '__main__':
    main()
