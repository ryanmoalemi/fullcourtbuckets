#!/usr/bin/env python3
"""Build the WNBA couples page from data/wnba_couples.json.

The page lists the couples array only. The excluded array is never rendered.
"""
from __future__ import annotations

import html
import json
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from analytics import GA4_TAG
import site_nav
from link_graph import iter_html, page_url

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://fullcourtbuckets.com'
PAGE_URL = '/wnba/couples/'
DATA_PATH = ROOT / 'data' / 'wnba_couples.json'
PAGE_PATH = ROOT / 'wnba' / 'couples' / 'index.html'
PHOTO_DIR = ROOT / 'images' / 'couples'
CHECKED = 'September 29, 2026'
UA = 'FullCourtBuckets/1.0 (https://fullcourtbuckets.com/wnba/couples/; source and photo check)'
BROWSER_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
)
ADSENSE_TAG = '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-6621195315204235" crossorigin="anonymous"></script>'

# Chips whose sources could not be verified. They are never published.
OMIT = {
    ('Courtney Vandersloot', 'Allie Quigley'): {'kids'},
    ('Alyssa Thomas', 'DeWanna Bonner'): {'met', 'since'},
    ('Paige Bueckers', 'Azzi Fudd'): {'met'},
    ("A'ja Wilson", 'Bam Adebayo'): {'extra'},
    ('Candace Parker', 'Anna Petrakova'): {'kids'},
}
CHIP_FIELDS = (
    ('met', 'How they met'),
    ('since', 'Together since'),
    ('engaged', 'Engaged'),
    ('wedding', 'Wedding'),
    ('kids', 'Kids'),
    ('extra', 'Note'),
)
STATUS_FIELDS = {
    'Married': ('wedding', 'engaged', 'since', 'met', 'kids', 'extra'),
    'Engaged': ('engaged', 'since', 'wedding', 'met', 'kids', 'extra'),
    'Dating': ('since', 'met', 'engaged', 'wedding', 'extra', 'kids'),
}
ALIASES = {
    'Marta Xargay Casademont': 'marta-xargay',
    'Megan Gustafson (DiLeo)': 'megan-dileo',
}
PAGE_CSS = """
.couples-intro h1{font:800 clamp(42px,12vw,76px)/.95 var(--display);margin:8px 0 12px;letter-spacing:-.4px}
.lede,.rules,.checked,.method p,.faq-item p{max-width:42rem}
.lede{font-size:16px;line-height:1.5;margin:0 0 12px}
.rules{margin:0 0 12px;padding:2px 0 2px 14px;border-left:2px solid var(--purple);color:var(--muted)}
.checked{font-size:12px;color:var(--muted);margin:0 0 22px}
.couple-card{border:1px solid var(--line);background:linear-gradient(160deg,#1c1522,#111015);padding:16px 16px 14px;margin:0 0 14px;scroll-margin-top:96px}
.pair{display:flex;align-items:center;min-height:76px}
.bubble{width:76px;height:76px;border-radius:50%;overflow:hidden;flex:0 0 auto;position:relative;z-index:1;border:3px solid #141319;background:#241c2c}
.bubble img{display:block;width:100%;height:100%;object-fit:cover;object-position:center 18%}
.bubble.initials{display:grid;place-items:center;font:700 24px/1 var(--display);letter-spacing:.04em;color:#f6f2f8;background:linear-gradient(145deg,#3c284c,#19141f)}
.heart{width:26px;height:26px;margin-left:-14px;margin-right:-14px;border-radius:50%;background:#ff4bb1;display:grid;place-items:center;position:relative;z-index:3;flex:0 0 auto;border:2px solid #0b0b10}
.pair .bubble:last-child{z-index:2}
.badge{display:inline-block;margin:10px 0 0;background:#ff4bb118;border:1px solid #7d3b624d;color:#ff91cd;font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;padding:4px 8px}
.couple-card h2{font-size:clamp(28px,8vw,42px);margin:8px 0;overflow-wrap:break-word}
.couple-card h2 a{text-decoration:underline;text-underline-offset:3px;text-decoration-color:#c678c555}
.role{color:var(--muted);font-size:13px;line-height:1.45;margin:0}
.chips{display:flex;flex-wrap:wrap;gap:8px;list-style:none;padding:0;margin:12px 0 0}
.chips a{flex:1 1 148px;min-width:0;min-height:44px;display:flex;flex-direction:column;justify-content:center;border:1px solid #5a4c61;background:#17121e;padding:8px 10px;overflow-wrap:break-word}
.chips a span{font-size:9px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--pink)}
.method,.faq,.credits{padding-top:8px;border-top:1px solid var(--line);margin-top:22px}
.faq-item{padding:10px 0;border-bottom:1px solid var(--line)}
.faq-item h3{font-size:22px;margin:0 0 6px}
.credits li{margin:0 0 8px;color:var(--muted);font-size:13px}
.credits a,.method a,.faq a,.lede a{color:#e4afeb;text-decoration:underline;text-underline-offset:3px}
@media(min-width:800px){
  .bubble{width:96px;height:96px}
  .bubble.initials{font-size:30px}
  .couple-card{padding:22px 22px 18px}
}
"""


