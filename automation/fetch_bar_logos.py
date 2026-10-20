"""Fill the `logo` column of data/where-to-watch-bars.csv from each venue's own website.

Candidates (best first): <img> marked as logo in the page, apple-touch-icon, sized <link rel=icon>,
og:image only when its URL says "logo". Images under 64px or photo-shaped are skipped. Saves a
128px square WebP (contain on white) to assets/bars/<slug>.webp. Rows with a logo value (or
logo=none, a manual reject) are left alone, so new venues added by the bar-reply routine get filled
on the next run:  python3 automation/fetch_bar_logos.py [--id ID ...] [--force]
"""
from __future__ import annotations
import csv, io, re, sys, urllib.parse, urllib.request
from pathlib import Path
from html.parser import HTMLParser
from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'where-to-watch-bars.csv'
OUT = ROOT / 'assets' / 'bars'
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36'}
SIZE, MIN = 128, 64
DARK_BG = {'ca-oakland-lucy-blue'}  # manual: glow logos that need a dark tile


def slug(s): return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')[:60]


def get(url, n=4_000_000):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
        return r.read(n), r.geturl()


class P(HTMLParser):
    def __init__(s): super().__init__(); s.c = []; s.depth_header = 0
    def handle_starttag(s, tag, a):
        a = {k: (v or '') for k, v in a}
        if tag in ('header', 'nav'): s.depth_header += 1
        if tag == 'link':
            rel = a.get('rel', '').lower(); href = a.get('href')
            if not href: return
            if 'apple-touch-icon' in rel: s.c.append((80, href))
            elif 'icon' in rel:
                m = re.findall(r'(\d+)x\d+', a.get('sizes', ''))
                if m and int(max(m, key=int)) >= MIN: s.c.append((60, href))
                elif href.lower().endswith('.svg'): s.c.append((55, href))
        elif tag == 'meta' and a.get('property', a.get('name', '')).lower() in ('og:image', 'og:logo'):
            u = a.get('content', '')
            if u and ('logo' in u.lower() or a.get('property') == 'og:logo'): s.c.append((70, u))
        elif tag == 'img':
            src = a.get('src') or a.get('data-src') or ''
            if not src or src.startswith('data:'):
                ss = a.get('srcset') or a.get('data-srcset') or ''
                src = ss.split(',')[-1].strip().split(' ')[0] if ss else ''
            blob = ' '.join([a.get('class', ''), a.get('id', ''), a.get('alt', ''), src]).lower()
            if src and 'logo' in blob: s.c.append((100 if s.depth_header else 90, src))
            elif src and s.depth_header and ('brand' in blob or 'site-title' in blob): s.c.append((85, src))
    def handle_endtag(s, tag):
        if tag in ('header', 'nav') and s.depth_header: s.depth_header -= 1


def load_img(data, url):
    if url.lower().split('?')[0].endswith('.svg') or data.lstrip()[:5] in (b'<?xml', b'<svg ') or b'<svg' in data[:300]:
        import cairosvg
        data = cairosvg.svg2png(bytestring=data, output_width=512)
    im = Image.open(io.BytesIO(data)); im.load()
    if getattr(im, 'n_frames', 1) > 1: im.seek(0)
    if im.format == 'ICO':
        im = max((Image.open(io.BytesIO(data)).ico.getimage(s) for s in im.ico.sizes()), key=lambda x: x.width)
    return im.convert('RGBA')


def usable(im):
    w, h = im.size
    if min(w, h) < MIN and max(w, h) < 120: return 'too small'
    if max(w, h) / max(1, min(w, h)) > 5: return 'too wide'
    bbox = im.getchannel('A').getbbox()
    if not bbox: return 'blank'
    return None


