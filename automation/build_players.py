#!/usr/bin/env python3
"""Build static FCB profiles from validated local JSON, never from browser API calls.
Python 3.11+, standard library only. No credentials, scraped biographies, or inferred trades.
"""
from __future__ import annotations
import argparse
import datetime as dt
import html
import json
import math
from pathlib import Path
import re
from zoneinfo import ZoneInfo

BASE = 'https://fullcourtbuckets.com'
SOURCE = 'https://wnba.balldontlie.io/'
SLUG = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*\Z')
COLUMNS = [('games_played','GP'),('min','MIN'),('pts','PTS'),('reb','REB'),('ast','AST'),
           ('stl','STL'),('blk','BLK'),('turnover','TO'),('fg_pct','FG%'),('fg3_pct','3P%'),('ft_pct','FT%')]

class BuildError(RuntimeError):
    pass

def esc(value):
    return html.escape('' if value is None else str(value), quote=True)

def value(n, integer=False):
    if isinstance(n, bool) or not isinstance(n, (float, int)) or not math.isfinite(n):
        return '&mdash;'
    return str(int(n)) if integer and int(n) == n else f'{n:.1f}'

def timestamp(raw, short=False):
    try:
        date = dt.datetime.fromisoformat(str(raw).replace('Z','+00:00'))
        if date.tzinfo is not None:
            date = date.astimezone(ZoneInfo('America/Los_Angeles'))
        return date.strftime('%b %d, %Y' if short else '%b %d, %Y at %I:%M %p PT')
    except (ValueError, TypeError):
        return 'Not supplied'

def tname(team):
    return (team or {}).get('full_name') or (team or {}).get('name') or 'Team not supplied'

def bio_fields(player):
    # Some provider biography fields contain shifted text. Do not relabel or guess it.
    clean = {}
    for key in ('position','height','jersey_number','college','weight'):
        text = str(player.get(key) or '').strip()
        if not text or len(text) > 150:
            continue
        if key == 'weight' and not re.fullmatch(r'\d{2,3}(?:\.\d+)?\s*(?:lbs?\.?|kg)?',text,re.I):
            continue
        if key == 'height' and not re.search(r'\d',text):
            continue
        if key == 'jersey_number' and not re.fullmatch(r'\d{1,2}',text):
            continue
        if key == 'college' and (not re.search(r'[A-Za-z]',text) or re.fullmatch(r'\d+\s*(?:lbs?|kg)?',text,re.I)):
            continue
        clean[key] = text
    return clean

def headline(profile):
    rows = profile.get('season_stats',[])
    for kind in (2,3):
        selected = [r for r in rows if r['season_type']==kind]
        if not selected:
            continue
        year = max(r['season'] for r in selected)
        latest = [r for r in selected if r['season']==year]
        # No synthetic career averages, no combined aggregate plus team-stint sums.
        if len(latest)==1:
            return latest[0]
        aggregate=[r for r in latest if not (r.get('team') or {}).get('id')]
        if len(aggregate)==1:
            return aggregate[0]
        return None
    return None

def validate(profile, slug):
    if not SLUG.fullmatch(slug) or profile.get('slug')!=slug:
        raise BuildError('Invalid or mismatched player slug.')
    p=profile.get('player',{})
    if isinstance(p.get('id'),bool) or not isinstance(p.get('id'),int) or p['id'] <= 0 or not (p.get('first_name') or p.get('last_name')):
        raise BuildError('Missing player identity.')
    seen=set()
    for row in profile.get('season_stats',[]):
        if row.get('player_id')!=p['id'] or row.get('season_type') not in (2,3) or row.get('season',0)<2008:
            raise BuildError('Invalid player, season, or competition in profile.')
        key=(row['season'],row['season_type'],(row.get('team') or {}).get('id'))
        if key in seen:
            raise BuildError('Duplicate season/team row.')
        seen.add(key)
    for game in profile.get('recent_completed_games',[]):
        if game.get('player_id')!=p['id']:
            raise BuildError('Game record belongs to a different player.')

