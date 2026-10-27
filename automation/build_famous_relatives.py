#!/usr/bin/env python3
"""Build /news/wnba-players-famous-relatives/ from data/famous-relatives.json.

A standalone builder, modeled on build_couples.py. It reuses the news-article
chrome (byline, lead photo, article end, listings) through publish_articles and
internal_links without changing either one. Adding a pair means adding one row
to the data file, putting its photos in images/relatives/, and running:

    python automation/build_famous_relatives.py

Counts, the Updated line, the table, the CSV download, the FAQ answers and the
JSON-LD are all worked out from the data, so they cannot drift from each other.
"""
from __future__ import annotations

import csv
import html
import io
import json
import re
import shutil
import sys
from collections import Counter, OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'automation'))

import internal_links as links  # noqa: E402
import publish_articles as pa  # noqa: E402
import team_coverage  # noqa: E402

SLUG = 'wnba-players-famous-relatives'
DATA_PATH = ROOT / 'data' / 'famous-relatives.json'
PAGE_PATH = ROOT / 'news' / SLUG / 'index.html'
CSV_NAME = 'famous-relatives.csv'
CSV_PATH = ROOT / 'news' / SLUG / CSV_NAME
PHOTO_DIR = ROOT / 'images' / 'relatives'
HERO_DIR = ROOT / 'images' / 'articles' / SLUG
HERO_NAMES = ('photo.webp', 'photo.jpg', 'photo.jpeg', 'photo.png')


def hero_source(article: dict | None = None) -> Path:
    """The hero file that exists: the record's imageSource first, then photo.webp/.jpg/.jpeg/.png."""
    names = []
    if article and article.get('imageSource'):
        names.append(Path(str(article['imageSource'])).name)
    names += [n for n in HERO_NAMES if n not in names]
    for name in names:
        path = HERO_DIR / name
        if path.is_file():
            return path
    raise SystemExit(f'no hero photo in {HERO_DIR} (tried {", ".join(names)})')


PUBLISHED = '2026-10-19'
HEADLINE = "Steph Curry, Karl Malone and Donovan McNabb top our list of {relatives} WNBA players' famous relatives"
CATEGORY = 'WNBA'
HERO_ALT = 'Cameron Brink of the Los Angeles Sparks, left, and Stephen Curry of the Golden State Warriors'
FEATURED_TEAMS = ('atlanta-dream', 'golden-state-valkyries')
HERO_FOCAL = 'center 30%'
STYLE_ID = 'fcb-relatives-css'
SCRIPT_ID = 'fcb-relatives-sort'
SITE = links.BASE
CSV_FIELDS = (
    'rank', 'player', 'player_slug', 'team_2026', 'relative', 'relation', 'relation_type',
    'sport', 'known_for', 'source_urls', 'source_kinds', 'date_added',
)
DICTIONARY = (
    ('rank', 'Order on the page. Lower numbers are better-known relatives or more-searched pairs.'),
    ('player', 'The WNBA player, current or former.'),
    ('player_slug', 'The player\'s FCB profile, at fullcourtbuckets.com/wnba/<player_slug>/.'),
    ('team_2026', 'The player\'s team in FCB\'s 2026 player data. Blank when she is not on a 2026 roster.'),
    ('relative', 'The famous relative.'),
    ('relation', 'How the relative is related to the player, in the player\'s terms (her father, her cousin).'),
    ('relation_type', 'One of sibling, parent, grandparent, uncle/aunt, cousin, godfamily or spouse (current or former).'),
    ('sport', 'Where the relative made their name.'),
    ('known_for', 'The verified one-line reason the relative is notable.'),
    ('source_urls', 'Every source for the row, separated by a space.'),
    ('source_kinds', 'primary (an official team, league, school, Olympic or government record) or report (a news report, used only when no primary record was found), one per URL.'),
    ('date_added', 'The day the row was added (YYYY-MM-DD).'),
)
PAGE_CSS = (
    '.fr-updated{margin:0 0 18px;color:#a29f99;font-size:14px;font-weight:600}'
    '.fr-updated strong{color:#f5f3ef}'
    '.fr-table th button{all:unset;cursor:pointer;display:inline-flex;align-items:center;gap:4px;min-height:32px}'
    '.fr-table th button:focus-visible{outline:2px solid #ff9800;outline-offset:2px}'
    '.fr-table th[aria-sort="ascending"] button:after{content:"\\25B2";font-size:10px}'
    '.fr-table th[aria-sort="descending"] button:after{content:"\\25BC";font-size:10px}'
    '.fr-table td{vertical-align:top}'
    '.fr-table td.fr-src{white-space:normal;min-width:140px}'
    '.fr-kind{display:inline-block;margin-left:4px;font-size:11px;line-height:1;padding:2px 5px;border:1px solid #d6d1c8;border-radius:3px;color:#6b665e;text-transform:uppercase;letter-spacing:.03em;vertical-align:1px}'
    '.fr-dot{color:#9a958c}'
    '.fr-who{display:inline-flex;align-items:center;gap:8px}'
    '.fr-table .fr-head{flex:0 0 32px;width:32px!important;height:32px!important;max-width:none!important;margin:0!important;border-radius:50%;object-fit:cover;background:#ece8e1;border:1px solid #e0dbd2}'
    '.fr-init{display:inline-flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;color:#5b4a8a;box-sizing:border-box}'
    '@media (max-width:600px){.fr-table .fr-head{flex-basis:26px;width:26px!important;height:26px!important}.fr-init{font-size:10px}}'
    '.fr-counts{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin:0 0 18px}'
    '.fr-counts table{width:100%}'
    '.fr-sources{font-size:13px;color:#a29f99;margin:6px 0 0}'
    '.fr-dict dt{font-weight:800;margin-top:8px}'
    '.fr-dict dd{margin:2px 0 0;color:#d0ccc6}'
    '.fr-download{display:inline-block;margin:4px 0 12px;padding:10px 14px;border:1px solid #ff9800;'
    'color:#f5f3ef;font-weight:800;text-decoration:none}'
    '.fr-faq h3{margin:18px 0 6px;font:800 20px/1.2 Barlow,sans-serif}'
)
SORT_JS = (
    "(function(){var t=document.getElementById('fr-table');if(!t)return;"
    "var heads=t.querySelectorAll('thead th');"
    "heads.forEach(function(th,i){var b=th.querySelector('button');if(!b)return;"
    "b.addEventListener('click',function(){"
    "var dir=th.getAttribute('aria-sort')==='ascending'?'descending':'ascending';"
    "heads.forEach(function(h){h.removeAttribute('aria-sort');});th.setAttribute('aria-sort',dir);"
    "var body=t.tBodies[0];var rows=Array.prototype.slice.call(body.rows);"
    "rows.sort(function(a,b){var x=a.cells[i].getAttribute('data-sort')||a.cells[i].textContent.trim();"
    "var y=b.cells[i].getAttribute('data-sort')||b.cells[i].textContent.trim();"
    "var nx=parseFloat(x),ny=parseFloat(y);var c=(!isNaN(nx)&&!isNaN(ny))?nx-ny:x.localeCompare(y);"
    "return dir==='ascending'?c:-c;});rows.forEach(function(r){body.appendChild(r);});});});})();"
)


