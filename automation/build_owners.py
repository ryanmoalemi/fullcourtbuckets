#!/usr/bin/env python3
"""Build /wnba/owners/ from the ownership dataset in data/wnba/owners/.

The CSVs in data/wnba/owners/ are the only source. Every count, finding, table
row, download and JSON-LD block on the page is worked out from them, so the
page cannot drift from the data. Run:

    python automation/build_owners.py

Page chrome (head styles, site header and footer) is copied from the
viewership page so the site look is unchanged. Shared templates and the
helpers in citation.py are used as-is; this page's CSS and JS are page-scoped.
"""
from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import re
import sys
import zipfile
from collections import Counter, OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'automation'))

import citation  # noqa: E402
import internal_links as links  # noqa: E402

ROUTE = '/wnba/owners/'
SITE = citation.BASE
CANONICAL = SITE + ROUTE
DATA_DIR = ROOT / 'data' / 'wnba' / 'owners'
PAGE_DIR = ROOT / 'wnba' / 'owners'
PAGE_PATH = PAGE_DIR / 'index.html'
SHELL_PAGE = ROOT / 'wnba' / 'viewership-attendance' / 'index.html'
PUBLISHED = '2026-10-19'
DATA_THROUGH = '2026-10-19'
DATASET_VERSION = 'v3'
LICENSE_URL = citation.CC0
CONTACT = 'ryan@fullcourtbuckets.com'
H1 = 'WNBA team owners 2026: who owns every team, plus sales and facility investments'
TITLE = 'WNBA team owners 2026: who owns every team and since when'
DESCRIPTION = (
    'Who owns every WNBA team, the investors teams have disclosed, every franchise sale and expansion fee FCB has documented, with sources and downloads.'
)
COLLECTIONS = (
    'ownership', 'investors', 'entities', 'transactions',
    'facility_projects', 'facility_financials', 'valuations', 'sources', 'owner_photos',
)
ZIP_NAME = 'wnba-owners-dataset.zip'
JSON_NAME = 'wnba-owners.json'
BANNED_SOURCES = ('espn.com', 'balldontlie', 'oursportscentral.com', 'wikipedia.org')
ESTIMATE_PUBLISHERS = ('sportico.com', 'cnbc.com', 'forbes.com')
TEAM_SLUGS = {
    'Golden State Valkyries': 'golden-state-valkyries', 'New York Liberty': 'new-york-liberty',
    'Indiana Fever': 'indiana-fever', 'Las Vegas Aces': 'las-vegas-aces', 'Seattle Storm': 'seattle-storm',
    'Phoenix Mercury': 'phoenix-mercury', 'Los Angeles Sparks': 'los-angeles-sparks',
    'Minnesota Lynx': 'minnesota-lynx', 'Connecticut Sun': 'connecticut-sun', 'Chicago Sky': 'chicago-sky',
    'Portland Fire': 'portland-fire', 'Dallas Wings': 'dallas-wings', 'Washington Mystics': 'washington-mystics',
    'Atlanta Dream': 'atlanta-dream', 'Toronto Tempo': 'toronto-tempo',
}
PLAYER_PAGES = {'Sue Bird': 'sue-bird', 'Renee Montgomery': 'renee-montgomery'}
STYLE_ID = 'fcb-owners-css'
SCRIPT_ID = 'fcb-owners-js'
PAGE_CSS = (
    '.ow-meta{margin:0 0 14px;color:#a29f99;font-size:14px;font-weight:600}'
    '.ow-answer{border-left:4px solid #ff9800;padding:10px 14px;margin:0 0 14px;background:rgba(255,152,0,.06)}'
    '.ow-answer p{margin:0 0 8px}.ow-answer p:last-child{margin:0}'
    '.ow-local{display:flex;flex-wrap:wrap;gap:8px 16px;margin:0 0 18px;font-weight:700}'
    '.ow-local a{color:#ff9800}'
    '.ow-section{margin:28px 0}'
    '.ow-controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0 10px}'
    '.ow-controls input,.ow-controls select{min-height:36px;padding:4px 8px;font:inherit;font-size:15px;'
    'background:#1b1a19;color:#f5f3ef;border:1px solid #55524d;border-radius:4px}'
    '.ow-controls input{flex:1 1 220px}'
    '.ow-count{color:#a29f99;font-size:14px}'
    '.page-header .eyebrow{font-size:12px}'
    '.page-header{margin-bottom:6px}.ow-meta{margin:0 0 2px!important;font-size:13px!important}'
    '.ow-intro{margin:0 0 6px;font-size:15px}#ownership{margin-top:4px}#ownership h2{margin:0 0 6px}'
    '#ownership .ow-controls{margin:0 0 6px}'
    '.visually-hidden{position:absolute!important;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}'
    '.ow-table-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch}'
    '.ow-scroll{position:relative}.ow-hint{display:none;margin:0 0 6px;font-size:13px;font-weight:700;color:#ff9800}'
    '.ow-av{display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;border-radius:50%;'
    'vertical-align:middle;margin:0 6px 2px 0;object-fit:cover;flex:none;background:#3a3835;color:#f5f3ef;font:800 12px/1 Barlow,sans-serif}'
    '.ow-person{display:inline-flex;align-items:center;white-space:nowrap}'
    '.ow-owners{display:inline-flex;flex-wrap:wrap;align-items:center;gap:3px 12px}'
    '.ow-owners .ow-av{margin:0 5px 0 0}'
    '.ow-table td:nth-child(2){min-width:250px}'
    # White table panel (copied page-locally from the Finals ratings tracker's .fcb-attendance table styles).
    '.ow-scroll{background:#fff;border:1px solid #e2ded8;border-radius:8px;overflow:hidden;color:#151413}'
    '.ow-scroll .ow-table{color:#151413;background:#fff;font-variant-numeric:tabular-nums}'
    '.ow-scroll .ow-table th{background:#2a1458;color:#fff;font-weight:700;border-bottom:0}'
    '.ow-scroll .ow-table td{border-bottom:1px solid #e2ded8;background:#fff;color:#151413}'
    '.ow-scroll .ow-table tbody tr:nth-child(even) td{background:#faf8fd}'
    '.ow-scroll .ow-table tbody tr:hover td{background:#efe6ff}'
    '.ow-scroll .ow-table tr:target td,.ow-scroll .ow-table tr.ow-hit td{background:#fff3df}'
    '.ow-scroll .ow-table a{color:#5b22c9}'
    '.ow-scroll .ow-table strong,.ow-scroll .ow-table b{color:#151413}'
    '.ow-scroll .ow-tag{color:#45413b;border-color:#bbb6ae;background:#fff}'
    '.ow-scroll .ow-tag.report{color:#7a4a00;border-color:#c98a2c;background:#fff3df}'
    '.ow-scroll .ow-tag.missing{color:#a12b2b;border-color:#d99;background:#fff0f0}'
    '.ow-scroll .ow-small{color:#5a554e}'
    '.ow-scroll .ow-av{background:#e9e4f5;color:#2a1458}'
    '.ow-table{width:100%;border-collapse:collapse;font-size:15px}'
    '.ow-table th,.ow-table td{padding:8px 10px;border-bottom:1px solid #3a3835;text-align:left;vertical-align:top}'
    '.ow-table th{font-size:14px;color:#d0ccc6;white-space:nowrap}'
    '.ow-table tr:target td,.ow-table tr.ow-hit td{background:rgba(255,152,0,.12)}'
    '.ow-ev{font-size:14px;line-height:1.5}'
    '.ow-tag{display:inline-block;font-size:13px;padding:1px 6px;border:1px solid #55524d;border-radius:3px;color:#d0ccc6}'
    '.ow-tag.report{border-color:#c98a2c;color:#f0c27a}'
    '.ow-tag.missing{border-color:#a65151;color:#f2a3a3}'
    '.ow-downloads{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}'
    '.ow-downloads a,.ow-downloads button{display:inline-block;padding:8px 12px;border:1px solid #ff9800;'
    'color:#f5f3ef;background:none;font:inherit;font-size:14px;font-weight:800;text-decoration:none;cursor:pointer}'
    '.ow-finding{border:1px solid #3a3835;padding:14px;margin:0 0 14px}'
    '.ow-finding h3{margin:0 0 8px;font:800 20px/1.2 Barlow,sans-serif}'
    '.ow-finding p{margin:0 0 6px;font-size:15px}'
    '.ow-finding .ow-small{color:#a29f99;font-size:14px}'
    '.ow-profile{border-top:1px solid #3a3835;padding:12px 0}'
    '.ow-profile h3{margin:0 0 6px;font:800 20px/1.2 Barlow,sans-serif}'
    '.ow-profile dl{display:grid;grid-template-columns:minmax(120px,190px) 1fr;gap:4px 12px;margin:0;font-size:15px}'
    '.ow-profile dt{font-weight:800;color:#d0ccc6}.ow-profile dd{margin:0}'
    '.ow-dict dt{font-weight:800;margin-top:8px}.ow-dict dd{margin:2px 0 0;color:#d0ccc6}'
    '.ow-faq h3{margin:18px 0 6px;font:800 19px/1.2 Barlow,sans-serif}'
    '.ow-cite{white-space:pre-wrap;font-size:14px;background:#1b1a19;padding:10px;border:1px solid #3a3835}'
    '@media (max-width:640px){.ow-profile dl{grid-template-columns:1fr}.ow-profile dt{margin-top:6px}'
    '.ow-table{font-size:14px}.ow-controls input{flex:1 1 100%}.ow-controls select{flex:1 1 auto;max-width:100%}'
    '.ow-hint{display:block}.ow-scroll:after{content:"";position:absolute;top:0;right:0;bottom:0;width:28px;pointer-events:none;'
    'background:linear-gradient(90deg,rgba(255,255,255,0),#fff)}'
    '.ow-table th:first-child,.ow-table td:first-child{position:sticky;left:0;z-index:1;min-width:96px;max-width:110px;box-shadow:inset -1px 0 0 #e2ded8}'
    '.ow-table td:nth-child(2){min-width:180px}'
    '.ow-person{white-space:normal}}'
    '.ow-collapse>summary{list-style:none;cursor:default}.ow-collapse>summary::-webkit-details-marker{display:none}'
    '.ow-collapse>summary h3{display:inline}.ow-sum{display:none}'
    '@media (max-width:600px){'
    '.ow-body{font-size:14px;line-height:1.45}.ow-body p{margin:0 0 8px}'
    '.ow-section{margin:16px 0}.section-title{font-size:21px!important;margin:0 0 6px!important}'
    '.ow-table{font-size:12px!important;line-height:1.35}.ow-table th,.ow-table td{padding:4px 6px!important}'
    '.ow-table th{font-size:12px!important}.ow-ev,.ow-tag{font-size:12px!important}'
    '.ow-table td:nth-child(n+3){min-width:120px}'
    '.ow-finding{padding:10px;margin:0 0 10px}.ow-finding h3{font-size:17px}.ow-finding p,.ow-finding .ow-small{font-size:13px}'
    '.ow-profile{padding:6px 0}.ow-collapse>summary{cursor:pointer;display:flex;flex-wrap:wrap;gap:2px 8px;align-items:baseline}'
    '.ow-collapse>summary h3{font-size:16px!important;margin:0!important}'
    '.ow-collapse>summary:after{content:"+";margin-left:auto;color:#ff9800;font-weight:800}.ow-collapse[open]>summary:after{content:"−"}'
    '.ow-sum{display:block;flex-basis:100%;font-size:12px;color:#a29f99}'
    '.ow-profile dl{font-size:13px;gap:2px 8px}'
    '.ow-faq h3{font-size:16px;margin:12px 0 4px}.ow-small{font-size:12px}'
    '.ow-downloads{gap:6px}.ow-downloads a,.ow-downloads button{padding:6px 9px;font-size:12px}'
    '.ow-cite{font-size:12px;padding:8px}'
    '.ow-more{display:block;width:100%;margin:6px 0;padding:8px;border:1px solid #ff9800;background:none;color:#f5f3ef;font:800 13px Barlow,sans-serif}}'
    '.ow-more{display:none}@media (max-width:600px){.ow-more:not([hidden]){display:block}}'
)
PAGE_JS = r"""(function(){
if(window.matchMedia&&matchMedia('(max-width:600px)').matches){document.querySelectorAll('details.ow-collapse[open]').forEach(function(d){if(!location.hash||!d.closest(location.hash))d.removeAttribute('open');});}
function q(s,r){return (r||document).querySelectorAll(s);}
var params=new URLSearchParams(location.search);
q('[data-ow-table]').forEach(function(box){
  var key=box.getAttribute('data-ow-table');var input=box.querySelector('input');var sel=box.querySelector('select');
  var rows=q('tbody tr',box);var count=box.querySelector('.ow-count');
  var phone=window.matchMedia&&matchMedia('(max-width:600px)').matches;var cap=phone&&rows.length>20?10:0;var more=null;
  if(cap){more=document.createElement('button');more.type='button';more.className='ow-more';box.querySelector('.ow-scroll').after(more);
    more.addEventListener('click',function(){cap=0;more.remove();more=null;apply();});}
  function apply(){var t=(input.value||'').toLowerCase().trim();var f=sel?sel.value:'';var n=0;var shown=0;
    rows.forEach(function(r){var ok=(!t||r.textContent.toLowerCase().indexOf(t)>-1)&&(!f||r.getAttribute('data-filter')===f);
      if(location.hash&&r.id===location.hash.slice(1))ok=true;if(ok)n++;var vis=ok&&(!cap||t||f||shown<cap||(location.hash&&r.id===location.hash.slice(1)));
      r.hidden=!vis;if(vis)shown++;});
    if(more){more.hidden=!!(t||f)||n<=cap;more.textContent='Show all '+n+' rows';}
    if(count)count.textContent=(shown<n?shown+' shown, ':'')+n+' of '+rows.length+' rows';
    var p=new URLSearchParams(location.search);if(t)p.set(key+'_q',t);else p.delete(key+'_q');
    if(f)p.set(key+'_f',f);else p.delete(key+'_f');var s=p.toString();
    history.replaceState(null,'',location.pathname+(s?'?'+s:'')+location.hash);}
  if(params.get(key+'_q'))input.value=params.get(key+'_q');
  if(sel&&params.get(key+'_f'))sel.value=params.get(key+'_f');
  input.addEventListener('input',apply);if(sel)sel.addEventListener('change',apply);
  var clr=box.querySelector('.ow-clear');if(clr)clr.addEventListener('click',function(){input.value='';if(sel)sel.value='';apply();});
  var dl=box.querySelector('.ow-dl-filtered');
  if(dl)dl.addEventListener('click',function(){var tbl=box.querySelector('table');var out=[];
    var head=[];q('thead th',tbl).forEach(function(th){head.push(th.textContent.trim());});out.push(head);
    rows.forEach(function(r){if(r.hidden)return;var c=[];q('td',r).forEach(function(td){c.push(td.textContent.replace(/\s+/g,' ').trim());});out.push(c);});
    var csv=out.map(function(row){return row.map(function(v){return '"'+v.replace(/"/g,'""')+'"';}).join(',');}).join('\n');
    var a=document.createElement('a');a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv'}));
    a.download='wnba-owners-'+key+'-filtered.csv';document.body.appendChild(a);a.click();a.remove();});
  apply();});
q('.ow-copy').forEach(function(b){b.addEventListener('click',function(){var n=document.getElementById(b.getAttribute('data-copy'));
  var text=n?n.textContent.trim():'';if(b.getAttribute('data-link'))text=location.origin+location.pathname+'#'+b.getAttribute('data-link');
  if(navigator.clipboard)navigator.clipboard.writeText(text);var l=b.textContent;b.textContent='Copied!';setTimeout(function(){b.textContent=l;},1500);});});
})();"""


