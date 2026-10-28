#!/usr/bin/env python3
"""Fill every marked time-sensitive section on the site from data files.

Marker convention (see AGENTS.md, "Dynamic sections"):

    <div data-fcb-dynamic="series-status" data-fcb-source="data/games data/finals-schedule.json"
         data-fcb-updated="2026-10-26">...</div><!--/fcb-dynamic-->

* data-fcb-dynamic names the renderer (RENDERERS below).
* data-fcb-source lists the data files the section is built from.
* data-fcb-updated is the date of the latest final the section reflects.
* Optional data-fcb-team="GS" renders from one team's point of view.

The element is any tag; its whole body up to the closing tag that sits right before
<!--/fcb-dynamic--> is owned by this script. Never hand-edit inside a marked section.

    python3 automation/dynamic_sections.py          # rewrite every marked section
    python3 automation/dynamic_sections.py --check  # fail on stale sections or stale wording

Runs in fcb-wnba.yml (daily build and the post-game dispatch from fcb-game-stats.yml)
and in publish-articles.yml.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import finals_series  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
E = html.escape
END = '<!--/fcb-dynamic-->'
SECTION = re.compile(
    r'<(?P<tag>[a-z][a-z0-9]*)(?P<attrs>[^>]*\sdata-fcb-dynamic="(?P<kind>[a-z0-9-]+)"[^>]*)>'
    r'(?P<body>.*?)</(?P=tag)>' + re.escape(END), re.S)
SKIP_DIRS = {'.git', 'node_modules', 'automation', 'data', 'assets', 'images'}
TEAM_NAMES = {'GS': 'Golden State', 'ATL': 'Atlanta'}
MONTHS = ['Jan.', 'Feb.', 'March', 'April', 'May', 'June', 'July', 'Aug.', 'Sept.', 'Oct.', 'Nov.', 'Dec.']


def _day(iso: str) -> str:
    y, m, d = (int(x) for x in iso.split('-'))
    return f'{MONTHS[m - 1]} {d}'


def _articles(root: Path) -> list[dict]:
    try:
        return json.loads((root / 'articles.json').read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return []


def _href(root: Path, pattern: str) -> str:
    rx = re.compile(pattern)
    for article in _articles(root):
        if rx.search(article.get('slug') or ''):
            return article.get('url') or f"/news/{article['slug']}/"
    return ''


def recap_href(root: Path, n: int) -> str:
    return _href(root, rf'finals-game-{n}-recap$')


def preview_href(root: Path, n: int) -> str:
    return _href(root, rf'finals-game-{n}-preview')


def pbp_href(root: Path, season, n: int) -> str:
    path = f'/wnba/finals/{season}/game-{n}/play-by-play/'
    return path if (root / path.strip('/') / 'index.html').exists() else ''


def _a(href: str, text: str) -> str:
    return f'<a href="{E(href)}">{E(text)}</a>' if href else E(text)


def _status_line(s: dict) -> str:
    lead, trail = s['teams'][0], s['teams'][-1]
    if s['champion']:
        return f"The {lead['full_name']} won the {s['season']} WNBA championship, {lead['wins']}-{trail['wins']}."
    if lead['wins'] == trail['wins']:
        return f"The {s['season']} WNBA Finals are tied {lead['wins']}-{trail['wins']}."
    return f"The {lead['name']} lead the {s['season']} WNBA Finals {lead['wins']}-{trail['wins']}."


def _result(s: dict, game: dict) -> str:
    names = {t['abbreviation']: t['name'] for t in s['teams']}
    w = game['winner']
    l = next(x for x in game['scores'] if x != w)
    return f"{names[w]} {game['scores'][w]}, {names[l]} {game['scores'][l]}"


def _next_line(s: dict) -> str:
    if s['champion'] or not s['upcoming']:
        return ''
    g = s['upcoming'][0]
    when = ', '.join(x for x in (g.get('day'), g.get('time')) if x)
    watch = '. '.join(x for x in (f"TV: {g['tv']}" if g.get('tv') else '', f"Streaming: {g['stream']}" if g.get('stream') else '') if x)
    return f"Next: Game {g['game']}, {when}, at {g['arena']}" + (f" ({watch})" if watch else '') + '.'


def render_series_status(root: Path, s: dict, attrs: dict) -> str:
    """One-paragraph series summary with each game's result and recap link."""
    team = attrs.get('data-fcb-team')
    parts = []
    for game in s['games']:
        label = _a(recap_href(root, game['game']), f"Game {game['game']}")
        if team:
            verb = 'won' if game['winner'] == team else 'lost'
            score = game['scores']
            them = next(x for x in score if x != team)
            hi, lo = max(score[team], score[them]), min(score[team], score[them])
            parts.append(f"{verb} {label} {hi}-{lo} on {_day(game['date'])}")
        else:
            parts.append(f"{label}: {E(_result(s, game))} ({_day(game['date'])})")
    if team:
        name = next((t['name'] for t in s['teams'] if t['abbreviation'] == team), team)
        # Team pages have a 100-200 word budget, so only the latest game is named.
        me = next(t for t in s['teams'] if t['abbreviation'] == team)
        them = next(t for t in s['teams'] if t['abbreviation'] != team)
        if s['champion']:
            state = 'won the title' if s['champion']['abbreviation'] == team else 'lost the Finals'
        else:
            state = 'lead' if me['wins'] > them['wins'] else 'trail' if me['wins'] < them['wins'] else 'are tied'
        series = f"{me['wins']}-{them['wins']}"
        status = (f"That puts them up {series} in the series." if state == 'lead' else
                  f"They now face a {series} deficit." if state == 'trail' else
                  f"The series stands at {series}." if state == 'are tied' else
                  f"They {state}, {series}.")
        body = f"The {E(name)} {parts[-1]}. " + E(status)
        if s['upcoming']:
            g = s['upcoming'][0]
            body += f" Next: Game {g['game']}, {E(_day(g['date']))}."
        return body
    else:
        body = '; '.join(parts) + '. '
    body += E(_status_line(s))
    nxt = _next_line(s)
    if nxt:
        g = s['upcoming'][0]
        extra = [x for x in (_a(preview_href(root, g['game']), f"Game {g['game']} preview") if preview_href(root, g['game']) else '',
                              _a(pbp_href(root, s['season'], g['game']), f"Game {g['game']} play-by-play") if pbp_href(root, s['season'], g['game']) else '') if x]
        body += ' ' + E(nxt) + (' ' + ' · '.join(extra) if extra else '')
    return body


