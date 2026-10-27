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


RENDERERS = {
    'finals-attendance-lead': render_attendance_lead,
    'finals-attendance-counter': render_attendance_counter,
    'finals-attendance-data': render_attendance_data,
    'next-game': render_next_game,
    'series-status': render_series_status,
    'finals-schedule': render_finals_schedule,
}


def _attrs(text: str) -> dict:
    return dict(re.findall(r'\s([a-z-]+)="([^"]*)"', text))


def _set_attr(attrs: str, name: str, value: str) -> str:
    if re.search(rf'\s{name}="[^"]*"', attrs):
        return re.sub(rf'(\s{name}=")[^"]*(")', lambda m: m.group(1) + value + m.group(2), attrs)
    return attrs + f' {name}="{value}"'


def render_html(text: str, root: Path, s: dict | None) -> str:
    def swap(m: re.Match) -> str:
        fn = RENDERERS.get(m.group('kind'))
        if not fn or not s:
            return m.group(0)
        attrs = _set_attr(m.group('attrs'), 'data-fcb-updated', s['last_day'])
        if fn is render_attendance_data:
            body = fn(root, s, {}, m.group('body'))
        else:
            body = fn(root, s, _attrs(m.group('attrs')))
        return f"<{m.group('tag')}{attrs}>{body}</{m.group('tag')}>{END}"
    return SECTION.sub(swap, text)


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
