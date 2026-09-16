#!/usr/bin/env python3
"""Apply approved, ID-matched artwork after the statistics page generator.

Artwork is kept outside the API snapshot. No network calls or secrets are used.
Only explicitly approved profiles are changed; statistics and other pages stay intact.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
import re

BASE = 'https://fullcourtbuckets.com'
ASSET = re.compile(r'/images/players/[a-z0-9][a-z0-9._-]*\Z')
SLUG = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*\Z')
SLOT = re.compile(r'<div class="hero-art" aria-hidden="true">.*?</small></div>', re.S)
APPLIED = re.compile(r'<!-- FCB:approved-portrait:start -->.*?<!-- FCB:approved-portrait:end -->', re.S)

CSS = '''
/* Portrait-only overrides. All names, labels, and statistics remain HTML. */
.hero.has-player-portrait{background:#000}
.has-player-portrait .hero-main{grid-template-columns:55% 45%;background:#000}
.has-player-portrait .hero-art.portrait-art{position:relative;inset:auto;margin:0;display:flex;align-items:flex-end;justify-content:center;opacity:1;pointer-events:auto;background:#000;min-height:420px;padding:16px 14px 0;overflow:hidden}
.has-player-portrait .portrait-art:before,.has-player-portrait .portrait-art:after{display:none}
.portrait-art .player-illustration{display:block;align-self:flex-end;margin:0;width:100%;max-width:560px;height:auto;aspect-ratio:640/596;object-fit:contain;object-position:center bottom;-webkit-mask-image:var(--portrait-mask);mask-image:var(--portrait-mask);-webkit-mask-size:100% 100%;mask-size:100% 100%;-webkit-mask-repeat:no-repeat;mask-repeat:no-repeat}
@media(max-width:780px){
 .has-player-portrait .hero-main{grid-template-columns:1fr}
 .has-player-portrait .hero-copy{width:100%;min-height:0;padding-bottom:15px}
 .has-player-portrait .hero-art.portrait-art{min-height:0;padding:0 16px 0}
 .has-player-portrait .player-illustration{width:min(100%,410px)}
}
@media(prefers-reduced-motion:reduce){.portrait-art *{animation:none!important;transition:none!important}}
'''.strip()


def esc(value):
    return html.escape(str(value), quote=True)


def asset_url(root: Path, path: str) -> str:
    if not isinstance(path, str) or not ASSET.fullmatch(path):
        raise ValueError('Approved artwork must use a safe local /images/players/ path.')
    file = root / path.lstrip('/')
    if file.is_symlink() or not file.is_file() or file.stat().st_size == 0:
        raise ValueError('Approved portrait asset is missing or unsafe.')
    return path + '?v=' + hashlib.sha256(file.read_bytes()).hexdigest()[:12]


def render(page: str, profile: dict, record: dict, root: Path) -> str:
    player = profile.get('player', {})
    pid = record.get('player_id')
    slug = record.get('slug', '')
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0 or player.get('id') != pid:
        raise ValueError('Illustration does not match the permanent player ID.')
    if not SLUG.fullmatch(slug) or profile.get('slug') != slug:
        raise ValueError('Illustration does not match the permanent player URL.')
    if record.get('approved') is not True or record.get('kind') != 'illustration':
        raise ValueError('Only approved illustrations can be published.')
    name = ' '.join(str(player.get(k) or '').strip() for k in ('first_name', 'last_name')).strip()
    if record.get('player_name') != name:
        raise ValueError('Player name does not match the approved illustration record.')
    if f'{BASE}/wnba/{slug}/' not in page:
        raise ValueError('Generated page has a different canonical URL.')
    width, height = record.get('width'), record.get('height')
    if not all(isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= 10000 for n in (width, height)):
        raise ValueError('Invalid portrait dimensions.')
    src = asset_url(root, record['src'])
    mask = asset_url(root, record['mask'])
    # Keep provenance in structured metadata and source notes, not below the portrait.
    caption = 'AI-generated illustration · Full Court Buckets'
    figure = (
        '<!-- FCB:approved-portrait:start -->'
        '<figure class="hero-art portrait-art" aria-label="Player illustration">'
        f'<img class="player-illustration" src="{esc(src)}" '
        f'alt="{esc(name)} illustrated portrait" width="{width}" height="{height}" '
        f'style="--portrait-mask:url(\'{esc(mask)}\')" fetchpriority="high" decoding="async">'
        '</figure>'
        '<!-- FCB:approved-portrait:end -->'
    )
    if APPLIED.search(page):
        page, count = APPLIED.subn(lambda _: figure, page)
    else:
        page, count = SLOT.subn(lambda _: figure, page)
    if count != 1:
        raise ValueError('Expected exactly one portrait slot; no page was changed.')
    page = page.replace('<section class="hero" aria-labelledby="player-name">',
                        '<section class="hero has-player-portrait" aria-labelledby="player-name">', 1)
    if 'class="hero has-player-portrait"' not in page:
        raise ValueError('Portrait hero wrapper was not found.')
    style = '<style id="fcb-portrait-styles">' + CSS + '</style>'
    if '<style id="fcb-portrait-styles">' in page:
        page = re.sub(r'<style id="fcb-portrait-styles">.*?</style>', lambda _: style, page, count=1, flags=re.S)
    else:
        page = page.replace('</head>', style + '</head>', 1)
    page = page.replace('The number artwork is a design element, not a player photograph.',
                        'The portrait is an AI-generated editorial illustration, not a photograph. Names, team information and statistics are separate HTML text.')
    # Add image metadata without changing the existing name, URL, or statistics.
    def update_schema(match):
        schema = json.loads(match.group(1))
        for entity in schema.get('@graph', []):
            if entity.get('@type') == 'Person' and entity.get('@id') == f'{BASE}/wnba/{slug}/#player':
                entity['image'] = {'@type': 'ImageObject', 'contentUrl': BASE + src,
                                   'caption': f'{name}. {caption}.', 'width': width, 'height': height}
        encoded = json.dumps(schema, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
        return '<script type="application/ld+json">' + encoded + '</script>'
    page = re.sub(r'<script type="application/ld\+json">(.*?)</script>', update_schema, page, flags=re.S)
    return page


def apply(root: Path) -> int:
    manifest = root / 'content' / 'player-illustrations.json'
    if not manifest.exists():
        return 0
    records = json.loads(manifest.read_text(encoding='utf-8'))['portraits']
    outputs = {}; ids = set(); slugs = set()
    for record in records:
        pid, slug = record.get('player_id'), record.get('slug', '')
        if not SLUG.fullmatch(slug) or pid in ids or slug in slugs:
            raise ValueError('Unsafe or duplicate illustration mapping.')
        ids.add(pid); slugs.add(slug)
        profile = json.loads((root / 'data/wnba/players' / (slug + '.json')).read_text(encoding='utf-8'))
        page = root / 'wnba' / slug / 'index.html'
        outputs[page] = render(page.read_text(encoding='utf-8'), profile, record, root)
    # Validate all mapped artwork before replacing any output file.
    for page, content in outputs.items():
        if page.read_text(encoding='utf-8') != content:
            temp = page.with_suffix('.html.tmp')
            temp.write_text(content, encoding='utf-8')
            temp.replace(page)
    print(f'Applied {len(outputs)} approved player illustration(s); all other profiles unchanged.')
    return len(outputs)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    apply(parser.parse_args().root)