def esc(text) -> str:
    return html.escape(str(text), quote=True)


def ext(label: str, href: str) -> str:
    if href.startswith('/') and not href.startswith('//'):
        return f'<a class="inline-link" href="{esc(href)}">{esc(label)}</a>'
    return f'<a class="inline-link" href="{esc(href)}" target="_blank" rel="noopener">{esc(label)}</a>'


def human_date(iso: str) -> str:
    return links._format_date(iso)


def load() -> dict:
    return json.loads(DATA_PATH.read_text(encoding='utf-8'))


def team_for(player_slug: str) -> tuple[str | None, str | None]:
    """2026 team from FCB player data, with its team-page slug. None when not on a roster."""
    path = ROOT / 'data' / 'wnba' / 'players' / f'{player_slug}.json'
    if not path.is_file():
        return None, None
    team = json.loads(path.read_text(encoding='utf-8')).get('current_team')
    name = team.get('full_name') if isinstance(team, dict) else None
    if not name:
        return None, None
    slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    if not (ROOT / 'wnba' / 'teams' / slug / 'index.html').is_file():
        return name, None
    return name, slug


def has_page(slug: str) -> bool:
    return (ROOT / 'wnba' / slug / 'index.html').is_file()


def validate(doc: dict) -> list[dict]:
    entries = sorted(doc['entries'], key=lambda e: e['rank'])
    ranks = [e['rank'] for e in entries]
    if ranks != list(range(1, len(entries) + 1)):
        raise SystemExit('ranks must run 1..N with no gaps')
    seen = set()
    for e in entries:
        key = (e['player_slug'], e['relative_slug'])
        if key in seen:
            raise SystemExit(f'duplicate pair {key}')
        seen.add(key)
        for field in ('player', 'player_slug', 'relative', 'relative_slug', 'relation', 'relation_type', 'sport', 'known_for', 'sources', 'date_added'):
            if not e.get(field):
                raise SystemExit(f'{key}: missing {field}')
        if not has_page(e['player_slug']):
            raise SystemExit(f'{key}: no FCB player page at /wnba/{e["player_slug"]}/')
        for src in e['sources']:
            if src.get('kind') not in ('primary', 'report') or not str(src.get('url', '')).startswith('http'):
                raise SystemExit(f'{key}: bad source {src}')
            if 'wikipedia.org' in src['url']:
                raise SystemExit(f'{key}: Wikipedia is not a source')
        if not any(src['kind'] == 'primary' for src in e['sources']) and not any(src['kind'] == 'report' for src in e['sources']):
            raise SystemExit(f'{key}: needs a source')
        for side in ('photo_player', 'photo_relative'):
            photo = e.get(side)
            if photo:
                if photo.get('file') and not (ROOT / photo['file'].lstrip('/')).is_file():
                    raise SystemExit(f'{key}: missing {photo["file"]}')
                for field in ('author', 'license', 'source_page'):
                    if not photo.get(field):
                        raise SystemExit(f'{key}: {side} missing {field}')
        team, team_slug = team_for(e['player_slug'])
        e['_team'], e['_team_slug'] = team, team_slug
    return entries


