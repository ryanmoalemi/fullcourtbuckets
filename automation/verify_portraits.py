#!/usr/bin/env python3
"""Decode approved files before deployment; verify those exact bytes in live browsers.

Never infers a person's identity from pixels. The owner-approved ID/file mapping
is the input; an exact hash verifies the same file is displayed on that page.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

BASE = 'https://fullcourtbuckets.com'
SLUG = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*\Z')
VIEWPORTS = ((1365, 850, 'desktop'), (390, 844, 'mobile-390'), (320, 568, 'mobile-320'))

class VerificationError(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise VerificationError(message)

def normal_name(text):
    return ' '.join(str(text).replace('’', "'").split()).casefold()

def decode_asset(raw: bytes, record: dict, legacy: dict) -> dict:
    from PIL import Image
    require(0 < len(raw) <= 12_000_000, 'Missing or oversized image')
    digest = hashlib.sha256(raw).hexdigest()
    require(record.get('asset_sha256') == digest, 'Approved file checksum mismatch')
    try:
        image = Image.open(io.BytesIO(raw)); image.load()
        size = image.size
        alpha = image.convert('RGBA').getchannel('A').getextrema()
        fmt = image.format
    except Exception as exc:
        raise VerificationError('Image bytes cannot be decoded') from exc
    require(fmt in ('WEBP', 'AVIF', 'PNG'), 'Unsupported image format')
    require(size == (record.get('width'), record.get('height')), 'Actual dimensions differ from manifest')
    require(alpha[0] < 255 and alpha[1] > 0, 'Image must contain visible artwork and real transparency')
    exempt = legacy.get(record['src']) == digest
    if not exempt:
        require(size[0] >= 640 and size[1] >= 650, 'New portrait is below 640x650')
        settings = record.get('export_settings', {})
        require(settings.get('upscaled') is False, 'No-upscaling provenance missing')
        require(settings.get('source_width', 0) >= 1024 and settings.get('source_height', 0) >= 1024,
                'New portrait must come from a full-resolution master')
    return {'asset_sha256': digest, 'width': size[0], 'height': size[1],
            'format': fmt, 'bytes': len(raw), 'legacy_resolution': exempt and (size[0] < 640 or size[1] < 650)}

def make_plan(root: Path) -> dict:
    from portrait_folders import matches_player_path
    records = json.loads((root/'content/player-illustrations.json').read_text())['portraits']
    legacy = json.loads((root/'content/portrait-quality.json').read_text()).get('unchanged_legacy_assets', {})
    ids, slugs, hashes = set(), set(), set()
    result = []
    for record in records:
        slug, pid, src = record.get('slug'), record.get('player_id'), record.get('src', '')
        require(isinstance(slug, str) and SLUG.fullmatch(slug), 'Unsafe slug')
        require(type(pid) is int and pid > 0 and pid not in ids and slug not in slugs, 'Duplicate or invalid ID')
        require(record.get('approved') is True, f'{slug}: unapproved image')
        require(matches_player_path(src, slug), f'{slug}: unsafe image path or different player folder')
        path = root/src.lstrip('/')
        require(path.is_file() and not path.is_symlink(), f'{slug}: missing image')
        profile = json.loads((root/'data/wnba/players'/f'{slug}.json').read_text())
        player = profile['player']
        name = ' '.join(str(player.get(k) or '').strip() for k in ('first_name','last_name')).strip()
        require(profile['slug'] == slug and player['id'] == pid and record['player_name'] == name,
                f'{slug}: player/approval identity mismatch')
        try:
            decoded = decode_asset(path.read_bytes(), record, legacy)
        except VerificationError as exc:
            raise VerificationError(f'{slug}: {exc}') from exc
        require(decoded['asset_sha256'] not in hashes, 'Same portrait bytes assigned to different players')
        result.append({'player_id': pid, 'slug': slug, 'name': name, 'src': src,
                       'expected_image': True, 'has_season_stats': bool(profile.get('season_stats')), **decoded})
        ids.add(pid); slugs.add(slug); hashes.add(decoded['asset_sha256'])
    quarantine = root/'content/portrait-quarantine.json'
    if quarantine.exists():
        for item in json.loads(quarantine.read_text()).get('portraits', []):
            if item['slug'] not in slugs:
                profile=json.loads((root/'data/wnba/players'/f'{item["slug"]}.json').read_text())
                require(profile['player']['id']==item['player_id'], 'Quarantine identity mismatch')
                result.append({'player_id':item['player_id'],'slug':item['slug'],'name':item['player_name'],
                               'expected_image':False,'has_season_stats':bool(profile.get('season_stats'))})
    return {'version': 1, 'base': BASE, 'records': result,
            'note': 'Hash/ID binding verifies the approved mapping, not independent facial identification.'}

MEASURE = '''() => {
 const box=s=>{const e=document.querySelector(s);if(!e)return null;const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,top:r.top,bottom:r.bottom,right:r.right}};
 const img=document.querySelector('img.player-illustration');
 return {heading:document.querySelector('h1')?.innerText,canonical:document.querySelector('link[rel=canonical]')?.href,
   src:img?.currentSrc,complete:img?.complete,naturalWidth:img?.naturalWidth,naturalHeight:img?.naturalHeight,
   hero:box('.hero-main'),portrait:box('.portrait-art'),copy:box('.hero-copy'),stats:box('.hero-stats'),
   innerWidth,scrollWidth:document.documentElement.scrollWidth,
   numberCards:document.querySelectorAll('.hero .number-card').length,captions:document.querySelectorAll('.hero figcaption').length,
   imageCount:document.querySelectorAll('img.player-illustration').length,statsRows:document.querySelectorAll('#stats tbody tr').length,
   sourceText:document.querySelector('#sources')?.textContent||''};
}'''

def verify_pages(plan: dict, origin: str, output: Path, engines: list[str], retries: int = 1) -> dict:
    from playwright.sync_api import sync_playwright
    output.mkdir(parents=True, exist_ok=True)
    report={'status':'running','origin':origin,'verified':[],'failures':[],
            'checked_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
    with sync_playwright() as p:
        for engine in engines:
            browser=getattr(p,engine).launch()
            try:
                for record in plan['records']:
                    slug=record['slug']
                    for width,height,label in VIEWPORTS:
                        context=browser.new_context(viewport={'width':width,'height':height},device_scale_factor=1,
                                                    service_workers='block')
                        page=context.new_page(); page.set_default_timeout(15000)
                        failure=None
                        for attempt in range(retries):
                            try:
                                url=f'{origin}/wnba/{slug}/?portrait_verify={time.time_ns()}'
                                response=page.goto(url,wait_until='domcontentloaded',timeout=45000)
                                require(response is not None and response.status==200, 'Player page did not return HTTP 200')
                                page.evaluate('document.fonts.ready')
                                require(page.locator('h1').count()==1, 'Expected one player heading')
                                if record['expected_image']:
                                    image=page.locator('img.player-illustration')
                                    require(image.count()==1, 'Portrait is missing or duplicated')
                                    image.evaluate('(el)=>el.decode()')
                                m=page.evaluate(MEASURE)
                                require(normal_name(m['heading'])==normal_name(record['name']), 'Wrong player name')
                                require(m['canonical']==f'{BASE}/wnba/{slug}/', 'Wrong canonical player URL')
                                require(f"Provider player ID: {record['player_id']}." in m['sourceText'], 'Wrong provider ID')
                                if record['expected_image']:
                                    require(m['complete'] and m['naturalWidth']==record['width'] and m['naturalHeight']==record['height'], 'Browser image decode/dimensions failed')
                                    require(urlparse(m['src']).path==record['src'], 'Wrong or outdated portrait URL')
                                    require(urlparse(m['src']).netloc==urlparse(origin).netloc, 'Unexpected image host')
                                    asset=page.request.get(m['src'],timeout=30000)
                                    require(asset.status==200 and asset.headers.get('content-type','').startswith('image/'), 'Image HTTP response is invalid')
                                    require(hashlib.sha256(asset.body()).hexdigest()==record['asset_sha256'], 'Live bytes differ from approved file')
                                    m['asset_sha256']=record['asset_sha256']
                                else:
                                    require(m['imageCount']==0, 'Quarantined image is still embedded')
                                require(m['scrollWidth']<=width+1, 'Page overflows horizontally')
                                require(m['numberCards']==0 and m['captions']==0, 'Unapproved square/caption returned')
                                require(abs(m['hero']['bottom']-m['stats']['top'])<=1.1, 'Gap between hero and stats')
                                require(abs(m['portrait']['bottom']-m['stats']['top'])<=1.1, 'Portrait is not flush with divider')
                                require(m['copy']['right']<=m['portrait']['x']+1.1, 'Mobile portrait/name are not side by side')
                                if record['has_season_stats']:
                                    require(m['statsRows']>0, 'Statistics table disappeared')
                                m.update(slug=slug,engine=engine,viewport=[width,height],stats_above_fold=m['stats']['bottom']<=height,
                                         approved_replacement_verified=record['expected_image'])
                                page.screenshot(path=str(output/f'{slug}-{engine}-{label}.png'),full_page=False)
                                report['verified'].append(m); failure=None; break
                            except Exception as exc:
                                failure=f'{type(exc).__name__}: {exc}'
                                if attempt+1<retries: time.sleep(3)
                        if failure:
                            report['failures'].append({'slug':slug,'engine':engine,'viewport':[width,height],'error':failure})
                            try: page.screenshot(path=str(output/f'{slug}-{engine}-{label}-FAILED.png'))
                            except Exception: pass
                        context.close()
                        (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
            finally:
                browser.close()
    report['status']='failed' if report['failures'] else 'passed'
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    require(not report['failures'], f"{len(report['failures'])} portrait/browser checks failed; see report.json")
    print(f"PASSED {len(report['verified'])} exact-file/browser checks at {origin}")
    return report

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--create-plan',action='store_true')
    parser.add_argument('--origin')
    parser.add_argument('--output',type=Path,default=Path('portrait-verification'))
    parser.add_argument('--engines',default='chromium')
    parser.add_argument('--retries',type=int,default=1)
    args=parser.parse_args()
    if args.create_plan:
        args.plan.parent.mkdir(parents=True,exist_ok=True)
        args.plan.write_text(json.dumps(make_plan(args.root),indent=2)+'\n')
    if args.origin:
        engines=args.engines.split(',')
        require(set(engines)<={'chromium','webkit','firefox'},'Unknown browser engine')
        verify_pages(json.loads(args.plan.read_text()),args.origin.rstrip('/'),args.output,engines,args.retries)
    return 0

if __name__=='__main__':
    try: sys.exit(main())
    except VerificationError as exc:
        print(f'PORTRAIT VERIFICATION FAILED: {exc}',file=sys.stderr); sys.exit(1)