def render_finals_schedule(root: Path, s: dict, attrs: dict) -> str:
    """Full series schedule table: results for played games, details for the rest."""
    rows = []
    sched = {int(g['game']): g for g in finals_series.schedule(root).get('games') or []}
    names = {t['abbreviation']: t['name'] for t in s['teams']}
    for game in s['games']:
        n = game['game']
        links = ' · '.join(x for x in (_a(recap_href(root, n), 'Recap') if recap_href(root, n) else '',
                                         _a(pbp_href(root, s['season'], n), 'Play-by-play') if pbp_href(root, s['season'], n) else '') if x)
        rows.append(f"<tr><td>Game {n}</td><td>{E(_day(game['date']))}</td>"
                    f"<td>{E(names[game['away']])} at {E(names[game['home']])}</td>"
                    f"<td>Final: {E(_result(s, game))}</td><td>{links}</td></tr>")
    for g in s['upcoming']:
        n = int(g['game'])
        home = g.get('home')
        away = next((x for x in names if x != home), '')
        info = ', '.join(x for x in (g.get('time'), g.get('arena')) if x)
        watch = '; '.join(x for x in (f"TV: {g['tv']}" if g.get('tv') else '', f"Streaming: {g['stream']}" if g.get('stream') else '') if x)
        links = ' · '.join(x for x in (_a(preview_href(root, n), 'Preview') if preview_href(root, n) else '',
                                         _a(pbp_href(root, s['season'], n), 'Play-by-play') if pbp_href(root, s['season'], n) else '') if x)
        label = f"Game {n}" + (' (if needed)' if g.get('if_needed') else '')
        rows.append(f"<tr><td>{E(label)}</td><td>{E(g.get('day') or _day(g['date']))}</td>"
                    f"<td>{E(names.get(away, away))} at {E(names.get(home, home))}</td>"
                    f"<td>{E(info)}{('. ' + E(watch)) if watch else ''}</td><td>{links}</td></tr>")
    if s['champion']:
        done = len(s['games'])
        for n in range(done + 1, s['best_of'] + 1):
            if n in sched:
                rows.append(f"<tr><td>Game {n}</td><td>{E(sched[n].get('day') or '')}</td><td></td><td>Not needed</td><td></td></tr>")
    return (f"<p>{E(_status_line(s))}</p>"
            '<div class="table-scroll"><table class="fcb-table"><thead><tr><th>Game</th><th>Date</th>'
            '<th>Matchup</th><th>Result or tip time</th><th>Links</th></tr></thead><tbody>'
            + ''.join(rows) + '</tbody></table></div>')