def stats(entries: list[dict]) -> dict:
    players = OrderedDict()
    for e in entries:
        players.setdefault(e['player_slug'], e)
    sport_key = lambda e: e['sport'].split(' (')[0]  # noqa: E731
    on_roster = {e['player_slug'] for e in entries if e['_team']}
    teams = Counter()
    for slug in on_roster:
        teams[players[slug]['_team']] += 1
    return {
        'players': len(players),
        'relatives': len(entries),
        'by_relation': Counter(e['relation_type'] for e in entries),
        'by_sport': Counter(sport_key(e) for e in entries),
        'by_team': teams,
        'on_roster': len(on_roster),
        'primary_rows': sum(1 for e in entries if all(s['kind'] == 'primary' for s in e['sources'])),
        'with_report': sum(1 for e in entries if any(s['kind'] == 'report' for s in e['sources'])),
        'photo_pairs': sum(1 for e in entries if e.get('photo_player') and e.get('photo_relative')),
        'wnba_families': sum(1 for e in entries if e['sport'] == 'WNBA' and e['relation_type'] != 'spouse'),
        'spouses': sum(1 for e in entries if e['relation_type'] == 'spouse'),
        'wnba_spouses': sum(1 for e in entries if e['relation_type'] == 'spouse' and e['sport'] == 'WNBA'),
    }


RELATION_LABEL = OrderedDict((
    ('sibling', 'Siblings'), ('parent', 'Parents'), ('grandparent', 'Grandparents'),
    ('uncle/aunt', 'Uncles and aunts'), ('cousin', 'Cousins'), ('godfamily', 'Godfamily'),
    ('spouse', 'Spouses'),
))


def player_link(e: dict) -> str:
    return ext(e['player'], f'/wnba/{e["player_slug"]}/')


def relative_name_html(e: dict) -> str:
    if has_page(e['relative_slug']):
        return ext(e['relative'], f'/wnba/{e["relative_slug"]}/')
    return esc(e['relative'])


def relative_html(e: dict) -> str:
    return f'<span class="fr-who">{relative_head_html(e)}{relative_name_html(e)}</span>'


def team_html(e: dict) -> str:
    if e['_team'] and e['_team_slug']:
        return ext(e['_team'], f'/wnba/teams/{e["_team_slug"]}/')
    if e['_team']:
        return esc(e['_team'])
    return 'Not on a 2026 roster'


def sources_html(e: dict) -> str:
    parts = []
    for src in e['sources']:
        label = src['label'] + (' (report)' if src['kind'] == 'report' else '')
        parts.append(ext(label, src['url']))
    return '; '.join(parts)


SHORT_SOURCE = {
    'Big 12 Conference': 'Big 12', 'University of Maryland': 'Maryland', 'Canadian Olympic Committee': 'Team Canada',
    'Daily Emerald (University of Oregon student paper)': 'Daily Emerald', 'National Football Foundation': 'NFF',
    'Nashville Metro Council resolution R98-1304 honoring the Nashville Noise': 'Nashville Metro Council',
    'Sport Australia Hall of Fame': 'Sport Australia HOF', 'Candace Parker official site': 'CandaceParker.com',
    'Milwaukee Bucks': 'Milwaukee Bucks', 'Team USA': 'Team USA', 'WNBA.com 2009 transactions (archived)': 'WNBA.com',
}


def short_source(label: str) -> str:
    """Publisher-only link text, e.g. 'Stanford Athletics bio: Cameron Brink' -> 'Stanford'."""
    head = label.split(':')[0].split(',')[0].strip()
    if head in SHORT_SOURCE:
        return SHORT_SOURCE[head]
    head = re.sub(r'\s+(bio|release|feature|report|profile|player record|athlete record|game summary|draft profile|Q&A|transactions|inaugural draft results|press room bio|Press Room bio)\b.*$', '', head, flags=re.I).strip()
    head = re.sub(r'^(.*?) Athletics$', r'\1', head)
    return SHORT_SOURCE.get(head, head)


def source_cell(e: dict) -> str:
    parts, seen = [], {}
    for src in e['sources']:
        name = short_source(src['label'])
        seen[name] = seen.get(name, 0) + 1
        if seen[name] > 1:
            name = f'{name} ({seen[name]})'
        tag = '<span class="fr-kind">report</span>' if src['kind'] == 'report' else ''
        parts.append(f'<a class="inline-link" href="{esc(src["url"])}" target="_blank" rel="noopener" title="{esc(src["label"])}">{esc(name)}</a>{tag}')
    return ' <span class="fr-dot" aria-hidden="true">\u00b7</span> '.join(parts)


def initials(name: str) -> str:
    bits = [b for b in re.split(r'[\s-]+', name) if b and b[0].isalpha()]
    return (bits[0][0] + bits[-1][0]).upper() if len(bits) > 1 else bits[0][:2].upper()


# Table-only headshot credits for relatives without a composite photo record.
TABLE_ONLY_RELATIVE_PHOTOS = {
    'antonio-davis': {'author': 'Lordcolus (derivative work: Lpdrew)', 'license': 'CC BY 2.0',
                      'license_url': 'https://creativecommons.org/licenses/by/2.0', 'source_page': 'https://commons.wikimedia.org/wiki/File:Antonio_Davis.jpg'},
    'joe-salavea': {'author': 'Office of U.S. Congressman Eni Faleomavaega of American Samoa', 'license': 'Public domain',
                    'license_url': None, 'source_page': 'https://commons.wikimedia.org/wiki/File:Joe_Salave%27a.jpg'},
}