def esc(value) -> str:
    return html.escape('' if value is None else str(value), quote=True)


def load() -> dict:
    data = {}
    for name in COLLECTIONS:
        with (DATA_DIR / f'{name}.csv').open(encoding='utf-8') as handle:
            data[name] = list(csv.DictReader(handle))
    return data


def all_urls(row: dict) -> list[str]:
    return re.findall(r'https?://[^\s|,;)"]+', ' '.join(str(v) for v in row.values()))


def validate(data: dict) -> None:
    """Fail the build on a banned source or a missing ID."""
    for name, rows in data.items():
        id_field = next(iter(rows[0]))
        ids = [r[id_field] for r in rows]
        if len(ids) != len(set(ids)) or not all(ids):
            raise SystemExit(f'{name}: IDs must be unique and present')
        for row in rows:
            for url in all_urls(row):
                if any(bad in url for bad in BANNED_SOURCES):
                    raise SystemExit(f'{name} {row[id_field]}: banned source {url}')
    for row in data['valuations']:
        if row['publisher'] not in ('CNBC', 'Sportico'):
            raise SystemExit(f'valuation {row["valuation_id"]}: unexpected publisher')


def source_label(url: str, kind: str = '') -> str:
    if not url:
        return ''
    host = url.split('/')[2].replace('www.', '')
    kind = (kind or '').lower()
    if 'sec.gov' in host:
        return 'SEC filing'
    if host.endswith('toronto.ca'):
        return 'City of Toronto document'
    if 'sportico' in url and host.endswith('wnba.com'):
        return 'Sportico report (reposted by team)'
    if host.endswith('wnba.com') or host.endswith('nba.com'):
        return 'League release' if host in ('wnba.com', 'nba.com') else 'Team release'
    if host in ('mohegangaming.com', 'monumentalsports.com', 'bkse.com'):
        return 'Owner release'
    names = {
        'apnews.com': 'AP report', 'sportico.com': 'Sportico', 'cnbc.com': 'CNBC', 'forbes.com': 'Forbes',
        'seattletimes.com': 'Seattle Times report', 'sportsbusinessjournal.com': 'SBJ report',
        'opb.org': 'OPB report', 'chron.com': 'Houston Chronicle report', 'frontofficesports.com': 'Front Office Sports report',
    }
    if host in names:
        return names[host]
    if 'journalism' in kind or 'report' in kind:
        return f'{host} report'
    return host