def esc(value) -> str:
    return html.escape('' if value is None else str(value), quote=True)


def slugify(name: str) -> str:
    text = unicodedata.normalize('NFKD', name.casefold().replace("'", ''))
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')
    return text or 'player'


def couple_anchor(couple: dict) -> str:
    return f"{slugify(couple['a'])}-{slugify(couple['b'])}"


def load_couples(root: Path = ROOT) -> list[dict]:
    data = json.loads((root / 'data' / 'wnba_couples.json').read_text(encoding='utf-8'))
    couples = data.get('couples') or []
    if not isinstance(couples, list) or not couples:
        raise SystemExit('data/wnba_couples.json has no couples.')
    return couples


def load_slugs(root: Path = ROOT) -> dict[str, str]:
    names = {}
    path = root / 'data' / 'wnba' / 'players-index.json'
    if path.is_file():
        index = json.loads(path.read_text(encoding='utf-8'))
        for entry in index.get('players') or []:
            name = str(entry.get('name') or '').strip()
            slug = str(entry.get('slug') or '').strip()
            if name and slug and (root / 'wnba' / slug / 'index.html').is_file():
                names[name] = slug
    for name, slug in ALIASES.items():
        if (root / 'wnba' / slug / 'index.html').is_file():
            names.setdefault(name, slug)
    return names


def person_link(name: str, slug: str | None) -> str:
    safe = esc(name)
    if not slug:
        return safe
    return f'<a href="/wnba/{esc(slug)}/">{safe}</a>'


def note_html(couple: dict, partner: str, partner_slug: str | None) -> str:
    status = couple.get('status') or ''
    who = person_link(partner, partner_slug)
    if status == 'Married':
        sentence = f'Married to {who}.'
    elif status == 'Engaged':
        sentence = f'Engaged to {who}.'
    elif status == 'Dating':
        sentence = f'Dating {who}.'
    else:
        return ''
    href = f"/wnba/couples/#{couple_anchor(couple)}"
    return (
        f'<p class="relationship-note">{sentence} '
        f'<a href="{esc(href)}">Couples page</a>.</p>'
    )


def note_for_slug(root, slug: str) -> str:
    root = Path(root)
    path = root / 'data' / 'wnba_couples.json'
    if not slug or not path.is_file():
        return ''
    slugs = load_slugs(root)
    notes = []
    for couple in load_couples(root):
        slug_a = slugs.get(couple['a'])
        slug_b = slugs.get(couple['b'])
        if slug == slug_a:
            notes.append(note_html(couple, couple['b'], slug_b))
        elif slug == slug_b:
            notes.append(note_html(couple, couple['a'], slug_a))
    return ''.join(notes)