def relative_photo(e: dict):
    return e.get('photo_relative') or TABLE_ONLY_RELATIVE_PHOTOS.get(e['relative_slug'])


def relative_head_html(e: dict) -> str:
    src = f'/images/relatives/heads/relatives/{e["relative_slug"]}.webp'
    if relative_photo(e) and (ROOT / src.lstrip('/')).is_file():
        return f'<img class="fr-head" src="{src}" alt="" width="32" height="32" loading="lazy" decoding="async">'
    return f'<span class="fr-head fr-init" aria-hidden="true">{esc(initials(e["relative"]))}</span>'


def head_html(e: dict) -> str:
    src = f'/images/relatives/heads/{e["player_slug"]}.webp'
    if (ROOT / src.lstrip('/')).is_file():
        return f'<img class="fr-head" src="{src}" alt="" width="32" height="32" loading="lazy" decoding="async">'
    return f'<span class="fr-head fr-init" aria-hidden="true">{esc(initials(e["player"]))}</span>'


def credit(photo: dict) -> str:
    lic = re.sub(r' (at|de|fr|nl|es|it|us)$', lambda m: ' ' + m.group(1).upper(), photo['license'])
    lic_html = ext(lic, photo['license_url']) if photo.get('license_url') else esc(lic)
    return f'{esc(photo["author"])}, {lic_html}, via {ext("Wikimedia Commons", photo["source_page"])}'


def figure(src: str, alt: str, caption: str) -> str:
    return (
        '<figure class="body-photo"><picture>'
        f'<source srcset="{esc(src)}" type="image/webp">'
        f'<img src="{esc(src)}" alt="{esc(alt)}" style="object-position:center 20%" width="1600" height="900" decoding="async" loading="lazy">'
        f'</picture><figcaption>{caption}</figcaption></figure>'
    )


def entry_figure(e: dict) -> str:
    pp, rp = e.get('photo_player'), e.get('photo_relative')
    if pp and rp:
        src = f'/images/relatives/{e["player_slug"]}--{e["relative_slug"]}.webp'
        if not (ROOT / src.lstrip('/')).is_file():
            raise SystemExit(f'missing composite {src}')
        alt = f'{e["player"]}, left, and {e["relative"]}'
        cap = f'{esc(e["player"])} (left) and {esc(e["relative"].rstrip("."))}. Photos: {credit(pp)}; {credit(rp)}.'
        return figure(src, alt, cap)
    return ''


def player_figure(e: dict) -> str:
    pp = e.get('photo_player')
    if not pp:
        return ''
    src = pp['file']
    return figure(src, e['player'], f'{esc(e["player"])}. Photo: {credit(pp)}.')


def table_html(entries: list[dict]) -> str:
    heads = ('#', 'WNBA player', '2026 team', 'Relative', 'Relation', 'Sport', 'Sources')
    head = ''.join(f'<th scope="col"><button type="button">{esc(h)}</button></th>' for h in heads)
    rows = []
    for e in entries:
        rows.append(
            '<tr>'
            f'<td data-sort="{e["rank"]}">{e["rank"]}</td>'
            f'<td data-sort="{esc(e["player"])}"><span class="fr-who">{head_html(e)}{player_link(e)}</span></td>'
            f'<td data-sort="{esc(e["_team"] or "zzz")}">{team_html(e)}</td>'
            f'<td>{relative_html(e)}</td>'
            f'<td>{esc(e["relation"])}</td>'
            f'<td>{esc(e["sport"])}</td>'
            f'<td class="fr-src">{source_cell(e)}</td>'
            '</tr>'
        )
    return f'<div class="table-wrap"><table id="fr-table" class="fr-table"><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def count_table(title: str, rows: list[tuple[str, int]]) -> str:
    body = ''.join(f'<tr><td>{label}</td><td>{n}</td></tr>' for label, n in rows)
    return f'<div class="table-wrap"><table><thead><tr><th scope="col">{esc(title)}</th><th scope="col">Relatives</th></tr></thead><tbody>{body}</tbody></table></div>'


def pct(n: int, total: int) -> str:
    return f'{round(100 * n / total)}%'