def is_report(url: str, kind: str = '') -> bool:
    label = source_label(url, kind)
    return 'report' in label.lower() or label in ('Sportico', 'CNBC', 'Forbes')


def src_link(url: str, kind: str = '', label: str = '') -> str:
    if not url:
        return '<span class="ow-tag missing">Primary not located</span>'
    if '/resource/' in url and '.json' in url:
        host = url.split('/')[2].replace('data.', '').replace('.gov', '').upper()
        rec = url.rsplit('=', 1)[-1]
        return f'<span>{esc(host)} state registry record {esc(rec)} (open-data API; see CSV)</span>'
    text = label or source_label(url, kind)
    tag = ' <span class="ow-tag report">report</span>' if is_report(url, kind) and 'report' not in text.lower() else ''
    if is_report(url, kind) and 'report' in text.lower():
        tag = ''
    return f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(text)}</a>{tag}'


def team_link(team: str) -> str:
    base = team.split(' (')[0]
    slug = TEAM_SLUGS.get(base)
    if slug and (ROOT / 'wnba' / 'teams' / slug / 'index.html').is_file():
        rest = team[len(base):]
        return f'<a href="/wnba/teams/{slug}/">{esc(base)}</a>{esc(rest)}'
    return esc(team)


def person_link(name: str) -> str:
    slug = PLAYER_PAGES.get(name)
    if slug and (ROOT / 'wnba' / slug / 'index.html').is_file():
        return f'<a href="/wnba/{slug}/">{esc(name)}</a>'
    return esc(name)


def human_date(value: str) -> str:
    value = (value or '').strip()
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return links._format_date(value)
    if re.fullmatch(r'\d{4}-\d{2}', value):
        months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
                  'September', 'October', 'November', 'December']
        return f'{months[int(value[5:7]) - 1]} {value[:4]}'
    return value or 'Not established'