def header():
    return '''<div class="brand-line"></div><header class="site-header"><div class="wrap masthead"><a class="brand" href="/" aria-label="Full Court Buckets home"><img src="/logo.png" alt="Full Court Buckets" width="220" height="76"></a><nav aria-label="Main navigation"><a href="/#latest">News</a><a href="/wnba/" class="selected">Players</a><a href="/standings/">Standings</a><a href="/fiba-womens-basketball-world-cup-2026/">World Cup</a></nav></div></header><div class="tagline"><div class="wrap"><span>WNBA NEWS · ANALYSIS · COMMENTARY</span><span>Independent coverage. Facts first.</span></div></div>'''

def footer():
    return '''<footer class="site-footer"><div class="wrap"><a class="footer-brand" href="/">FULL COURT <b class="gradient">BUCKETS</b></a><p>Independent WNBA coverage. Not affiliated with the WNBA or its teams.</p><a href="/wnba/">Browse player profiles</a></div></footer>'''

def document(title, description, route, body, structured=None):
    canonical=BASE+route
    schema=json.dumps(structured or {},ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><meta name="description" content="{esc(description)}"><meta name="robots" content="index,follow,max-image-preview:large"><link rel="canonical" href="{canonical}"><link rel="icon" href="/favicon.svg"><meta property="og:type" content="website"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(description)}"><meta property="og:url" content="{canonical}"><meta property="og:site_name" content="Full Court Buckets"><meta name="theme-color" content="#0c0c10"><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700;800;900&amp;family=Inter:wght@400;500;600;700;800&amp;display=swap" rel="stylesheet"><link rel="stylesheet" href="/wnba/assets/players.css"><script type="application/ld+json">{schema}</script><script src="/wnba/assets/players.js" defer></script></head><body><a class="skip" href="#content">Skip to content</a>{header()}<main id="content" class="wrap">{body}</main>{footer()}</body></html>'''

def stats_table(profile, kind):
    rows=sorted([r for r in profile.get('season_stats',[]) if r['season_type']==kind],key=lambda r:-r['season'])
    if not rows:
        return ''
    label='Regular season' if kind==2 else 'Playoffs'
    cells=[]
    for r in rows:
        cols=''.join(f'<td>{value(r.get(key),key=="games_played")}</td>' for key,_ in COLUMNS)
        cells.append(f'<tr data-season="{r["season"]}"><th scope="row">{r["season"]}</th><td class="team-cell">{esc(tname(r.get("team")))}</td>{cols}</tr>')
    heads=''.join(f'<th scope="col"><abbr title="{esc({"GP":"Games played","MIN":"Minutes per game","PTS":"Points per game","REB":"Rebounds per game","AST":"Assists per game","STL":"Steals per game","BLK":"Blocks per game","TO":"Turnovers per game","FG%":"Field goal percentage","3P%":"Three-point percentage","FT%":"Free throw percentage"}[text])}">{text}</abbr></th>' for _,text in COLUMNS)
    return f'<div class="competition" data-competition="{kind}"><h3>{label}</h3><div class="table-scroll" role="region" aria-label="{label} season statistics" tabindex="0"><table><caption>{label}: per-game averages, except games played and shooting percentages.</caption><thead><tr><th scope="col">YEAR</th><th scope="col">TEAM</th>{heads}</tr></thead><tbody>{"".join(cells)}</tbody></table></div></div>'