def faq_items(entries: list[dict], s: dict, updated: str) -> list[tuple[str, str]]:
    by = {(e['player_slug'], e['relative_slug']): e for e in entries}

    def item(key, question, answer):
        if key in by:
            return (question, answer(by[key]))
        return None

    items = [
        ('How many WNBA players have famous relatives?',
         f'Full Court Buckets has verified {s["relatives"]} famous relatives of {s["players"]} current and former WNBA players as of {human_date(updated)}. '
         f'Siblings are the most common tie ({s["by_relation"]["sibling"]}), and the NBA is the most common sport ({s["by_sport"]["NBA"]}). The list grows as new family ties are confirmed.'),
        item(('angel-reese', 'julian-reese'), "Who is Angel Reese's brother?",
             lambda e: f'Julian Reese, her younger brother. {e["known_for"]}'),
        item(('cameron-brink', 'stephen-curry'), 'Is Cameron Brink related to Steph Curry?',
             lambda e: e['extra']),
        item(('gabriela-jaquez', 'jaime-jaquez-jr'), "Who is Gabriela Jaquez's brother?",
             lambda e: f'Jaime Jaquez Jr., her older brother. {e["known_for"]}'),
        item(('flaujae-johnson', 'camoflauge'), "Who is Flau'jae Johnson's dad?",
             lambda e: f'Jason Johnson, the rapper known as Camoflauge. {e["known_for"]}'),
        item(('satou-sabally', 'nyara-sabally'), 'Who are the Sabally sisters?',
             lambda e: f'Satou Sabally and her younger sister, Nyara Sabally. {e["known_for"]} {e["extra"]}'),
        item(('candace-parker', 'anthony-parker'), "Who is Candace Parker's brother?",
             lambda e: f'Anthony Parker, her older brother. {e["known_for"]}'),
        item(('angel-reese', 'jordan-hawkins'), 'Is Jordan Hawkins related to Angel Reese?',
             lambda e: f'Yes. They are cousins. {e["known_for"]}'),
        item(('veronica-burton', 'ron-burton'), "Who is Veronica Burton's grandfather?",
             lambda e: f'Ron Burton. {e["known_for"]}'),
        item(('lexie-brown', 'dee-brown'), "Who is Lexie Brown's dad?",
             lambda e: f'Dee Brown. {e["known_for"]}'),
        item(('breanna-stewart', 'marta-xargay'), "Who is Breanna Stewart's wife?",
             lambda e: f'Marta Xargay. {e["known_for"]} {e["extra"]}'),
        item(('diana-taurasi', 'penny-taylor'), "Who is Diana Taurasi's wife?",
             lambda e: f'Penny Taylor. {e["known_for"]} {e["extra"]}'),
    ]
    return [i for i in items if i]


def entries_html(entries: list[dict]) -> str:
    groups = OrderedDict()
    for e in entries:
        groups.setdefault(e['player_slug'], []).append(e)
    out = []
    for slug, es in groups.items():
        e0 = es[0]
        names = [e['relative'] for e in es]
        joined = names[0] if len(names) == 1 else ', '.join(names[:-1]) + ' and ' + names[-1]
        heading = f'{e0["player"]} and {joined}' if len(names) == 1 else f'{e0["player"]}: {joined}'
        out.append(f'<h2 class="section-title" id="{esc(slug)}">{esc(heading)}</h2>')
        team = f', {team_html(e0)}' if e0['_team'] else ''
        out.append(f'<p class="fr-sources">{player_link(e0)}{team}</p>')
        shown_player = False
        for e in es:
            fig = '' if e['rank'] == 1 else entry_figure(e)
            if e['rank'] == 1:
                shown_player = True
            if not fig and not shown_player:
                fig = player_figure(e)
                shown_player = bool(fig)
            elif fig:
                shown_player = True
            if fig:
                out.append(fig)
            text = f'<strong>{esc(e["relative"])}, {esc(e["relation"].lower())}.</strong> {esc(e["known_for"])}'
            if e.get('extra'):
                text += ' ' + esc(e['extra'])
            out.append(f'<p>{text}</p>')
            out.append(f'<p class="fr-sources">Sources: {sources_html(e)}</p>')
    return '\n'.join(out)


def all_sources(entries: list[dict]) -> str:
    seen = OrderedDict()
    for e in entries:
        for src in e['sources']:
            seen.setdefault(src['url'], src)
    primary = [s for s in seen.values() if s['kind'] == 'primary']
    reports = [s for s in seen.values() if s['kind'] == 'report']
    li = lambda s: f'<li>{ext(s["label"], s["url"])}</li>'  # noqa: E731
    return (
        f'<p>Primary records: official team, league, school, Olympic, hall of fame and government pages ({len(primary)}).</p>'
        f'<ul>{"".join(li(s) for s in primary)}</ul>'
        f'<p>News reports, used only where we found no primary record ({len(reports)}):</p>'
        f'<ul>{"".join(li(s) for s in reports)}</ul>'
        '<p>2026 teams come from Full Court Buckets player data.</p>'
        + head_credits(entries)
    )


def head_credits(entries: list[dict]) -> str:
    seen, items, missing = set(), [], []
    for e in entries:
        if e['player_slug'] in seen:
            continue
        seen.add(e['player_slug'])
        if (ROOT / 'images' / 'relatives' / 'heads' / f'{e["player_slug"]}.webp').is_file() and e.get('photo_player'):
            items.append(f'<li>{esc(e["player"])}: {credit(e["photo_player"])}</li>')
        else:
            missing.append(esc(e['player']))
    out = f'<p id="table-photo-credits">Table headshots, cropped from licensed photos ({len(items)}):</p><ul>{"".join(items)}</ul>'
    if missing:
        out += f'<p>Initials are shown for players with no licensed photo we could find: {", ".join(missing)}.</p>'
    rseen, ritems, rmissing = set(), [], []
    for e in entries:
        if e['relative_slug'] in rseen:
            continue
        rseen.add(e['relative_slug'])
        if relative_photo(e) and (ROOT / 'images' / 'relatives' / 'heads' / 'relatives' / f'{e["relative_slug"]}.webp').is_file():
            ritems.append(f'<li>{esc(e["relative"])}: {credit(relative_photo(e))}</li>')
        else:
            rmissing.append(esc(e['relative']))
    out += f'<p>Relatives ({len(ritems)}):</p><ul>{"".join(ritems)}</ul>'
    if rmissing:
        out += f'<p>Initials are shown for relatives with no licensed photo we could find: {", ".join(rmissing)}.</p>'
    return out


