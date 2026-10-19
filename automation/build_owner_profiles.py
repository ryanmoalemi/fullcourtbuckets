"""One page per controlling owner at /wnba/owners/<slug>/, built only from that owner's own sourced records.

Information gain: each page carries an FCB-compiled ownership timeline (deal, approvals, roles, facility
commitments, credited valuations) and, where a price is on record, FCB's estimate-to-price calculation.
Owners whose records are too thin (no primary-sourced deal, unsourced control, or a co-owner whose records
are identical to the first-named owner's) get no page and stay unlinked.
"""
import json
import re

import build_owners as B

MIN_EVENTS = 4
PRIMARY_EVENT_TYPES = ('primary filing', 'official announcement', 'official publication')


def slug(name: str) -> str:
    return re.sub(r'[^a-z]+', '-', name.lower()).strip('-')


def _date(r: dict) -> str:
    for k in ('closing_date', 'approval_date', 'announcement_date'):
        if r.get(k):
            return r[k]
    return r.get('year', '')


def deals_for(data: dict, person: str, team: str) -> list[dict]:
    tokens = [t for t in person.split() if len(t) > 2]
    out = []
    for r in data['transactions']:
        fr = r['franchise']
        if team not in fr and not fr.startswith(team.split(' (')[0]):
            continue
        if any(t in r['buyer'] for t in tokens) or (r['transaction_type'].startswith('expansion') and 'ownership' in r['buyer']):
            out.append(r)
    return out


def records(data: dict, ph: dict) -> dict:
    own = next(r for r in data['ownership'] if r['team_id'] == ph['team_id'])
    team = own['team'].split(' (')[0]
    deals = deals_for(data, ph['person'], team)
    inv = [r for r in data['investors'] if r['team'].startswith(team) and ph['person'].split()[-1] in r['investor']
           and ph['person'].split()[0] in r['investor']]
    projects = {p['project_id']: p for p in data['facility_projects']}
    fac = [projects[x.strip()] for x in own['facility_project_ids'].split(';') if x.strip() in projects]
    vals = sorted([v for v in data['valuations'] if v['team'] == team], key=lambda v: (v['published_date'], v['publisher']))
    ents = [e for e in data['entities'] if e['team'].startswith(team) and e['status'].startswith('found')]
    return {'own': own, 'team': team, 'deals': deals, 'inv': inv, 'fac': fac, 'vals': vals, 'ents': ents}


def timeline(rec: dict, person: str) -> list[tuple[str, str, str, str]]:
    ev = []
    for d in rec['deals']:
        amt = B.money(d['amount_usd_m']) if d['amount_usd_m'] else ''
        detail = f'{d["seller"]} → {d["buyer"]}. {(amt + " (" + d["amount_status"] + ")") if amt else d["amount_status"].capitalize()}.'
        for k, label in (('announcement_date', 'announced'), ('approval_date', 'approved'), ('closing_date', 'closed')):
            if d.get(k):
                ev.append((d[k], f'{d["transaction_type"].capitalize()} {label}', detail, d['event_source_url']))
        if not any(d.get(k) for k in ('announcement_date', 'approval_date', 'closing_date')):
            ev.append((d['year'], d['transaction_type'].capitalize(), detail, d['event_source_url']))
        if d['amount_source_url'] and d['amount_source_url'] != d['event_source_url'] and amt:
            ev.append((_date(d), 'Price on record', f'{amt}: {d["amount_status"]}. {d["consideration_scope"]}', d['amount_source_url']))
    for r in rec['inv']:
        if r['effective_date']:
            stake = r['disclosed_stake'] or 'not disclosed'
            ev.append((r['effective_date'], 'Ownership role on record', f'{r["role_as_described"]}; stake {stake}.', r['primary_source_url']))
    own = rec['own']
    if own.get('governor_source_url') and own['governor'] != 'not yet sourced':
        ev.append(('2026-09-04', 'Team governor named', own['governor'], own['governor_source_url']))
    for p in rec['fac']:
        if p['announced']:
            ev.append((p['announced'], 'Facility announced', p['project_name'], p['primary_source_url']))
        if p['delivery_status'] == 'operational' and p['operational_date']:
            ev.append((p['operational_date'] if not re.match(r'\d{4}-\d\d-\d\d', p['operational_date']) else p['operational_date'][:10], 'Facility opened', p['project_name'], p['primary_source_url']))
        elif p['delivery_status'] != 'operational':
            ev.append((p['status_as_of'] or '', f'Facility status: {p["delivery_status"]}', p['project_name'], p['primary_source_url']))
    for v in rec['vals']:
        if v['published_date'].startswith('2026'):
            ev.append((v['published_date'], f'{v["publisher"]} valuation estimate', f'{B.money(v["amount_usd_m"])} (publisher estimate, not a price)', v['source_url']))
    ev = [e for e in ev if e[0] and e[3]]
    ev.sort(key=lambda e: e[0])
    return ev