def cap1(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def money(value) -> str:
    if value in (None, ''):
        return ''
    try:
        number = float(value)
    except ValueError:
        return f'${value}M'
    if number >= 1000:
        return f'${number / 1000:.2f}B'.replace('.00B', 'B')
    return f'${number:,.1f}M'.replace('.0M', 'M')


def active(data: dict) -> list[dict]:
    return [r for r in data['ownership'] if r['scope'].startswith('active')]


def stats(data: dict) -> dict:
    s: dict = {}
    teams = active(data)
    s['teams'] = len(teams)
    s['owner_sourced'] = sum(1 for r in teams if r['controlling_owner_evidence'] == 'sourced')
    s['nba_shared'] = sum(1 for r in teams if r['nba_relationship_current'].startswith('shared'))
    s['governors_sourced'] = sum(1 for r in teams if r['governor'] and r['governor'] != 'not yet sourced')
    inv = [r for r in data['investors'] if r['counts_toward_active_findings'] == 'yes']
    s['relationships'] = len(inv)
    s['people'] = len({r['person_or_entity_id'] for r in inv})
    s['inv_sourced'] = sum(1 for r in inv if r['evidence_status'] == 'sourced')
    s['inv_report'] = sum(1 for r in inv if r['evidence_status'] == 'report only')
    rows = data['investors']
    s['rows_total'] = len(rows)
    s['rows_future'] = sum(1 for r in rows if r['team_scope'] != 'active')
    s['rows_unnamed'] = sum(1 for r in rows if r['entity_type'] == 'unnamed group')
    s['rows_other_excluded'] = len(rows) - len(inv) - s['rows_future'] - s['rows_unnamed']
    s['distinct_people'] = len({r['person_or_entity_id'] for r in inv if r['entity_type'] in ('person', 'family group')})
    s['distinct_orgs'] = len({r['person_or_entity_id'] for r in inv if r['entity_type'] == 'institution'})
    s['franchises_with_investors'] = len({r['team'] for r in inv})
    ath = [r for r in inv if r.get('has_professional_playing_experience') == 'yes' and r['entity_type'] == 'person']
    s['athlete_ids'] = sorted({r['person_or_entity_id'] for r in ath})
    s['athletes'] = sorted({r['investor'] for r in ath})
    s['athlete_teams'] = sorted({r['team'] for r in ath})
    s['athlete_rels'] = len({(r['person_or_entity_id'], r['team']) for r in ath})
    dates = sorted(r['effective_date'][:4] for r in ath if r['effective_date'])
    s['athlete_period'] = f'{dates[0]}-{dates[-1]}' if dates else ''
    s['athlete_recheck'] = sorted({r['investor'] for r in ath if r.get('review_trigger')})
    tx = data['transactions']
    s['ledger_rows'] = len(tx)
    events = [r for r in tx if r['transaction_type'].startswith(('control sale', 'expansion'))]
    eligible = [r for r in events if r['eligible_for_summaries'].startswith('yes')]
    s['events'] = len(events)
    s['priced'] = len(eligible)
    s['unpriced'] = len(events) - len(eligible)
    fees = [r for r in eligible if r['transaction_type'].startswith('expansion')]
    early = [r for r in fees if int(r['year']) < 2010]
    late = [r for r in fees if int(r['year']) == 2025]
    s['fee_early'] = sorted(float(r['amount_2026_usd_m']) for r in early)
    s['fee_early_years'] = sorted({r['year'] for r in early})
    s['fee_early_nominal'] = sorted({float(r['amount_usd_m']) for r in early})
    s['fee_2025'] = float(late[0]['amount_2026_usd_m']) if late else None
    s['fee_2025_nominal'] = float(late[0]['amount_usd_m']) if late else None
    s['fee_ratio_real'] = round(s['fee_2025'] / min(s['fee_early']), 1) if late and early else None
    s['fee_by_year'] = {r['year']: float(r['amount_2026_usd_m']) for r in early}
    s['fee_multiples'] = {y: round(s['fee_2025'] / v, 1) for y, v in s['fee_by_year'].items()} if late else {}
    s['fee_ratio_nominal'] = round(s['fee_2025_nominal'] / max(s['fee_early_nominal'])) if late and early else None
    s['control_priced'] = [r for r in eligible if r['transaction_type'].startswith('control')]
    proj = data['facility_projects']
    s['projects'] = len(proj)
    s['operational_own'] = [p for p in proj if p['delivery_status'] == 'operational' and not p['use_classification'].startswith('shared')]
    s['operational_shared'] = [p for p in proj if p['delivery_status'] == 'operational' and p['use_classification'].startswith('shared')]
    s['not_operational'] = [p for p in proj if p['delivery_status'] != 'operational']
    fin = data['facility_financials']
    bucket_a = [o for o in fin if o['total_bucket'] == 'A']
    s['budget_a'] = sum(float(o['amount_usd_m']) for o in bucket_a)
    s['budget_a_n'] = len(bucket_a)
    s['budget_a_stated'] = sum(float(o['amount_usd_m']) for o in bucket_a if o['source_type'] == 'official announcement')
    s['budget_a_reported'] = s['budget_a'] - s['budget_a_stated']
    s['private_b'] = sum(float(o['amount_usd_m']) for o in fin if o['total_bucket'] == 'B')
    s['val_counts'] = Counter(v['publisher'] for v in data['valuations'])
    return s


def fmt_m(x: float) -> str:
    return f'${x:,.1f}M'.replace('.0M', 'M')


def names_list(items: list[str]) -> str:
    items = list(items)
    if len(items) <= 2:
        return ' and '.join(items)
    return ', '.join(items[:-1]) + ' and ' + items[-1]


def filter_box(key: str, label: str, options: list[tuple[str, str]], table: str, csv_name: str) -> str:
    opts = ''.join(f'<option value="{esc(v)}">{esc(t)}</option>' for v, t in options)
    select = (f'<label class="visually-hidden" for="ow-{key}-f">Filter</label>'
              f'<select id="ow-{key}-f"><option value="">All</option>{opts}</select>') if options else ''
    return (
        f'<div class="ow-tab" data-ow-table="{key}"' + (' data-fcb-data-table' if key == 'ownership' else '') + '>'
        f'<div class="ow-controls"><label class="visually-hidden" for="ow-{key}-q">Search {esc(label)}</label>'
        f'<input id="ow-{key}-q" type="search" placeholder="Search names, teams, entities">{select}'
        '<button type="button" class="ow-clear">Clear all</button><span class="ow-count" aria-live="polite"></span></div>'
        f'{table}'
        f'<div class="ow-downloads"><a href="{csv_name}" download>Download CSV (all)</a>'
        '<button type="button" class="ow-dl-filtered">CSV of current filters</button>'
        f'<a href="{ZIP_NAME}" download>Full dataset (JSON + all CSVs, zip)</a></div></div>'
    )


def table(headers: list[str], rows: list[tuple[str, str, list[str]]]) -> str:
    head = ''.join(f'<th scope="col">{esc(h)}</th>' for h in headers)
    body = ''.join(
        f'<tr id="{esc(rid)}" data-filter="{esc(flt)}">' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>'
        for rid, flt, cells in rows
    )
    return ('<p class="ow-hint" aria-hidden="true">Swipe for more columns →</p>'
            f'<div class="ow-scroll"><div class="ow-table-wrap"><table class="ow-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div></div>')


def nba_short(value: str) -> str:
    if value.startswith('shared'):
        inner = re.search(r'\((.*)\)', value)
        return 'Shared control' + (f' ({inner.group(1)})' if inner else '')
    if value.startswith('other'):
        inner = re.search(r'\((.*)\)', value)
        return 'Other affiliation' + (f' ({inner.group(1)})' if inner else '')
    return 'None identified'


def first_effective(data: dict, team: str) -> str:
    dates = [r['effective_date'] for r in data['investors']
             if r['team'].split(' (')[0] == team.split(' (')[0] and r['current_status'].startswith('current (controlling')]
    return human_date(sorted(dates)[0]) if dates else ''


def evidence_cell(r: dict) -> str:
    if not r['controlling_owner_source_url']:
        return '<span class="ow-tag missing">Primary not located</span>'
    status = r['controlling_owner_evidence']
    tag = '' if status == 'sourced' else f' <span class="ow-tag report">{esc(status)}</span>'
    return src_link(r['controlling_owner_source_url']) + tag


def governor_cell(r: dict) -> str:
    if r['governor'] == 'not yet sourced':
        return 'Not yet sourced'
    return esc(r['governor']) + (' ' + src_link(r['governor_source_url']) if r.get('governor_source_url') else '')


def initials(name: str) -> str:
    return ''.join(w[0] for w in name.split() if w[0].isalpha())[:2].upper()


def owner_cell(data: dict, r: dict) -> str:
    """Controlling owner text with a small circle photo (openly licensed) or initials before each person."""
    text = esc(r['controlling_owner'])
    for ph in (x for x in data['owner_photos'] if x['team_id'] == r['team_id']):
        name = esc(ph['person'])
        if ph['display'] == 'photo':
            av = (f'<img class="ow-av" src="{esc(ph["image_path"])}" alt="" width="26" height="26" loading="lazy" '
                  f'title="Photo: {esc(ph["author"])}, {esc(ph["license"])}">')
        else:
            av = f'<span class="ow-av" aria-hidden="true">{esc(initials(ph["person"]))}</span>'
        label = f'<a href="{OWNER_PAGES[ph["person"]]}">{name}</a>' if ph['person'] in OWNER_PAGES else name
        text = text.replace(name, f'<span class="ow-person">{av}{label}</span>', 1)
    text = re.sub(r'</span>\s*(?:and|;|,)\s*<span class="ow-person">', '</span><span class="ow-person">', text)
    return f'<span class="ow-owners">{text}</span>'


def photo_credits(data: dict) -> str:
    rows = [x for x in data['owner_photos'] if x['display'] == 'photo']
    n_init = sum(1 for x in data['owner_photos'] if x['display'] != 'photo')
    items = '; '.join(
        f'{esc(x["person"])}: <a href="{esc(x["source_url"])}" target="_blank" rel="noopener">{esc(x["title"][5:])}</a> by {esc(x["author"])}, '
        + (f'<a href="{esc(x["license_url"])}" target="_blank" rel="noopener">{esc(x["license"])}</a>' if x['license_url'] else esc(x['license']))
        for x in rows)
    return (f'<p><strong>Owner photos:</strong> {len(rows)} owners shown with openly licensed photos from Wikimedia Commons, '
            'matched to the person through Wikidata, cropped to the face and resized by FCB (changes made). '
            f'{n_init} owners without a licensable photo are shown with initials. Credits: {items}. '
            'Details per photo are in owner_photos.csv.</p>')


def ownership_section(data: dict) -> str:
    rows = []
    for r in active(data):
        ev = evidence_cell(r)
        flt = 'shared' if r['nba_relationship_current'].startswith('shared') else 'other'
        rows.append((r['team_id'], flt, [
            team_link(r['team']), owner_cell(data, r), governor_cell(r),
            esc(nba_short(r['nba_relationship_current'])), esc(first_effective(data, r['team'])), f'<span class="ow-ev">{ev}</span>',
        ]))
    t = table(['Team', 'Controlling owner/group', 'Team governor', f'NBA relationship ({human_date(DATA_THROUGH)})', 'Effective since', 'Evidence'], rows)
    return filter_box('ownership', 'ownership', [('shared', 'Shares control with an NBA team'), ('other', 'No NBA shared control')], t, 'ownership.csv')


def investor_section(data: dict) -> str:
    rows = []
    for r in data['investors']:
        if r['team_scope'] != 'active':
            continue
        team = team_link(r['team'])
        if r['parent_path']:
            team += f', <strong>via parent {esc(r["parent_path"])}</strong>'
        status = r['current_status']
        if status.startswith('current'):
            label = 'Current as of cited evidence'
        else:
            label = 'Historically disclosed; not reconfirmed'
        if r['evidence_status'] == 'primary not located' or not r['primary_source_url']:
            ev = '<span class="ow-tag missing">Primary not located</span>'
        else:
            ev = src_link(r['primary_source_url'], r['source_type'])
        rel = {'team ownership as described in source (legal structure not documented)': 'Ownership (as described)',
               'indirect via documented parent': 'Indirect (via parent)', 'unnamed investor group': 'Unnamed group (not counted)'}.get(r['relationship_type'], r['relationship_type'])
        flt = 'athlete' if 'former pro athlete' in r['background_tags'] else ('report' if r['evidence_status'] == 'report only' else 'other')
        rows.append((r['relationship_id'], flt, [
            person_link(r['investor']), team, esc(rel), esc(cap1(r['disclosed_stake'])), esc(human_date(r['effective_date'])),
            esc(label), f'<span class="ow-ev">{ev}</span>',
        ]))
    t = table(['Investor', 'Team or entity', 'Relationship', 'Disclosed stake', 'Effective', 'Status', 'Evidence'], rows)
    return filter_box('investors', 'investors', [('athlete', 'Former pro athletes'), ('report', 'Report-only evidence')], t, 'investors.csv')


def prices_section(data: dict) -> str:
    vals: dict = {}
    for v in data['valuations']:
        vals.setdefault(v['team'], []).append(v)
    tx_by_team: dict = {}
    for r in data['transactions']:
        for team in TEAM_SLUGS:
            if r['franchise'].startswith(team) or r['franchise'].endswith(team) or f'-> {team}' in r['franchise']:
                tx_by_team.setdefault(team, []).append(r)
    rows = []
    for o in active(data):
        team = o['team'].split(' (')[0]
        txs = sorted((r for r in tx_by_team.get(team, []) if 'context' not in r['transaction_type']), key=lambda r: r['year'])
        tx = txs[-1] if txs else None
        if tx:
            what = f'{tx["year"]}: {tx["transaction_type"]}'
            if tx['amount_usd_m']:
                price = f'{money(tx["amount_usd_m"])} ({esc(tx["amount_status"])})'
            elif tx['amount_status'].startswith('bundled'):
                price = 'Bundled; no WNBA price'
            else:
                price = esc(cap1(tx['amount_status']))
            ev = f'<a href="#{esc(tx["transaction_id"])}">Ledger row</a>'
        else:
            what, price, ev = 'None indexed', '', ''
        est = []
        for v in sorted((v for v in vals.get(team, []) if v['published_date'].startswith('2026')), key=lambda v: v['publisher']):
            est.append(f'{esc(v["publisher"])}: {money(v["amount_usd_m"])} ({esc(human_date(v["published_date"]))}), '
                       f'<a href="{esc(v["source_url"])}" target="_blank" rel="noopener">{esc(v["publisher"])} estimate</a>')
        rows.append((f'price-{TEAM_SLUGS.get(team, team)}', '', [team_link(team), esc(what), price, '<br>'.join(est) or 'Not rated', ev]))
    t = table(['Team', 'Relevant transaction', 'Price and status', 'Publisher estimates (credited)', 'Evidence'], rows)
    return (filter_box('prices', 'prices', [], t, 'valuations.csv')
            + '<p class="ow-small">Valuations are CNBC and Sportico estimates, credited to each publisher and not transaction prices. '
              'The page shows no ratio, multiple or return. Bundled NBA and WNBA prices are never split.</p>')


def findings(data: dict, s: dict) -> str:
    out = []
    out.append(
        '<div class="ow-finding" id="finding-athletes"><h3>'
        f'{len(s["athlete_ids"])} people with professional playing experience were publicly identified as investors in {len(s["athlete_teams"])} active franchises</h3>'
        f'<p id="finding-athletes-text">FCB has documented {len(s["athlete_ids"])} people with professional playing experience who were publicly identified as investors in '
        f'{len(s["athlete_teams"])} currently active franchises ({esc(names_list(s["athlete_teams"]))}): {esc(names_list(s["athletes"]))}. '
        f'Disclosures cover {s["athlete_period"]}; not all holdings have been reconfirmed as of {human_date(DATA_THROUGH)}. '
        f'Evidence for {len(s["athlete_recheck"])} of them is more than 24 months old and is flagged for recheck, which is not evidence of an exit.</p>'
        '<p class="ow-small">Method: distinct person IDs with has_professional_playing_experience = yes, matched to active-franchise IDs. '
        'An executive career is a separate, overlapping tag, not an exclusion (Masai Ujiri played professionally in Europe, per a Nuggets release). '
        'Olympic participation alone does not qualify. No row carries an explicit current-holding confirmation, so this is a count of disclosures, not current holdings. Stakes are not disclosed.</p>'
        '<p><button type="button" class="ow-copy" data-copy="finding-athletes">Copy finding</button> '
        '<button type="button" class="ow-copy" data-link="finding-athletes">Copy link</button></p></div>'
    )
    if s['fee_2025']:
        early = s['fee_early']
        out.append(
            '<div class="ow-finding" id="finding-fees"><h3>Expansion fees: '
            f'{s["fee_multiples"].get("2008")} times the 2008 fee in 2026 dollars</h3>'
            f'<p id="finding-fees-text">In 2026 dollars, the reported WNBA expansion fee was {fmt_m(s["fee_by_year"].get("2006", 0))} in 2006 and {fmt_m(s["fee_by_year"].get("2008", 0))} in 2008, '
            f'against {fmt_m(s["fee_2025"])} for each 2025 franchise: about {s["fee_multiples"].get("2006")} times the 2006 fee and {s["fee_multiples"].get("2008")} times the 2008 fee in purchasing-power terms. '
            f'The nominal jump, {fmt_m(max(s["fee_early_nominal"]))} to {fmt_m(s["fee_2025_nominal"])}, is {s["fee_ratio_nominal"]} times. Data through {human_date(DATA_THROUGH)}.</p>'
            f'<p class="ow-small">Coverage: {s["events"]} control-change and fee events indexed; {s["priced"]} priced and undisputed, {s["unpriced"]} unpriced or disputed. '
            'Method: BLS CPI-U (CUUR0000SA0) annual averages against the January-September 2026 average (not a full-year 2026 average); series, periods and index values are exported per row in transactions.csv. Multiples use unrounded values. '
            'Caveat: the 2006 and 2008 fees appear only in secondary reports, and the 2025 fee is from AP (the league release names the owners, not the fee). '
            'Portland\'s fee is disputed and excluded. Inflation adjustment measures purchasing power, not investor returns.</p>'
            '<p><button type="button" class="ow-copy" data-copy="finding-fees">Copy finding</button> '
            '<button type="button" class="ow-copy" data-link="finding-fees">Copy link</button></p></div>'
        )
    tracked = s['projects']
    out.append(
        '<div class="ow-finding" id="finding-facilities"><h3>'
        f'{len(s["not_operational"])} of {tracked} tracked facility projects are not operational yet</h3>'
        f'<p id="finding-facilities-text">Among the {tracked} facility projects FCB tracks, {len(s["operational_own"])} provide operational team-specific practice space, '
        f'{len(s["operational_shared"])} is an operational shared complex and {len(s["not_operational"])} are not yet operational. '
        f'This project inventory is separate from where all {s["teams"]} teams currently practice. Data through {human_date(DATA_THROUGH)}.</p>'
        '<p class="ow-small">Budget and funding totals are held back until currency, scope and sources are reviewed. Each project\'s amounts are listed in the table with their status and currency. '
        'Budgets are announcements, not spending, and the Storm\'s financing is part of the same $64M budget, not an extra investment.</p>'
        '<p><button type="button" class="ow-copy" data-copy="finding-facilities">Copy finding</button> '
        '<button type="button" class="ow-copy" data-link="finding-facilities">Copy link</button></p></div>'
    )
    return ''.join(out)


def transactions_section(data: dict) -> str:
    rows = []
    for r in sorted(data['transactions'], key=lambda r: (r['year'], r['transaction_id'])):
        date = r['closing_date'] or r['approval_date'] or r['announcement_date'] or r['year']
        amt = money(r['amount_usd_m']) if r['amount_usd_m'] else ''
        status = r['amount_status']
        real = money(r['amount_2026_usd_m']) if r['amount_2026_usd_m'] else ''
        flt = 'expansion' if r['transaction_type'].startswith('expansion') else ('control' if r['transaction_type'].startswith('control') else 'other')
        seller_buyer = ' → '.join(x for x in (r['seller'], r['buyer']) if x)
        rows.append((r['transaction_id'], flt, [
            esc(human_date(date)), team_link(r['franchise']), esc(seller_buyer), esc(r['transaction_type']),
            (amt + '<br>' if amt else '') + f'<span class="ow-small">{esc(status)}</span>', esc(r['consideration_scope']), esc(real),
            f'<span class="ow-ev">{src_link(r["event_source_url"], r["event_source_type"]) if r["event_source_url"] else "<span class=\"ow-tag missing\">Primary not located</span>"}</span>',
            f'<span class="ow-ev">{src_link(r["amount_source_url"]) if r["amount_source_url"] else ""}</span>',
        ]))
    t = table(['Date', 'Franchise', 'Seller → buyer', 'Type', 'Amount', 'What it covers', '2026 $', 'Evidence (deal)', 'Evidence (amount)'], rows)
    return (
        '<p>One row per deal. "Not disclosed" appears only where a document shows nondisclosure; otherwise the row says "not established from available sources." '
        'Bundled NBA and WNBA prices are never allocated to the WNBA team, and an unknown amount is never shown as zero.</p>'
        + filter_box('transactions', 'transactions', [('control', 'Control sales'), ('expansion', 'Expansion fees'), ('other', 'Bundled and context')], t, 'transactions.csv')
        + '<p class="ow-small">Known gaps: the 2003 Utah Starzz to San Antonio move, the 2003 Charlotte Sting, the 2006-07 Sparks sale, the 2007 Houston Comets sale and '
          'the 2002-03 transfers of league-held teams. Defunct franchises are not indexed yet. The 2027 Houston Comets are the relocated Sun franchise, not the 1997-2008 Comets, '
          'and the 2026 Portland Fire is a new franchise, not the 2000-02 Fire.</p>'
    )


def facilities_section(data: dict) -> str:
    fin: dict = {}
    for o in data['facility_financials']:
        fin.setdefault(o['project_id'], []).append(o)
    rows = []
    for p in data['facility_projects']:
        obs = fin.get(p['project_id'], [])
        budget = [o for o in obs if o['total_bucket'].startswith('A')]
        funding = [o for o in obs if o['total_bucket'][:1] in ('B', 'C')]
        btxt = '; '.join((f'{money(o["amount_usd_m"])}' if o.get('currency') == 'USD' else f'About {o["amount_usd_m"]}M, currency unresolved') + f' ({esc(o["status"].split(";")[0])})' for o in budget) or 'Not disclosed'
        ftxt = '; '.join(
            esc(o['observation_type']) + (f': {money(o["amount_usd_m"])}' if o['amount_usd_m'] else '') + f' ({esc(o["status"].split(";")[0])})'
            for o in funding) or 'Not itemized'
        opening = p['operational_date'] or p['revised_target'] or p['original_target']
        opening = re.sub(r'^(\d{4}-\d{2}(?:-\d{2})?)', lambda m: human_date(m.group(1)), opening)
        evs = [src_link(p['primary_source_url'])] + [src_link(o['source_url'], o['source_type']) for o in obs if o['source_url'] and o['source_url'] != p['primary_source_url']]
        evs = list(OrderedDict.fromkeys(evs))
        flt = 'operational' if p['delivery_status'] == 'operational' else 'pending'
        rows.append((p['project_id'], flt, [
            esc(p['project_name']) + '<br>' + team_link(p['linked_teams']), esc(p['use_classification']), esc(p['delivery_status']),
            btxt, ftxt, esc(opening), '<span class="ow-ev">' + ' · '.join(evs) + '</span>',
        ]))
    t = table(['Project / team', 'WNBA use', 'Status', 'Announced budget', 'Documented funding', 'Opening (actual or target)', 'Evidence'], rows)
    return (filter_box('facilities', 'facilities', [('operational', 'Operational'), ('pending', 'Not yet operational')], t, 'facility_projects.csv')
            + '<p class="ow-small">No project of their own: Lynx (share with the Timberwolves), Mystics (CareFirst Arena), Dream (partner facility), Sun (none announced). '
              'Budgets are announcements, not spending, and the page shows no grand total across budgets, private funding and public support.</p>')


def profiles(data: dict) -> str:
    inv: dict = {}
    for r in data['investors']:
        inv.setdefault(r['team'].split(' (')[0], []).append(r)
    ents: dict = {}
    for e in data['entities']:
        ents.setdefault(e['team'].split(' (')[0], []).append(e)
    vals: dict = {}
    for v in data['valuations']:
        vals.setdefault(v['team'], []).append(v)
    projects = {p['project_id']: p for p in data['facility_projects']}
    out = []
    for o in active(data):
        team = o['team'].split(' (')[0]
        slug = TEAM_SLUGS.get(team, team)
        people = [r for r in inv.get(team, []) if r['counts_toward_active_findings'] == 'yes']
        named = ', '.join(person_link(r['investor']) for r in people) or 'None disclosed'
        found = [e for e in ents.get(team, []) if e['status'].startswith('found')]
        ent_txt = '; '.join(f'{esc(e["entity"])} ({esc(e["documented_role"])}) {src_link(e["primary_source_url"])}' for e in found) or 'Not documented'
        v_txt = '; '.join(f'{esc(v["publisher"])} {money(v["amount_usd_m"])} ({esc(human_date(v["published_date"]))})' for v in sorted(vals.get(team, []), key=lambda v: v['publisher']) if v['published_date'].startswith('2026')) or 'Not rated'
        fac = [projects[p] for p in o['facility_project_ids'].split(';') if p.strip() in projects] if o['facility_project_ids'] else []
        f_txt = '; '.join(f'<a href="#{esc(p["project_id"])}">{esc(p["project_name"])}</a> ({esc(p["delivery_status"])})' for p in fac) or 'None announced'
        ev = evidence_cell(o)
        page = f'<a href="/wnba/teams/{slug}/">{esc(team)} team page</a>' if team in TEAM_SLUGS else ''
        out.append(
            f'<section class="ow-profile" id="{esc(slug)}"><details class="ow-collapse" open><summary><h3>{esc(o["team"])}</h3>'
            f'<span class="ow-sum">{esc(o["controlling_owner"])}</span></summary><dl>'
            f'<dt>Controlling owner</dt><dd>{esc(o["controlling_owner"])} ({ev})</dd>'
            f'<dt>What the source says</dt><dd>{esc(o["owner_claim_as_described"])}{(" " + esc(o["owner_claim_note"])) if o["owner_claim_note"] else ""}</dd>'
            f'<dt>Current practice arrangement</dt><dd>{esc(o["practice_arrangement"])}</dd>'
            f'<dt>Documented entities</dt><dd>{ent_txt}</dd>'
            f'<dt>Governor</dt><dd>{governor_cell(o)}</dd>'
            f'<dt>Public investors</dt><dd>{named} (<a href="?investors_q={esc(team.lower())}#investors">filter</a>)</dd>'
            f'<dt>NBA relationship</dt><dd>{esc(nba_short(o["nba_relationship_current"]))}</dd>'
            f'<dt>Valuation estimates</dt><dd>{v_txt}</dd>'
            f'<dt>Facility</dt><dd>{f_txt}</dd>'
            f'<dt>Verified</dt><dd>{esc(human_date(o["last_verified_at"]))}{" · " + page if page else ""}</dd>'
            '</dl></details></section>'
        )
    return ''.join(out)


def future_section(data: dict) -> str:
    future = [r for r in data['ownership'] if r['scope'].startswith('future')]
    fee = next((r for r in data['transactions'] if r['year'] == '2025' and r['transaction_type'].startswith('expansion')), None)
    items = ''.join(f'<li><strong>{esc(r["team"])}</strong>: {esc(r["controlling_owner"])} ({src_link(r["controlling_owner_source_url"])})</li>' for r in future)
    fee_txt = (f' Each fee was reported at {money(fee["amount_usd_m"])} ({src_link(fee["amount_source_url"])}).' if fee else '')
    shared_now = sum(1 for r in active(data) if r['nba_relationship_current'].startswith('shared'))
    total = len(active(data)) + len(future)
    return (
        f'<ul>{items}</ul><p>The league announced all three on June 30, 2025, subject to Board approval.{fee_txt} '
        f'They are outside every active count on this page. If they launch on schedule with these owners, {shared_now + len(future)} of {total} teams would share '
        'control with an NBA team by 2030. That is a projection, not a finding.</p>'
        '<p>The full expansion story is at <a href="/news/wnba-expansion-teams/">WNBA expansion teams</a>.</p>'
    )


def coverage_table(data: dict) -> str:
    rows = []
    for name in ('ownership', 'investors', 'entities', 'transactions', 'facility_projects', 'facility_financials', 'valuations'):
        recs = data[name]
        rows.append([name, len(recs)])
    return citation.data_table(['Collection', 'Records'], rows)


def dictionary_html() -> str:
    text = (DATA_DIR / 'data-dictionary.md').read_text(encoding='utf-8')
    return f'<details><summary>Data dictionary</summary><pre class="ow-cite">{esc(text)}</pre></details>'


def faq(data: dict, s: dict) -> list[tuple[str, str]]:
    brady = next((r for r in data['investors'] if r['investor'] == 'Tom Brady'), None)
    bird = next((r for r in data['investors'] if r['investor'] == 'Sue Bird'), None)
    items = [
        ('Who owns WNBA teams?', f'Each of the {s["teams"]} teams has its own controlling owner; the ownership table above lists each one with the document that names them.'),
        ('Does the NBA own the WNBA?', 'No single owner holds every team. The NBA relationship column in the ownership table shows, team by team, where a WNBA team shares an owner with an NBA team and what document supports it.'),
        ('Which WNBA investors played professionally?', f'{names_list(s["athletes"])} were publicly identified as investors, per the investor register. Not every holding has been reconfirmed as of {human_date(DATA_THROUGH)}.'),
        ('What did the Mohegan Tribe pay for the Sun?', f'$10 million in 2003: $2 million in cash plus an $8 million note to the league, according to SEC filings.'),
    ]
    if brady:
        items.append(('Is Tom Brady part owner of the Aces?', f'The Aces announced on {human_date(brady["effective_date"])} that Brady acquired an ownership interest. His stake was not disclosed, and FCB has not found a later reconfirmation.'))
    if bird:
        items.append(('Does Sue Bird own part of the Storm?', f'The Storm announced on {human_date(bird["effective_date"])} that Bird joined its ownership group. Her stake was not disclosed.'))
    return items


def body(data: dict, s: dict) -> str:
    p = []
    # Ryan's rule (academic data-publication norms): only supporting material sits above the first table:
    # the data-through line, a one- or two-sentence answer and the coverage line. No lists, findings or news.
    p.append(f'<p class="ow-meta">Published {esc(human_date(PUBLISHED))} · Data through {esc(human_date(DATA_THROUGH))} · Dataset {DATASET_VERSION}</p>')
    p.append(f'<p class="ow-intro">Controlling owners, investors, sales and facility projects for all {s["teams"]} WNBA teams, each linked to its source.</p>')
    missing = [f"{r['team']}: {r['controlling_owner_evidence']}" for r in active(data) if r['controlling_owner_evidence'] != 'sourced']
    miss_txt = f' (not yet primary-sourced for control: {"; ".join(missing)})' if missing else ''
    p.append('<section class="ow-section" id="ownership"><h2 class="section-title">Who owns every WNBA team</h2>' + ownership_section(data)
             + '<p class="ow-small">Future teams (not in active counts): Cleveland 2028, Detroit 2029, Philadelphia 2030. See <a href="#future">future teams</a>.</p></section>')
    p.append('<section class="ow-section" id="investors"><h2 class="section-title">Publicly disclosed investors</h2>'
             '<p>Governor and executive titles never create an ownership row. Parent-company percentages are never converted into franchise percentages. '
             '"Former pro athlete" means the person played professionally; tags overlap and are never added together.</p>' + investor_section(data) + '</section>')
    p.append('<section class="ow-section" id="prices"><h2 class="section-title">Prices and valuations</h2>' + prices_section(data) + '</section>')
    p.append(
        '<div class="ow-answer"><p><strong>Who owns WNBA teams?</strong> '
        f'Search the controlling owners, publicly disclosed investors, transaction records and facility projects for all {s["teams"]} teams in FCB\'s 2026 ownership reference. '
        'Team ownership, governor roles and league investments are recorded separately, with evidence attached to each claim.</p>'
        '</div>'
    )
    p.append('<p class="ow-detail">One detail from the filings: the Mohegan Tribe\'s 2003 purchase of the Sun was $2 million in cash plus an $8 million note to the league, according to its SEC registration statement.</p>')
    p.append('<nav class="ow-local" aria-label="On this page"><a href="#ownership">Ownership</a><a href="#investors">Investors</a>'
             '<a href="#transactions">Transactions</a><a href="#facilities">Facilities</a><a href="#methods">Methods</a></nav>')
    p.append('<section class="ow-section" id="findings"><h2 class="section-title">What FCB\'s research shows</h2>' + findings(data, s) + '</section>')
    p.append('<section class="ow-section" id="transactions"><h2 class="section-title">Franchise sales and expansion fees</h2>' + transactions_section(data) + '</section>')
    p.append('<section class="ow-section" id="facilities"><h2 class="section-title">Practice facility investments</h2>' + facilities_section(data) + '</section>')
    p.append('<section class="ow-section" id="profiles"><h2 class="section-title">Team-by-team ownership profiles</h2>' + profiles(data) + '</section>')
    p.append('<section class="ow-section" id="future"><h2 class="section-title">Future teams</h2>' + future_section(data) + '</section>')
    items = faq(data, s)
    p.append('<section class="ow-section ow-faq" id="faq"><h2 class="section-title">Frequently asked questions</h2>'
             + ''.join(f'<h3>{esc(q)}</h3><p>{esc(a)}</p>' for q, a in items) + '</section>')
    coverage_li = (f'<li><strong>Coverage:</strong> {s["teams"]} active teams indexed; {s["owner_sourced"]} have a sourced controlling-owner record{esc(miss_txt)}. '
             f'Investor register: {s["rows_total"]} rows = {s["relationships"]} person-or-organization relationships with active franchises '
             f'({s["distinct_people"]} distinct people or families, {s["distinct_orgs"]} organization, across {s["franchises_with_investors"]} franchises; '
             f'{s["inv_sourced"]} relationships tied to a primary document, {s["inv_report"]} to a labeled report only) + {s["rows_future"]} future-team rows + {s["rows_unnamed"]} unnamed group'
             f'{" + " + str(s["rows_other_excluded"]) + " other excluded" if s["rows_other_excluded"] else ""}. '
             'Investors are the ones teams or filings have made public; this is not a complete cap table.</li>')
    gov_teams = [r['team'] for r in active(data) if r['governor'] and r['governor'] != 'not yet sourced']
    cite_apa = (f'Moalemi, R. ({PUBLISHED[:4]}, {human_date(PUBLISHED).split(",")[0]}). {H1} (Dataset {DATASET_VERSION}). Full Court Buckets. {CANONICAL}')
    cite_plain = f'Source: Full Court Buckets WNBA ownership dataset {DATASET_VERSION} (data through {human_date(DATA_THROUGH)}), {CANONICAL}'
    p.append(
        '<section class="ow-section" id="methods"><h2 class="section-title">Methods, data and sources</h2><ul>'
        '<li><strong>Compiled by:</strong> Ryan Moalemi for Full Court Buckets.</li>'
        '<li><strong>Sources:</strong> team and league releases, SEC filings (Form D, S-4, 10-Q and exhibits), owner releases and City of Toronto documents. '
        'Where no primary document exists, the earliest original report is used and labeled as a report.</li>'
        '<li><strong>Evidence:</strong> every record links the document behind it. A deal row links both the document that establishes the event and the one that establishes the amount.</li>'
        '<li><strong>Investors:</strong> only investors that teams, leagues or filings have made public; stakes appear only when disclosed.</li>'
        '<li><strong>Prices:</strong> amounts are nominal as disclosed or reported. 2026-dollar figures use BLS CPI-U (CUUR0000SA0) annual averages against the January to September 2026 average. '
        'They measure purchasing power, not returns.</li>'
        '<li><strong>Valuations:</strong> CNBC (May 4, 2026) and Sportico (May 1, 2026) estimates, each credited to its publisher.</li>'
        + coverage_li
        + f'<li><strong>Governors:</strong> {s["governors_sourced"]} of {s["teams"]} sourced ({esc(", ".join(gov_teams))}); the rest are not yet sourced.</li>'
        '<li><strong>Not yet sourced:</strong> defunct franchises and the transactions listed as known gaps.</li></ul>'
        + photo_credits(data)
        + coverage_table(data)
        + '<h3>Download the data</h3><div class="ow-downloads">'
        + ''.join(f'<a href="{n}.csv" download>{n}.csv</a>' for n in COLLECTIONS)
        + f'<a href="{ZIP_NAME}" download>Everything (zip: JSON, all CSVs, manifest, findings review file)</a></div>'
        + dictionary_html()
        + f'<p><strong>License:</strong> FCB\'s dataset, calculations and text are free to use and republish (<a href="{LICENSE_URL}" target="_blank" rel="noopener">CC0</a>), '
          'no credit required. Valuations remain the work of CNBC and Sportico, and linked documents belong to their publishers.</p>'
        + f'<p><strong>Corrections:</strong> spot an error? Email <a href="mailto:{CONTACT}">{CONTACT}</a> with a link to the document. Each fix is dated.</p>'
        + citation.media_line_html()
        + '<h3>Cite this page</h3>'
        + f'<p class="ow-cite" id="cite-apa">{esc(cite_apa)}</p><p class="ow-cite" id="cite-plain">{esc(cite_plain)}</p>'
        + '<p><button type="button" class="ow-copy" data-copy="cite-apa">Copy APA citation</button> <button type="button" class="ow-copy" data-copy="cite-plain">Copy plain citation</button></p>'
        + '</section>'
    )
    p.append(f'<p class="how-made">{links.HOW_MADE_OTHER} <a href="{links.HOW_MADE_PAGE}">How we make Full Court Buckets</a></p>')
    return '\n'.join(p)


def temporal(data: dict) -> str:
    years = [int(m) for r in data['investors'] + data['transactions'] for m in re.findall(r'\b(19\d\d|20\d\d)\b', r.get('effective_date', '') + ' ' + r.get('year', ''))]
    return f'{min(years)}/{DATA_THROUGH[:4]}'


def findings_record(data: dict, s: dict) -> dict:
    """Inputs and method behind each finding. Any change makes a new hash and resets review."""
    def h(obj):
        return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    inv = [r for r in data['investors'] if r.get('has_professional_playing_experience') == 'yes']
    fees = [r for r in data['transactions'] if r['transaction_type'].startswith('expansion')]
    method = (ROOT / 'automation' / 'build_owners.py').read_bytes()
    return {
        'finding-athletes': {'inputs_hash': h(inv), 'method_hash': hashlib.sha256(method).hexdigest(), 'review_state': 'pending Ryan review'},
        'finding-fees': {'inputs_hash': h(fees), 'method_hash': hashlib.sha256(method).hexdigest(), 'review_state': 'pending Ryan review'},
        'finding-facilities': {'inputs_hash': h(data['facility_projects']), 'method_hash': hashlib.sha256(method).hexdigest(), 'review_state': 'pending Ryan review'},
    }


def jsonld(data: dict) -> str:
    article = {
        '@context': 'https://schema.org', '@type': 'Article', 'headline': H1, 'description': DESCRIPTION,
        'url': CANONICAL, 'mainEntityOfPage': CANONICAL, 'datePublished': PUBLISHED, 'dateModified': DATA_THROUGH,
        'author': {'@type': 'Person', 'name': 'Ryan Moalemi', 'url': SITE + '/authors/ryan-moalemi/'},
        'publisher': {'@type': 'Organization', 'name': 'Full Court Buckets', 'url': SITE + '/'},
    }
    crumbs = {
        '@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
            {'@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': SITE + '/'},
            {'@type': 'ListItem', 'position': 2, 'name': 'WNBA', 'item': SITE + '/wnba/'},
            {'@type': 'ListItem', 'position': 3, 'name': 'Owners', 'item': CANONICAL},
        ],
    }
    primary = sorted({u for r in data['sources'] for u in [r['url']] if u and not any(x in u for x in ESTIMATE_PUBLISHERS)})
    dataset = {
        '@context': 'https://schema.org', '@type': 'Dataset', 'name': 'Full Court Buckets WNBA ownership dataset',
        'description': 'Controlling owners, publicly disclosed investors, franchise transactions, facility projects and credited valuation estimates for every WNBA team, each row linked to its source document.',
        'url': CANONICAL, 'version': DATASET_VERSION, 'temporalCoverage': temporal(data), 'dateModified': DATA_THROUGH,
        'creator': {'@type': 'Organization', 'name': 'Full Court Buckets', 'url': SITE + '/'},
        'license': LICENSE_URL, 'isAccessibleForFree': True, 'isBasedOn': primary,
        'distribution': [{'@type': 'DataDownload', 'encodingFormat': 'text/csv', 'contentUrl': f'{CANONICAL}{n}.csv'} for n in COLLECTIONS]
        + [{'@type': 'DataDownload', 'encodingFormat': 'application/json', 'contentUrl': CANONICAL + JSON_NAME}],
    }
    return ''.join('<script type="application/ld+json">' + json.dumps(x, ensure_ascii=False).replace('<', '\\u003c') + '</script>'
                   for x in (article, crumbs, dataset))