def body(doc: dict, entries: list[dict], s: dict) -> str:
    updated = doc['updated']
    total = s['relatives']
    by_e = {(e['player_slug'], e['relative_slug']): e for e in entries}
    lead = (
        'Steph Curry is Cameron Brink\'s godbrother, Karl Malone is Cheryl Ford\'s father, Donovan McNabb is Kia Nurse\'s uncle by marriage, and JaVale McGee is '
        'Imani McGee-Stafford\'s older half-brother. Angel Reese\'s younger brother, Julian, signed with the New Orleans Pelicans on Sept. 24, 2026. '
        f'Full Court Buckets has checked {total} famous relatives of {s["players"]} current and former WNBA players against team, league and school records. '
        f'The NBA accounts for {s["by_sport"]["NBA"]} of them, and {s["on_roster"]} of the players are on 2026 rosters.'
    )
    parts = [f'<p class="lead">{esc(lead)}</p>']
    parts.append(
        f'<p class="fr-updated"><strong>Updated {esc(human_date(updated))}</strong> &middot; {s["players"]} WNBA players &middot; '
        f'{total} famous relatives &middot; New family ties are added as they are verified.</p>'
    )
    finals = [t for t in ('Atlanta Dream', 'Golden State Valkyries') if s['by_team'].get(t)]
    if finals:
        n = sum(s['by_team'][t] for t in finals)
        parts.append(
            f'<p>The two 2026 WNBA Finals teams have {n} of the players: '
            f'{s["by_team"].get("Atlanta Dream", 0)} with the {ext("Atlanta Dream", "/wnba/teams/atlanta-dream/")} and '
            f'{s["by_team"].get("Golden State Valkyries", 0)} with the {ext("Golden State Valkyries", "/wnba/teams/golden-state-valkyries/")}.</p>'
        )
    parts.append('<h2 class="section-title" id="list">All famous relatives of WNBA players</h2>')
    parts.append('<p>Tap a column heading to sort. Sources are primary unless marked report.</p>')
    parts.append(table_html(entries))
    parts.append(f'<p><a class="fr-download" href="{CSV_NAME}" download>Download the data (CSV)</a></p>')
    rel = s['by_relation']
    sport = s['by_sport']
    parts.append('<h2 class="section-title" id="numbers">By the numbers</h2>')
    parts.append('<p>This count is Full Court Buckets\' own. Every row was checked against an official record or, where none exists, a labeled news report.</p>')
    parts.append('<ul>'
        f'<li><strong>NBA is the most common link:</strong> {sport["NBA"]} of {total} relatives ({pct(sport["NBA"], total)}).</li>'
        f'<li><strong>Siblings lead the relations:</strong> {rel["sibling"]} siblings and {rel["parent"]} parents.</li>'
        f'<li><strong>WNBA families:</strong> {s["wnba_families"]} relatives also played in the WNBA, so the league has its own families: the Sabally, Ogwumike, Samuelson, Jones and Paris sisters, Bonner and McCall, and Pamela McGee and her daughter.</li>'
        + (f'<li><strong>Spouses:</strong> {s["spouses"]} spouses are notable in their own right, {s["wnba_spouses"]} of them WNBA players. '
           'Only spouses with a public career and an official team, league or school record of the marriage are listed. Private spouses are left out.</li>' if s.get('spouses') else '')
        + f'<li><strong>Primary records:</strong> {s["primary_rows"]} of {total} rows rest only on official records. The other {s["with_report"]} also cite a news report, labeled as one.</li>'
        f'<li><strong>Photos:</strong> {s["photo_pairs"]} pairs have freely licensed photos of both people.</li>'
        '</ul>')
    rel_rows = [(label, rel[key]) for key, label in RELATION_LABEL.items() if rel.get(key)]
    sport_rows = sorted(sport.items(), key=lambda kv: (-kv[1], kv[0]))
    team_rows = sorted(s['by_team'].items(), key=lambda kv: (-kv[1], kv[0]))
    team_body = ''.join(
        f'<tr><td>{ext(t, "/wnba/teams/" + re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-") + "/")}</td><td>{n}</td></tr>' for t, n in team_rows
    )
    parts.append('<div class="fr-counts">'
        + count_table('Relation', [(esc(l), n) for l, n in rel_rows])
        + count_table('Sport', [(esc(l), n) for l, n in sport_rows])
        + f'<div class="table-wrap"><table><thead><tr><th scope="col">2026 team</th><th scope="col">Players</th></tr></thead><tbody>{team_body}</tbody></table></div>'
        + '</div>')
    parts.append(entries_html(entries))
    parts.append('<h2 class="section-title" id="faq">Frequently asked questions</h2>')
    faq = faq_items(entries, s, updated)
    parts.append('<div class="fr-faq">' + ''.join(f'<h3>{esc(q)}</h3><p>{esc(a)}</p>' for q, a in faq) + '</div>')
    parts.append('<h2 class="section-title" id="data">Download the data</h2>')
    parts.append(
        f'<p>The full list is a free CSV, one row per player and relative: <a class="fr-download" href="{CSV_NAME}" download>Download famous-relatives.csv</a>. '
        'The data is free to use.</p>'
    )
    parts.append('<dl class="fr-dict">' + ''.join(f'<dt>{esc(k)}</dt><dd>{esc(v)}</dd>' for k, v in DICTIONARY) + '</dl>')
    parts.append(f'<p>Spot an error or know a relative we missed? Email <a href="mailto:{esc(doc["corrections"])}">{esc(doc["corrections"])}</a> with a link to an official record. Each fix is dated.</p>')
    parts.append('<h2 class="section-title">Sources</h2>')
    parts.append(all_sources(entries))
    parts.append('<p>Photos are from Wikimedia Commons under the license named in each caption. A pair shows only the player when we found no freely licensed photo of the relative.</p>')
    return '\n'.join(parts), faq