def initials(name: str) -> str:
    cleaned = re.sub(r'\([^)]*\)', ' ', name)
    cleaned = re.sub(r'\bjr\.?\b', ' ', cleaned, flags=re.I)
    parts = [part for part in re.split(r'[^A-Za-z]+', cleaned) if part]
    if not parts:
        return '?'
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _fetch(url: str, browser: bool = False, timeout: int = 25) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={
        'User-Agent': BROWSER_UA if browser else UA,
        'Accept': 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(120000)
            return response.status, raw.decode('utf-8', 'replace')
    except urllib.error.HTTPError as exc:
        body = exc.read(4000).decode('utf-8', 'replace') if exc.fp else ''
        return exc.code or 0, body
    except Exception as exc:  # noqa: BLE001 - a failed fetch is a dead source
        return 0, str(exc)


def _looks_like_article(status: int, body: str) -> bool:
    if status != 200 or len(body) < 700:
        return False
    sample = body[:2500].casefold()
    if 'access denied' in sample or 'gokuprops' in sample or 'awswafintegration' in sample:
        return False
    if '<title>page not found' in sample or '<title>404' in sample:
        return False
    return '<html' in sample or '<!doctype html' in sample


def _article_fetch(url: str) -> bool:
    status, body = _fetch('https://r.jina.ai/' + url, browser=True, timeout=45)
    if status != 200 or 'URL Source:' not in body or 'Title:' not in body:
        return False
    title = ''
    for line in body.splitlines():
        if line.startswith('Title:'):
            title = line[6:].strip().casefold()
            break
    if not title or 'access denied' in title or title.startswith('404') or 'not found' in title:
        return False
    return True


# These articles were fetched and read on 2026-09-29. A direct request from this
# network gets a bot wall, not a missing page.
ARTICLE_CONFIRMED = {
    'https://www.theknot.com/content/wnba-relationships',
    'https://www.theknot.com/content/allisha-gray-relationship',
    'https://www.espn.com/wnba/story/_/id/49660963/paige-bueckers-azzi-fudd-dallas-wings-relationship-comments-dynasty-uconn-huskies',
}


def _is_block_page(status: int, body: str) -> bool:
    sample = body[:2500].casefold()
    if status in (401, 403, 429, 503):
        return True
    return 'access denied' in sample or 'gokuprops' in sample or 'just a moment' in sample or 'awswafintegration' in sample


def source_resolves(url: str, cache: dict[str, bool]) -> bool:
    if url in cache:
        return cache[url]
    status, body = _fetch(url, browser=True)
    if status in (404, 410):
        cache[url] = False
        return False
    ok = _looks_like_article(status, body) or _article_fetch(url)
    if not ok and url in ARTICLE_CONFIRMED and _is_block_page(status, body):
        ok = True
    cache[url] = ok
    return ok


def clean_text(value: str) -> str:
    text = re.sub(r'<[^>]+>', ' ', value or '')
    text = html.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()


def licenses_match(expected: str, short: str, usage: str) -> bool:
    wanted = ' '.join((expected or '').casefold().split())
    blob = ' '.join(f'{short} {usage}'.casefold().split())
    if wanted and wanted in blob:
        return True
    if wanted == 'public domain' and 'public domain' in blob:
        return True
    if wanted == 'cc0' and 'cc0' in blob:
        return True
    return False


def credit_author(commons_artist: str, data_author: str) -> str:
    artist = clean_text(commons_artist)
    data = (data_author or '').strip()
    if data and data.casefold() in artist.casefold():
        return data
    artist = re.sub(r'^File:[^:]+:\s*', '', artist)
    artist = re.sub(r'\s+derivative work:', '; derivative work:', artist, count=1)
    return artist or data


def commons_metadata(titles: list[str]) -> dict[str, dict]:
    body = urllib.parse.urlencode({
        'action': 'query',
        'format': 'json',
        'prop': 'imageinfo',
        'redirects': 1,
        'titles': '|'.join(titles),
        'iiprop': 'url|extmetadata|mime|size',
        'iiurlwidth': '640',
    }).encode()
    request = urllib.request.Request(
        'https://commons.wikimedia.org/w/api.php',
        data=body,
        headers={'User-Agent': UA},
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = json.loads(response.read().decode())
    query = payload.get('query') or {}
    normalized = {item['from']: item['to'] for item in query.get('normalized') or []}
    pages = {page.get('title'): page for page in (query.get('pages') or {}).values()}
    found = {}
    for title in titles:
        page = pages.get(normalized.get(title, title))
        if not page or 'imageinfo' not in page:
            continue
        info = page['imageinfo'][0]
        meta = info.get('extmetadata') or {}

        def val(key: str) -> str:
            return (meta.get(key) or {}).get('value') or ''

        found[title] = {
            'short': clean_text(val('LicenseShortName')),
            'usage': clean_text(val('UsageTerms')),
            'artist': val('Artist'),
            'license_url': val('LicenseUrl'),
            'thumb': info.get('thumburl') or '',
            'width': info.get('thumbwidth') or 640,
            'height': info.get('thumbheight') or 640,
        }
    return found


def download(url: str, dest: Path) -> None:
    request = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(request, timeout=60) as response:
        dest.write_bytes(response.read())


def prepare_photos(couples: list[dict]) -> tuple[dict[str, dict], list[str]]:
    """Confirm each Commons license, then save a 640px version. Returns path-keyed photos."""
    wanted = []
    for couple in couples:
        for key in ('photo_a', 'photo_b'):
            raw = couple.get(key)
            if not raw:
                continue
            page, author, license_name = raw.split('|', 2)
            title = urllib.parse.unquote(page.split('/wiki/')[-1])
            if not title.startswith('File:'):
                title = 'File:' + title
            person = couple['a'] if key == 'photo_a' else couple['b']
            wanted.append((person, title, page, author, license_name))
    meta = commons_metadata([item[1] for item in wanted])
    photos = {}
    dropped = []
    jobs = []
    for person, title, page, author, license_name in wanted:
        info = meta.get(title)
        if not info:
            dropped.append(f'{person}: Commons file missing ({title})')
            continue
        if not licenses_match(license_name, info['short'], info['usage']):
            dropped.append(
                f"{person}: license mismatch, data {license_name}, Commons {info['short'] or info['usage']}"
            )
            continue
        if not info['thumb']:
            dropped.append(f'{person}: no web-sized Commons file')
            continue
        ext = Path(urllib.parse.urlparse(info['thumb']).path).suffix.lower() or '.jpg'
        if ext not in ('.jpg', '.jpeg', '.png', '.webp'):
            ext = '.jpg'
        dest = PHOTO_DIR / f'{slugify(person)}{ext}'
        jobs.append((person, dest, info, page, author, license_name))
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(download, info['thumb'], dest): (person, dest, info, page, author, license_name)
                   for person, dest, info, page, author, license_name in jobs}
        for future in as_completed(futures):
            person, dest, info, page, author, license_name = futures[future]
            try:
                future.result()
            except Exception as exc:  # noqa: BLE001
                dropped.append(f'{person}: photo download failed ({exc})')
                continue
            photos[person] = {
                'src': '/' + dest.relative_to(ROOT).as_posix(),
                'author': credit_author(info['artist'], author),
                'license': info['short'] or license_name,
                'license_url': info['license_url'],
                'page': page,
                'width': info['width'],
                'height': info['height'],
            }
    return photos, dropped


def kept_fields(couple: dict, live: dict[str, bool], dropped: list[str]) -> dict[str, tuple[str, str]]:
    skip = OMIT.get((couple['a'], couple['b']), set())
    kept = {}
    for key, _label in CHIP_FIELDS:
        if key in skip:
            continue
        text = str(couple.get(key) or '').strip()
        src = str(couple.get(key + '_src') or '').strip()
        if not text:
            continue
        if not src or not live.get(src):
            dropped.append(f"{couple['a']} / {couple['b']}: {key} source did not resolve")
            continue
        kept[key] = (text, src)
    return kept


def build_cards(couples: list[dict], photos: dict[str, dict], live: dict[str, bool]) -> tuple[list[dict], list[str]]:
    dropped = []
    cards = []
    slugs = load_slugs()
    ordered = sorted(enumerate(couples), key=lambda item: (not item[1].get('both_wnba'), item[0]))
    for _index, couple in ordered:
        fields = kept_fields(couple, live, dropped)
        status = str(couple.get('status') or '').strip()
        chips = []
        status_src = ''
        for key in STATUS_FIELDS.get(status, ()):
            if key in fields:
                status_src = fields[key][1]
                break
        if status and status_src:
            chips.append(('Status', status, status_src))
        elif status:
            dropped.append(f"{couple['a']} / {couple['b']}: status had no live source")
        for key, label in CHIP_FIELDS:
            if key in fields:
                text, src = fields[key]
                chips.append((label, text, src))
        cards.append({
            'a': couple['a'],
            'b': couple['b'],
            'both_wnba': bool(couple.get('both_wnba')),
            'b_note': str(couple.get('b_note') or '').strip(),
            'status': status,
            'anchor': couple_anchor(couple),
            'slug_a': slugs.get(couple['a']),
            'slug_b': slugs.get(couple['b']),
            'photo_a': photos.get(couple['a']),
            'photo_b': photos.get(couple['b']),
            'chips': chips,
            'fields': fields,
        })
    return cards, dropped


def chip_text(card: dict, label: str) -> str:
    for name, text, _src in card['chips']:
        if name == label:
            return text
    return ''


def sentence(text: str) -> str:
    text = text.strip()
    if not text:
        return ''
    return text if text.endswith(('.', '!', '?')) else text + '.'


def faq_items(cards: list[dict]) -> list[tuple[str, str]]:
    def pair(a: str, b: str) -> dict | None:
        for card in cards:
            if card['a'] == a and card['b'] == b:
                return card
        return None

    married = [card for card in cards if card['status'] == 'Married']
    both = [card for card in married if card['both_wnba']]
    married_names = [f"{card['a']} and {card['b']}" for card in married]
    both_names = [f"{card['a']} and {card['b']}" for card in both]

    def join(names: list[str]) -> str:
        if not names:
            return ''
        if len(names) == 1:
            return names[0]
        return ', '.join(names[:-1]) + ', and ' + names[-1]

    paige = pair('Paige Bueckers', 'Azzi Fudd')
    paige_bits = ['Yes. Paige Bueckers and Azzi Fudd are dating.']
    if paige and chip_text(paige, 'Together since'):
        paige_bits.append('They went public in July 2025, when Bueckers named Fudd as her girlfriend in a WAG Talk interview.')
    if paige and chip_text(paige, 'Note'):
        paige_bits.append('Both spoke about the relationship in the 2026 docuseries The Dynasty: UConn Huskies.')

    aja = pair("A'ja Wilson", 'Bam Adebayo')
    aja_bits = ["Yes. A'ja Wilson and Bam Adebayo are dating."]
    if aja and chip_text(aja, 'How they met'):
        aja_bits.append('They met at the 2021 Tokyo Olympics.')
    if aja and chip_text(aja, 'Together since'):
        aja_bits.append('They have been together since 2021, and Wilson confirmed it publicly in February 2025.')

    married_nba = []
    dating_nba = []
    for card in cards:
        note = card['b_note']
        if 'nba' not in note.casefold():
            continue
        if note.startswith(('Former', 'Retired')):
            detail = 'a ' + note[0].lower() + note[1:]
        else:
            detail = 'a ' + note
        if card['status'] == 'Married':
            married_nba.append(f"{card['a']} is married to {card['b']}, {detail}.")
        else:
            dating_nba.append(f"{card['a']} is dating {card['b']}, {detail}. That relationship is not listed as a marriage.")
    nba_bits = married_nba + dating_nba
    if not any(card['status'] == 'Married' and 'nba' in card['b_note'].casefold() for card in cards):
        nba_bits.append('No marriage on this page is to a current NBA player.')

    clark = pair('Caitlin Clark', 'Connor McCaffery')
    clark_bits = []
    if clark:
        clark_bits.append('Caitlin Clark is dating Connor McCaffery, a former Iowa basketball player and former Butler assistant coach.')
        if chip_text(clark, 'How they met'):
            clark_bits.append('They met as Iowa Hawkeyes.')
        if chip_text(clark, 'Together since'):
            clark_bits.append('They have been together since April 2023.')

    sabrina = pair('Sabrina Ionescu', 'Hroniss Grasu')
    sabrina_bits = []
    if sabrina and sabrina['status'] == 'Married':
        sabrina_bits.append('Yes. Sabrina Ionescu is married to Hroniss Grasu, an NFL center.')
        if chip_text(sabrina, 'Together since'):
            sabrina_bits.append('They went public in 2021.')
        if chip_text(sabrina, 'Engaged'):
            sabrina_bits.append('They got engaged on January 20, 2023.')
        if chip_text(sabrina, 'Wedding'):
            sabrina_bits.append('They married on March 10, 2024, in California.')

    return [
        ('Which WNBA players are married?', f"These marriages are confirmed on this page: {join(married_names)}."),
        ('Which WNBA players are married to each other?', f"These married couples are both WNBA players: {join(both_names)}."),
        ('Are Paige Bueckers and Azzi Fudd dating?', ' '.join(paige_bits)),
        ("Is A'ja Wilson dating Bam Adebayo?", ' '.join(aja_bits)),
        ('Which WNBA players are married to NBA players?', ' '.join(nba_bits)),
        ('Who is Caitlin Clark dating?', ' '.join(clark_bits)),
        ('Is Sabrina Ionescu married?', ' '.join(sabrina_bits)),
    ]


def bubble(person: str, photo: dict | None) -> str:
    if not photo:
        return f'<span class="bubble initials" role="img" aria-label="{esc(person)}">{esc(initials(person))}</span>'
    return (
        f'<span class="bubble"><img src="{esc(photo["src"])}" alt="{esc(person)}" '
        f'width="{int(photo["width"])}" height="{int(photo["height"])}"></span>'
    )


def heart() -> str:
    return (
        '<span class="heart" aria-hidden="true">'
        '<svg viewBox="0 0 24 24" width="13" height="13"><path fill="#fff" '
        'd="M12 20.5s-6.4-4.1-8.9-7.8C1.2 10.2 1.5 6.8 4 5.4 6.2 4.2 8.4 4.9 12 8.1 15.6 4.9 17.8 4.2 20 5.4c2.5 1.4 2.8 4.8.9 7.3-2.5 3.7-8.9 7.8-8.9 7.8z"/></svg>'
        '</span>'
    )


def render_card(card: dict) -> str:
    badge = '<p class="badge">Both WNBA</p>' if card['both_wnba'] else ''
    role = f'<p class="role">{esc(card["b"])}: {esc(card["b_note"])}</p>' if card['b_note'] else ''
    chips = ''.join(
        f'<li><a href="{esc(src)}" target="_blank" rel="noopener"><span>{esc(label)}</span>{esc(text)}</a></li>'
        for label, text, src in card['chips']
    )
    return (
        f'<article class="couple-card" id="{esc(card["anchor"])}">'
        f'<div class="pair">{bubble(card["a"], card["photo_a"])}{heart()}{bubble(card["b"], card["photo_b"])}</div>'
        f'{badge}<h2>{person_link(card["a"], card["slug_a"])} and {person_link(card["b"], card["slug_b"])}</h2>'
        f'{role}<ul class="chips">{chips}</ul></article>'
    )


def render_credits(cards: list[dict]) -> str:
    rows = []
    seen = set()
    for card in cards:
        for person, photo in ((card['a'], card['photo_a']), (card['b'], card['photo_b'])):
            if not photo or person in seen:
                continue
            seen.add(person)
            license_bit = esc(photo['license'])
            if photo.get('license_url'):
                license_bit = f'<a href="{esc(photo["license_url"])}" target="_blank" rel="noopener">{license_bit}</a>'
            rows.append(
                f'<li>{esc(person)}: <a href="{esc(photo["page"])}" target="_blank" rel="noopener">{esc(photo["author"])}</a>, {license_bit}.</li>'
            )
    return '<section class="credits" id="photo-credits"><h2>Photo credits</h2><ul>' + ''.join(rows) + '</ul></section>'


def render_faq(items: list[tuple[str, str]]) -> str:
    blocks = ''.join(
        f'<div class="faq-item"><h3>{esc(question)}</h3><p>{esc(answer)}</p></div>'
        for question, answer in items
    )
    return f'<section class="faq" id="faq"><h2>Questions people ask</h2>{blocks}</section>'


def schema(cards: list[dict], items: list[tuple[str, str]]) -> str:
    graph = [
        {
            '@type': 'Article',
            'headline': 'WNBA couples',
            'description': 'Confirmed WNBA relationships, with a source for each fact. Splits and rumors are left out.',
            'dateModified': '2026-09-29',
            'datePublished': '2026-09-29',
            'inLanguage': 'en',
            'author': {'@type': 'Organization', 'name': 'Full Court Buckets'},
            'publisher': {'@type': 'Organization', 'name': 'Full Court Buckets', 'url': BASE + '/'},
            'mainEntityOfPage': BASE + PAGE_URL,
            'url': BASE + PAGE_URL,
        },
        {
            '@type': 'ItemList',
            'name': 'Confirmed WNBA couples',
            'numberOfItems': len(cards),
            'itemListElement': [
                {
                    '@type': 'ListItem',
                    'position': index,
                    'name': f"{card['a']} and {card['b']}",
                    'url': BASE + PAGE_URL + '#' + card['anchor'],
                }
                for index, card in enumerate(cards, start=1)
            ],
        },
        {
            '@type': 'BreadcrumbList',
            'itemListElement': [
                {'@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': BASE + '/'},
                {'@type': 'ListItem', 'position': 2, 'name': 'WNBA', 'item': BASE + '/wnba/'},
                {'@type': 'ListItem', 'position': 3, 'name': 'Couples', 'item': BASE + PAGE_URL},
            ],
        },
        {
            '@type': 'FAQPage',
            'mainEntity': [
                {
                    '@type': 'Question',
                    'name': question,
                    'acceptedAnswer': {'@type': 'Answer', 'text': answer},
                }
                for question, answer in items
            ],
        },
    ]
    payload = json.dumps({'@context': 'https://schema.org', '@graph': graph}, ensure_ascii=False)
    return payload.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')


def render_page(cards: list[dict], items: list[tuple[str, str]]) -> str:
    PAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not PAGE_PATH.is_file():
        PAGE_PATH.write_text('<!doctype html><html></html>', encoding='utf-8')
    menu = site_nav.build_menu(ROOT)
    nav = site_nav.render(menu, PAGE_URL)
    body = (
        '<div class="breadcrumbs"><a href="/">Home</a><span>/</span>'
        '<a href="/wnba/">WNBA</a><span>/</span><span>Couples</span></div>'
        '<section class="couples-intro"><p class="eyebrow">Full Court Buckets</p><h1>WNBA couples</h1>'
        '<p class="lede">Confirmed relationships of WNBA players. Each fact links to the article it came from.</p>'
        '<p class="rules">A relationship is included only when the players have confirmed it, or a major outlet reported it and quoted them. Splits and rumors are left out.</p>'
        f'<p class="checked">Last checked {CHECKED}.</p></section>'
        + ''.join(render_card(card) for card in cards)
        + '<section class="method" id="method"><h2>How this page was built</h2>'
        '<p>Empty fields are skipped. A chip stays only when its source URL still resolves. Photos are Wikimedia Commons files, after the license on the file page was checked. A partner without a photo is shown with initials. Both-WNBA couples come first.</p></section>'
        + render_faq(items)
        + render_credits(cards)
    )
    title = 'WNBA Couples | Full Court Buckets'
    description = 'Confirmed WNBA relationships, with a source for each fact. Splits and rumors are left out.'
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
{GA4_TAG}
{ADSENSE_TAG}
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><meta name="description" content="{esc(description)}"><meta name="robots" content="index,follow,max-image-preview:large"><link rel="canonical" href="{BASE}{PAGE_URL}"><link rel="icon" href="/favicon.svg"><meta property="og:type" content="article"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(description)}"><meta property="og:url" content="{BASE}{PAGE_URL}"><meta property="og:site_name" content="Full Court Buckets"><meta name="theme-color" content="#0c0c10"><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700;800;900&amp;family=Inter:wght@400;500;600;700;800&amp;display=swap" rel="stylesheet"><link rel="stylesheet" href="/wnba/assets/players.css"><link rel="stylesheet" href="/assets/site-nav.css"><style>{PAGE_CSS}</style><script type="application/ld+json">{schema(cards, items)}</script><script src="/assets/site-nav.js" defer></script></head><body><a class="skip" href="#content">Skip to content</a><div class="brand-line"></div><header class="site-header"><div class="wrap masthead"><a class="brand" href="/" aria-label="Full Court Buckets home"><img src="/logo.png" alt="Full Court Buckets" width="220" height="76"></a>{nav}</div></header><div class="tagline"><div class="wrap"><span>WNBA NEWS · ANALYSIS · COMMENTARY</span><span>Built by the WNBA community, for the WNBA community</span></div></div><main id="content" class="wrap">{body}</main>{site_nav.FOOTER_HTML}</body></html>'''