def shell_parts() -> tuple[str, str, str]:
    shell = SHELL_PAGE.read_text(encoding='utf-8')
    # The image step and the viewership builder disagree on whether the header logo
    # carries fetchpriority; drop it so this page does not depend on the shell's history.
    shell = shell.replace(' decoding="async" fetchpriority="high"></picture></a>', ' decoding="async"></picture></a>')
    head_end = shell.index('</head>')
    head = shell[:head_end]
    head = re.sub(r'<script type="application/ld\+json">.*?</script>', '', head, flags=re.S)
    # The feed link and Pinterest tag are re-added by site_nav.ensure_assets in render();
    # drop the shell's copies so their position does not depend on the shell's history.
    head = re.sub(r'<link rel="alternate" type="application/rss\+xml"[^>]*>', '', head)
    head = re.sub(r'<meta name="p:domain_verify"[^>]*>', '', head)
    head = re.sub(r'<title>.*?</title>', f'<title>{esc(TITLE)}</title>', head, count=1, flags=re.S)
    head = re.sub(r'\s*<meta (?:name|property)="(?:description|og:[a-z:]+|twitter:[a-z:]+)" content="[^"]*">', '', head)
    head = re.sub(r'<link rel="canonical" href="[^"]*">', f'<link rel="canonical" href="{CANONICAL}">', head)
    meta = (
        f'\n<meta name="description" content="{esc(DESCRIPTION)}">'
        f'\n<meta property="og:type" content="article">\n<meta property="og:title" content="{esc(H1)}">'
        f'\n<meta property="og:description" content="{esc(DESCRIPTION)}">\n<meta property="og:url" content="{CANONICAL}">'
        f'\n<meta property="og:site_name" content="Full Court Buckets">\n<meta name="twitter:card" content="summary">'
        f'\n<meta name="twitter:title" content="{esc(H1)}">\n<meta name="twitter:description" content="{esc(DESCRIPTION)}">'
    )
    head = head.replace(f'<title>{esc(TITLE)}</title>', f'<title>{esc(TITLE)}</title>{meta}', 1)
    body_start = shell.index('<main class="page">')
    top = shell[head_end:body_start]
    main_end = shell.index('</main>')
    bottom = shell[main_end + len('</main>'):]
    bottom = re.sub(r'<script>\s*\(function \(\) \{.*?</script>', '', bottom, flags=re.S)
    return head, top, bottom