def write_csv(entries: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator='\n')
    writer.writerow(CSV_FIELDS)
    for e in entries:
        writer.writerow([
            e['rank'], e['player'], e['player_slug'], e['_team'] or '', e['relative'], e['relation'], e['relation_type'],
            e['sport'], e['known_for'], ' '.join(s['url'] for s in e['sources']), ' '.join(s['kind'] for s in e['sources']), e['date_added'],
        ])
    return buf.getvalue()


def extra_jsonld(entries: list[dict], faq: list[tuple[str, str]], title: str) -> str:
    canonical = f'{SITE}/news/{SLUG}/'
    elements = []
    for e in entries:
        rel_type = e['relation_type']
        relative = {'@type': 'Person', 'name': e['relative']}
        if has_page(e['relative_slug']):
            relative['url'] = f'{SITE}/wnba/{e["relative_slug"]}/'
        person = {'@type': 'Person', 'name': e['player'], 'url': f'{SITE}/wnba/{e["player_slug"]}/'}
        if rel_type == 'sibling':
            person['sibling'] = relative
        elif rel_type == 'parent':
            person['parent'] = relative
        elif rel_type == 'spouse' and not e['relation'].lower().startswith('former'):
            person['spouse'] = relative
        else:
            person['relatedTo'] = relative
        elements.append({'@type': 'ListItem', 'position': e['rank'], 'item': person})
    item_list = {
        '@context': 'https://schema.org', '@type': 'ItemList',
        'name': 'Famous relatives of WNBA players', 'url': canonical,
        'numberOfItems': len(entries), 'itemListElement': elements,
    }
    faq_page = {
        '@context': 'https://schema.org', '@type': 'FAQPage',
        'mainEntity': [{'@type': 'Question', 'name': q, 'acceptedAnswer': {'@type': 'Answer', 'text': a}} for q, a in faq],
    }
    dataset = {
        '@context': 'https://schema.org', '@type': 'Dataset',
        'name': 'Famous relatives of WNBA players', 'url': canonical,
        'description': 'One row per WNBA player and famous relative, with the relation, sport and the primary record behind each row.',
        'creator': {'@type': 'Organization', 'name': 'Full Court Buckets', 'url': SITE + '/'},
        'distribution': [{'@type': 'DataDownload', 'encodingFormat': 'text/csv', 'contentUrl': canonical + CSV_NAME}],
    }
    return ''.join(f'<script type="application/ld+json" data-fr="1">{json.dumps(x, ensure_ascii=False)}</script>' for x in (item_list, faq_page, dataset))


def install_extras(page: str, ld: str) -> str:
    page = re.sub(r'<script type="application/ld\+json" data-fr="1">.*?</script>', '', page, flags=re.S)
    page = re.sub(rf'<style id="{STYLE_ID}">.*?</style>', '', page, flags=re.S)
    page = re.sub(rf'<script id="{SCRIPT_ID}">.*?</script>', '', page, flags=re.S)
    page = page.replace('</head>', f'<style id="{STYLE_ID}">{PAGE_CSS}</style>{ld}</head>', 1)
    page = page.replace('</body>', f'<script id="{SCRIPT_ID}">{SORT_JS}</script></body>', 1)
    return page


def render(doc: dict, entries: list[dict], s: dict, article: dict, articles: list) -> str:
    title = article['title']
    body_html, faq = body(doc, entries, s)
    meta = {'photo_credit': article['imageCredit'], 'photo_credit_url': doc['hero']['source_page'], 'license_url': doc['hero']['license_url']}
    if PAGE_PATH.is_file():
        page = PAGE_PATH.read_text(encoding='utf-8')
    else:
        page = pa.SHELL_PAGE.read_text(encoding='utf-8').replace('dream-valkyries-finals-game-1-recap', SLUG)
    how = f'<p class="how-made">{links.HOW_MADE_OTHER} {links.HOW_MADE_LINK}</p>'
    hero = re.sub(r'<figcaption>.*?</figcaption>', lambda _: f'<figcaption>{doc["hero"]["caption_html"]}</figcaption>', pa.figure_html(article, meta), count=1, flags=re.S)
    article_html = (
        '<article class="article">'
        f'<div class="meta-row"><span class="cat">{esc(article["category"])}</span>'
        '<span class="divider"></span><span>Full Court Buckets</span></div>'
        f'<h1>{esc(title)}</h1>'
        f'<div class="byline-row">{links.BYLINE_HTML}'
        f'<time class="article-date" datetime="{esc(article["date"])}">{esc(human_date(article["date"]))}</time></div>'
        f'{hero}{body_html}{how}'
        '<p class="brand-sign">Full Court Buckets &middot; WNBA News. Analysis. Commentary.</p>'
        '</article>'
    )
    page = re.sub(r'<article class="article">.*?</article>', lambda _: article_html, page, count=1, flags=re.S)
    page = links.ensure_article_end(page, ROOT, article, articles)
    page = pa.set_title(page, title, title, article['description'], article)
    page = re.sub(r'(<div class="ticker-text">)(.*?)(</div>)', lambda m: m.group(1) + 'WNBA news, analysis and commentary.' + m.group(3), page, count=1, flags=re.S)
    page = re.sub(
        r'(<nav class="breadcrumbs"[^>]*>.*)(<span>)(.*?)(</span></nav>)',
        lambda m: m.group(1) + m.group(2) + esc(title) + m.group(4), page, count=1, flags=re.S,
    )
    page = install_extras(page, extra_jsonld(entries, faq, title))
    return page