def square(im, dark=False):
    bbox = im.getchannel('A').getbbox(); im = im.crop(bbox)
    # trim a solid white margin around the art too
    flat = Image.new('RGB', im.size, (255, 255, 255)); flat.paste(im, mask=im.getchannel('A'))
    nb = Image.eval(flat.convert('L'), lambda v: 255 if v < 245 else 0).getbbox()
    opaque = im.getchannel('A').getextrema()[0] == 255
    if opaque and nb and (nb[2] - nb[0]) * (nb[3] - nb[1]) < 0.8 * im.width * im.height: im = im.crop(nb)
    # light logo on transparency would vanish on white: put it on dark instead
    rgb = Image.new('RGB', im.size, (255, 255, 255)); rgb.paste(im, mask=im.getchannel('A'))
    alpha_cov = ImageStat.Stat(im.getchannel('A')).mean[0] / 255
    lum = ImageStat.Stat(im.convert('L'), mask=im.getchannel('A').point(lambda v: 255 if v > 128 else 0)).mean[0]
    A = im.getchannel('A').point(lambda v: 255 if v > 128 else 0)
    white = Image.eval(im.convert('L'), lambda v: 255 if v > 235 else 0)
    from PIL import ImageChops
    wfrac = ImageStat.Stat(ImageChops.multiply(white, A)).mean[0] / max(1, ImageStat.Stat(A).mean[0])
    bg = (27, 26, 25) if alpha_cov < 0.95 and (lum > 200 or (wfrac > 0.25 and lum > 150)) else (255, 255, 255)
    if dark: bg = (27, 26, 25)
    inner = int(SIZE * 0.78)
    im.thumbnail((inner, inner), Image.LANCZOS)
    out = Image.new('RGB', (SIZE, SIZE), bg)
    out.paste(im, ((SIZE - im.width) // 2, (SIZE - im.height) // 2), im)
    return out


def find(site):
    html, final = get(site, 2_000_000)
    p = P(); p.feed(html.decode('utf-8', 'ignore'))
    seen, tried = set(), []
    for score, u in sorted(p.c, key=lambda x: -x[0]):
        u = urllib.parse.urljoin(final, u.strip())
        if u in seen or re.search(r'logo-default|cdninstagram|fbcdn|/banner\.', u): continue
        seen.add(u)
        try:
            data, _ = get(u); im = load_img(data, u); why = usable(im)
        except Exception as e:
            tried.append((u, f'err {type(e).__name__}')); continue
        if why: tried.append((u, why)); continue
        return u, im, tried
    return None, None, tried


def main(argv):
    force = '--force' in argv
    ids = set(argv[argv.index('--id') + 1:]) if '--id' in argv else None
    rows = list(csv.DictReader(DATA.open(encoding='utf-8', newline='')))
    fields = list(rows[0].keys())
    if 'logo' not in fields: fields.append('logo')
    OUT.mkdir(parents=True, exist_ok=True)
    for r in rows:
        r.setdefault('logo', '')
        if ids and r['id'] not in ids: continue
        if r['logo'] == 'none' or (r['logo'] and not force): continue
        if not r.get('website'): continue
        if re.search(r'(instagram|facebook|linktr\.ee|yelp|tiktok|x)\.com', urllib.parse.urlparse(r['website']).netloc):
            r['logo'] = 'none'; continue  # social profile, not the venue's own site
        try:
            src, im, tried = find(r['website'])
        except Exception as e:
            print(f"{r['id']}\t{r['name']}\tSITE ERR {type(e).__name__}"); continue
        if not im:
            r['logo'] = 'none'; print(f"{r['id']}\t{r['name']}\tnone {tried[:3]}"); continue
        name = f"{slug(r['name'])}-{r['id']}.webp"
        square(im, r['id'] in DARK_BG).save(OUT / name, 'WEBP', quality=88, method=6)
        r['logo'] = f'/assets/bars/{name}'
        print(f"{r['id']}\t{r['name']}\tOK {src}")
    with DATA.open('w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fields); w.writeheader(); w.writerows(rows)


if __name__ == '__main__':
    main(sys.argv[1:])