def price_rows(rec: dict) -> list[list[str]]:
    rows = []
    for d in rec['deals']:
        st = d['amount_status']
        if not d['amount_usd_m'] or st.startswith(('disputed', 'bundled', 'not')) or d['eligible_for_summaries'] not in ('yes', 'True', 'true', '1'):
            continue
        paid = float(d['amount_2026_usd_m'] or d['amount_usd_m'])
        for v in rec['vals']:
            if not v['published_date'].startswith('2026'):
                continue
            years = int(v['published_date'][:4]) - int(d['year'])
            rows.append([f'{B.esc(d["year"])} {B.esc(d["transaction_type"])}', B.esc(B.money(d['amount_usd_m'])) + f' <span class="ow-small">({B.esc(st)})</span> ' + B.src_link(d['amount_source_url']),
                         B.esc(B.money(d['amount_2026_usd_m'])) if d['amount_2026_usd_m'] else '',
                         f'{B.esc(v["publisher"])} {B.esc(B.money(v["amount_usd_m"]))} ({B.esc(B.human_date(v["published_date"]))}) ' + B.src_link(v['source_url'], label=f'{v["publisher"]} estimate'),
                         f'{float(v["amount_usd_m"]) / paid:.1f}×', str(years)])
    return rows


def eligible(data: dict) -> dict:
    """person -> records, for owners with enough sourced, person-specific data for an information-gain page."""
    out, seen = {}, {}
    for ph in data['owner_photos']:
        rec = records(data, ph)
        if rec['own']['controlling_owner_evidence'] != 'sourced':
            continue
        if not any(d['event_source_url'] and d['event_source_type'].startswith(PRIMARY_EVENT_TYPES) for d in rec['deals']):
            continue
        if len(timeline(rec, ph['person'])) < MIN_EVENTS:
            continue
        key = (rec['own']['team_id'], tuple(d['transaction_id'] for d in rec['deals']))
        if key in seen:  # co-owner with identical records: one page only
            continue
        seen[key] = ph['person']
        out[ph['person']] = rec
    return out


def skipped(data: dict) -> list[str]:
    ok = eligible(data)
    return [ph['person'] for ph in data['owner_photos'] if ph['person'] not in ok]


CSS = B.PAGE_CSS + (
    '.op-head{display:flex;align-items:center;gap:10px;margin:0 0 4px}'
    '.op-head img,.op-head .ow-av{width:48px;height:48px;font-size:16px;margin:0}'
    '.op-new{font-size:14px;margin:0 0 6px}.op-new a{color:#ff9800}'
)