def record(doc: dict, s: dict, existing: dict | None) -> dict:
    title = HEADLINE.format(relatives=s['relatives'])
    article = dict(existing or {})
    # Tag only the Finals teams the story features. The other clubs' pages keep
    # their league-story fallback, which test_thin_content expects.
    teams = sorted({e['_team_slug'] for e in doc['_entries'] if e['_team_slug'] in FEATURED_TEAMS})
    article.update({
        'slug': SLUG,
        'url': f'/news/{SLUG}/',
        'title': title,
        'description': (
            f"Steph Curry, Karl Malone, Donovan McNabb and Angel Reese's NBA brother lead {s['relatives']} famous relatives "
            f"of {s['players']} WNBA players, each checked against official records. Updated {human_date(doc['updated'])}."
        ),
        'category': CATEGORY,
        'date': PUBLISHED,
        'imageAlt': HERO_ALT,
        'imageCredit': doc['hero']['credit'],
        'teams': teams,
        'imageFocal': HERO_FOCAL,
    })
    if doc['updated'] != PUBLISHED:
        article['dateModified'] = doc['updated']
    return article


def refresh_team_stories() -> None:
    """Team pages list this story the same way the team builder does, then team coverage refreshes."""
    import team_season

    pattern = re.compile(r'<section class="section" id="team-news">.*?</section>', re.S)
    for page in sorted((ROOT / 'wnba' / 'teams').glob('*/index.html')):
        slot = links._slot_for_slug(ROOT, page.parent.name)
        expected = team_season.stories_section(ROOT, slot)
        html = page.read_text(encoding='utf-8')
        match = pattern.search(html)
        if not match or not expected or match.group(0) == expected:
            continue
        page.write_text(html[:match.start()] + expected + html[match.end():], encoding='utf-8')
    team_coverage.refresh(ROOT)


def main() -> None:
    doc = load()
    entries = validate(doc)
    doc['_entries'] = entries
    first = entries[0]
    pp, rp = first['photo_player'], first['photo_relative']
    doc['hero'] = {
        'credit': f'Photos: {pp["author"]}, {pp["license"]}; {rp["author"]}, {rp["license"]}, via Wikimedia Commons',
        'caption_html': f'{esc(first["player"])} (left) and {esc(first["relative"])}. Photos: {credit(pp)}; {credit(rp)}.',
        'source_page': pp['source_page'], 'license_url': pp.get('license_url') or '',
    }
    s = stats(entries)
    articles = pa.load_articles()
    existing = next((a for a in articles if a.get('slug') == SLUG), None)
    is_new = existing is None
    article = record(doc, s, existing)
    hero_path = hero_source(existing)
    photo = hero_path.read_bytes()
    if not (existing and pa.images_ready(existing, photo)):
        pa.write_images(article, hero_path, photo)
    else:
        for key in ('image', 'imageSource', 'imageHero', 'imageHeroWidth', 'imageHeroHeight', 'imageOg', 'imageOgWidth', 'imageOgHeight', 'imageWidth', 'imageHeight'):
            if key in existing:
                article[key] = existing[key]
    articles, record_changed = pa.upsert_record(articles, article)
    article = next(a for a in articles if a.get('slug') == SLUG)
    pa.save_articles(articles)
    page = render(doc, entries, s, article, articles)
    pa.write_if_changed(PAGE_PATH, __import__("site_nav").apply_now_bar(page))
    # Run the same pass the nightly news build runs, so tonight's rebuild is a no-op.
    page = links.prepare_article_page(ROOT, article, articles)
    pa.write_if_changed(PAGE_PATH, __import__("site_nav").apply_now_bar(page))
    pa.write_if_changed(CSV_PATH, write_csv(entries))
    pa.write_if_changed(ROOT / SLUG / 'index.html', pa.redirect_html(SLUG))
    if is_new or record_changed:
        item = links._news_list_item(article)
        pa.prepend_news_list(ROOT / 'news' / 'index.html', item, article)
        pa.prepend_news_list(ROOT / 'authors' / 'ryan-moalemi' / 'index.html', item, article)
        pa.update_homepage(articles)
        pa.update_sitemap_html(article)
        pa.update_latest(article, articles)
        pa.sync_feeds(articles)
    refresh_team_stories()
    print(f'{s["relatives"]} relatives, {s["players"]} players, updated {doc["updated"]}')


if __name__ == '__main__':
    main()
    import search_index; search_index.write()  # keep site search current
