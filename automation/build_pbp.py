#!/usr/bin/env python3
"""Build a WNBA Finals play-by-play page at /wnba/finals/2026/game-<n>/play-by-play/.

  python3 automation/build_pbp.py --game-id 401918306 --game-json data/games/2026-10-19-atl-gs.json

Without a game JSON (or before the game is final) the page is a placeholder with no plays.
With one, every scoring play must rebuild the running score and the final, or nothing is written
(exit 2). Player counts use box-score values where play text disagrees. No feed is named on the page.
"""
from __future__ import annotations
import argparse, datetime as dt, html, json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
import site_nav  # noqa: E402
import social_meta  # noqa: E402
import seo_meta  # noqa: E402

E = html.escape
CONF = ROOT / 'data/pbp-games.json'
BASE = 'https://fullcourtbuckets.com'
CATS = ['made 2PT', 'missed 2PT', 'made 3PT', 'missed 3PT', 'made FT', 'missed FT', 'rebound', 'turnover', 'foul', 'substitution', 'timeout', 'other']


class ScoreCheckError(Exception):
    pass


def qname(n): return f"Q{n}" if n <= 4 else f"OT{n-4}"
def url_for(n): return f"/wnba/finals/2026/game-{n}/play-by-play/"


def derive(d, live=False):
    A = d['away']['abbreviation']
    roster = sorted([p for p in d.get('players', []) if not p.get('did_not_play')], key=lambda p: -len(p['name']))
    plays = sorted([dict(p) for p in d.get('plays') or []], key=lambda p: p['order'])
    if not plays:
        raise ScoreCheckError('no plays in game JSON')
    a = h = 0; prev = 0
    for p in plays:
        t = p.get('text') or ''; ty = (p.get('type') or '').replace('\n', ' '); p['type'] = ty
        before = a - h
        if p.get('scoring_play'):
            if p['team'] == A: a += p['score_value']
            else: h += p['score_value']
            if (a, h) != (p['away_score'], p['home_score']):
                raise ScoreCheckError(f"play {p['order']}: rebuilt {a}-{h}, feed {p['away_score']}-{p['home_score']}")
        p['a'], p['h'] = a, h
        l = (a > h) - (a < h); p['flag'] = ''
        if p.get('scoring_play'):
            if l == 0 and prev != 0: p['flag'] = 'tie'
            elif l != 0 and prev != 0 and l != prev: p['flag'] = 'lead change'
            if l != 0: prev = l
        low = f' {t.lower()} '
        blk = re.match(r"(.+?) blocks (.+?) ?'s ", t)
        if blk: cat = 'missed ' + ('3PT' if 'three point' in low else '2PT')
        elif ' makes ' in low or ' misses ' in low:
            kind = 'FT' if 'free throw' in low else ('3PT' if ('three point' in low or (p.get('scoring_play') and p['score_value'] == 3)) else '2PT')
            cat = ('made ' if ' makes ' in low else 'missed ') + kind
        elif 'Rebound' in ty: cat = 'rebound'
        elif 'Turnover' in ty or 'Traveling' in ty or 'turnover' in low: cat = 'turnover'
        elif 'Foul' in ty: cat = 'foul'
        elif ty == 'Substitution': cat = 'substitution'
        elif 'Timeout' in ty: cat = 'timeout'
        else: cat = 'other'
        p['cat'] = cat
        inv = sorted((t.find(r['name']), r['name']) for r in roster if r['name'] in t)
        p['players'] = [n for _, n in inv]
        p['player'] = inv[0][1] if inv and inv[0][0] == 0 else None
        if blk: p['player'] = blk.group(2).strip()
        c = p.get('clock') or '0'
        s = int(c.split(':')[0]) * 60 + float(c.split(':')[1]) if ':' in c else float(c)
        p['clutch'] = p['period'] >= 4 and s <= 300 and abs(before) <= 5
    if live:  # final score check runs on Final; live = running score must match the scoring plays
        if (a, h) != (d['away']['score'], d['home']['score']):
            raise ScoreCheckError(f"live rebuilt {a}-{h}, page score {d['away']['score']}-{d['home']['score']}")
        return plays, roster
    if (a, h) != (d['away']['score'], d['home']['score']):
        raise ScoreCheckError(f"final rebuilt {a}-{h}, box {d['away']['score']}-{d['home']['score']}")
    return plays, roster