def series_plain_text(root: Path | None = None) -> str:
    """Plain-text series summary for places that cannot hold markup (FAQ answers, JSON-LD)."""
    root = Path(root or ROOT)
    s = finals_series.series(root)
    if not s:
        return ''
    results = '; '.join(f"Game {g['game']}, {_day(g['date'])}: {_result(s, g)}" for g in s['games'])
    return ' '.join(x for x in (_status_line(s), f'Results: {results}.', _next_line(s)) if x)


def _attendance(root: Path) -> list[dict]:
    try:
        rows = json.loads((root / 'data' / 'finals-attendance.json').read_text(encoding='utf-8'))['finals']
    except (OSError, json.JSONDecodeError, KeyError):
        return []
    return [r for r in rows if str(r.get('season')) == str(finals_series.schedule(root).get('season') or '')]


RECORD_TOTAL, RECORD_YEAR, RECORD_GAMES = 92599, 2024, 5


def render_attendance_lead(root: Path, s: dict, attrs: dict) -> str:
    rows = [r for r in _attendance(root) if r.get('attendance')]
    total = sum(int(r['attendance']) for r in rows)
    text = _status_line(s)
    if s['games']:
        g = s['games'][-1]
        text += f" Game {g['game']} ({_day(g['date'])}): {_result(s, g)}."
    if rows:
        last = rows[-1]
        text += (f" Game {last['game']} drew {int(last['attendance']):,} at {last['arena']}."
                 f" Through {len(rows)} games with reported attendance the Finals have drawn {total:,} combined.")
        if total < RECORD_TOTAL and not s['champion'] and s['upcoming']:
            need = RECORD_TOTAL - total
            text += (f" Game {s['upcoming'][0]['game']} needs {need:,} to tie the Finals series record of "
                     f"{RECORD_TOTAL:,} ({RECORD_YEAR}) and {need + 1:,} to pass it.")
        elif total > RECORD_TOTAL:
            text += f" That passes the Finals series record of {RECORD_TOTAL:,} set in {RECORD_YEAR} over {RECORD_GAMES} games."
    return f'<strong style="color:#151413 !important">{E(text)}</strong>'


def render_attendance_counter(root: Path, s: dict, attrs: dict) -> str:
    rows = [r for r in _attendance(root) if r.get('attendance')]
    if not rows:
        return 'No reported attendance yet'
    return f"Through Game {rows[-1]['game']}: {sum(int(r['attendance']) for r in rows):,} combined reported attendance"


def render_attendance_data(root: Path, s: dict, attrs: dict, body: str = '') -> str:
    """Rewrite the tracker's FCB.finals2026 list (status, attendance, source) from the data file."""
    m = re.search(r'var FCB=(\{.*\});', body, re.S)
    if not m:
        return body
    data = json.loads(m.group(1))
    by_game = {int(r['game']): r for r in _attendance(root)}
    sched = {int(g['game']): g for g in finals_series.schedule(root).get('games') or []}
    for item in data.get('finals2026') or []:
        r = by_game.get(int(item['g']))
        if r and r.get('attendance'):
            item.update(status='actual', att=int(r['attendance']), src=r.get('source_url'), venue=r.get('arena') or item.get('venue'))
        elif int(item['g']) in sched and sched[int(item['g'])].get('arena'):
            item['venue'] = sched[int(item['g'])]['arena'].split(',')[0]
    return body[:m.start(1)] + json.dumps(data, ensure_ascii=False) + body[m.end(1):]


def render_next_game(root: Path, s: dict, attrs: dict) -> str:
    if s['champion']:
        return E(_status_line(s))
    line = _next_line(s)
    if s['upcoming'] and s['upcoming'][-1].get('if_needed'):
        line += f" Game {s['upcoming'][-1]['game']} is if necessary."
    return E(line)


def render_series_line(root: Path, s: dict, attrs: dict) -> str:
    """One-sentence series status for inline intros."""
    return E(_status_line(s))