def render_page(data: dict, person: str, rec: dict) -> str:
    own, team = rec['own'], rec['team']
    s = slug(person)
    url = f'https://fullcourtbuckets.com/wnba/owners/{s}/'
    ph = next(p for p in data['owner_photos'] if p['person'] == person)
    ev = timeline(rec, person)
    title = f'{person}: {team} ownership record and timeline'
    head, top, bottom = B.shell_parts()
    head = head.replace(f'<title>{B.esc(B.TITLE)}</title>', f'<title>{B.esc(title)} | Full Court Buckets</title>')
    head = head.replace(B.CANONICAL, url).replace(B.esc(B.DESCRIPTION), B.esc(f'FCB ownership timeline for {person} and the {team}: deal, approvals, roles, facilities and credited valuations, each linked to its source.'))
    head = head.replace(B.esc(B.H1), B.esc(title))
    person_ld = {'@context': 'https://schema.org', '@type': 'Person', 'name': person, 'url': url,
                 'affiliation': {'@type': 'SportsTeam', 'name': team}, 'jobTitle': 'Controlling owner (as described in cited source)'}
    if ph['display'] == 'photo':
        person_ld['image'] = url + ph['image_path'].split('/')[-1]
    ds_ld = {'@context': 'https://schema.org', '@type': 'Dataset', 'name': f'{person} ownership timeline ({team})', 'url': url,
             'creator': {'@type': 'Organization', 'name': 'Full Court Buckets'}, 'license': B.LICENSE_URL,
             'isPartOf': {'@type': 'Dataset', 'name': 'FCB WNBA ownership dataset', 'url': B.CANONICAL},
             'temporalCoverage': f'{ev[0][0][:4]}/{B.DATA_THROUGH}', 'dateModified': B.DATA_THROUGH}
    crumbs = {'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': 'https://fullcourtbuckets.com/'},
        {'@type': 'ListItem', 'position': 2, 'name': 'WNBA owners', 'item': B.CANONICAL},
        {'@type': 'ListItem', 'position': 3, 'name': person, 'item': url}]}
    head += f'<style id="{B.STYLE_ID}">{CSS}</style>' + ''.join(
        '<script type="application/ld+json">' + json.dumps(x, ensure_ascii=False).replace('<', '\\u003c') + '</script>' for x in (person_ld, ds_ld, crumbs))
    if ph['display'] == 'photo':
        av = f'<img class="ow-av" src="{B.esc(ph["image_path"].split("/")[-1])}" alt="{B.esc(person)}" width="48" height="48">'
    else:
        av = f'<span class="ow-av" aria-hidden="true">{B.esc(B.initials(person))}</span>'
    src_ = own['controlling_owner_source_url']
    intro = (f'{B.esc(person)} is listed as controlling owner of the {B.esc(team)}{(" (" + B.esc(own["controlling_owner"]) + ")") if own["controlling_owner"] != person else ""}, '
             f'per {B.src_link(src_)}.')
    rows = ''.join(f'<tr><td>{B.esc(B.human_date(d) if len(d) >= 10 else d)}</td><td>{B.esc(e)}</td><td>{B.esc(det)}</td><td class="ow-ev">{B.src_link(u)}</td></tr>'
                   for d, e, det, u in ev)
    table = ('<p class="ow-hint" aria-hidden="true">Swipe for more columns →</p><div class="ow-scroll"><div class="ow-table-wrap"><table class="ow-table">'
             '<thead><tr><th scope="col">Date</th><th scope="col">Event</th><th scope="col">Detail</th><th scope="col">Source</th></tr></thead>'
             f'<tbody>{rows}</tbody></table></div></div>')
    pr = price_rows(rec)
    price_html = ''
    if pr:
        price_html = ('<section class="ow-section" id="price"><h2 class="section-title">Price paid vs. later estimates</h2>'
                      + B.table(['Deal', 'Price on record', 'Price in 2026 $', 'Publisher estimate', 'Estimate ÷ 2026-$ price (FCB calculation)', 'Years after deal'],
                                [(f'p{i}', '', r) for i, r in enumerate(pr)])
                      + '<p class="ow-small">FCB calculation: a publisher\'s estimate divided by the inflation-adjusted price on record (BLS CPI-U, as in the main dataset). '
                        'It compares two published numbers; it is not a realized return, and estimates are not sale prices.</p></section>')
    teams = [r for r in B.active(data)]
    gov_n = sum(1 for r in teams if r['governor'] and r['governor'] != 'not yet sourced')
    real = lambda v: bool(v) and 'not' not in v.lower()
    stake = next((r['disclosed_stake'] for r in rec['inv'] if real(r['disclosed_stake'])), '')
    stakes_n = len({r['team'] for r in data['investors'] if real(r['disclosed_stake']) and r['counts_toward_active_findings'] == 'yes'})
    compare = (f'<p>Stake: {B.esc(stake) if stake else "not disclosed"}. {("No investor at any of the " + str(len(teams)) + " active teams has a disclosed stake in FCB's register.") if stakes_n == 0 else f"{stakes_n} of {len(teams)} active teams have a disclosed investor stake."} '
               f'Team governor: {B.esc(own["governor"]) if own["governor"] != "not yet sourced" else "not yet sourced"} ({gov_n} of {len(teams)} governors sourced). '
               f'NBA relationship: {B.esc(B.nba_short(own["nba_relationship_current"]))}.</p>')
    ents = ''.join(f'<li>{B.esc(e["entity"])}: {B.esc(e["documented_role"])} ({B.src_link(e["primary_source_url"])})</li>' for e in rec['ents'])
    urls = sorted({u for _, _, _, u in ev} | ({src_} if src_ else set()))
    srcs = ''.join(f'<li><a href="{B.esc(u)}" target="_blank" rel="noopener">{B.esc(u)}</a> · <a href="https://web.archive.org/web/*/{B.esc(u)}" target="_blank" rel="noopener">archive.org lookup</a></li>' for u in urls)
    lic = (f'<a href="{B.esc(ph["license_url"])}">{B.esc(ph["license"])}</a>' if ph['license_url'] else B.esc(ph['license']))
    credit = (f'<p class="ow-small">Photo: <a href="{B.esc(ph["source_url"])}" target="_blank" rel="noopener">{B.esc(ph["title"][5:])}</a> '
              f'by {B.esc(ph["author"])}, {lic}; cropped by FCB.</p>') if ph['display'] == 'photo' else ''
    main = (
        '<main class="page"><div class="standings-shell"><div class="page-header">'
        f'<nav class="breadcrumbs" aria-label="Breadcrumb"><a href="/">Home</a> › <a href="/wnba/owners/">WNBA owners</a> › <span>{B.esc(person)}</span></nav>'
        f'<h1>{B.esc(title)}</h1>'
        f'<div class="byline-row article">{B.links.BYLINE_HTML}<span class="byline-sep" aria-hidden="true">|</span>'
        f'<time class="article-date" datetime="{B.PUBLISHED}">{B.esc(B.human_date(B.PUBLISHED))}</time></div></div>'
        '<article class="ow-body">'
        f'<p class="ow-meta">Data through {B.esc(B.human_date(B.DATA_THROUGH))} · FCB WNBA ownership dataset {B.DATASET_VERSION}</p>'
        f'<p class="ow-intro">{intro}</p>'
        f'<section class="ow-section" id="timeline"><h2 class="section-title">Ownership timeline</h2>'
        f'<div data-fcb-data-table>{table}</div>'
        f'<p class="op-new">New from FCB: {len(ev)} dated, sourced events compiled from FCB\'s ledger into one timeline. Permalink: <a href="{url}#timeline">{url}#timeline</a></p></section>'
        + price_html
        + f'<section class="ow-section" id="compare"><h2 class="section-title">Stake and roles compared</h2><div class="op-head">{av}<strong>{B.esc(person)}</strong></div>{compare}</section>'
        + (f'<section class="ow-section" id="entities"><h2 class="section-title">Documented entities</h2><ul>{ents}</ul>'
           '<p class="ow-small">A registry or filing entry is not by itself proof of ownership or control.</p></section>' if ents else '')
        + f'<section class="ow-section" id="sources"><h2 class="section-title">Sources</h2><ul>{srcs}</ul>{credit}'
        f'<p>Full dataset, methods and corrections: <a href="/wnba/owners/#methods">WNBA team owners 2026</a>. Corrections: <a href="mailto:{B.CONTACT}">{B.CONTACT}</a>. '
        f'License: <a href="{B.LICENSE_URL}">CC BY 4.0</a> for FCB data and text; photos and linked documents keep their own licenses.</p></section>'
        f'<p class="how-made">{B.links.HOW_MADE_OTHER} <a href="{B.links.HOW_MADE_PAGE}">How we make Full Court Buckets</a></p>'
        '</article></div></main>'
    )
    bottom = bottom.replace('</body>', f'<script id="{B.SCRIPT_ID}">{B.PAGE_JS}</script>\n</body>', 1)
    return head + top + main + bottom


def build(data: dict) -> dict:
    import shutil
    ok = eligible(data)
    sm = B.ROOT / 'pages-sitemap.xml'
    text = sm.read_text(encoding='utf-8')
    for person, rec in ok.items():
        d = B.PAGE_DIR / slug(person)
        d.mkdir(exist_ok=True)
        B.write_if_changed(d / 'index.html', render_page(data, person, rec))
        ph = next(p for p in data['owner_photos'] if p['person'] == person)
        if ph['display'] == 'photo':
            shutil.copyfile(B.PAGE_DIR / ph['image_path'], d / ph['image_path'].split('/')[-1])
        loc = f'https://fullcourtbuckets.com/wnba/owners/{slug(person)}/'
        if f'<loc>{loc}</loc>' not in text:
            text = text.replace('</urlset>', f'  <url>\n    <loc>{loc}</loc>\n    <lastmod>{B.DATA_THROUGH}</lastmod>\n'
                                '    <changefreq>monthly</changefreq>\n    <priority>0.6</priority>\n  </url>\n</urlset>', 1)
    sm.write_text(text, encoding='utf-8')
    return ok