def player_counts(plays, roster):
    out, overrides = {}, []
    for r in roster:
        n = r['name']; m = dict(team=r['team'], pts=0, **{k: 0 for k in ('2pm', '2pa', '3pm', '3pa', 'ftm', 'fta', 'reb', 'to', 'pf', 'plays')})
        for p in plays:
            if n in p['players']: m['plays'] += 1
            if p['player'] != n: continue
            c = p['cat']
            for k, key in (('2PT', '2p'), ('3PT', '3p'), ('FT', 'ft')):
                if c.endswith(k):
                    m[key + 'a'] += 1
                    if c.startswith('made'): m[key + 'm'] += 1; m['pts'] += p['score_value']
            m['reb'] += c == 'rebound'; m['to'] += c == 'turnover'; m['pf'] += c == 'foul'
        for k, bk in (('3pa', 'fg3a'), ('3pm', 'fg3m'), ('ftm', 'ftm'), ('fta', 'fta'), ('pts', 'pts'), ('reb', 'reb'), ('to', 'turnovers'), ('pf', 'fouls')):
            if bk in r and m[k] != r[bk]:
                overrides.append(f"{n} {k.upper()}: {m[k]} in play text, {r[bk]} in box score"); m[k] = r[bk]
        if 'fga' in r: m['2pa'], m['2pm'] = r['fga'] - m['3pa'], r['fgm'] - m['3pm']
        out[n] = m
    return out, overrides


def social_tags(page):
    """Same twitter/og tags social_meta.py adds, so a rebuild matches the published page."""
    return social_meta.social_block(page, social_meta.default_image_url(), social_meta.DEFAULT_ALT, social_meta.W, social_meta.H)


def shell_parts(title, desc, path, date):
    src = (ROOT / 'news/dream-valkyries-finals-game-1-recap/index.html').read_text(encoding='utf-8')
    head = social_meta.BLOCK_RE.sub('', src[:src.index('</head>')])
    for pat in (r'<title>.*?</title>', r'<meta name="description"[^>]*>', r'<link rel="canonical"[^>]*>', r'<meta property="(?:og|article):[^"]*"[^>]*>',
                r'<meta name="twitter:[^"]*"[^>]*>', r'<script type="application/ld\+json">.*?</script>', r'<link rel="preload"[^>]*>'):
        head = re.sub(pat, '', head, flags=re.S)
    url = BASE + path
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "Dataset", "name": title, "description": desc, "url": url, "license": "https://creativecommons.org/licenses/by/4.0/",
         "creator": {"@type": "Organization", "name": "Full Court Buckets", "url": BASE + "/"}, "author": {"@type": "Person", "name": "Ryan Moalemi", "url": BASE + "/authors/ryan-moalemi/"},
         "dateModified": date, "isAccessibleForFree": True},
        {"@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "position": 1, "name": "Home", "item": BASE + "/"},
         {"@type": "ListItem", "position": 2, "name": "WNBA", "item": BASE + "/wnba/"}, {"@type": "ListItem", "position": 3, "name": title, "item": url}]}]}
    meta = (f'<title>{E(seo_meta.fit_title(title.replace(": ", ", ", 1)))}</title><meta name="description" content="{E(seo_meta.pbp_description(desc))}"><link rel="canonical" href="{url}">'
            f'<meta property="og:type" content="website"><meta property="og:title" content="{E(title)}"><meta property="og:description" content="{E(desc)}">'
            f'<meta property="og:url" content="{url}"><meta property="og:image" content="{BASE}/images/articles/dream-valkyries-finals-game-1-recap/hero-1200.webp">'
            f'<meta name="twitter:card" content="summary_large_image"><link rel="stylesheet" href="/assets/pbp.css">'
            f'<script type="application/ld+json">{json.dumps(ld)}</script>')
    head = head + meta + '</head>'
    body_open = src[src.index('</head>') + 7: src.index('<main')]
    body_open = re.sub(r'<div class="ticker fcb-now".*?</div></div></div>', site_nav.now_bar_html(), body_open, count=1, flags=re.S)
    byline = re.search(r'<div class="byline-row">.*?</time></div>', src, re.S).group(0)
    byline = re.sub(r'<time class="article-date" datetime="[^"]*">[^<]*</time>', f'<time class="article-date" datetime="{date}">{dt.date.fromisoformat(date):%B %-d, %Y}</time>', byline)
    foot = src[src.index('<footer'):]
    return head, body_open, byline, foot