def render(data: dict, s: dict) -> str:
    import build_owner_profiles as profiles_mod
    OWNER_PAGES.clear()
    OWNER_PAGES.update({p: f'/wnba/owners/{profiles_mod.slug(p)}/' for p in profiles_mod.eligible(data)})
    head, top, bottom = shell_parts()
    head += f'<style id="{STYLE_ID}">{PAGE_CSS}</style>{jsonld(data)}'
    main = (
        '<main class="page"><div class="standings-shell"><div class="page-header">'
        '<nav class="breadcrumbs" aria-label="Breadcrumb"><a href="/">Home</a> › <a href="/wnba/">WNBA</a> › <span>Owners</span></nav>'
        '<p class="eyebrow">WNBA / Data &amp; research</p>'
        f'<h1>{esc(H1)}</h1>'
        f'<div class="byline-row article">{links.BYLINE_HTML}<span class="byline-sep" aria-hidden="true">|</span>'
        f'<time class="article-date" datetime="{PUBLISHED}">{esc(human_date(PUBLISHED))}</time></div>'
        '</div>'
        f'<article class="ow-body">{body(data, s)}</article>'
        '</div></main>'
    )
    bottom = bottom.replace('</body>', f'<script id="{SCRIPT_ID}">{PAGE_JS}</script>\n</body>', 1)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import site_nav
    # Same shared head assets (feed link, Pinterest tag, fonts, icons) that
    # build_players' site_nav.install_tree adds, so the page is stable whatever
    # state the shell page was in when this ran.
    return site_nav.ensure_assets(head + top + main + bottom)


