#!/usr/bin/env python3
"""Apply approved, ID-matched artwork after the statistics page generator.

Artwork stays outside the API snapshot. This module uses no network or secrets.
Only explicitly approved profiles change; other profiles and statistics stay intact.
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
/* Compact shoulder crop; keep the original gradient, circles and outline number. */
.has-player-portrait .hero-main{grid-template-columns:55% 45%;min-height:0}
.has-player-portrait .hero-copy{padding-top:30px;padding-bottom:30px}
.has-player-portrait .hero-art.portrait-art{position:relative;inset:auto;margin:0;display:block;opacity:1;pointer-events:auto;background:transparent;min-height:0;min-width:0;padding:0;overflow:hidden;isolation:isolate}
.has-player-portrait .portrait-art:before,.has-player-portrait .portrait-art:after{z-index:0;pointer-events:none}
.portrait-art .portrait-backdrop{position:absolute;inset:0;z-index:0;pointer-events:none}
.portrait-art .portrait-crop{position:absolute;inset:12px 0 0;z-index:2;overflow:hidden}
.portrait-art .player-illustration{position:absolute;top:0;left:6%;display:block;margin:0;width:100%;max-width:none;height:130%;object-fit:cover;object-position:center top;-webkit-mask-image:var(--portrait-mask,none);mask-image:var(--portrait-mask,none);-webkit-mask-size:100% 100%;mask-size:100% 100%;-webkit-mask-repeat:no-repeat;mask-repeat:no-repeat}
@media(max-width:780px){
 .has-player-portrait .hero-main{grid-template-columns:55% 45%;min-height:0}
 .has-player-portrait .hero-copy{width:auto;min-height:0;padding:24px 18px}
 .has-player-portrait .hero-kicker{align-items:flex-start;flex-direction:column;gap:5px;font-size:8px;letter-spacing:.7px}
 .has-player-portrait h1{margin:14px 0 12px}
 .has-player-portrait h1>span{font-size:clamp(30px,6vw,46px)}
 .has-player-portrait h1>b{font-size:clamp(44px,8vw,64px)}
 .has-player-portrait .hero-meta{margin:12px 0 16px;font-size:11px;line-height:1.65}
 .has-player-portrait .actions{gap:6px;flex-wrap:wrap;min-height:36px}
 .has-player-portrait .actions .button{min-height:36px;padding:8px 10px;gap:12px;font-size:10px}
 .has-player-portrait .text-button{font-size:10px;padding:8px 4px}
 .has-player-portrait .portrait-crop{inset:10px 0 0}
 .has-player-portrait .player-illustration{left:0;width:100%;height:130%}
}
@media(max-width:480px){
 .has-player-portrait .hero-copy{padding:20px 8px 20px 12px}
 .has-player-portrait h1{line-height:1;margin:12px 0 10px}
 .has-player-portrait h1>span{font-size:30px}
 .has-player-portrait h1>b{font-size:clamp(36px,11.5vw,46px)}
 .has-player-portrait .hero-meta{font-size:10px;margin:10px 0 12px}
 .has-player-portrait .hero-kicker{font-size:7px;letter-spacing:.4px}
 .has-player-portrait .status{font-size:7px;padding:3px 6px}
}
@media(max-width:360px){
 .has-player-portrait .actions{flex-wrap:nowrap;gap:4px}
 .has-player-portrait .actions .button{gap:7px;padding:7px 8px;font-size:9px;white-space:nowrap}
 .has-player-portrait .text-button{padding:7px 2px;white-space:nowrap;flex:0 0 auto}
 .has-player-portrait #share-status:empty{display:none}
 .has-player-portrait .metric{padding-top:12px;padding-bottom:12px}
 .has-player-portrait .stat-context{padding-top:8px;padding-bottom:8px}
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
    pid, slug = record.get('player_id'), record.get('slug', '')
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
    # Native-alpha images need no silhouette mask. Preserve support for older assets.
    mask_style = ''
    if record.get('mask'):
        mask = asset_url(root, record['mask'])
        mask_style = f' style="--portrait-mask:url(\'{esc(mask)}\')"'
    number = str(player.get('jersey_number') if player.get('jersey_number') is not None else '')
    if not re.fullmatch(r'\d{1,2}', number):
        number = 'FCB'
    # Retain the outline number and CSS circles, not the square number card.
    backdrop = ('<div class="portrait-backdrop" aria-hidden="true">'
                f'<span class="ghost-number">{esc(number)}</span></div>')
    caption = 'AI-generated illustration · Full Court Buckets'
    figure = (
        '<!-- FCB:approved-portrait:start -->'
        '<figure class="hero-art portrait-art" aria-label="Player illustration">' + backdrop +
        '<div class="portrait-crop">'
        f'<img class="player-illustration" src="{esc(src)}" '
        f'alt="{esc(name)} illustrated portrait" width="{width}" height="{height}"'
        f'{mask_style} fetchpriority="high" decoding="async">'
        '</div></figure><!-- FCB:approved-portrait:end -->'
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
    # Provenance stays in source notes and metadata, not below the portrait.
    def update_schema(match):
        schema = json.loads(match.group(1))
        for entity in schema.get('@graph', []):
            if entity.get('@type') == 'Person' and entity.get('@id') == f'{BASE}/wnba/{slug}/#player':
                entity['image'] = {'@type': 'ImageObject', 'contentUrl': BASE + src,
                                   'caption': f'{name}. {caption}.', 'width': width, 'height': height}
        encoded = json.dumps(schema, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
        return '<script type="application/ld+json">' + encoded + '</script>'
    return re.sub(r'<script type="application/ld\+json">(.*?)</script>', update_schema, page, flags=re.S)


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