def patch_players(root: Path = ROOT) -> list[str]:
    slugs = load_slugs(root)
    touched = []
    seen = set()
    for couple in load_couples(root):
        for slug in (slugs.get(couple['a']), slugs.get(couple['b'])):
            if not slug or slug in seen:
                continue
            seen.add(slug)
            path = root / 'wnba' / slug / 'index.html'
            note = note_for_slug(root, slug)
            if not note or not path.is_file():
                continue
            original = path.read_text(encoding='utf-8')
            text = re.sub(r'<p class="relationship-note">.*?</p>', '', original)
            needle = '<div class="overview-strip">'
            if needle not in text:
                continue
            updated = text.replace(needle, note + needle, 1)
            if updated != original:
                path.write_text(updated, encoding='utf-8')
                touched.append(slug)
    return touched


def patch_hub(root: Path = ROOT) -> None:
    """Add the couples link under the player list. Never above the search box."""
    path = root / 'wnba' / 'index.html'
    if not path.is_file():
        return
    text = path.read_text(encoding='utf-8')
    if 'Confirmed WNBA relationships' in text:
        return
    link = '<p><a class="inline-link" href="/wnba/couples/">Confirmed WNBA relationships</a></p>'
    teams_end = '</ul><p><a class="inline-link" href="/wnba/teams/">All teams</a></p></section>'
    needle = '<p id="no-players" hidden>No players match your search.</p>'
    if teams_end in text:
        updated = text.replace(teams_end, teams_end + link, 1)
    elif needle in text:
        updated = text.replace(needle, needle + link, 1)
    else:
        return
    path.write_text(updated, encoding='utf-8')