# ---- 2026 Finals attendance tracker (/news/2026-wnba-finals-ratings-tracker/) ----
# Every time-sensitive line on that page is one of these sections, so a new final in
# data/games, a new row in data/finals-attendance.json or a schedule change in
# data/finals-schedule.json moves the header, schedule and calculator on its own.

def _att_rows(root: Path) -> list[dict]:
    return sorted((r for r in _attendance(root) if r.get('attendance')), key=lambda r: int(r['game']))


def _history(root: Path) -> dict:
    return {int(g['game']): g for g in finals_series.schedule(root).get('history') or []}


def tracker_through(root: Path, s: dict) -> int:
    """Highest 2026 Finals game with both a final and a published attendance."""
    rows = _att_rows(root)
    return min(len(s['games']), int(rows[-1]['game'])) if rows else 0


def _long_day(iso: str) -> str:
    y, m, d = (int(x) for x in iso.split('-'))
    return f'{MONTHS[m - 1]} {d}, {y}'


def tracker_updated_iso(root: Path, s: dict) -> str:
    days = [s['last_day']] + [str(r.get('date') or '') for r in _att_rows(root)]
    days.append(str(finals_series.schedule(root).get('verified') or ''))
    return max(d for d in days if d)


def render_tracker_updated(root: Path, s: dict, attrs: dict) -> str:
    return f'Updated {E(_long_day(tracker_updated_iso(root, s)))}, PT'


def _scope_text(root: Path, s: dict) -> str:
    n = tracker_through(root, s)
    return f'2026 Finals: through Game {n}.' if n else '2026 Finals: no games yet.'


def _upcoming_short(root: Path, s: dict) -> str:
    if s['champion'] or not s['upcoming']:
        return ''
    g = s['upcoming'][0]
    h = _history(root).get(int(g['game']), {})
    return f"Next: Game {g['game']}, {h.get('day') or g.get('day')}, {g.get('time')} at {g.get('arena')}."


def render_tracker_scope(root: Path, s: dict, attrs: dict) -> str:
    nxt = _upcoming_short(root, s)
    after = (f" Next data update after Game {s['upcoming'][0]['game']}." if nxt else '')
    return ('<b>Data through:</b> Finals archive: through 2025. 2026 playoffs: through semifinals. '
            f'{E(_scope_text(root, s))} <span class="ver">Dataset v1</span> · <a href="#verify">Methods</a>{E(after)}'
            + (f' <span class="fcb-next">{E(nxt)}</span>' if nxt else (f' <span class="fcb-next">{E(_status_line(s))}</span>' if s['champion'] else '')))


def render_tracker_schedule(root: Path, s: dict, attrs: dict) -> str:
    """Tbody of the tracker schedule table: result and attendance from data, the rest from the schedule."""
    names = {t['abbreviation']: t['name'] for t in s['teams']}
    hist = _history(root)
    att = {int(r['game']): r for r in _att_rows(root)}
    played = {g['game']: g for g in s['games']}
    upcoming = {int(g['game']): g for g in s['upcoming']}
    rows = []
    for n in range(1, s['best_of'] + 1):
        h = hist.get(n, {})
        up = upcoming.get(n, {})
        label = f'{n}*' if (up.get('if_needed') or (n == s['best_of'] and n not in played and not up)) else str(n)
        tip = h.get('tip') or ''
        arena = up.get('arena') or h.get('arena') or ''
        arena_cell = E(arena) if arena else 'Arena TBD'
        if n in played:
            res = f'<td data-label="Result" data-state="final">{E(_result(s, played[n]))}</td>'
        elif s['champion']:
            res = '<td class="pending" data-label="Result" data-state="not-needed">Not needed</td>'
        elif up.get('if_needed'):
            res = '<td class="pending" data-label="Result" data-state="if-necessary">If necessary</td>'
        else:
            res = '<td class="pending" data-label="Result" data-state="not-played">Not played yet</td>'
        r = att.get(n)
        if r:
            a = f'<td data-label="Attendance" data-state="published">{int(r["attendance"]):,}</td>'
            box = f'<a href="{E(r.get("source_url") or "")}" rel="nofollow">Box score</a>' if r.get('source_url') else 'Not available yet'
        else:
            state, txt = (('not-needed', 'Not needed') if s['champion'] and n not in played else
                          ('if-necessary', 'If necessary') if up.get('if_needed') else ('not-published', 'Not published yet'))
            a = f'<td class="pending" data-label="Attendance" data-state="{state}">{txt}</td>'
            box = 'Not available yet'
        rows.append(f'<tr id="finals-2026-g{n}"><td data-label="Game">{label}</td><td data-label="Date">{E(h.get("day") or "")}</td>'
                    f'<td data-label="Tip">{E(tip)}</td><td data-label="Arena">{arena_cell}</td>'
                    f'<td data-label="TV / Streaming">{E(h.get("watch") or "")}</td>{res}{a}<td data-label="Box score">{box}</td></tr>')
    return '\n' + '\n'.join(rows) + '\n'


