#!/usr/bin/env python3
"""Apply the approved compact player layout to the whole archive.

Uses the exact Caitlin CSS as its source of truth. Does not call an image service,
copy a player's portrait onto another person, or mark pending art as published.
Run after build_players.py and apply_portraits.py on every website build.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
import re

from apply_portraits import CSS as APPROVED_CSS, ASSET

BASE = 'https://fullcourtbuckets.com'
VERSION = 'fcb-compact-player-v1'
SLUG = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*\Z')
HERO = re.compile(r'<section class="([^"]*)" aria-labelledby="player-name"(?: data-name-size="[a-z]+")?>')
OLD_ART = re.compile(r'<div class="hero-art" aria-hidden="true">.*?</small></div>', re.S)
STYLE = re.compile(r'<style id="fcb-shared-player-layout">.*?</style>', re.S)
SHARED_CSS = APPROVED_CSS.replace('.has-player-portrait', '.fcb-player-compact') + '''
/* Full names remain HTML. Long surnames get room without a tall mobile hero. */
.fcb-player-compact[data-name-size="long"] h1>b{font-size:clamp(48px,5.8vw,76px)}
.fcb-player-compact[data-name-size="xlong"] h1>b{font-size:clamp(36px,4.3vw,56px)}
@media(max-width:780px){
 .fcb-player-compact[data-name-size="long"] h1>b{font-size:clamp(27px,6.2vw,44px)}
 .fcb-player-compact[data-name-size="xlong"] h1>b{font-size:clamp(23px,5vw,35px)}
}
@media(max-width:480px){
 .fcb-player-compact[data-name-size="long"] h1>b{font-size:29px}
 .fcb-player-compact[data-name-size="xlong"] h1>b{font-size:25px;line-height:1.08}
 .fcb-player-compact[data-name-size="xlong"] h1>span{font-size:26px}
}
'''

BRIEF = (
    'Original editorial basketball-player illustration in the approved Full Court Buckets style. '
    'Recognizable individual facial features, realistic proportions, confident natural expression, '
    'clean outlines and detailed graphic-novel shading. Exactly one player. Head and shoulders, '
    'top of hair fully visible with a little headroom; upper chest and both upper arms extend '
    'past the bottom of the frame for a clean straight crop. Transparent alpha background. '
    'Plain white basketball top with dark trim, without team or sponsor logos, numbers, names, '
    'watermarks or captions. No scenery or decorative shapes inside the image. '
    'The website supplies the background, every label and all statistics as HTML. '
    'Use the approved Caitlin illustration only for art direction, not as another player\'s face. '
    'A name or provider ID is not proof that a generated likeness is accurate; review before publication.'
)
FEATURED = ['angel-reese', 'aja-wilson', 'paige-bueckers', 'breanna-stewart',
            'napheesa-collier', 'sabrina-ionescu', 'kelsey-plum', 'aliyah-boston',
            'kelsey-mitchell', 'cameron-brink', 'rhyne-howard', 'allisha-gray']


def name_size(player: dict) -> str:
    length = len(str(player.get('last_name') or player.get('first_name') or ''))
    first_length = len(str(player.get('first_name') or ''))
    return 'xlong' if length >= 18 or first_length >= 10 else 'long' if length >= 12 else 'normal'


def render_layout(page: str, profile: dict, has_portrait: bool) -> str:
    slug = profile.get('slug', '')
    p = profile.get('player', {})
    if not isinstance(slug, str) or not SLUG.fullmatch(slug):
        raise ValueError('Unsafe profile URL.')
    if f'{BASE}/wnba/{slug}/' not in page:
        raise ValueError('Canonical does not match the player record.')
    if page.count('<h1 ') != 1 or len(HERO.findall(page)) != 1:
        raise ValueError('Expected one primary name and one hero.')
    image_present = 'class="player-illustration"' in page
    if image_present != has_portrait:
        raise ValueError('Published portrait does not match the approved manifest.')
    old_tables = re.findall(r'<table\b.*?</table>', page, re.S)
    def hero_class(match):
        classes = match.group(1).split()
        if 'hero' not in classes:
            raise ValueError('Unexpected hero wrapper.')
        if 'fcb-player-compact' not in classes:
            classes.append('fcb-player-compact')
        return '<section class="' + ' '.join(classes) + '" aria-labelledby="player-name" data-name-size="' + name_size(p) + '">'
    page = HERO.sub(hero_class, page, count=1)
    if not has_portrait:
        number = str(p.get('jersey_number') or '')
        number = number if re.fullmatch(r'\d{1,2}', number) else 'FCB'
        art = ('<div class="hero-art portrait-art" aria-hidden="true">'
               '<div class="portrait-backdrop"><span class="ghost-number">'
               + html.escape(number) + '</span></div></div>')
        page, count = OLD_ART.subn(lambda _: art, page)
        if count != 1 and 'class="hero-art portrait-art" aria-hidden="true"' not in page:
            raise ValueError('Unrecognized placeholder; not changing the profile.')
    style = '<style id="fcb-shared-player-layout">' + SHARED_CSS + '</style>'
    if STYLE.search(page):
        page = STYLE.sub(lambda _: style, page, count=1)
    elif page.count('</head>') == 1:
        page = page.replace('</head>', style + '</head>', 1)
    else:
        raise ValueError('Missing or duplicate HTML head.')
    if re.findall(r'<table\b.*?</table>', page, re.S) != old_tables:
        raise ValueError('A design change unexpectedly modified statistics.')
    return page


def rollout(root: Path) -> dict:
    data = root / 'data/wnba'
    index = json.loads((data/'players-index.json').read_text(encoding='utf-8'))
    entries = index.get('players', [])
    if not entries:
        raise ValueError('No imported players. Refusing an empty rollout.')
    manifest = root/'content/player-illustrations.json'
    records = json.loads(manifest.read_text(encoding='utf-8')).get('portraits', []) if manifest.exists() else []
    approved = {}
    for record in records:
        pid = record.get('player_id')
        if type(pid) is not int or pid in approved or record.get('approved') is not True:
            raise ValueError('Invalid, duplicate or unapproved portrait record.')
        approved[pid] = record
    outputs = {}; ids = set(); slugs = set(); queue = []
    for entry in entries:
        pid, slug = entry.get('id'), entry.get('slug', '')
        if type(pid) is not int or not isinstance(slug, str) or not SLUG.fullmatch(slug) or pid in ids or slug in slugs:
            raise ValueError('Unsafe or duplicate player identity.')
        ids.add(pid); slugs.add(slug)
        profile = json.loads((data/'players'/f'{slug}.json').read_text(encoding='utf-8'))
        player = profile.get('player', {})
        name = ' '.join(str(player.get(k) or '').strip() for k in ('first_name','last_name')).strip()
        if player.get('id') != pid or profile.get('slug') != slug or name != entry.get('name'):
            raise ValueError('Directory, profile and identity do not agree.')
        record = approved.get(pid)
        if record:
            if record.get('slug') != slug or record.get('player_name') != name:
                raise ValueError('Approved artwork belongs to a different player.')
            src = record.get('src', '')
            if not ASSET.fullmatch(src):
                raise ValueError('Artwork must use a safe local asset.')
            asset = root/src.lstrip('/')
            if not asset.is_file() or asset.is_symlink() or asset.stat().st_size == 0:
                raise ValueError('Approved image is missing.')
        path = root/'wnba'/slug/'index.html'
        outputs[path] = render_layout(path.read_text(encoding='utf-8'), profile, record is not None)
        if record is None:
            queue.append({'player_id':pid, 'slug':slug, 'player_name':name,
                          'listed_active':entry.get('active_in_provider_feed') is True,
                          'profile_path':f'/wnba/{slug}/', 'state':'awaiting_illustration',
                          'reference_and_likeness_review_required':True})
    if set(approved) - ids:
        raise ValueError('Approved artwork refers to a player outside the current directory.')
    queue.sort(key=lambda p:(0 if p['slug'] in FEATURED else 1 if p['listed_active'] else 2,
                              FEATURED.index(p['slug']) if p['slug'] in FEATURED else 0,
                              p['player_name'].casefold(),p['player_id']))
    report = {'layout_version':VERSION, 'profile_count':len(entries),
              'profiles_with_approved_illustrations':len(approved),
              'profiles_awaiting_illustrations':len(queue),
              'illustration_generation_started':False,
              'automatic_paid_generation_enabled':False,
              'data_snapshot_checked_at':index.get('checked_at'),
              'approved_layout_source':'/wnba/caitlin-clark/',
              'approved_css_sha256':hashlib.sha256(APPROVED_CSS.encode()).hexdigest(),
              'scope':'All current player pages; design only. No statistics or player identities changed.'}
    outputs[data/'illustration-rollout.json'] = json.dumps(report, indent=2)+'\n'
    outputs[data/'illustration-queue.json'] = json.dumps({
        'schema_version':1, 'layout_version':VERSION,
        'status':'awaiting_image_generation_setup', 'generation_started':False,
        'brief':BRIEF, 'entries':queue}, ensure_ascii=False, indent=2)+'\n'
    changed = 0
    for path, content in outputs.items():
        if path.exists() and path.read_text(encoding='utf-8') == content:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix+'.tmp')
        temp.write_text(content, encoding='utf-8'); temp.replace(path); changed += 1
    print(f'Compact layout: {len(entries)} profiles; illustrated: {len(approved)}; awaiting art: {len(queue)}; files changed: {changed}.')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    rollout(parser.parse_args().root)
