"""Fill drafting team (player-draft.json) and 1997-2009 conference finish (team-history.json).

Sources: WNBA.com draft boards (wnba.com/draft/<year>/board, 2016 on) and WNBA.com draft
result pages (wnba.com/draft/<year>, 2009-2015; wnba.com/draft/2015/draftboard for round 2).
Finish 1997-2009: archived WNBA.com conference standings via the Wayback Machine where a
final snapshot exists; Basketball-Reference only for seasons with no archived official table.
Run once by hand; the results are saved in the data files.
"""
import html, json, re, sys, time, unicodedata, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = {'User-Agent': 'Mozilla/5.0'}

def get(u):
    for i in range(3):
        try:
            return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40).read().decode('utf-8', 'ignore')
        except Exception:
            time.sleep(2)
    raise RuntimeError(u)

def norm(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s.casefold()) if c.isalpha())

def nd(t):
    return json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', t, re.S).group(1))['props']['pageProps']

CITY_2015 = {'Seattle': 'Seattle Storm', 'Chicago': 'Chicago Sky', 'San Antonio': 'San Antonio Stars',
             'Connecticut': 'Connecticut Sun', 'New York': 'New York Liberty', 'Phoenix': 'Phoenix Mercury',
             'Washington': 'Washington Mystics', 'Tulsa': 'Tulsa Shock', 'Los Angeles': 'Los Angeles Sparks',
             'Atlanta': 'Atlanta Dream', 'Indiana': 'Indiana Fever', 'Minnesota': 'Minnesota Lynx'}

def team_names(year):
    data = json.loads(get(f'https://www.wnba.com/api/schedule?season={year}&regionId=1'))
    out = {}
    for d in data['leagueSchedule']['gameDates']:
        for g in d.get('games') or []:
            for t in (g['homeTeam'], g['awayTeam']):
                out[t['teamId']] = f'{t.get("teamCity")} {t.get("teamName")}'.strip()
    return out

def fill_draft():
    path = ROOT / 'data/wnba/player-draft.json'
    doc = json.loads(path.read_text())
    boards, names, pages = {}, {}, {}
    filled = 0
    for p in doc['players'].values():
        y = p.get('year')
        p.pop('drafted_by', None); p.pop('drafted_by_source', None)
        if not y:
            continue
        first = norm(p['player'].split()[0])
        if y >= 2016:
            if y not in boards:
                boards[y] = nd(get(f'https://www.wnba.com/draft/{y}/board'))['draftRounds']
                names[y] = team_names(y)
            rounds = boards[y]
            idx = p['pick'] - sum(len(r['picks']) for r in rounds[:p['round'] - 1])
            hit = [x for x in rounds[p['round'] - 1]['picks'] if x['pick'] == idx]
            if hit and norm(hit[0]['firstName'].split()[0]) == first and hit[0].get('teamExternalId') in names[y]:
                p['drafted_by'] = names[y][hit[0]['teamExternalId']]
                p['drafted_by_source'] = f'https://www.wnba.com/draft/{y}/board'
        else:
            urls = [f'https://www.wnba.com/draft/{y}'] + ([f'https://www.wnba.com/draft/{y}/draftboard'] if y == 2015 else [])
            for url in urls:
                if url not in pages:
                    pages[url] = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '\n', get(url))))
                txt = pages[url]
                last = p['player'].split()[-1].split('-')[0]
                m = re.search(r'(?:^|\s)%d\. ([A-Z][A-Za-z\. ]+?)\s?(?:\(from [^)]*\))?\s?: ?[A-Za-z]+ [A-Za-z\'\- ]*%s' % (p['pick'], re.escape(last)), txt)
                if not m:
                    m = re.search(r'\(%d\) ([A-Z][A-Za-z\. ]+?)(?: \(from [^)]*\))?, [A-Za-z]+ %s' % (p['pick'], re.escape(last)), txt)
                if m:
                    team = m.group(1).strip()
                    p['drafted_by'] = CITY_2015.get(team, team)
                    p['drafted_by_source'] = url
                    break
        if p.get('drafted_by'):
            filled += 1
        else:
            print('no team:', p['player'], y, p['round'], p['pick'], file=sys.stderr)
    doc['note'] = ('Draft year, round and overall pick as published on each player page. Drafting team from the '
                   'WNBA.com draft board for that year (wnba.com/draft/<year>/board, 2016 on) or the WNBA.com draft '
                   'results page (wnba.com/draft/<year>, 2009-2015), matched on year, round and pick. It is the team '
                   'that made the pick, under its name that year.')
    path.write_text(json.dumps(doc, indent=2) + '\n')
    return filled