def render_tracker_sched_note(root: Path, s: dict, attrs: dict) -> str:
    sched = finals_series.schedule(root)
    src = next((g for g in sched.get('games') or [] if g.get('source')), None)
    lead, trail = s['teams'][0], s['teams'][-1]
    done = len(s['games'])
    parts = [f"Results for Games 1–{done} come from the final box scores and attendance from the published game records."]
    if s['champion']:
        parts.append(_status_line(s))
    else:
        state = f"tied {lead['wins']}-{trail['wins']}" if lead['wins'] == trail['wins'] else f"{lead['wins']}-{trail['wins']}, {lead['name']} leading"
        must = [g['game'] for g in s['upcoming'] if not g.get('if_needed')]
        maybe = [g['game'] for g in s['upcoming'] if g.get('if_needed')]
        bits = []
        if must:
            bits.append(('Game ' + ' and '.join(map(str, must))) + (' will be played' if len(must) > 1 else ' will be played'))
        if maybe:
            bits.append(('Game ' + ' and '.join(map(str, maybe))) + ' is if necessary')
        parts.append(f"With the series {state} after Game {done}, " + '; '.join(bits) + '.')
    body = E(' '.join(parts))
    if src and not s['champion']:
        body += (f' Upcoming tip times and arenas are from the official <a href="{E(src["source"])}">{E(src.get("source_label") or "WNBA.com game page")}</a>'
                 f' and WNBA.com game pages, checked {E(_long_day(sched.get("verified") or s["last_day"]))}.')
    return body


def _g6(root: Path) -> dict:
    sched = finals_series.schedule(root)
    g = next((x for x in sched.get('games') or [] if int(x['game']) == 6), None)
    if g is None:
        g = _history(root).get(6, {})
    return g


def render_tracker_g6_venue(root: Path, s: dict, attrs: dict) -> str:
    g = _g6(root)
    arena = (g.get('arena') or '').split(',')[0]
    if not arena:
        return 'Game 6 venue unconfirmed'
    src = g.get('source')
    where = f' per the <a href="{E(src)}">{E(g.get("source_label") or "WNBA.com game page")}</a>' if src else ''
    return f'Game 6 at {E(arena)}{where}'


def render_tracker_g6_cell(root: Path, s: dict, attrs: dict) -> str:
    arena = (_g6(root).get('arena') or '').split(',')[0]
    opts = ['Chase Center', 'State Farm Arena']
    if arena:
        sel = ''.join(f'<option{" selected" if o == arena else ""}>{o}</option>' for o in opts)
        return (f'<b>G6</b><span class="vn">{E(arena)}</span><select id="v5" aria-label="Game 6 venue">{sel}</select>'
                f'<span class="st" id="st5">Future · assumption</span>'
                f'<input id="a5" type="number" value="{18064 if arena == "Chase Center" else 17099}" min="0" step="1" aria-label="Game 6 attendance">')
    return ('<b>G6</b><span class="vn">Venue unconfirmed</span><select id="v5" aria-label="Game 6 venue"><option>Venue unconfirmed</option>'
            + ''.join(f'<option>{o}</option>' for o in opts) +
            '</select><span class="st" id="st5">Future · assumption</span><input id="a5" type="number" value="17099" min="0" step="1" aria-label="Game 6 attendance">')


def render_tracker_finals_row(root: Path, s: dict, attrs: dict) -> str:
    rows = _att_rows(root)
    n = tracker_through(root, s)
    vals = [int(r['attendance']) for r in rows[:n]]
    total = sum(vals)
    avg = int(total / len(vals) + 0.5) if vals else 0
    return (f'<td><b>Finals (through Game {n})</b></td><td>{len(vals)}</td><td>{total:,}</td><td>{avg:,}</td>'
            f'<td>{max(vals) if vals else 0:,}</td><td><a class="cl" href="https://fullcourtbuckets.com/news/2026-wnba-finals-ratings-tracker/#po2026-f" data-a="po2026-f">Copy link</a></td>')


