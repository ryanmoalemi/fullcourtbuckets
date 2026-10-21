"""Where to watch WNBA games: bar directory at /wnba/where-to-watch/, built from data/where-to-watch-bars.csv.

Data rule: a row is listed only when an official team watch-party page, the venue's own WNBA page,
a named local news report, or a written staff reply shows WNBA screenings. verification_type
'staff_reply' renders "Confirmed with staff on <date>" plus the optional games_note (e.g. 'every WNBA game'); anything else renders the source line.
Run: python automation/build_where_to_watch.py
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import internal_links as links  # noqa: E402

DATA = ROOT / 'data' / 'where-to-watch-bars.csv'
PAGE_DIR = ROOT / 'wnba' / 'where-to-watch'
PAGE_PATH = PAGE_DIR / 'index.html'
CSV_NAME = 'where-to-watch-wnba-bars.csv'
OG_NAME = 'og-1200.jpg'
OG_URL = 'https://fullcourtbuckets.com/wnba/where-to-watch/' + OG_NAME
OG_SIZE = (1200, 630)
SHELL_PAGE = ROOT / 'wnba' / 'viewership-attendance' / 'index.html'
CANONICAL = 'https://fullcourtbuckets.com/wnba/where-to-watch/'
PATH = '/wnba/where-to-watch/'
PUBLISHED = '2026-10-20'
DATA_THROUGH = '2026-10-20'
H1 = 'Where to Watch WNBA Games: Bars That Show the Games'
TITLE = 'Where to watch WNBA games: bars that show the games | Full Court Buckets'
NAV_LABEL = 'Where to watch WNBA games'
CONTACT = 'ryan@fullcourtbuckets.com'
NOTICE = ('These venues have advertised or confirmed WNBA screenings, but may not show every game. Contact the venue '
          'before visiting to confirm your game, opening hours, age restrictions, cover charges and reservation requirements.')
STYLE_ID = 'fcb-ww-css'
SCRIPT_ID = 'fcb-ww-js'
TEAM_COLORS = {
    'Golden State Valkyries': '#5b2b82', 'Indiana Fever': '#c8102e', 'New York Liberty': '#1f7a6c',
    'Seattle Storm': '#2c5234', 'Atlanta Dream': '#a6192e', 'Minnesota Lynx': '#236192',
    'Phoenix Mercury': '#b4530f', 'Toronto Tempo': '#7a2a3a', 'Los Angeles Sparks': '#552583',
    'Chicago Sky': '#2b6cb0', 'Washington Mystics': '#0c2340', 'Las Vegas Aces': '#5a5a5a',
    'Dallas Wings': '#1d6fb8', 'Connecticut Sun': '#c4511f', 'Portland Fire': '#b3261e',
}
STATES = {'CA': 'California', 'NY': 'New York', 'IN': 'Indiana', 'WA': 'Washington', 'GA': 'Georgia',
          'MN': 'Minnesota', 'CO': 'Colorado', 'AZ': 'Arizona', 'ON': 'Ontario', 'FL': 'Florida', 'IL': 'Illinois',
          'DC': 'District of Columbia', 'OR': 'Oregon', 'TX': 'Texas', 'NV': 'Nevada', 'CT': 'Connecticut'}
NO_TEAM = 'No local team'
esc = html.escape

PAGE_CSS = '''
.ww-wrap{max-width:900px}
.ww-top{display:flex;flex-direction:column}
.ww-intro{margin:14px 0;font-size:17px;line-height:1.6;max-width:65ch}
.ww-box{display:flex;flex-wrap:wrap;gap:6px 18px;margin:0 0 12px;padding:12px 16px;border:1px solid #e4dfd8;background:#faf8fd;font-size:14px;color:#3b3833}
.ww-box strong{color:#1b1a19}
.ww-notice{margin:0 0 18px;padding:12px 16px;border-left:4px solid #ff9800;background:#fff3df;font-size:14px;line-height:1.55;color:#2b2925}
.ww-notice-short,.ww-notice-below{display:none}
.ww-count.is-on{color:#1b1a19;font-weight:700;background:#fff1a8;padding:2px 6px;border-radius:3px}
.ww-controls{position:sticky;top:64px;z-index:5;display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:10px 0;background:#fff;border-bottom:1px solid #e4dfd8}
.ww-controls input,.ww-controls select{min-height:44px;padding:0 12px;border:1px solid #cfc9c1;border-radius:3px;font:500 16px Inter,system-ui,sans-serif;background:#fff;color:#1b1a19}
.ww-controls input{flex:1 1 320px}.ww-controls select{flex:0 1 260px}
.ww-count{font-size:14px;color:#5d5952;font-weight:600}
.ww-sr{position:absolute;left:-9999px}
.ww-state-h{margin:28px 0 4px;font:800 26px/1.15 Barlow,sans-serif}
.ww-city-h{margin:14px 0 6px;font:700 18px/1.3 Barlow,sans-serif;color:#3b3833}.ww-n{color:#6b665f;font-weight:600}
.ww-list{list-style:none;margin:0;padding:0}
.ww-dym{flex:1 1 100%;margin:0}.ww-row.is-active{background:#f6f1ff;outline:2px solid #5b22c9;outline-offset:-2px}
.ww-page .byline-row{display:flex;flex-wrap:wrap;align-items:center;gap:8px 14px;margin:12px 0 8px;background:none;padding:0;box-shadow:none;border:0}
.ww-page .byline-row .byline{display:flex;align-items:center;gap:10px;margin:0;font:600 14px/1.3 Inter,system-ui,sans-serif;text-decoration:none}
.ww-page .byline-row .byline img{width:40px;height:40px;max-width:40px;border-radius:50%;object-fit:cover;border:1px solid var(--line,#2b2930);flex:0 0 40px}
.ww-page .byline-row .article-date{font-size:13px;margin:0;line-height:1.3}
.ww-logo-img{display:block;object-fit:contain;border-radius:50%!important;padding:0!important;background:#fff;border:1px solid #e4dfd8;box-sizing:border-box}
.ww-row[hidden],.ww-city[hidden],.ww-state[hidden]{display:none!important}
.ww-row{display:flex;gap:14px;padding:14px 0;border-bottom:1px solid #ece7e0}
.ww-logo{flex:0 0 44px;width:44px;height:44px;border-radius:50%;display:flex;align-items:center;justify-content:center;color:#fff;font:800 15px/1 Barlow,sans-serif;letter-spacing:.5px}
.ww-body p{margin:0}.ww-name{font:700 17px/1.3 Inter,sans-serif;color:#1b1a19}
.ww-loc,.ww-team{font-size:14px;color:#4a4740;line-height:1.45}
.ww-tag{display:inline-block;margin-top:4px!important;padding:2px 8px;border:1px solid #2a8f4f;border-radius:3px;color:#1f6b3a;font:700 12px/1.5 Inter,sans-serif}
.ww-ver{margin-top:4px!important;font-size:13px;color:#5d5952}.ww-ver a{color:#9a5200;text-decoration:underline}
.ww-quote{margin-top:6px!important;font-size:14px;line-height:1.45;color:#2b2925;font-style:italic;border-left:3px solid #c8102e;padding-left:8px}
.ww-btns{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}
.ww-btns .btn{min-height:44px;padding:0 14px;border:1px solid #ff9800;border-radius:3px;color:#8a4a00;font:700 14px Inter,sans-serif;text-decoration:none;display:inline-flex;align-items:center}
.ww-empty{display:none;padding:20px 0;color:#5d5952}
.ww-below h2{margin:40px 0 10px;font:800 26px/1.15 Barlow,sans-serif}.ww-below h3{margin:16px 0 6px;font:700 17px/1.35 Barlow,sans-serif}
.ww-below p,.ww-below li{font-size:15px;line-height:1.65;color:#2f2c28;max-width:70ch}.ww-below a{color:#9a5200}
.ww-dl{display:inline-flex;align-items:center;min-height:44px;padding:0 16px;border:1px solid #ff9800;border-radius:3px;font-weight:700;text-decoration:none}
@media(max-width:600px){
.ww-page .page-header .eyebrow{display:none}
.ww-page .page-header h1{font-size:23px!important;line-height:1.2;margin:6px 0 0}
.ww-page .page-header .breadcrumbs{font-size:12px}
.ww-controls{order:1;top:56px;gap:8px;padding:8px 0}
.ww-controls input,.ww-controls select{flex:1 1 100%}
.ww-count{font-size:12px}
.ww-notice-short{display:block;order:2;margin:8px 0 6px;font-size:13px;line-height:1.45;color:#2b2925}
.ww-intro{order:3;font-size:13px;line-height:1.5;margin:4px 0 6px}
.ww-box{order:3;font-size:12px;padding:6px 10px;gap:2px 10px;margin:0 0 6px}
.ww-notice-top{display:none}
.ww-notice-below{display:block;margin:20px 0 0;font-size:13px}
.ww-dir{order:4}
.ww-logo{flex-basis:36px;width:36px;height:36px;font-size:13px}
.ww-state-h{font-size:22px}
}
'''

PAGE_JS = r'''(function(){
/* Venue filter built on the main site search engine (window.FCBSearch from /assets/site-nav.js):
   same tokenizing, accent folding, stemming, prefix + typo-tolerant matching, ranking, "Did you mean" and highlighting. */
function init(){var q=document.getElementById('ww-q'),c=document.getElementById('ww-c'),e=document.getElementById('ww-e'),dym=document.getElementById('ww-dym');
if(!q)return;
/* Fallback if a phone still has an old cached site-nav.js without createIndex: plain accent-folded word-prefix filter. */
var FS=(window.FCBSearch&&FCBSearch.createIndex)?FCBSearch:{fold:function(x){x=String(x||'').toLowerCase();return x.normalize?x.normalize('NFD').replace(/[\u0300-\u036f]/g,''):x;},
highlight:function(n,x){n.textContent=x;},createIndex:function(it){var f=this.fold;return{search:function(qs){var w=f(qs).split(/[^a-z0-9]+/).filter(Boolean),res=[];
it.forEach(function(d){var h=' '+f([d.t,d.w,d.k,d.b].join(' ')).replace(/[^a-z0-9]+/g,' ');if(w.every(function(x){return h.indexOf(' '+x)>-1;}))res.push({doc:{item:d},score:1,hits:[]});});
return{results:res,terms:w,suggestion:''};}};}};
var rows=[].slice.call(document.querySelectorAll('.ww-row')),items=[],timer=null,active=-1;
rows.forEach(function(r,i){var n=r.querySelector('.ww-name'),l=r.querySelector('.ww-loc');r._i=i;r._n=n?n.textContent:'';r._l=l?l.textContent:'';
items.push({t:r._n,w:r._l,k:r.dataset.team||'',b:r.dataset.q||'',_r:i});});
var idx=FS.createIndex(items);
function vis(){return rows.filter(function(r){return !r.hidden&&!r.closest('[hidden]');});}
function setActive(i){var v=vis();rows.forEach(function(r){r.classList.remove('is-active');});if(!v.length){active=-1;return;}
if(i<0)i=v.length-1;if(i>=v.length)i=0;active=i;v[i].classList.add('is-active');v[i].scrollIntoView({block:'nearest'});}
function run(){var query=q.value.trim(),n=0,score={},terms=[];active=-1;dym.hidden=true;
if(query){var out=idx.search(query),res=out.results,clean=res.filter(function(x){return !x.hits.some(function(h){return h[2]==='f';});});
if(clean.length)res=clean;terms=out.terms;res.forEach(function(x){score[x.doc.item._r]=x.score;});
if(out.suggestion&&FS.fold(out.suggestion)!==FS.fold(query)){var a=dym.querySelector('a');a.textContent=out.suggestion;dym.hidden=false;}}
rows.forEach(function(r){var ok=!query||r._i in score;r.hidden=!ok;if(ok)n++;r.classList.remove('is-active');
var nm=r.querySelector('.ww-name'),lc=r.querySelector('.ww-loc');if(nm)FS.highlight(nm,r._n,ok?terms:[]);if(lc)FS.highlight(lc,r._l,ok?terms:[]);});
document.querySelectorAll('.ww-city ul,.ww-city ol').forEach(function(u){var rs=[].slice.call(u.children).filter(function(x){return x.classList.contains('ww-row');});
rs.sort(function(x,y){return query?((score[y._i]||0)-(score[x._i]||0))||x._i-y._i:x._i-y._i;});rs.forEach(function(x){u.appendChild(x);});});
document.querySelectorAll('.ww-city,.ww-state').forEach(function(d){d.hidden=!d.querySelector('.ww-row:not([hidden])');});
c.textContent=query?(n+' of '+rows.length+' venues match \u201c'+query+'\u201d'):('Showing all '+n+' venues');c.classList.toggle('is-on',!!query);e.style.display=n?'none':'block';if(!n&&query)e.textContent='No venues match \u201c'+query+'\u201d. Try a city, neighborhood or bar name, or clear the search.';}
function soon(){clearTimeout(timer);timer=setTimeout(run,60);}['input','keyup','compositionend','change','search'].forEach(function(k){q.addEventListener(k,soon);});
q.addEventListener('keydown',function(ev){if(ev.key==='ArrowDown'){ev.preventDefault();setActive(active+1);}else if(ev.key==='ArrowUp'){ev.preventDefault();setActive(active-1);}
else if(ev.key==='Escape'){ev.preventDefault();q.value='';run();}else if(ev.key==='Enter'){ev.preventDefault();var v=vis(),r=v[active<0?0:active];if(r){var l=r.querySelector('a');r.scrollIntoView({block:'center'});if(l)l.focus({preventScroll:true});}}});
dym.querySelector('a').addEventListener('click',function(ev){ev.preventDefault();q.value=this.textContent;run();q.focus();});
if(q.value.trim())run();}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();})();'''


def load() -> list[dict]:
    with DATA.open(encoding='utf-8', newline='') as fh:
        rows = list(csv.DictReader(fh))
    seen = set()
    for r in rows:
        for k in ('id', 'name', 'city', 'state', 'team_market', 'source_url'):
            if not r.get(k):
                raise SystemExit(f'{r.get("id")}: missing {k}')
        if r['id'] in seen:
            raise SystemExit(f'duplicate id {r["id"]}')
        seen.add(r['id'])
    return rows


def human(day: str) -> str:
    d = dt.date.fromisoformat(day)
    return f'{d.strftime("%b")} {d.day}, {d.year}'


def initials(name: str) -> str:
    base = re.sub(r'^(The|A)\s', '', name.split(' - ')[0])
    words = [w for w in re.split(r'[\s\-&/]+', base) if w and w[0].isalnum()]
    if not words:
        return '?'
    return (words[0][0] + (words[1][0] if len(words) > 1 else words[0][1:2])).upper()


def tel(phone: str) -> str:
    digits = re.sub(r'[^\d]', '', phone)
    return '+' + digits if len(digits) == 11 else '+1' + digits[-10:]


def verification(r: dict) -> str:
    if r.get('verification_type') == 'staff_reply':
        line = f'Confirmed with staff on {human(r["verification_date"])}'
        note = (r.get('games_note') or '').strip()
        return f'{line}. Shows {esc(note)}.' if note else line
    return (f'Source: <a href="{esc(r["source_url"])}" rel="nofollow noopener" target="_blank">{esc(r["source_name"])}</a>'
            f' (accessed {human(r["verification_date"])})')


def quote_html(r: dict) -> str:
    q = (r.get('bar_quote') or '').strip()
    if not q or r.get('verification_type') != 'staff_reply':
        return ''
    d = dt.date.fromisoformat(r['verification_date'])
    return (f'<p class="ww-quote">From the bar: &ldquo;{esc(q)}&rdquo; '
            f'({d.strftime("%B")} {d.day}, {d.year})</p>')


def logo_html(r: dict, color: str) -> str:
    logo = (r.get('logo') or '').strip()
    if logo.startswith('/assets/bars/') and (ROOT / logo.lstrip('/')).exists():
        return (f'<img class="ww-logo ww-logo-img" src="{esc(logo)}" alt="{esc(r["name"])} logo" '
                'width="44" height="44" loading="lazy" decoding="async">')
    return f'<span class="ww-logo" style="background:{color}" aria-hidden="true">{esc(initials(r["name"]))}</span>'


def row_html(r: dict) -> str:
    color = TEAM_COLORS.get(r['team_market'], '#555')
    btns = []
    if r.get('directions'):
        btns.append(f'<a class="btn" href="{esc(r["directions"])}" rel="nofollow noopener" target="_blank">Directions</a>')
    if r.get('website'):
        btns.append(f'<a class="btn" href="{esc(r["website"])}" rel="nofollow noopener" target="_blank">Website</a>')
    if r.get('phone'):
        btns.append(f'<a class="btn" href="tel:{tel(r["phone"])}">Call</a>')
    area = ', '.join(x for x in (r['street'], r['city'], r['state']) if x)
    team = '' if r['team_market'] == NO_TEAM else f'<p class="ww-team">Team market: {esc(r["team_market"])}</p>'
    hay = ' '.join([r['name'], r['street'], r['city'], r['state'], STATES.get(r['state'], ''), r['team_market']]).lower()
    return (f'<li class="ww-row" data-team="{esc(r["team_market"])}" data-q="{esc(hay)}">'
            + logo_html(r, color) +
            f'<div class="ww-body"><p class="ww-name">{esc(r["name"])}</p><p class="ww-loc">{esc(area)}</p>{team}'
            f'<p class="ww-tag">Shows WNBA games</p><p class="ww-ver">{verification(r)}</p>{quote_html(r)}'
            f'<div class="ww-btns">{"".join(btns)}</div></div></li>')


def directory(rows: list[dict]) -> str:
    groups: dict = defaultdict(lambda: defaultdict(list))
    for r in rows:
        groups[STATES.get(r['state'], r['state'])][r['city']].append(r)
    out = []
    for state in sorted(groups):
        out.append(f'<section class="ww-state"><h2 class="ww-state-h">{esc(state)}</h2>')
        for city in sorted(groups[state]):
            items = sorted(groups[state][city], key=lambda r: r['name'].lower())
            out.append(f'<div class="ww-city"><h3 class="ww-city-h">{esc(city)}, {esc(state)} <span class="ww-n">({len(items)})</span></h3>'
                       f'<ul class="ww-list">{"".join(row_html(r) for r in items)}</ul></div>')
        out.append('</section>')
    return ''.join(out)


def stats(rows: list[dict]) -> dict:
    teams = sorted({r['team_market'] for r in rows if r['team_market'] != NO_TEAM})
    confirmed = sum(1 for r in rows if r.get('verification_type') == 'staff_reply')
    cities = {(r['city'], r['state']) for r in rows}
    states = {r['state'] for r in rows}
    return {'venues': len(rows), 'teams': teams, 'cities': len(cities), 'states': len(states), 'confirmed': confirmed, 'sourced': len(rows) - confirmed}


def description(s: dict) -> str:
    return (f'{s["venues"]} bars and restaurants in {s["cities"]} U.S. and Canadian cities that show WNBA games, '
            'from official team watch-party lists, venue pages and venue confirmations. Search by city.')


FAQ = [
    ('Do these bars show every WNBA game?', 'Not always. Contact the venue to check your game.'),
    ('What does "Confirmed with staff" mean?', 'The venue told us in writing, on the date listed, that it shows WNBA games.'),
    ('My bar shows WNBA games. How do I get listed?',
     f'Email <a href="mailto:{CONTACT}">{CONTACT}</a> with your bar name, address and a link to your WNBA listing or event page.'),
    ('A listing is wrong or a bar closed. What should I do?', f'Email <a href="mailto:{CONTACT}">{CONTACT}</a> and we will recheck it.'),
    ('Can I reuse the data?', 'Yes, under CC BY 4.0 with credit to Full Court Buckets.'),
]


def jsonld(s: dict) -> str:
    strip = lambda x: re.sub(r'<[^>]+>', '', x)
    graph = [
        {'@type': 'WebPage', '@id': CANONICAL, 'url': CANONICAL, 'name': H1, 'description': description(s),
         'datePublished': PUBLISHED, 'dateModified': DATA_THROUGH,
         'author': {'@type': 'Person', 'name': 'Ryan Moalemi', 'url': 'https://fullcourtbuckets.com/authors/ryan-moalemi/'},
         'publisher': {'@type': 'Organization', 'name': 'Full Court Buckets', 'url': 'https://fullcourtbuckets.com/'}},
        {'@type': 'Dataset', 'name': 'Full Court Buckets: where to watch WNBA games', 'url': CANONICAL,
         'description': description(s), 'license': 'https://creativecommons.org/licenses/by/4.0/',
         'creator': {'@type': 'Organization', 'name': 'Full Court Buckets'}, 'dateModified': DATA_THROUGH,
         'distribution': [{'@type': 'DataDownload', 'encodingFormat': 'text/csv', 'contentUrl': CANONICAL + CSV_NAME}]},
        {'@type': 'BreadcrumbList', 'itemListElement': [
            {'@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': 'https://fullcourtbuckets.com/'},
            {'@type': 'ListItem', 'position': 2, 'name': 'WNBA', 'item': 'https://fullcourtbuckets.com/wnba/'},
            {'@type': 'ListItem', 'position': 3, 'name': 'Where to watch', 'item': CANONICAL}]},
        {'@type': 'FAQPage', 'mainEntity': [{'@type': 'Question', 'name': q, 'acceptedAnswer': {'@type': 'Answer', 'text': strip(a)}} for q, a in FAQ]},
    ]
    return '<script type="application/ld+json">' + json.dumps({'@context': 'https://schema.org', '@graph': graph}, ensure_ascii=False) + '</script>'


def write_og_image(s: dict) -> None:
    """1200x630 JPEG share card (X does not reliably render WebP cards)."""
    from PIL import Image, ImageDraw, ImageFont
    w, h = OG_SIZE
    img = Image.new('RGB', OG_SIZE, '#faf8fd')
    d = ImageDraw.Draw(img)
    for x in range(w):  # FCB purple-pink-orange accent bar
        t = x / (w - 1)
        a, b = ((125, 53, 255), (241, 0, 145)) if t < .5 else ((241, 0, 145), (255, 152, 0))
        u = t * 2 if t < .5 else (t - .5) * 2
        d.line([(x, 0), (x, 17)], fill=tuple(int(a[i] + (b[i] - a[i]) * u) for i in range(3)))
    fonts = ROOT / 'assets' / 'fonts'
    bold = lambda n: ImageFont.truetype(str(fonts / 'Inter-Bold.ttf'), n)
    med = lambda n: ImageFont.truetype(str(fonts / 'Inter-Medium.ttf'), n)
    logo = Image.open(ROOT / 'logo.png').convert('RGBA')
    logo.thumbnail((210, 140))
    img.paste(logo, (w - logo.width - 60, 52), logo)
    d.text((70, 70), 'WNBA / DATA & RESEARCH', font=bold(26), fill='#c2007a')
    d.text((70, 150), 'Where to watch', font=bold(92), fill='#2a1458')
    d.text((70, 258), 'WNBA games', font=bold(92), fill='#2a1458')
    d.text((70, 390), f'{s["venues"]} bars and restaurants in {s["cities"]} cities', font=med(40), fill='#2b2925')
    d.text((70, 448), 'Search by city. Check before you go.', font=med(32), fill='#5d5952')
    d.text((70, 540), 'fullcourtbuckets.com/wnba/where-to-watch', font=bold(28), fill='#9a5200')
    PAGE_DIR.mkdir(parents=True, exist_ok=True)
    img.save(PAGE_DIR / OG_NAME, 'JPEG', quality=88, optimize=True, progressive=True)


def shell_parts(s: dict) -> tuple[str, str, str]:
    shell = SHELL_PAGE.read_text(encoding='utf-8')
    head_end = shell.index('</head>')
    head = shell[:head_end]
    # cache-bust shared assets so phones never pair this page with a stale site-nav.js (CDN max-age=600)
    import hashlib
    for asset in ('site-nav.js', 'site-nav.css'):
        v = hashlib.sha1((ROOT / 'assets' / asset).read_bytes()).hexdigest()[:10]
        shell = re.sub(rf'/assets/{re.escape(asset)}(\?v=[0-9a-f]+)?"', f'/assets/{asset}?v={v}"', shell)
    head_end = shell.index('</head>')
    head = shell[:head_end]
    head = re.sub(r'<script type="application/ld\+json">.*?</script>', '', head, flags=re.S)
    head = re.sub(r'<title>.*?</title>', f'<title>{esc(TITLE)}</title>', head, count=1, flags=re.S)
    head = re.sub(r'\s*<meta (?:name|property)="(?:description|og:[a-z:_]+|twitter:[a-z:_]+)" content="[^"]*">', '', head)
    head = re.sub(r'<link rel="canonical" href="[^"]*">', f'<link rel="canonical" href="{CANONICAL}">', head)
    d = esc(description(s))
    meta = (f'\n<meta name="description" content="{d}">\n<meta property="og:type" content="website">'
            f'\n<meta property="og:title" content="{esc(H1)}">\n<meta property="og:description" content="{d}">'
            f'\n<meta property="og:url" content="{CANONICAL}">\n<meta property="og:site_name" content="Full Court Buckets">'
            f'\n<meta property="og:image" content="{OG_URL}">\n<meta property="og:image:type" content="image/jpeg">'
            f'\n<meta property="og:image:width" content="{OG_SIZE[0]}">\n<meta property="og:image:height" content="{OG_SIZE[1]}">'
            f'\n<meta property="og:image:alt" content="Where to watch WNBA games: bars and restaurants by city and team">'
            f'\n<meta name="twitter:card" content="summary_large_image">\n<meta name="twitter:title" content="{esc(H1)}">'
            f'\n<meta name="twitter:description" content="{d}">\n<meta name="twitter:image" content="{OG_URL}">')
    head = head.replace(f'<title>{esc(TITLE)}</title>', f'<title>{esc(TITLE)}</title>{meta}', 1)
    body_start = shell.index('<main class="page">')
    top = shell[head_end:body_start]
    bottom = shell[shell.index('</main>') + len('</main>'):]
    bottom = re.sub(r'<script>\s*\(function \(\) \{.*?</script>', '', bottom, flags=re.S)
    return head, top, bottom


def render(rows: list[dict]) -> str:
    s = stats(rows)
    head, top, bottom = shell_parts(s)
    head += f'<style id="{STYLE_ID}">{PAGE_CSS}</style>{jsonld(s)}'
    opts = ''.join(f'<option value="{esc(t)}">{esc(t)} ({sum(1 for r in rows if r["team_market"] == t)})</option>' for t in s['teams'])
    others = sum(1 for r in rows if r['team_market'] == NO_TEAM)
    if others:
        opts += f'<option value="{NO_TEAM}">Other cities, no local team ({others})</option>'
    faq = ''.join(f'<h3>{esc(q)}</h3><p>{a}</p>' for q, a in FAQ)
    main = (
        '<main class="page ww-page"><div class="standings-shell ww-wrap"><div class="page-header">'
        '<nav class="breadcrumbs" aria-label="Breadcrumb"><a href="/">Home</a> › <a href="/wnba/">WNBA</a> › <span>Where to watch</span></nav>'
        '<p class="eyebrow">WNBA / Data &amp; research</p>'
        f'<h1>{esc(H1)}</h1>'
        f'<div class="byline-row">{links.BYLINE_HTML}'
        f'<time class="article-date" datetime="{DATA_THROUGH}">{esc(human(DATA_THROUGH))}</time></div>'
        '</div><div class="ww-top">'
        f'<div class="ww-box"><span><strong>Data through:</strong> {human(DATA_THROUGH)} (PT)</span><span><strong>{s["venues"]}</strong> venues</span>'
        f'<span><strong>{s["confirmed"]}</strong> confirmed with staff</span><span><strong>{s["sourced"]}</strong> from team or venue pages</span></div>'
        f'<div class="ww-notice ww-notice-top" role="note"><strong>Check before you go:</strong> {NOTICE}</div>'
        '<p class="ww-notice-short"><strong>Check before you go:</strong> call ahead to confirm your game. <a href="#check-before-you-go">Details</a></p>'
        '<div class="ww-controls" data-fcb-data-table><label class="ww-sr" for="ww-q">Search venues</label>'
        '<input id="ww-q" type="search" placeholder="Search bars, neighborhoods or cities..." autocomplete="off"><p class="ss-dym ww-dym" id="ww-dym" hidden>Did you mean <a href="#"></a>?</p>'
        f'<span class="ww-count" id="ww-c" aria-live="polite">Showing {s["venues"]} venues</span></div>'
        f'<div class="ww-dir" id="ww-dir">{directory(rows)}'
        '<p class="ww-empty" id="ww-e">No venues match. Try a city, neighborhood or bar name, or clear the search.</p>'
        f'<div class="ww-notice ww-notice-below" id="check-before-you-go" role="note"><strong>Check before you go:</strong> {NOTICE}</div></div>'
        '</div><div class="ww-below">'
        '<h2 id="download">Download the data (CC BY 4.0)</h2>'
        f'<p><a class="ww-dl" href="{PATH}{CSV_NAME}" download>Download CSV</a></p>'
        '<p>Columns: id, name, street, city, state, country, team_market, verification_type, verification_date, source_name, source_url, website, phone, directions. '
        'Credit: "Full Court Buckets, Where to Watch WNBA Games (CC BY 4.0)" with a link to this page.</p>'
        '<h2 id="methods">How we build this list</h2>'
        f'<p class="ww-intro">A directory of bars and restaurants that list WNBA screenings on official team watch-party pages or their own websites, or that confirmed with our staff. Covers {s["venues"]} venues in {s["cities"]} cities across the U.S. and Canada, in WNBA team markets and beyond.</p>'
        '<ul>'
        "<li>A venue is listed only when an official team watch-party page, the venue's own WNBA page, a named local news report, or a written reply to our staff shows WNBA screenings.</li>"
        '<li>"Confirmed with staff" means the venue replied to us in writing on that date. We keep those replies on file.</li>'
        '<li>Reddit, aggregators and third-party directories are not used as evidence.</li>'
        '<li>Venues that are closed, not yet open, or have no current address stay off the page until checked.</li>'
        '<li>Directions links are built from the street address. No rankings, ratings, tiers or badges. Listing here is not an endorsement or an official team or league partnership.</li></ul>'
        '<h2 id="sources">Sources</h2><ul>'
        '<li><a href="https://valkyries.wnba.com/bar-network" rel="noopener" target="_blank">Golden State Valkyries Bar Network</a>, '
        '<a href="https://storm.wnba.com/bar-league" rel="noopener" target="_blank">Seattle Storm Bar League</a>, '
        '<a href="https://liberty.wnba.com/bar-network" rel="noopener" target="_blank">New York Liberty Bar Network</a>, '
        '<a href="https://dream.wnba.com/playoff-finals-watch-parties" rel="noopener" target="_blank">Atlanta Dream Finals Watch Parties</a>, '
        '<a href="https://go.feverbasketball.com/barnetwork" rel="noopener" target="_blank">Indiana Fever Bar Network</a> '
        "(all accessed Oct 19, 2026), plus each venue's own website and the local reports named on each listing.</li></ul>"
        f'<h2 id="faq">FAQ</h2>{faq}'
        '</div></div></main>'
    )
    bottom = bottom.replace('</body>', f'<script id="{SCRIPT_ID}">{PAGE_JS}</script>\n</body>', 1)
    return head + top + main + bottom


def write_if_changed(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file() or path.read_text(encoding='utf-8') != content:
        path.write_text(content, encoding='utf-8')


def update_sitemaps() -> None:
    for name in ('pages-sitemap.xml', 'sitemap.xml'):
        path = ROOT / name
        text = path.read_text(encoding='utf-8')
        if f'<loc>{CANONICAL}</loc>' in text or '<urlset' not in text:
            continue
        entry = (f'  <url>\n    <loc>{CANONICAL}</loc>\n    <lastmod>{DATA_THROUGH}</lastmod>\n'
                 '    <changefreq>daily</changefreq>\n    <priority>0.8</priority>\n  </url>\n')
        path.write_text(text.replace('</urlset>', entry + '</urlset>', 1), encoding='utf-8')
    path = ROOT / 'sitemap' / 'index.html'
    page = path.read_text(encoding='utf-8')
    if f'href="{PATH}"' not in page:
        marker = '<li><a href="/wnba/teams/">Teams</a></li>'
        if marker not in page:
            raise SystemExit('HTML sitemap main list marker missing')
        page = page.replace(marker, marker + f'<li><a href="{PATH}">{NAV_LABEL}</a></li>', 1)
        path.write_text(page, encoding='utf-8')


def fill_missing_logos() -> None:
    """New venues (e.g. from the bar-reply routine) get a logo on the next build. Blank `logo` = not tried yet;
    `none` = checked, use initials. Set FCB_NO_LOGO_FETCH=1 to skip the network step."""
    import os
    if os.environ.get('FCB_NO_LOGO_FETCH'): return
    with DATA.open(encoding='utf-8', newline='') as fh:
        todo = [r['id'] for r in csv.DictReader(fh) if r.get('website') and not (r.get('logo') or '').strip()]
    if not todo: return
    try:
        import fetch_bar_logos
        fetch_bar_logos.main(['--id', *todo])
    except Exception as e:  # never block a page build on logo fetching
        print(f'logo fetch skipped: {e}', file=sys.stderr)


def main() -> None:
    fill_missing_logos()
    rows = load()
    write_if_changed(PAGE_PATH, render(rows))
    write_og_image(stats(rows))
    write_if_changed(PAGE_DIR / CSV_NAME, DATA.read_text(encoding='utf-8'))
    update_sitemaps()
    s = stats(rows)
    print(f'{s["venues"]} venues, {s["cities"]} cities, {s["states"]} states, {len(s["teams"])} team markets, {s["confirmed"]} confirmed with staff')


if __name__ == '__main__':
    main()