WAYBACK = {
    1998: 'https://web.archive.org/web/20010820083311/http://www.wnba.com/standings.html',
    2002: 'https://web.archive.org/web/20021204210544/http://www.wnba.com/standings/by_conference.html',
    2003: 'https://web.archive.org/web/20031008043936/http://www.wnba.com/standings/by_conference.html',
    2004: 'https://web.archive.org/web/20041206211525/http://www.wnba.com/standings/by_conference.html',
    2007: 'https://web.archive.org/web/20071001152424/http://www.wnba.com/standings/team_record_comparison/conferenceNew_Std_Cnf.html',
    2008: 'https://web.archive.org/web/20081217022011/http://www.wnba.com/standings/team_record_comparison/conferenceNew_Std_Cnf.html',
    2009: 'https://web.archive.org/web/20091002080655/http://www.wnba.com/standings/team_record_comparison/conferenceNew_Std_Cnf.html',
}

def ordinal(n):
    return f'{n}' + ('th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th'))

def fill_finish(parsed_path):
    parsed = json.loads(Path(parsed_path).read_text())
    path = ROOT / 'data/wnba/team-history.json'
    doc = json.loads(path.read_text())
    counts = {'official': 0, 'bref': 0, 'blank': 0, 'mismatch': []}
    for rows in doc['teams'].values():
        for r in rows:
            y = r['season']
            if y >= 2010:
                continue
            r['finish'] = None; r.pop('finish_source', None); r.pop('finish_source_label', None)
            table = parsed.get(str(y)) or {}
            for conf, teams in table.items():
                for i, (name, w, l) in enumerate(teams, 1):
                    name = name.replace('Streak ', '')
                    if (r.get('team_name') or '').startswith(name) or name == r.get('team_name'):
                        if (w, l) != (r.get('wins'), r.get('losses')):
                            counts['mismatch'].append((y, r['team_name'], (w, l), (r.get('wins'), r.get('losses'))))
                        r['finish'] = f'{ordinal(i)} in the {"East" if conf == "Eastern" else "West"}'
                        if y in WAYBACK:
                            r['finish_source'] = WAYBACK[y]; r['finish_source_label'] = 'WNBA.com standings (archived)'
                            counts['official'] += 1
                        else:
                            r['finish_source'] = f'https://www.basketball-reference.com/wnba/years/{y}.html'
                            r['finish_source_label'] = 'Basketball-Reference (no official table found)'
                            counts['bref'] += 1
            if not r['finish']:
                counts['blank'] += 1
    doc['note'] = ('W-L and finish from wnba.com/standings when published (2010 on). Before 2010 the W-L is counted '
                   'from final regular-season scores in the league schedule feed, and the finish is the conference '
                   'rank from archived WNBA.com standings pages (Wayback Machine) for 1998, 2002-2004 and 2007-2009, '
                   'or from Basketball-Reference for 1997, 1999-2001, 2005 and 2006, where no archived official '
                   'table was found. Each row names its finish source.')
    path.write_text(json.dumps(doc, indent=2) + '\n')
    return counts

if __name__ == '__main__':
    print('draft teams filled:', fill_draft())
    print(fill_finish(sys.argv[1]))