_THROUGH = re.compile(r'(2026 Finals:? through Game |plus 2026 Finals through Game )\d+')
_APA = re.compile(r'(Moalemi, R\. \(2026, )[A-Z][a-z]+ \d+(\))')
FULL_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']


def render_tracker_scope_text(root: Path, s: dict, attrs: dict, body: str = '') -> str:
    """Rewrite 'through Game N' and the APA date inside a block (attributes such as data-copy included)."""
    n = tracker_through(root, s)
    body = _THROUGH.sub(lambda m: m.group(1) + str(n), body)
    y, mo, d = (int(x) for x in tracker_updated_iso(root, s).split('-'))
    return _APA.sub(lambda m: f'{m.group(1)}{FULL_MONTHS[mo - 1]} {d}{m.group(2)}', body)


def render_tracker_2026_total(root: Path, s: dict, attrs: dict) -> str:
    """Answer-line sentence: 2026 Finals combined attendance so far, from the data file."""
    rows = [r for r in _attendance(root) if r.get('attendance')]
    if not rows:
        return 'The 2026 Finals have no reported attendance yet.'
    return f"The 2026 Finals are at {sum(int(r['attendance']) for r in rows):,} through Game {rows[-1]['game']}."


RENDERERS = {
    'tracker-2026-total': render_tracker_2026_total,
    'series-line': render_series_line,
    'finals-attendance-lead': render_attendance_lead,
    'finals-attendance-counter': render_attendance_counter,
    'finals-attendance-data': render_attendance_data,
    'next-game': render_next_game,
    'series-status': render_series_status,
    'finals-schedule': render_finals_schedule,
    'tracker-updated': render_tracker_updated,
    'tracker-scope': render_tracker_scope,
    'tracker-schedule': render_tracker_schedule,
    'tracker-sched-note': render_tracker_sched_note,
    'tracker-g6-venue': render_tracker_g6_venue,
    'tracker-g6-cell': render_tracker_g6_cell,
    'tracker-finals-row': render_tracker_finals_row,
    'tracker-scope-text': render_tracker_scope_text,
}
BODY_RENDERERS = {render_attendance_data, render_tracker_scope_text}


def _attrs(text: str) -> dict:
    return dict(re.findall(r'\s([a-z-]+)="([^"]*)"', text))


def _set_attr(attrs: str, name: str, value: str) -> str:
    if re.search(rf'\s{name}="[^"]*"', attrs):
        return re.sub(rf'(\s{name}=")[^"]*(")', lambda m: m.group(1) + value + m.group(2), attrs)
    return attrs + f' {name}="{value}"'


# ---- Tracker database counts ----
# The header ("N games indexed · K with published attendance"), the default filter
# summary and the coverage line are printed in the HTML before JavaScript runs.
# They are counted from the database rows themselves so a new game row can never
# leave the printed counts behind the table (crawlers and no-JS readers see them).
_DB_TABLE = re.compile(r'<table[^>]*\bid="fdb".*?</table>', re.S)
_DB_ROW = re.compile(r'<tr id="g[^"]*"[^>]*\bdata-att="(\d*)"')


def tracker_counts(text: str):
    m = _DB_TABLE.search(text)
    if not m:
        return None
    atts = _DB_ROW.findall(m.group(0))
    if not atts:
        return None
    known = [int(a) for a in atts if a]
    total = sum(known)
    return {'games': len(atts), 'with_att': len(known), 'total': total,
            'avg': int(total / len(known) + 0.5) if known else 0}