def game_table(profile):
    games=profile.get('recent_completed_games',[])
    if not games:
        return ''
    rows=[]
    for g in sorted(games,key=lambda r:str(r.get('date','')),reverse=True):
        tid=(g.get('team') or {}).get('id')
        home=(g.get('home_team') or {}).get('id')
        away=(g.get('visitor_team') or {}).get('id')
        if tid not in (home,away) or tid is None:
            opponent='Opponent not supplied'; outcome='&mdash;'
        else:
            at_home=tid==home
            opponent=('vs. ' if at_home else '@ ')+tname(g.get('visitor_team' if at_home else 'home_team'))
            ours,theirs=(g.get('home_score'),g.get('away_score')) if at_home else (g.get('away_score'),g.get('home_score'))
            outcome=(('W' if ours>theirs else 'L' if ours<theirs else 'T')+f' {ours}–{theirs}') if isinstance(ours,(int,float)) and isinstance(theirs,(int,float)) else '&mdash;'
        label='Playoffs' if g.get('postseason') is True else 'Regular' if g.get('postseason') is False else 'Not supplied'
        nums=''.join(f'<td>{value(g.get(k),True)}</td>' for k in ('pts','reb','ast','stl','blk','turnover'))
        rows.append(f'<tr><th scope="row">{esc(timestamp(g.get("date"),True))}</th><td class="team-cell">{esc(opponent)}</td><td>{label}</td><td>{outcome}</td><td>{esc(g.get("minutes") or "Not supplied")}</td>{nums}</tr>')
    return f'''<section id="games" class="section"><p class="eyebrow">Completed games</p><h2>Recent game log</h2><p class="muted small">Imported window: {esc(profile.get('game_log_window_start'))} onward. Dates shown in Pacific time. This is not a complete career game log.</p><div class="table-scroll" role="region" tabindex="0" aria-label="Recent completed game statistics"><table><caption>Regular-season and playoff games are labeled separately.</caption><thead><tr><th scope="col">DATE</th><th scope="col">OPPONENT</th><th scope="col">TYPE</th><th scope="col">RESULT</th><th scope="col">MIN</th><th scope="col">PTS</th><th scope="col">REB</th><th scope="col">AST</th><th scope="col">STL</th><th scope="col">BLK</th><th scope="col">TO</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>'''

