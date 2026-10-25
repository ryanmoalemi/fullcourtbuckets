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
ASSET = re.compile(r'/images/players/(?:[a-z0-9][a-z0-9._-]*|[a-z0-9]+(?:-[a-z0-9]+)*/portrait\.(?:png|webp|avif))\Z')
SLUG = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*\Z')
SLOT = re.compile(r'<div class="hero-art" aria-hidden="true">.*?</small></div>', re.S)
COMPACT_SLOT = re.compile(
    r'<div class="hero-art portrait-art" aria-hidden="true"><div class="portrait-backdrop"><span class="ghost-number">.*?</span></div></div>',
    re.S)
NUMBER_ARTWORK = 'The number artwork is a design element, not a player photograph.'
APPLIED = re.compile(r'<!-- FCB:approved-portrait:start -->.*?<!-- FCB:approved-portrait:end -->', re.S)

CSS = '''
/* Show the full illustration, including shoulders and upper chest. Keep the original gradient, circles and outline number. */
.has-player-portrait .hero-main{grid-template-columns:55% 45%;min-height:0}
.has-player-portrait .hero-copy{padding-top:30px;padding-bottom:30px}
.has-player-portrait .hero-art.portrait-art{position:relative;inset:auto;margin:0;display:block;opacity:1;pointer-events:auto;background:transparent;min-height:0;min-width:0;padding:0;overflow:hidden;isolation:isolate}
@media(min-width:781px){.has-player-portrait .portrait-art:has(.player-illustration){min-height:570px}}
.has-player-portrait .portrait-art:before,.has-player-portrait .portrait-art:after{z-index:0;pointer-events:none}
.portrait-art .portrait-backdrop{position:absolute;inset:0;z-index:0;pointer-events:none}
.portrait-art .portrait-crop{position:absolute;inset:12px 0 0;z-index:2;overflow:hidden}
.portrait-art .player-illustration{position:absolute;top:0;left:0;display:block;margin:0;width:100%;max-width:none;height:100%;object-fit:cover;object-position:center top;-webkit-mask-image:var(--portrait-mask,none);mask-image:var(--portrait-mask,none);-webkit-mask-size:100% 100%;mask-size:100% 100%;-webkit-mask-repeat:no-repeat;mask-repeat:no-repeat}
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
 .has-player-portrait .player-illustration{left:0;width:100%;height:100%}
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


def photo_credit(root: Path, slug: str):
    """Licensed real photo credit (CC BY / CC BY-SA / PD) from content/player-photo-credits.json."""
    path = root / 'content' / 'player-photo-credits.json'
    if not path.is_file():
        return None
    credit = json.loads(path.read_text(encoding='utf-8')).get('credits', {}).get(slug)
    if not credit:
        return None
    lic = str(credit.get('license', ''))
    if re.search(r'\b(ND|NC)\b', lic):
        raise ValueError(f'{slug}: ND/NC photo licenses are not allowed.')
    for key in ('file_url', 'license_url'):
        if credit.get(key) and not re.fullmatch(r'https://[^"<>\s]+', credit[key]):
            raise ValueError(f'{slug}: unsafe credit URL')
    return credit


def credit_html(credit: dict) -> str:
    lic = esc(credit['license'])
    if credit.get('license_url'):
        lic = f'<a href="{esc(credit["license_url"])}" rel="license noopener" target="_blank">{lic}</a>'
    author = f'<a href="{esc(credit["file_url"])}" rel="noopener" target="_blank">{esc(credit["author"])}</a>'
    changes = f', {esc(credit["changes"])}' if credit.get('changes') else ''
    return f'<span class="photo-credit">Photo: {author}, {lic}, via Wikimedia Commons{changes}.</span>'


CREDIT_CSS = '.photo-credit{font-size:11px;line-height:1.4;color:inherit;opacity:.8}.photo-credit a{color:inherit;text-decoration:underline}'
CREDIT_SOURCES = re.compile(r'<p class="photo-credit-source">.*?</p>', re.S)


def render(page: str, profile: dict, record: dict, root: Path) -> str:
    player = profile.get('player', {})
    pid, slug = record.get('player_id'), record.get('slug', '')
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0 or player.get('id') != pid:
        raise ValueError('Illustration does not match the permanent player ID.')
    if not SLUG.fullmatch(slug) or profile.get('slug') != slug:
        raise ValueError('Illustration does not match the permanent player URL.')
    kind = record.get('kind')
    if record.get('approved') is not True or kind not in ('illustration', 'photograph'):
        raise ValueError('Only approved illustrations or photographs can be published.')
    photo = kind == 'photograph'
    name = ' '.join(str(player.get(k) or '').strip() for k in ('first_name', 'last_name')).strip()
    if record.get('player_name') != name:
        raise ValueError('Player name does not match the approved illustration record.')
    if f'{BASE}/wnba/{slug}/' not in page:
        raise ValueError('Generated page has a different canonical URL.')
    width, height = record.get('width'), record.get('height')
    if not all(isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= 10000 for n in (width, height)):
        raise ValueError('Invalid portrait dimensions.')
    src = asset_url(root, record['src'])
    mask_style = ''
    if record.get('mask'):
        mask = asset_url(root, record['mask'])
        mask_style = f' style="--portrait-mask:url(\'{esc(mask)}\')"'
    number = str(player.get('jersey_number') if player.get('jersey_number') is not None else '')
    if not re.fullmatch(r'\d{1,2}', number):
        number = 'FCB'
    backdrop = ('<div class="portrait-backdrop" aria-hidden="true">'
                f'<span class="ghost-number">{esc(number)}</span></div>')
    caption = name if photo else 'AI-generated illustration · Full Court Buckets'
    alt = name if photo else f'{name} illustrated portrait'
    aria = name if photo else 'Player illustration'
    figure = (
        '<!-- FCB:approved-portrait:start -->'
        f'<figure class="hero-art portrait-art" aria-label="{esc(aria)}">' + backdrop +
        '<div class="portrait-crop">'
        f'<img class="player-illustration" src="{esc(src)}" '
        f'alt="{esc(alt)}" width="{width}" height="{height}"'
        f'{mask_style} fetchpriority="high" decoding="async">'
        '</div></figure><!-- FCB:approved-portrait:end -->'
    )
    if APPLIED.search(page):
        page, count = APPLIED.subn(lambda _: figure, page)
    elif SLOT.search(page):
        page, count = SLOT.subn(lambda _: figure, page)
    else:
        page, count = COMPACT_SLOT.subn(lambda _: figure, page)
    if count != 1:
        raise ValueError('Expected exactly one portrait slot; no page was changed.')
    if not re.search(r'class="hero has-player-portrait(?: |")', page):
        updated = page.replace('<section class="hero" aria-labelledby="player-name">',
                               '<section class="hero has-player-portrait" aria-labelledby="player-name">', 1)
        if updated == page:
            updated = page.replace('<section class="hero ',
                                   '<section class="hero has-player-portrait ', 1)
        page = updated
    # Rollout appends fcb-player-compact after the portrait class, so the attribute
    # no longer ends at has-player-portrait. Accept that already-published hero.
    if not re.search(r'class="hero has-player-portrait(?: |")', page):
        raise ValueError('Portrait hero wrapper was not found.')
    style = '<style id="fcb-portrait-styles">' + CSS + '</style>'
    if '<style id="fcb-portrait-styles">' in page:
        page = re.sub(r'<style id="fcb-portrait-styles">.*?</style>', lambda _: style, page, count=1, flags=re.S)
    else:
        page = page.replace('</head>', style + '</head>', 1)
    portrait_bit = 'Portrait is an AI illustration. '
    photo_line = 'Portrait is a photograph. '
    note_bit = 'checked against the stats on this page. '
    legacy = (
        'The portrait is an AI-generated editorial illustration, not a photograph. '
        'Names, team information and statistics are separate HTML text. '
        'Profile text and FAQs are written with help from AI tools, using the stats and sources on this page.'
    )
    short_note = (
        'The portrait is an AI-generated editorial illustration, not a photograph. '
        'Names, team information and statistics are separate HTML text.'
    )
    if photo:
        # A real photograph replaces the number-art disclaimer. Do not call it an illustration.
        page = page.replace(' ' + NUMBER_ARTWORK, '')
        page = page.replace(NUMBER_ARTWORK, '')
        page = page.replace(' ' + portrait_bit, ' ')
        page = page.replace(portrait_bit, '')
        page = page.replace(legacy, '')
        page = page.replace(short_note, '')
        if note_bit in page and photo_line not in page:
            page = page.replace(note_bit, note_bit + photo_line, 1)
        credit = photo_credit(root, slug)
        if credit:
            # Credit lives in the small provenance line under the stats and in Sources,
            # never as a caption over or under the photo.
            line = credit_html(credit)
            page = re.sub(r' ?<span class="photo-credit">.*?</span>', '', page, flags=re.S)
            page = re.sub(r'<p class="muted small photo-credit-fallback">.*?</p>', '', page, flags=re.S)
            if photo_line in page:
                page = page.replace(photo_line, photo_line + line + ' ', 1)
            else:
                # Inactive pages have no AI provenance sentence. The career
                # sources line is their Sources line; keep the credit there,
                # not under the photo, so a stats rebuild can put it back.
                marker = 'class="career-sources">'
                at = page.find(marker)
                if at != -1:
                    end = page.find('</p>', at)
                    if end != -1:
                        extra = '<p class="muted small photo-credit-fallback">' + line + '</p>'
                        page = page[:end + 4] + extra + page[end + 4:]
            src_p = '<p class="photo-credit-source">' + line.replace('<span class="photo-credit">', '').replace('</span>', '') + '</p>'
            page = CREDIT_SOURCES.sub('', page)
            page = page.replace('<details class="sources section" id="sources"><summary>About these numbers</summary>',
                                '<details class="sources section" id="sources"><summary>About these numbers</summary>' + src_p, 1)
            if CREDIT_CSS not in page:
                page = page.replace('</head>', '<style id="fcb-photo-credit">' + CREDIT_CSS + '</style></head>', 1)
    else:
        if note_bit in page and portrait_bit not in page:
            page = page.replace(note_bit, note_bit + portrait_bit, 1)
        page = page.replace(legacy, NUMBER_ARTWORK)
        if short_note in page:
            page = page.replace(short_note, NUMBER_ARTWORK)
    def update_schema(match):
        schema = json.loads(match.group(1))
        for entity in schema.get('@graph', []):
            if entity.get('@type') == 'Person' and entity.get('@id') == f'{BASE}/wnba/{slug}/#player':
                entity['image'] = {'@type': 'ImageObject', 'contentUrl': BASE + src,
                                   'caption': caption if photo else f'{name}. {caption}.',
                                   'width': width, 'height': height}
                credit = photo_credit(root, slug) if photo else None
                if credit:
                    entity['image'].update(creditText=credit['author'] + ' via Wikimedia Commons',
                                           license=credit.get('license_url', ''),
                                           acquireLicensePage=credit['file_url'])
        encoded = json.dumps(schema, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
        return '<script type="application/ld+json">' + encoded + '</script>'
    return re.sub(r'<script type="application/ld\+json">(.*?)</script>', update_schema, page, flags=re.S)


def apply(root: Path) -> int:
    from portrait_folders import sync
    sync(root)
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