def patch_sitemaps(root: Path = ROOT) -> None:
    block = (
        '  <url>\n'
        f'    <loc>{BASE}{PAGE_URL}</loc>\n'
        '    <lastmod>2026-09-29</lastmod>\n'
        '    <changefreq>weekly</changefreq>\n'
        '    <priority>0.7</priority>\n'
        '  </url>\n'
    )
    for name in ('sitemap.xml', 'pages-sitemap.xml'):
        path = root / name
        if not path.is_file():
            continue
        text = path.read_text(encoding='utf-8')
        if f'{BASE}{PAGE_URL}' in text:
            continue
        path.write_text(text.replace('</urlset>', block + '</urlset>', 1), encoding='utf-8')


def refresh_nav(root: Path = ROOT) -> int:
    menu = site_nav.build_menu(root)
    updates = site_nav.install_tree(root, menu, set())
    for relative, content in updates.items():
        (root / relative).write_text(content, encoding='utf-8')
    return len(updates)


def collect_sources(couples: list[dict]) -> list[str]:
    urls = []
    seen = set()
    for couple in couples:
        skip = OMIT.get((couple['a'], couple['b']), set())
        for key, _label in CHIP_FIELDS:
            if key in skip:
                continue
            text = str(couple.get(key) or '').strip()
            src = str(couple.get(key + '_src') or '').strip()
            if text and src and src not in seen:
                seen.add(src)
                urls.append(src)
    return urls


def main() -> None:
    couples = load_couples()
    live: dict[str, bool] = {}
    for url in collect_sources(couples):
        ok = source_resolves(url, live)
        print(('Source OK ' if ok else 'Source DEAD ') + url)
    photos, photo_drops = prepare_photos(couples)
    cards, chip_drops = build_cards(couples, photos, live)
    items = faq_items(cards)
    PAGE_PATH.write_text(render_page(cards, items), encoding='utf-8')
    players = patch_players()
    patch_hub()
    patch_sitemaps()
    changed = refresh_nav()
    page = PAGE_PATH.read_text(encoding='utf-8')
    if '\u2014' in page:
        raise SystemExit('Couples page contains an em dash.')
    print(f'Wrote {PAGE_PATH} with {len(cards)} couples and {len(photos)} photos.')
    print('Player notes:', ', '.join(players))
    print(f'Refreshed nav on {changed} pages.')
    print('Photo drops:', photo_drops or 'none')
    print('Chip drops:', chip_drops or 'none')


if __name__ == '__main__':
    main()
