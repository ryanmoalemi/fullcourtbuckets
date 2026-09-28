#!/usr/bin/env python3
"""Refresh /players pages from ESPN and record roster moves.

Reads players.json, compares each athlete's team, jersey, and position with
ESPN, and refreshes 2026 season stats. A failed request skips that player.
Stored values are never replaced with blanks. Article HTML is not touched.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import html
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = 'https://fullcourtbuckets.com'
ATHLETE = 'https://site.web.api.espn.com/apis/common/v3/sports/basketball/wnba/athletes/{espn_id}'
SEASON_KEYS = ('GP', 'GS', 'MIN', 'PTS', 'REB', 'AST', 'STL', 'BLK', 'TO', 'FG%', '3P%', 'FT%')
GAME_KEYS = ('MIN', 'PTS', 'REB', 'AST', 'STL', 'BLK', 'TO')
PT = ZoneInfo('America/Los_Angeles')
ET = ZoneInfo('America/New_York')
TEAM_QUESTION = re.compile(r"what team does .+ play for\?", re.I)
USER_AGENT = 'FullCourtBuckets/1.0'


class RosterError(RuntimeError):
    pass


def esc(value):
    return html.escape('' if value is None else str(value), quote=True)


def norm_name(value):
    return str(value or '').replace('\u2019', "'").replace('`', "'").casefold().strip()


def short_team(full_name, nickname=None):
    nick = str(nickname or '').strip()
    if nick:
        return nick
    parts = str(full_name or '').split()
    return parts[-1] if parts else ''


def fetch_json(url, timeout=25):
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if getattr(response, 'status', 200) != 200:
                print(f'skip fetch {url}: HTTP {response.status}', file=sys.stderr)
                return None
            payload = json.loads(response.read().decode('utf-8'))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError) as exc:
        print(f'skip fetch {url}: {exc}', file=sys.stderr)
        return None
    return payload if isinstance(payload, dict) else None


def clean_text(value, limit):
    text = str(value or '').strip()
    if not text or len(text) > limit:
        return None
    return text


def jersey_text(value):
    text = str(value or '').strip().lstrip('#')
    if not re.fullmatch(r'\d{1,2}', text):
        return None
    return text


def parse_athlete(payload, player):
    """Return roster fields, or None when the response cannot be trusted."""
    athlete = (payload or {}).get('athlete')
    if not isinstance(athlete, dict):
        return None
    if str(athlete.get('id') or '') != str(player.get('espnId') or ''):
        print(f"skip {player.get('slug')}: ESPN id did not match", file=sys.stderr)
        return None
    if norm_name(athlete.get('displayName')) != norm_name(player.get('name')):
        print(f"skip {player.get('slug')}: ESPN name did not match {player.get('name')}", file=sys.stderr)
        return None
    team = athlete.get('team') if isinstance(athlete.get('team'), dict) else {}
    position = athlete.get('position') if isinstance(athlete.get('position'), dict) else {}
    active = athlete.get('active') if isinstance(athlete.get('active'), bool) else None
    return {
        'team': clean_text(team.get('displayName'), 60),
        'team_short': short_team(team.get('displayName'), team.get('name')),
        'team_slug': clean_text(team.get('slug'), 80),
        'jersey': jersey_text(athlete.get('jersey')),
        'position': clean_text(position.get('displayName'), 40),
        'active': active,
    }


def averages_2026(payload, team_slug):
    """Return the 2026 average row, or None to keep the stored row."""
    categories = (payload or {}).get('categories')
    if not isinstance(categories, list):
        return None
    averages = next((item for item in categories if isinstance(item, dict) and item.get('name') == 'averages'), None)
    if not averages:
        return None
    labels = averages.get('labels') or []
    if not isinstance(labels, list):
        return None
    rows = []
    for row in averages.get('statistics') or []:
        if not isinstance(row, dict):
            continue
        season = row.get('season') if isinstance(row.get('season'), dict) else {}
        if season.get('year') != 2026:
            continue
        stats = row.get('stats') or []
        if not isinstance(stats, list) or len(stats) != len(labels):
            continue
        mapped = {str(labels[index]): str(stats[index]).strip() for index in range(len(labels))}
        if any(not mapped.get(key) for key in SEASON_KEYS):
            continue
        rows.append((row.get('teamSlug'), {key: mapped[key] for key in SEASON_KEYS}))
    if not rows:
        return None
    # ESPN supplies a combined "2026 Totals" row when a player has more than one
    # team. Use that for the single 2026 season line. Do not invent a sum, and
    # do not replace a stored line with one stint when several are listed.
    totals = [row for row in rows if 'total' in str(row[0] or '').casefold()]
    if len(totals) == 1:
        return totals[0][1]
    if team_slug:
        matched = [row for row in rows if row[0] == team_slug]
        if len(matched) == 1 and len(rows) == 1:
            return matched[0][1]
    if len(rows) == 1:
        return rows[0][1]
    return None


def parse_game_date(raw):
    try:
        parsed = dt.datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    local = parsed.astimezone(ET)
    return local.date().isoformat(), f'{local.strftime("%B")} {local.day}, {local.year}'


def newest_game(payload):
    """Return one completed game dict, or None to keep the stored game."""
    game_log = (payload or {}).get('gameLog')
    if not isinstance(game_log, dict):
        return None
    events = game_log.get('events')
    stats_block = game_log.get('statistics')
    if not isinstance(events, dict) or not isinstance(stats_block, list) or not stats_block:
        return None
    labels = stats_block[0].get('labels') if isinstance(stats_block[0], dict) else None
    logged = stats_block[0].get('events') if isinstance(stats_block[0], dict) else None
    if not isinstance(labels, list) or not isinstance(logged, list):
        return None
    by_id = {}
    for item in logged:
        if isinstance(item, dict) and item.get('eventId') and isinstance(item.get('stats'), list):
            by_id[str(item['eventId'])] = item['stats']
    candidates = []
    for event_id, event in events.items():
        if not isinstance(event, dict):
            continue
        if str(event.get('leagueAbbreviation') or '').upper() != 'WNBA':
            continue
        dated = parse_game_date(event.get('gameDate'))
        stats = by_id.get(str(event_id))
        if not dated or stats is None or len(stats) != len(labels):
            continue
        mapped = {str(labels[index]): str(stats[index]).strip() for index in range(len(labels))}
        if any(not mapped.get(key) for key in GAME_KEYS):
            continue
        side = str(event.get('atVs') or '').strip().lower()
        if side in ('@', 'at'):
            at_vs = 'at'
        elif side in ('vs', 'vs.'):
            at_vs = 'vs'
        else:
            continue
        opponent = event.get('opponent') if isinstance(event.get('opponent'), dict) else {}
        opponent_name = clean_text(opponent.get('displayName'), 60)
        result = clean_text(event.get('gameResult'), 8)
        score = clean_text(event.get('score'), 20)
        if not opponent_name or not result or not score:
            continue
        candidates.append({
            'date': dated[0],
            'displayDate': dated[1],
            'opponent': opponent_name,
            'atVs': at_vs,
            'result': result,
            'score': score,
            'line': {key: mapped[key] for key in GAME_KEYS},
        })
    if not candidates:
        return None
    return max(candidates, key=lambda game: game['date'])


def apply_game(player, game):
    """Update the newest game without erasing a newer stored game."""
    if not game:
        return False
    if game['date'] >= '2026-01-01':
        current = player.get('lastGame') if isinstance(player.get('lastGame'), dict) else None
        if current and str(current.get('date') or '') > game['date']:
            return False
        if current == game:
            return False
        player['lastGame'] = game
        return True
    if isinstance(player.get('lastGame'), dict):
        return False
    current = player.get('lastGameOnRecord') if isinstance(player.get('lastGameOnRecord'), dict) else None
    if current and str(current.get('date') or '') >= game['date']:
        return False
    if current == game:
        return False
    player['lastGameOnRecord'] = game
    return True


def team_answer(player):
    name = player.get('name') or ''
    team = player.get('team') or ''
    jersey = jersey_text(player.get('jersey'))
    if not name or not team:
        return None
    if jersey:
        return f'{name} plays for the {team} and wears No. {jersey}.'
    return f'{name} plays for the {team}.'


def update_team_faq(player):
    answer = team_answer(player)
    if not answer:
        return False
    changed = False
    for item in player.get('faq') or []:
        if not isinstance(item, dict) or not TEAM_QUESTION.fullmatch(str(item.get('q') or '').strip()):
            continue
        if item.get('a') != answer:
            item['a'] = answer
            changed = True
    return changed


def refresh_player(player, fetch, today):
    """Return (player, info). info['skipped'] is set when the athlete request failed."""
    slug = player.get('slug') or '?'
    espn_id = str(player.get('espnId') or '').strip()
    if not espn_id:
        return player, {'slug': slug, 'skipped': 'missing espnId'}
    athlete_payload = fetch(ATHLETE.format(espn_id=espn_id))
    if not athlete_payload:
        return player, {'slug': slug, 'skipped': 'athlete request failed'}
    roster = parse_athlete(athlete_payload, player)
    if roster is None:
        return player, {'slug': slug, 'skipped': 'athlete record rejected'}

    updated = copy.deepcopy(player)
    changes = {'slug': slug, 'name': player.get('name') or slug, 'skipped': None, 'roster': {}, 'stats': False}

    def take(field, incoming):
        if incoming is None:
            return
        current = updated.get(field)
        left = str(current or '').strip()
        right = str(incoming).strip()
        if field in ('team', 'position'):
            same = left.casefold() == right.casefold()
        else:
            same = left == right
        if same:
            return
        changes['roster'][field] = (current, incoming)
        updated[field] = incoming

    take('team', roster['team'])
    take('jersey', roster['jersey'])
    take('position', roster['position'])
    if roster['active'] is not None and updated.get('active') is not roster['active']:
        changes['roster']['active'] = (updated.get('active'), roster['active'])
        updated['active'] = roster['active']
    if 'team' in changes['roster']:
        old_full, new_full = changes['roster']['team']
        old_short = short_team(old_full)
        new_short = roster['team_short'] or short_team(new_full)
        if old_short and new_short:
            line = f'Traded/moved from {old_short} to {new_short} on {today.strftime("%B")} {today.day}, {today.year}.'
            move = {
                'date': today.isoformat(),
                'fromTeam': old_full,
                'toTeam': new_full,
                'fromShort': old_short,
                'toShort': new_short,
                'line': line,
            }
            moves = list(updated.get('rosterMoves') or [])
            if not moves or moves[-1].get('line') != line:
                moves.append(move)
            updated['rosterMoves'] = moves
            changes['roster']['move'] = (old_short, new_short)
    if 'team' in changes['roster'] or 'jersey' in changes['roster']:
        if update_team_faq(updated):
            changes['roster']['faq'] = True

    team_slug = roster['team_slug']
    for field, season_type in (('season2026', 2), ('playoffs2026', 3)):
        payload = fetch(ATHLETE.format(espn_id=espn_id) + f'/stats?seasontype={season_type}')
        parsed = averages_2026(payload, team_slug) if payload else None
        if parsed and parsed != updated.get(field):
            updated[field] = parsed
            changes['stats'] = True
    game_payload = fetch(ATHLETE.format(espn_id=espn_id) + '/overview')
    if game_payload and apply_game(updated, newest_game(game_payload)):
        changes['stats'] = True
    changes['changed'] = bool(changes['roster'] or changes['stats'])
    return (updated if changes['changed'] else player), changes


def should_publish(roster_changed, stats_changed, already_today):
    if roster_changed:
        return True
    return bool(stats_changed and not already_today)


def commit_message(changes):
    parts = []
    for change in changes:
        roster = change.get('roster') or {}
        if not roster:
            continue
        bits = []
        if roster.get('move'):
            old_short, new_short = roster['move']
            bits.append(f'{old_short} to {new_short}')
        if roster.get('jersey'):
            old, new = roster['jersey']
            bits.append(f'jersey {old} to {new}')
        if roster.get('position'):
            old, new = roster['position']
            bits.append(f'position {old} to {new}')
        if roster.get('active') and 'move' not in roster:
            bits.append('marked active' if roster['active'][1] else 'marked inactive')
        if bits:
            parts.append(f"{change['name']} " + ', '.join(bits))
    if parts:
        return 'Roster update: ' + '; '.join(parts)
    return 'Roster update: refresh 2026 stats'


def stats_commit_already_today(root, today):
    start = dt.datetime(today.year, today.month, today.day, tzinfo=PT)
    try:
        result = subprocess.run(
            ['git', 'log', '--since', start.isoformat(), '--pretty=%s'],
            cwd=root, check=False, capture_output=True, text=True,
        )
    except OSError:
        return False
    if result.returncode != 0:
        return False
    return any(line.startswith('Roster update:') for line in result.stdout.splitlines())


def deck(player):
    position = player.get('position') or 'Player'
    team = player.get('team') or 'Team'
    season = player.get('season2026') if isinstance(player.get('season2026'), dict) else {}
    points = season.get('PTS')
    if points:
        return f'{position}. {team}. {points} points per game in 2026.'
    return f'{position}. {team}. No 2026 regular-season statistics listed.'


def bio_html(player):
    team = player.get('team') or ''
    if team and player.get('active') is False:
        team = f'{team} (inactive)'
    rows = []
    if team:
        rows.append(('Team', team))
    if player.get('position'):
        rows.append(('Position', player['position']))
    jersey = jersey_text(player.get('jersey'))
    if jersey:
        rows.append(('Jersey', f'#{jersey}'))
    for key, label in (
        ('height', 'Height'), ('weight', 'Weight'), ('born', 'Born'), ('birthPlace', 'Birthplace'),
        ('college', 'College'), ('draft', 'Draft'), ('experience', 'Experience'),
    ):
        if player.get(key):
            rows.append((label, player[key]))
    return ''.join(f'<dt>{esc(label)}</dt><dd>{esc(value)}</dd>' for label, value in rows)


def stats_html(player):
    season = player.get('season2026') if isinstance(player.get('season2026'), dict) else None
    if not season or any(not season.get(key) for key in SEASON_KEYS):
        body = '<p>ESPN did not list 2026 regular-season statistics.</p>'
    else:
        heads = ''.join(f'<th>{esc(key)}</th>' for key in SEASON_KEYS)
        cells = ''.join(f'<td>{esc(season[key])}</td>' for key in SEASON_KEYS)
        body = f'<table class="stats"><thead><tr>{heads}</tr></thead><tbody><tr>{cells}</tr></tbody></table>'
    playoffs = player.get('playoffs2026') if isinstance(player.get('playoffs2026'), dict) else None
    if playoffs and all(playoffs.get(key) for key in ('GP', 'PTS', 'REB', 'AST', 'STL', 'BLK')):
        body += (
            f'<p>2026 playoffs: {esc(playoffs["GP"])} GP, {esc(playoffs["PTS"])} PPG, '
            f'{esc(playoffs["REB"])} RPG, {esc(playoffs["AST"])} APG, {esc(playoffs["STL"])} SPG, '
            f'{esc(playoffs["BLK"])} BPG.</p>'
        )
    game = player.get('lastGame') if isinstance(player.get('lastGame'), dict) else None
    label = 'Last game'
    if not game:
        game = player.get('lastGameOnRecord') if isinstance(player.get('lastGameOnRecord'), dict) else None
        label = 'Last game on record'
    line = game.get('line') if isinstance(game, dict) else None
    if isinstance(line, dict) and all(line.get(key) for key in ('PTS', 'REB', 'AST', 'STL', 'BLK', 'MIN')) and all(game.get(key) for key in ('displayDate', 'atVs', 'opponent', 'result', 'score')):
        body += (
            f'<p>{label}: {esc(game["displayDate"])} {esc(game["atVs"])} {esc(game["opponent"])}, '
            f'{esc(game["result"])} {esc(game["score"])} — {esc(line["PTS"])} points, {esc(line["REB"])} rebounds, '
            f'{esc(line["AST"])} assists, {esc(line["STL"])} steals, {esc(line["BLK"])} blocks, {esc(line["MIN"])} minutes.</p>'
        )
    return body


def photo_html(player):
    photo = player.get('photo')
    if not isinstance(photo, dict) or not photo.get('src'):
        return ''
    credit = photo.get('credit')
    credit_url = photo.get('creditUrl')
    license_name = photo.get('license')
    license_url = photo.get('licenseUrl')
    if not (credit and credit_url and license_name and license_url):
        return ''
    return (
        f'<figure><img src="{esc(photo["src"])}" alt="{esc(photo.get("alt") or player.get("name"))}">'
        f'<figcaption>Photo: <a href="{esc(credit_url)}" target="_blank" rel="noopener">{esc(credit)}</a> '
        f'/ Wikimedia Commons (<a href="{esc(license_url)}" target="_blank" rel="noopener">{esc(license_name)}</a>)</figcaption></figure>'
    )


def related_html(player):
    related = [item for item in (player.get('related') or []) if isinstance(item, dict) and item.get('slug') and item.get('title')]
    if not related:
        return ''
    links = ''.join(
        f'<a href="/{esc(item["slug"])}/" target="_blank" rel="noopener">{esc(item["title"])}<span>{esc(item.get("date") or "")}</span></a>'
        for item in related
    )
    return f'<h2 class="section-title">Related stories</h2><div class="related">{links}</div>'


def moves_html(player):
    lines = []
    for move in player.get('rosterMoves') or []:
        if isinstance(move, dict) and move.get('line'):
            lines.append(f'<p>{esc(move["line"])}</p>')
    return ''.join(lines)


def faq_html(player):
    items = []
    for item in player.get('faq') or []:
        if isinstance(item, dict) and str(item.get('q') or '').strip() and str(item.get('a') or '').strip():
            items.append(item)
    if not items:
        return '', ''
    blocks = []
    entities = []
    for item in items:
        source = str(item.get('source') or '')
        source_html = ''
        if source.startswith('https://'):
            source_html = f' <a href="{esc(source)}" target="_blank" rel="noopener">ESPN</a>'
        blocks.append(f'<details>\n<summary>{esc(item["q"])}</summary>\n<p>{esc(item["a"])}{source_html}</p>\n</details>')
        entities.append({
            '@type': 'Question',
            'name': item['q'],
            'acceptedAnswer': {'@type': 'Answer', 'text': item['a']},
        })
    visible = '<h2 class="section-title">FAQ</h2>\n<div class="faq">\n' + '\n'.join(blocks) + '\n</div>\n'
    payload = json.dumps({
        '@context': 'https://schema.org',
        '@type': 'FAQPage',
        'mainEntity': entities,
    }, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return visible, f'<script type="application/ld+json">{payload}</script>\n'


def shared_style(root):
    page = root / 'players' / 'aja-wilson' / 'index.html'
    if not page.is_file():
        raise RosterError('Cannot read the player page style from players/aja-wilson/index.html.')
    match = re.search(r'<style>.*?</style>', page.read_text(encoding='utf-8'), re.S)
    if not match:
        raise RosterError('Player page style block is missing.')
    return match.group(0)


def render_page(player, style):
    slug = player.get('slug') or ''
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug):
        raise RosterError(f'Unsafe player slug: {slug}')
    name = player.get('name') or slug
    summary = deck(player)
    faq_block, faq_ld = faq_html(player)
    photo = photo_html(player)
    photo_html_block = f'\n{photo}' if photo else ''
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(name)} | Full Court Buckets</title>
<meta name="description" content="{esc(summary)}">
<link rel="canonical" href="{BASE}/players/{esc(slug)}/">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@500;600;700;800&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
{style}
{faq_ld}</head>
<body>
<div class="utility"><div class="shell"><div class="utility-tag">WNBA News · Analysis · Commentary</div><div class="utility-note">Independent coverage. Facts first.</div></div></div>
<header><div class="shell nav"><a class="brand" href="/" target="_blank" rel="noopener"><img src="/logo.png" alt="Full Court Buckets"></a><nav><a href="/" target="_blank" rel="noopener">News</a><a href="/standings/" target="_blank" rel="noopener">Standings</a><a href="/players/" target="_blank" rel="noopener">Players</a></nav></div></header>
<main class="shell article-wrap">
<article class="article">
<div class="meta-row"><span class="cat">Player</span><span class="divider"></span><span>2026</span></div>
<h1>{esc(name)}</h1>
<p class="deck">{esc(summary)}</p>{photo_html_block}
<dl class="bio">{bio_html(player)}</dl>
<h2 class="section-title">2026 season</h2>
{stats_html(player)}
{moves_html(player)}
{related_html(player)}
{faq_block}
<p class="source">Season statistics and bio details are from ESPN. Statistics are shown only when ESPN listed them.</p>
</article>

</main>
<footer class="footer"><div class="shell footer-row"><div class="footer-brand">Full Court Buckets</div><div>Independent WNBA news, analysis and commentary. Not affiliated with or endorsed by the WNBA.</div></div></footer>
</body>
</html>
'''


def render_index_list(players):
    parts = []
    for player in players:
        label = ' · '.join(part for part in (player.get('position') or '', player.get('team') or '') if part)
        parts.append(
            f'<a href="/players/{esc(player["slug"])}/" target="_blank" rel="noopener">{esc(player["name"])}<span>{esc(label)}</span></a>'
        )
    return ''.join(parts)


def update_index(text, players):
    updated, count = re.subn(
        r'(<div class="player-list">).*?(</div>)',
        lambda match: match.group(1) + render_index_list(players) + match.group(2),
        text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RosterError('Player index is missing its player list.')
    return updated


def write_output(name, value):
    path = os.environ.get('GITHUB_OUTPUT')
    if not path:
        return
    with open(path, 'a', encoding='utf-8') as handle:
        handle.write(f'{name}<<ROSTER_EOF\n{value}\nROSTER_EOF\n')


def safe_path(root, relative):
    path = (root / relative).resolve()
    if path != root.resolve() and root.resolve() not in path.parents:
        raise RosterError(f'Refused to write outside the repository: {relative}')
    allowed = relative == 'players.json' or relative == 'players/index.html' or (
        relative.startswith('players/') and relative.endswith('/index.html') and relative.count('/') == 2
    )
    if not allowed:
        raise RosterError(f'Refused to write {relative}. Article pages are left unchanged.')
    return path


def run(root, fetch=fetch_json, today=None, already_today=None, dry_run=False, pause=0.15):
    root = Path(root)
    players_path = root / 'players.json'
    players = json.loads(players_path.read_text(encoding='utf-8'))
    if not isinstance(players, list) or not players:
        raise RosterError('players.json must be a non-empty list.')
    today = today or dt.datetime.now(PT).date()
    if already_today is None:
        already_today = stats_commit_already_today(root, today)
    style = shared_style(root)
    refreshed = []
    for index, player in enumerate(players):
        if index and pause:
            time.sleep(pause)
        updated, info = refresh_player(player, fetch, today)
        refreshed.append((player, updated, info))
        state = info.get('skipped') or ('changed' if info.get('changed') else 'unchanged')
        print(f'{info.get("slug")}: {state}')

    roster_changed = any(info.get('roster') for _, _, info in refreshed)
    stats_changed = any(info.get('stats') for _, _, info in refreshed)
    publish = should_publish(roster_changed, stats_changed, already_today)
    roster_infos = [info for _, _, info in refreshed if info.get('roster')]
    message = commit_message(roster_infos if roster_changed else [])
    skipped = [info['slug'] for _, _, info in refreshed if info.get('skipped')]
    print(f'roster_changes={len(roster_infos)} stats_changed={stats_changed} publish={publish} skipped={len(skipped)}')
    if skipped:
        print('skipped: ' + ', '.join(skipped))
    if not publish:
        print('No roster commit.')
        write_output('commit', 'false')
        return {'commit': False, 'message': '', 'written': []}

    final_players = []
    pages = {}
    index_identity_changed = False
    for original, updated, info in refreshed:
        include = bool(info.get('roster')) or (bool(info.get('stats')) and (roster_changed or not already_today))
        if not include or not info.get('changed'):
            final_players.append(original)
            continue
        page = render_page(updated, style)
        if esc(updated.get('name') or '') not in page:
            print(f'keep {info["slug"]}: rendered page failed the name check', file=sys.stderr)
            final_players.append(original)
            continue
        pages[updated['slug']] = page
        final_players.append(updated)
        if (original.get('team'), original.get('position')) != (updated.get('team'), updated.get('position')):
            index_identity_changed = True
    if not pages:
        print('No roster commit.')
        write_output('commit', 'false')
        return {'commit': False, 'message': '', 'written': []}

    written = ['players.json', *[f'players/{slug}/index.html' for slug in pages]]
    index_text = None
    if index_identity_changed:
        index_path = root / 'players' / 'index.html'
        index_text = update_index(index_path.read_text(encoding='utf-8'), final_players)
        written.append('players/index.html')
    print(message)
    if dry_run:
        print('Dry run: no files written.')
        write_output('commit', 'false')
        return {'commit': False, 'message': message, 'written': written, 'dry_run': True}

    for relative in written:
        safe_path(root, relative)
    players_path.write_text(json.dumps(final_players, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    for slug, page in pages.items():
        path = safe_path(root, f'players/{slug}/index.html')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(page, encoding='utf-8')
    if index_text is not None:
        safe_path(root, 'players/index.html').write_text(index_text, encoding='utf-8')
    write_output('commit', 'true')
    write_output('message', message)
    return {'commit': True, 'message': message, 'written': written}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    try:
        run(args.root, dry_run=args.dry_run)
    except RosterError as exc:
        print(f'Roster update stopped: {exc}', file=sys.stderr)
        write_output('commit', 'false')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