def write_if_changed(path: Path, content) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = content.encode('utf-8') if isinstance(content, str) else content
    if not path.is_file() or path.read_bytes() != raw:
        path.write_bytes(raw)


def write_downloads(data: dict, s: dict) -> None:
    files = {}
    for name in COLLECTIONS:
        files[f'{name}.csv'] = (DATA_DIR / f'{name}.csv').read_bytes()
    files['data-dictionary.md'] = (DATA_DIR / 'data-dictionary.md').read_bytes()
    payload = {'dataset': 'Full Court Buckets WNBA ownership dataset', 'version': DATASET_VERSION, 'data_through': DATA_THROUGH,
               'license': LICENSE_URL, 'url': CANONICAL, 'collections': data}
    files['findings.json'] = (json.dumps(findings_record(data, s), indent=1) + '\n').encode('utf-8')
    files[JSON_NAME] = (json.dumps(payload, ensure_ascii=False, indent=1) + '\n').encode('utf-8')
    manifest = {'version': DATASET_VERSION, 'data_through': DATA_THROUGH, 'license': LICENSE_URL,
                'files': {n: {'sha256': hashlib.sha256(b).hexdigest(), 'bytes': len(b)} for n, b in sorted(files.items())},
                'records': {n: len(data[n]) for n in COLLECTIONS}}
    files['manifest.json'] = (json.dumps(manifest, indent=1) + '\n').encode('utf-8')
    for name, raw in files.items():
        write_if_changed(PAGE_DIR / name, raw)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 19, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, raw)
    write_if_changed(PAGE_DIR / ZIP_NAME, buf.getvalue())


def update_sitemap() -> None:
    path = ROOT / 'pages-sitemap.xml'
    text = path.read_text(encoding='utf-8')
    if f'<loc>{CANONICAL}</loc>' in text:
        return
    entry = (f'  <url>\n    <loc>{CANONICAL}</loc>\n    <lastmod>{DATA_THROUGH}</lastmod>\n'
             '    <changefreq>weekly</changefreq>\n    <priority>0.8</priority>\n  </url>\n')
    text = text.replace('</urlset>', entry + '</urlset>', 1)
    path.write_text(text, encoding='utf-8')


OWNER_PAGES: dict = {}


def main() -> None:
    import build_owner_profiles as profiles_mod
    data = load()
    validate(data)
    profiles_mod.build(data)
    s = stats(data)
    write_if_changed(PAGE_PATH, render(data, s))
    write_downloads(data, s)
    print(f'{s["teams"]} teams, {s["relationships"]} investor relationships, {s["ledger_rows"]} ledger rows, {s["projects"]} facility projects')


if __name__ == '__main__':
    main()