def profile_page(profile):
    p=profile['player']; name=(str(p.get('first_name') or '')+' '+str(p.get('last_name') or '')).strip()
    slug=profile['slug']; fields=bio_fields(p); active=profile.get('active_in_provider_feed') is True
    team=profile.get('current_team') if active else None
    row=headline(profile); stats=profile.get('season_stats',[])
    years=sorted({r['season'] for r in stats})
    span=f'{years[0]}–{years[-1]}' if len(years)>1 else str(years[0]) if years else 'No season records yet'
    state='Listed active' if active else 'Archive profile'
    position={'G':'Guard','F':'Forward','C':'Center'}.get(fields.get('position'),fields.get('position',''))
    number=fields.get('jersey_number','')
    note=(f'{row["season"]} · '+('regular season' if row['season_type']==2 else 'playoffs')) if row else 'No combined season line supplied'
    metrics=''.join(f'<div class="metric"><strong>{value((row or {}).get(k))}</strong><span>{label}<small>PER GAME</small></span></div>' for k,label in [('pts','POINTS'),('ast','ASSISTS'),('reb','REBOUNDS')])
    meta=' / '.join(esc(x) for x in [('#'+number) if number else '',position,tname(team) if team else ''] if x)
    details=[('Provider status','Listed in active feed' if active else 'Not listed in active feed'),('Records available',span)]
    if team: details.append(('Current listed team',tname(team)))
    for key,label in [('position','Position'),('height','Height'),('jersey_number','Jersey number'),('college','College'),('weight','Weight')]:
        if key in fields: details.append((label,fields[key]))
    detail_html=''.join(f'<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k,v in details)
    regular=[r for r in stats if r['season_type']==2]
    intro=f'{name}: WNBA player statistics and available season records from 2008 onward.'
    if row:
        intro=f'{name} averaged {row["pts"]:.1f} points, {row["reb"]:.1f} rebounds and {row["ast"]:.1f} assists in {row["games_played"]} games in the {row["season"]} '+('regular season.' if row['season_type']==2 else 'playoffs.') if all(isinstance(row.get(k),(int,float)) for k in ('pts','reb','ast','games_played')) else intro
    overview=f'<p>{esc(intro)}</p>'
    if team: overview+=f'<p class="muted">Current team in the provider\'s active-player feed: <strong>{esc(tname(team))}</strong>.</p>'
    if not active: overview+='<p class="muted">This player is not listed in the current active-player feed. That alone does not establish retirement or free-agent status.</p>'
    tablehtml=stats_table(profile,2)+stats_table(profile,3)
    controls=''
    if tablehtml:
        kinds=sorted({r['season_type'] for r in stats})
        radios=''.join(f'<button type="button" data-kind="{k}" aria-pressed="false">{"Regular season" if k==2 else "Playoffs"}</button>' for k in kinds)
        opts=''.join(f'<option value="{y}">{y}</option>' for y in sorted(years,reverse=True))
        controls=f'<div class="filters js-only"><div class="segmented" role="group" aria-label="Competition">{radios}<button type="button" data-kind="all" aria-pressed="true">Both</button></div><label>Season <select id="season-filter"><option value="all">All seasons</option>{opts}</select></label></div>'
    statshtml=f'<section class="section" id="stats"><p class="eyebrow">The numbers</p><h2>Season-by-season stats</h2>{controls}{tablehtml}<p id="stats-empty" class="muted" hidden>No records for this selection.</p><p class="muted small">Statistics since 2008. Team-specific lines are preserved when supplied. They are not added to combined lines or presented as complete career totals.</p></section>' if tablehtml else ''
    all_teams=[]
    for r in sorted(stats,key=lambda r:-r['season']):
        item=(r['season'],tname(r.get('team')))
        if item not in all_teams: all_teams.append(item)
    timeline=''.join(f'<li><strong>{year}</strong><span>{esc(team_name)}</span></li>' for year,team_name in all_teams)
    history=f'<section class="section" id="teams"><p class="eyebrow">Team records</p><h2>Teams by season</h2><p class="muted small">Team labels attached to the imported statistics. Not a complete transaction history.</p><ul class="timeline">{timeline}</ul></section>' if timeline else ''
    checked=timestamp(profile.get('checked_at'))
    latest=profile.get('recent_completed_games',[])
    latest_label=timestamp(max(g['date'] for g in latest),True) if latest else None
    last_game=f'<p>Most recent completed game in this imported log: <b>{esc(latest_label)}</b>.</p>' if latest_label else ''
    nav='<a href="#overview">Overview</a>'+('<a href="#stats">Stats</a>' if stats else '')+('<a href="#games">Game log</a>' if latest else '')+('<a href="#teams">Teams</a>' if timeline else '')+'<a href="#sources">Sources</a>'
    hero=f'''<div class="breadcrumbs"><a href="/">Home</a><span>/</span><a href="/wnba/">WNBA players</a><span>/</span><span>{esc(name)}</span></div><section class="hero" aria-labelledby="player-name"><div class="hero-main"><div class="hero-copy"><div class="hero-kicker"><span class="status">{state}</span><span>WNBA PLAYER PROFILE</span></div><h1 id="player-name"><span>{esc(p.get('first_name'))}</span><b class="gradient">{esc(p.get('last_name') or p.get('first_name'))}</b></h1><p class="hero-meta">{meta}</p><div class="actions">{('<a class="button" href="#stats">View stats <span>→</span></a>' if stats else '<a class="button" href="#overview">Player overview →</a>')}<button type="button" id="share" class="text-button js-only">Share ↑</button><span id="share-status" role="status"></span></div></div><div class="hero-art" aria-hidden="true"><span class="ghost-number">{esc(number or 'FCB')}</span><div class="number-card"><span>{esc(p.get('last_name') or name)}</span><strong class="gradient">{esc(number or 'FCB')}</strong></div><small>FULL COURT BUCKETS · PLAYER ARCHIVE</small></div></div><div class="hero-stats">{metrics}<div class="stat-context"><b>{esc(note)}</b><span>Provider per-game averages</span></div></div></section><nav class="section-nav" aria-label="On this page">{nav}</nav>'''
    sources=f'''<details class="sources section" id="sources"><summary>Data, sources &amp; coverage notes</summary><p>Data source: <a href="{SOURCE}" target="_blank" rel="noopener noreferrer">BALLDONTLIE WNBA API ↗</a>. Provider player ID: {p['id']}.</p><p>API snapshot checked {esc(checked)}. A successful refresh does not guarantee that the provider includes every subsequent game or correction.</p>{last_game}<p>Available coverage begins in 2008. Regular-season and playoff statistics are separate. Career totals and career averages are not calculated from rounded season averages. Missing values are displayed as a dash, never silently converted to zero.</p><p>Some provider biography fields can be missing or incorrectly formatted. Invalid fields are omitted rather than guessed. Absence from the active-player feed is not proof of retirement. A changed team field is not evidence of a particular trade or signing.</p><p>Automatic news and confirmed transaction feeds are not connected. The number artwork is a design element, not a player photograph.</p><a href="/data/wnba/players/{slug}.json">View this player's imported data</a></details>'''
    body=hero+f'<div class="content-grid"><div><section class="section" id="overview"><p class="eyebrow">Player overview</p><h2>{esc(name)}</h2>{overview}<div class="overview-strip"><div><b>{len(set(r["season"] for r in regular))}</b><span>Regular seasons in this dataset</span></div><div><b>{esc(span)}</b><span>Available statistical years</span></div></div></section>{statshtml}{game_table(profile)}{history}</div><aside><section class="side-card"><p class="eyebrow">The essentials</p><h2>Player details</h2><dl>{detail_html}</dl></section><section class="freshness"><p class="eyebrow">Scheduled data updates</p><h3>Source snapshot</h3><p>Checked {esc(checked)}.</p>{last_game}<p class="small">Daily during the season. Every seven days in the offseason.</p></section><a class="button wide" href="/wnba/">Explore WNBA players →</a></aside></div>'+sources+'<section class="archive-band"><div><p class="eyebrow">Full Court Buckets · Player archive</p><h2>WNBA players. Past and present.</h2><p>Explore the available records from 2008 onward.</p></div><a class="button" href="/wnba/">Browse players →</a></section>'
    route=f'/wnba/{slug}/'
    structured={'@context':'https://schema.org','@graph':[{'@type':'Person','@id':BASE+route+'#player','name':name,'url':BASE+route}, {'@type':'WebPage','name':name+' WNBA Stats & Player Profile','url':BASE+route,'about':{'@id':BASE+route+'#player'}}, {'@type':'BreadcrumbList','itemListElement':[{'@type':'ListItem','position':1,'name':'Home','item':BASE+'/'},{'@type':'ListItem','position':2,'name':'WNBA players','item':BASE+'/wnba/'},{'@type':'ListItem','position':3,'name':name,'item':BASE+route}]}]}
    return document(name+' WNBA Stats, Teams & Player Profile | Full Court Buckets',f'{name} WNBA season statistics, regular-season and playoff records, team information and recent game logs. Available coverage from 2008 onward.',route,body,structured)

def directory_page(index):
    entries=index['players']; cards=[]
    for p in sorted(entries,key=lambda p:p['name'].casefold()):
        state='Listed active' if p.get('active_in_provider_feed') else 'Archive profile'
        team=tname(p['current_team']) if p.get('current_team') else 'Historical player records'
        query=' '.join([p['name'],team,state]).casefold()
        cards.append(f'<a class="player-card" href="/wnba/{p["slug"]}/" data-search="{esc(query)}" data-active="{str(bool(p.get("active_in_provider_feed"))).lower()}"><span class="eyebrow">{state}</span><h2>{esc(p["name"])}</h2><p>{esc(team)}</p><span class="small">View profile →</span></a>')
    body=f'''<div class="breadcrumbs"><a href="/">Home</a><span>/</span><span>WNBA players</span></div><section class="directory-header"><p class="eyebrow">Full Court Buckets · The player archive</p><h1>WNBA players.<br><span class="gradient">Past and present.</span></h1><p>{len(entries)} profiles. Available statistics from 2008 onward.</p><p class="muted small">Snapshot checked {esc(timestamp(index.get('checked_at')))}. Archive status is not a retirement designation.</p></section><div class="directory-filters js-only"><label for="player-search">Find a player<input type="search" id="player-search" placeholder="Search a player or team" autocomplete="off"></label><label for="active-filter">Show<select id="active-filter"><option value="all">All profiles</option><option value="true">Listed active</option><option value="false">Archive profiles</option></select></label></div><p class="small muted" id="result-count" role="status">{len(entries)} profiles</p><div class="player-grid">{''.join(cards)}</div><p id="no-players" hidden>No players match your search.</p>'''
    return document('WNBA Player Stats & Profiles, 2008 Onward | Full Court Buckets','Browse WNBA player profiles, season statistics, team information and recent game logs. Available coverage begins in 2008.','/wnba/',body)

def build(root: Path):
    data=root/'data/wnba'
    index=json.loads((data/'players-index.json').read_text())
    status=json.loads((data/'status.json').read_text())
    if status.get('status')!='ok' or not index.get('players'):
        raise BuildError('No successful nonempty import is available.')
    files={}; ids=set(); slugs=set()
    for entry in index['players']:
        slug=entry.get('slug','')
        if not SLUG.fullmatch(slug) or slug in slugs or entry.get('id') in ids:
            raise BuildError('Unsafe, missing, or duplicate identity in directory.')
        slugs.add(slug); ids.add(entry['id'])
        profile=json.loads((data/'players'/f'{slug}.json').read_text())
        validate(profile,slug)
        if profile['player']['id']!=entry['id']:
            raise BuildError('Profile does not match its directory identity.')
        files[f'wnba/{slug}/index.html']=profile_page(profile)
    files['wnba/index.html']=directory_page(index)
    for name in ('players.css','players.js'):
        files['wnba/assets/'+name]=(root/'automation'/name).read_text()
    locations=['/wnba/']+[f'/wnba/{slug}/' for slug in sorted(slugs)]
    files['player-sitemap.xml']='<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join(f'<url><loc>{BASE}{loc}</loc></url>' for loc in locations)+'</urlset>\n'
    homepage=root/'index.html'
    if homepage.exists():
        text=homepage.read_text()
        match=re.search(r'<nav\b[^>]*>.*?</nav>',text,re.S)
        if 'Full Court Buckets' not in text or not match:
            raise BuildError('Homepage safety check failed; not changing navigation.')
        if not re.search(r'href=[\'\"](?:https://fullcourtbuckets.com)?/wnba/',match.group()):
            text=text[:match.end()-6]+'<a href="/wnba/">Players</a>'+text[match.end()-6:]
            files['index.html']=text
    robots=root/'robots.txt'
    robots_text=robots.read_text() if robots.exists() else 'User-agent: *\nAllow: /\n'
    sitemap='Sitemap: '+BASE+'/player-sitemap.xml'
    if sitemap not in robots_text:
        files['robots.txt']=robots_text.rstrip()+'\n'+sitemap+'\n'
    report={'status':'ok','profile_count':len(slugs),'data_checked_at':index.get('checked_at'), 'source':'BALLDONTLIE','coverage_start':2008,'complete_career_totals':False,'news_connected':False,'transactions_connected':False,'directory':'/wnba/'}
    files['data/wnba/site-build.json']=json.dumps(report,indent=2)+'\n'
    # All profiles are validated and rendered before any existing page is replaced.
    changes=0
    for relative,content in files.items():
        path=root/relative
        if path.exists() and path.read_text()==content:
            continue
        path.parent.mkdir(parents=True,exist_ok=True)
        temporary=path.with_suffix(path.suffix+'.tmp')
        temporary.write_text(content)
        temporary.replace(path)
        changes+=1
    print(f'Built {len(slugs)} static player profiles and directory; {changes} files changed.')
    return len(slugs)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    build(args.root)