# Ryan's standing rule: live play-by-play pages update every 30 seconds during a game.
LIVE_UPDATE_SECONDS = 30
LIVE_NOTE = f'Live: updates every {LIVE_UPDATE_SECONDS} seconds.'
LIVE_REFRESH = ('<script id="pbp-live-refresh">setInterval(function(){if(!document.hidden)location.reload()},'
                f'{LIVE_UPDATE_SECONDS * 1000});</script>')


def with_live_refresh(page):
    """Pre-game and live pages reload themselves every LIVE_UPDATE_SECONDS; final pages do not."""
    return page.replace('</body>', LIVE_REFRESH + '</body>', 1) if '</body>' in page else page + LIVE_REFRESH


def build(game_id, game_json=None, today=None, live=False):
    conf = json.loads(CONF.read_text())
    g = conf['games'][game_id]; n = g['number']; A, H = conf['away'], conf['home']; NAME = conf['names']
    path = url_for(n)
    d = None
    gj = game_json or g.get('game_json')
    if gj and (ROOT / gj).exists():
        d = json.loads((ROOT / gj).read_text())
        if d.get('away', {}).get('abbreviation') == H and d.get('home', {}).get('abbreviation') == A:
            # Feed sides flipped (e.g. Atlanta home games): keep the series orientation A/H used by the page.
            d['away'], d['home'] = d['home'], d['away']
            for p in d.get('plays') or []:
                p['away_score'], p['home_score'] = p.get('home_score'), p.get('away_score')
            for q in d.get('periods') or []:
                q['away'], q['home'] = q.get('home'), q.get('away')
        if str(d.get('espn_game_id')) != str(game_id):
            raise ScoreCheckError(f'{gj} is game {d.get("espn_game_id")}, not {game_id}')
        if d.get('status') == 'live' and live:
            pass
        elif d.get('status') != 'final':
            if d.get('plays'):  # never publish a 'not started' page once plays exist (Game 3 final-buzzer bug)
                raise ScoreCheckError(f"{gj} has {len(d['plays'])} plays but status {d.get('status')!r}: build with --live or wait for the final file")
            d = None
        else:
            live = False
    title = f"Dream vs. Valkyries play-by-play: 2026 WNBA Finals Game {n}"
    others = ' '.join(f'<a href="{url_for(x["number"])}">Game {x["number"]}</a>' for k, x in sorted(conf['games'].items(), key=lambda kv: kv[1]['number']) if k != game_id)
    links = ([f'<a href="{g["preview"]}">Game {n} preview</a>'] if g.get('preview') else []) + ([f'<a href="{g["recap"]}">Game {n} recap</a>'] if g.get('recap') else [])
    sb = lambda st, a, h: f'<div class="sb"><div class="tm">{NAME[A]} <b>{a}</b></div><span class="st">{st}</span><div class="tm h"><b>{h}</b> {NAME[H]}</div></div>'
    sbf = g['series_before']
    if not (g.get('tv') and g.get('stream')):
        raise ValueError(f"pbp-games.json game {n} needs both 'tv' and 'stream' (where-to-watch must list TV and Streaming)")
    bline = f'<p class="note broadcast-line"><b>Where to watch:</b> TV: {E(g["tv"])}. Streaming: {E(g["stream"])}.</p>'
    def series_text(w):
        lead = max(w, key=w.get); lo = min(w, key=w.get)
        return 'Series tied ' + f"{w[lead]}-{w[lo]}" if w[lead] == w[lo] else f"{NAME[lead]} lead {w[lead]}-{w[lo]}"
    if d is None:
        desc = f"Play-by-play for Game {n} of the 2026 WNBA Finals, {'Valkyries at Dream' if 'State Farm' in g['venue'] else 'Dream at Valkyries'}, {g['tip']}, {g['venue']}. {LIVE_NOTE}"
        head, bo, byline, foot = shell_parts(title, desc, path, g['date'])
        main = (f'<main class="shell article-wrap pbp"><article class="article"><h1>{E(title)}</h1>{byline}'
                f'{bline}<p class="thru">Game {n} has not started. {LIVE_NOTE}</p>'
                f'<div class="pbp-panel" data-fcb-data-table>{sb("NOT STARTED", "&ndash;", "&ndash;")}'
                f'<p class="pbp-wait">Tip: {E(g["tip"])}, {E(g["venue"])}<br>{E(series_text(sbf))}<br><b>{LIVE_NOTE}</b></p></div>'
                f'<p class="note">{" · ".join(links + ["Other games: " + others])}</p></article></main>')
        return path, with_live_refresh(social_tags(head + '\n' + bo + main + '\n' + foot))
    plays, roster = derive(d, live)
    pc, overrides = player_counts(plays, roster)
    winner = A if d['away']['score'] > d['home']['score'] else H
    after = dict(sbf)
    if not live: after[winner] += 1
    lc = sum(p['flag'] == 'lead change' for p in plays); ties = sum(p['flag'] == 'tie' for p in plays)
    runs, cur = [], None
    for p in plays:
        if not p.get('scoring_play'): continue
        if cur and cur['team'] == p['team']: cur['pts'] += p['score_value']; cur['endp'] = p
        else:
            if cur: runs.append(cur)
            cur = {'team': p['team'], 'pts': p['score_value'], 'sp': p, 'endp': p}
    runs.append(cur)
    runs = sorted([r for r in runs if r['pts'] >= 6], key=lambda r: -r['pts'])
    rows = [{'o': p['order'], 'q': p['period'], 'c': p['clock'], 't': p['team'] or '', 'x': p['text'], 'a': p['a'], 'h': p['h'], 'k': p['cat'],
             's': 1 if p.get('scoring_play') else 0, 'f': p['flag'], 'cl': 1 if p['clutch'] else 0, 'p': p['player'] or '', 'ps': p['players']} for p in plays]
    fs, fa = (d['home']['score'], NAME[H]), (d['away']['score'], NAME[A])
    hi, lo = (fs, fa) if fs[0] > fa[0] else (fa, fs)
    thru = f"Final: {hi[1]} {hi[0]}, {lo[1]} {lo[0]}, {g['date_text']}, {g['venue']}. {series_text(after)}. {len(rows)} plays, newest first. {lc} lead changes, {ties} ties."
    if live:
        from zoneinfo import ZoneInfo
        now = (today or dt.datetime.now(ZoneInfo('America/Los_Angeles')))
        stamp = now.strftime('%-I:%M ') + ('a.m.' if now.hour < 12 else 'p.m.') + ' PT'
        lp, lc_ = d.get('last_play_period') or plays[-1]['period'], d.get('last_play_clock') or plays[-1]['clock']
        where = f"{qname(int(lp))} {lc_}" if lp else ''
        thru = (f"{NAME[A]} {d['away']['score']}, {NAME[H]} {d['home']['score']}, {where}. {series_text(after)} entering Game {n}. "
                f"Updated {stamp}. {LIVE_NOTE} {len(rows)} plays so far, newest first.")
    desc = f"Every play from Game {n} of the 2026 WNBA Finals ({hi[1]} {hi[0]}, {lo[1]} {lo[0]}): search by player, team, quarter, runs and clutch time, and download CSV or JSON."
    head, bo, byline, foot = shell_parts(title, desc, path, g['date'])
    per = d['periods']
    qrow = lambda t, k: f"<tr><td>{NAME[t]}</td>" + ''.join(f"<td>{x[k]}</td>" for x in per) + f"<td>{d[k]['score']}</td></tr>"
    popt = ''.join(f'<option value="{E(nm)}">{E(nm)} ({pc[nm]["team"]})</option>' for nm in sorted(pc, key=lambda x: (pc[x]['team'], x.split()[-1])))
    static = ''.join(f'<tr id="play-{r["o"]}" class="{"sc " + r["t"] if r["s"] else ""}"><td class="c">{qname(r["q"])} {E(r["c"] or "")}</td><td class="t">{E(r["t"])}</td><td class="x">{E(r["x"])}</td><td class="s">{r["a"]}-{r["h"]}</td><td class="l"><a href="#play-{r["o"]}">#</a></td></tr>' for r in reversed(rows))
    ptab = ''.join(f'<tr><td><button class="lnk" data-player="{E(nm)}">{E(nm)}</button></td><td>{m["team"]}</td><td>{m["pts"]}</td><td>{m["2pm"]}-{m["2pa"]}</td><td>{m["3pm"]}-{m["3pa"]}</td><td>{m["ftm"]}-{m["fta"]}</td><td>{m["reb"]}</td><td>{m["to"]}</td><td>{m["pf"]}</td><td>{m["plays"]}</td></tr>' for nm, m in sorted(pc.items(), key=lambda x: (x[1]['team'], -x[1]['pts'])))
    opt = lambda v, t: f'<option value="{E(v)}">{E(t)}</option>'
    def rlabel(r): return f"{r['pts']}-0 {NAME[r['team']]}, {qname(r['sp']['period'])} {r['sp']['clock']} to {qname(r['endp']['period'])} {r['endp']['clock']}"
    ov = ('; '.join(overrides) + '. ') if overrides else ''
    main = f"""<main class="shell article-wrap pbp"><article class="article"><h1>{E(title)}</h1>{byline}
{bline}
<p class="thru">{'<span class="live-badge">LIVE</span> ' if live else ''}{E(thru)}</p>
<div class="pbp-panel" data-fcb-data-table>{sb(('LIVE ' + qname(int(d.get('last_play_period') or plays[-1]['period'])) + ' ' + E(str(d.get('last_play_clock') or ''))) if live else 'FINAL', d['away']['score'], d['home']['score'])}
<table class="ql"><thead><tr><th></th>{''.join(f'<th>{qname(x["period"])}</th>' for x in per)}<th>T</th></tr></thead><tbody>{qrow(A, 'away')}{qrow(H, 'home')}</tbody></table>
<button type="button" class="fbtn" id="fbtn" aria-expanded="false" aria-controls="flt">Filter</button><form class="flt" id="flt" role="search" aria-label="Filter plays" onsubmit="return false">
<input type="search" name="q" placeholder="Search plays, e.g. Reese steal" aria-label="Search play text">
<select name="player" aria-label="Player"><option value="">All players</option>{popt}</select>
<select name="team" aria-label="Team"><option value="">Both teams</option>{opt(A, NAME[A])}{opt(H, NAME[H])}</select>
<select name="type" aria-label="Play type"><option value="">All play types</option>{opt('shots', 'All shots')}{opt('made', 'Made shots')}{opt('missed', 'Missed shots')}{''.join(opt(c, c[0].upper() + c[1:]) for c in CATS)}</select>
<select name="period" aria-label="Quarter"><option value="">All quarters</option>{''.join(opt(str(x), qname(x)) for x in sorted({r['q'] for r in rows}))}</select>
<select name="run" aria-label="Scoring run"><option value="">All game</option>{''.join(opt(f"{r['sp']['order']}-{r['endp']['order']}", 'Run: ' + rlabel(r)) for r in runs)}</select>
<div class="chips"><label><input type="checkbox" name="scoring"> Scoring only</label><label><input type="checkbox" name="swing"> Lead changes and ties</label><label><input type="checkbox" name="clutch"> Clutch</label><label><input type="checkbox" name="oldest"> Oldest first</label></div>
<div class="bar"><span id="count" role="status">{len(rows)} plays</span><span class="acts"><button type="button" id="csv">CSV</button><button type="button" id="json">JSON</button><button type="button" id="reset">Reset</button></span></div></form>
<div class="tw"><table class="pl" id="pl"><thead><tr><th>Time</th><th>Team</th><th>Play</th><th>{A}-{H}</th><th><span class="vh">Link</span></th></tr></thead><tbody>{static}</tbody></table></div></div>
{'' if live else f'<h2>Player play counts</h2><p class="note">Tap a name to filter the plays.</p><div class="tw"><table class="pc"><thead><tr><th>Player</th><th>Team</th><th>PTS</th><th>2P</th><th>3P</th><th>FT</th><th>REB</th><th>TO</th><th>PF</th><th>Plays</th></tr></thead><tbody>{ptab}</tbody></table></div>'}
<p class="note">{' · '.join(links + ['Other games: ' + others])}</p>
<h2>Methods</h2><p class="note">The running score is rebuilt from the scoring plays and checked against every scoring play and the final before this page is published. Player counts come from the plays and are checked against the official box score; where they differ, the box score value is shown. {E(ov)}"Plays" counts every play that names the player. Clutch: last 5 minutes of the 4th quarter or overtime with the score within 5 points before the play. Lead changes, ties and runs (6 or more unanswered points) are computed from scoring plays. Data: Full Court Buckets, licensed <a href="https://creativecommons.org/licenses/by/4.0/" rel="license">CC BY 4.0</a>.</p>
</article></main><div id="toast" role="status" hidden></div>
<script>window.PBP={json.dumps({'rows': rows, 'q': {r['q']: qname(r['q']) for r in rows}, 'url': BASE + path, 'title': title, 'file': f'fcb-2026-finals-game-{n}-plays', 'an': NAME[A], 'hn': NAME[H], 'date': g['date_text']})};</script><script src="/assets/pbp.js" defer></script>"""
    page = social_tags(head + '\n' + bo + main + '\n' + foot)
    return path, (with_live_refresh(page) if live else page)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('--game-id')
    ap.add_argument('--all', action='store_true',
                    help='rebuild every configured game page; pages copy the recap shell, so rerun after news pages change')
    ap.add_argument('--game-json')
    ap.add_argument('--live', action='store_true', help='game in progress: LIVE badge, running score check only')
    a = ap.parse_args(argv)
    if a.all:
        rc = 0
        for gid in json.loads(CONF.read_text())['games']:
            rc = max(rc, main(['--game-id', gid]))
        return rc
    if not a.game_id:
        ap.error('--game-id or --all is required')
    try:
        path, out = build(a.game_id, a.game_json, live=a.live)
    except ScoreCheckError as e:
        print(f'SCORE CHECK FAILED, page not written: {e}', file=sys.stderr); return 2
    dest = ROOT / path.strip('/') / 'index.html'
    dest.parent.mkdir(parents=True, exist_ok=True); dest.write_text(out, encoding='utf-8')
    if a.game_json and not a.live:
        conf = json.loads(CONF.read_text()); conf['games'][a.game_id]['game_json'] = a.game_json
        CONF.write_text(json.dumps(conf, indent=2) + '\n')
    print(f'wrote {dest.relative_to(ROOT)} ({"live" if "live-badge" in out else "final" if "data-player" in out else "placeholder"})')
    return 0


if __name__ == '__main__':
    _rc = main()
    if '--live' not in sys.argv:
        import search_index; search_index.write()  # keep site search current
    sys.exit(_rc)