def sync_tracker_counts(text: str) -> str:
    c = tracker_counts(text)
    if not c:
        return text
    text = re.sub(r'(<span class="dyn-ng">)\d+(</span>)', lambda m: f"{m.group(1)}{c['games']}{m.group(2)}", text)
    text = re.sub(r'(<span class="dyn-nk">)\d+(</span>)', lambda m: f"{m.group(1)}{c['with_att']}{m.group(2)}", text)
    text = re.sub(r'(<b id="sg">)[\d,]+(</b>)', lambda m: f"{m.group(1)}{c['games']}{m.group(2)}", text)
    text = re.sub(r'(<b id="sk">)[\d,]+(</b>)', lambda m: f"{m.group(1)}{c['with_att']}{m.group(2)}", text)
    text = re.sub(r'(<b id="st">)[\d,]+(</b>)', lambda m: f"{m.group(1)}{c['total']:,}{m.group(2)}", text)
    text = re.sub(r'(<b id="sa">)[\d,]+(</b>)', lambda m: f"{m.group(1)}{c['avg']:,}{m.group(2)}", text)
    missing = c['games'] - c['with_att']
    text = re.sub(r'(<span class="note" id="sx"[^>]*>Excluded from arithmetic: )\d+( games? with no attendance shown)',
                  lambda m: f"{m.group(1)}{missing}{m.group(2)}", text)
    return text


def tracker_count_problems(text: str) -> list:
    if not tracker_counts(text):
        return []
    return [] if sync_tracker_counts(text) == text else ['printed database counts do not match the table rows']


def render_html(text: str, root: Path, s: dict | None) -> str:
    def swap(m: re.Match) -> str:
        fn = RENDERERS.get(m.group('kind'))
        if not fn or not s:
            return m.group(0)
        attrs = _set_attr(m.group('attrs'), 'data-fcb-updated', s['last_day'])
        if fn in BODY_RENDERERS:
            body = fn(root, s, {}, m.group('body'))
        else:
            body = fn(root, s, _attrs(m.group('attrs')))
        return f"<{m.group('tag')}{attrs}>{body}</{m.group('tag')}>{END}"
    return sync_tracker_counts(SECTION.sub(swap, text))


def html_files(root: Path):
    for path in sorted(root.rglob('index.html')):
        if not SKIP_DIRS.intersection(path.relative_to(root).parts):
            yield path


# Wording that goes stale once a game is played. Hand-written text that matches
# fails the check unless it sits inside a marked section.
STALE_PATTERNS = [
    re.compile(r'\bGame \d is (?:tonight|today|tomorrow|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b'),
    re.compile(r'\bFinals open (?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|tonight|today)\b'),
    re.compile(r'\b0 games completed\b'),
]
# Pages where a dated article legitimately says "tonight" in its own body.
ARTICLE_BODY = re.compile(r'<article\b.*?</article>', re.S)
CARD = re.compile(r'<a class="(?:article-card|team-news-item)[^"]*"[^>]*>.*?</a>', re.S)


def _visible(text: str) -> str:
    text = re.sub(r'<script\b.*?</script>', ' ', text, flags=re.S)
    return text


def stale_problems(root: Path) -> list[str]:
    problems = []
    latest = finals_series.latest_day(root)
    for path in html_files(root):
        text = path.read_text(encoding='utf-8', errors='replace')
        rel = path.relative_to(root).as_posix()
        for m in SECTION.finditer(text):
            updated = _attrs(m.group('attrs')).get('data-fcb-updated', '')
            if m.group('kind') in RENDERERS and latest and updated < latest:
                problems.append(f'{rel}: {m.group("kind")} section updated {updated or "never"}, latest final {latest}')
        problems.extend(f'{rel}: {p}' for p in tracker_count_problems(text))
        unmarked = _visible(SECTION.sub(' ', text))
        if rel.startswith('news/'):
            # A news story is dated; only cards that link to other stories must stay current.
            scope = ' '.join(CARD.findall(ARTICLE_BODY.sub(' ', unmarked))) + ' '.join(CARD.findall(unmarked))
        else:
            scope = unmarked
        for rx in STALE_PATTERNS:
            for hit in sorted(set(rx.findall(scope))):
                problems.append(f'{rel}: stale wording "{hit}" outside a data-fcb-dynamic section')
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--root', default=str(ROOT))
    args = ap.parse_args(argv)
    root = Path(args.root)
    if args.check:
        problems = stale_problems(root)
        for p in problems:
            print(p)
        return 1 if problems else 0
    s = finals_series.series(root)
    changed = []
    for path in html_files(root):
        text = path.read_text(encoding='utf-8')
        if 'data-fcb-dynamic' not in text:
            continue
        new = render_html(text, root, s)
        if new != text:
            path.write_text(new, encoding='utf-8')
            changed.append(path.relative_to(root).as_posix())
    print(f'dynamic sections: {len(changed)} page(s) updated')
    for c in changed:
        print('  /' + c.removesuffix('index.html'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
