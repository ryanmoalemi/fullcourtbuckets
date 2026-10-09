"""Playoff series for /standings/, built from stored game results.

Final scores come from data/games. Player logs written by the same stats
import fill in playoff games that do not have a box file yet. A scheduled
game in data/games/schedule.json can supply the next tip. Series wins are
counted from those finals. A cross-check that disagrees raises CheckError
so the page builder can keep the last good file.
"""
from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import team_names

PT = ZoneInfo('America/Los_Angeles')
MONTHS = ('', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')
WEEKDAYS = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
FIRST_PAIRS = {(1, 8), (4, 5), (2, 7), (3, 6)}
HALF_A = {1, 8, 4, 5}
HALF_B = {2, 7, 3, 6}
ROUND_ORDER = ('First round', 'Semifinals', 'Finals')
WINS_NEEDED = {'First round': 2, 'Semifinals': 3, 'Finals': 4}
SERIES_LENGTH = {'First round': 3, 'Semifinals': 5, 'Finals': 7}


class CheckError(RuntimeError):
    """Stored games and the cross-check do not agree. Do not publish."""


def _pt(value) -> dt.datetime | None:
    text = str(value or '').strip()
    if not text:
        return None
    try:
        if 'T' in text or text.endswith('Z'):
            moment = dt.datetime.fromisoformat(text.replace('Z', '+00:00'))
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=dt.timezone.utc)
            return moment.astimezone(PT)
        day = dt.date.fromisoformat(text[:10])
        return dt.datetime(day.year, day.month, day.day, tzinfo=PT)
    except (ValueError, TypeError):
        return None


def _nick(full_name: str, short: str = '') -> str:
    short = str(short or '').strip()
    if short and short.casefold() not in ('', 'team'):
        return team_names.public_name(short) if ' ' not in short else short.split()[-1]
    parts = team_names.public_name(full_name).split()
    return parts[-1] if parts else ''


def _int(value):
    if isinstance(value, bool) or value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _side(team) -> dict:
    team = team if isinstance(team, dict) else {}
    full = team_names.public_name(str(team.get('full_name') or team.get('displayName') or team.get('name') or '').strip())
    abbr = str(team.get('abbreviation') or '').strip().upper()
    return {
        'abbreviation': abbr,
        'full_name': full,
        'nick': _nick(full, str(team.get('name') or '')),
    }


def _game_key(away: str, home: str, day: dt.date, game_id) -> tuple:
    if game_id:
        return ('id', int(game_id))
    return ('pair', day.isoformat(), frozenset((away, home)))


def _result(away, home, away_score, home_score, when, season, game_id, overtime=None, status='final') -> dict:
    return {
        'id': game_id,
        'when': when,
        'day': when.date(),
        'season': season,
        'away': away,
        'home': home,
        'away_score': away_score,
        'home_score': home_score,
        'overtime': overtime,
        'status': status,
    }


def _same_score(left: dict, right: dict) -> bool:
    return (
        left['away']['abbreviation'] == right['away']['abbreviation']
        and left['home']['abbreviation'] == right['home']['abbreviation']
        and left['away_score'] == right['away_score']
        and left['home_score'] == right['home_score']
        and left['day'] == right['day']
    )


def load_results(root: Path, season: int | None = None) -> list[dict]:
    """Final playoff games. Box files win; player logs fill gaps. Scores must agree."""
    found: dict[tuple, dict] = {}

    def add(row: dict, label: str) -> None:
        if season and row.get('season') not in (None, season):
            return
        if row['status'] != 'final':
            return
        if not row['away']['abbreviation'] or not row['home']['abbreviation']:
            raise CheckError(f'A stored playoff game is missing a team ({label}).')
        if row['away_score'] is None or row['home_score'] is None:
            raise CheckError(f'A stored playoff game is missing a score ({label}).')
        if row['away_score'] == row['home_score']:
            raise CheckError(f'A stored playoff game is tied ({label}).')
        key = _game_key(row['away']['abbreviation'], row['home']['abbreviation'], row['day'], row.get('id'))
        previous = found.get(key)
        if previous is None:
            found[key] = row
            return
        if not _same_score(previous, row):
            raise CheckError(
                'Stored playoff games disagree: '
                f"{previous['away']['abbreviation']} {previous['away_score']} at "
                f"{previous['home']['abbreviation']} {previous['home_score']} on {previous['day'].isoformat()}, "
                f"and {row['away']['abbreviation']} {row['away_score']} at "
                f"{row['home']['abbreviation']} {row['home_score']} on {row['day'].isoformat()}."
            )
        if row.get('overtime') and not previous.get('overtime'):
            previous['overtime'] = True

    players = root / 'data' / 'wnba' / 'players'
    if players.is_dir():
        for path in sorted(players.glob('*.json')):
            try:
                profile = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError):
                continue
            for raw in profile.get('recent_completed_games') or []:
                if not isinstance(raw, dict) or not raw.get('postseason'):
                    continue
                when = _pt(raw.get('date'))
                if when is None:
                    continue
                away_score, home_score = _int(raw.get('away_score')), _int(raw.get('home_score'))
                add(_result(
                    _side(raw.get('visitor_team')), _side(raw.get('home_team')),
                    away_score, home_score, when, _int(raw.get('season')), _int(raw.get('game_id')),
                ), path.name)

    folder = root / 'data' / 'games'
    if folder.is_dir():
        for path in sorted(folder.glob('*.json')):
            if path.name in ('index.json', 'balldontlie-endpoints.json', 'schedule.json'):
                continue
            try:
                doc = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(doc, dict) or not doc.get('postseason'):
                continue
            when = _pt(doc.get('date'))
            if when is None:
                continue
            status = str(doc.get('status') or '').strip().lower()
            if status not in ('final', 'post', 'final/ot', 'final/2ot'):
                continue
            add(_result(
                _side(doc.get('away')), _side(doc.get('home')),
                _int((doc.get('away') or {}).get('score')), _int((doc.get('home') or {}).get('score')),
                when, _int(doc.get('season')), _int(doc.get('balldontlie_game_id')),
                overtime=bool(doc.get('overtime')),
            ), path.name)

    # The same game can arrive once by id and once by date if a box file has no id.
    collapsed: dict[tuple, dict] = {}
    for row in found.values():
        key = (row['day'], frozenset((row['away']['abbreviation'], row['home']['abbreviation'])))
        previous = collapsed.get(key)
        if previous is None:
            collapsed[key] = row
            continue
        if not _same_score(previous, row):
            raise CheckError(
                'Stored playoff games disagree for '
                f"{row['away']['abbreviation']} at {row['home']['abbreviation']} on {row['day'].isoformat()}."
            )
        if row.get('overtime'):
            previous['overtime'] = True
    rows = list(collapsed.values())
    rows.sort(key=lambda row: (row['when'], row['away']['abbreviation'], row['home']['abbreviation']))
    return rows


def load_schedule(root: Path, season: int | None = None) -> list[dict]:
    path = root / 'data' / 'games' / 'schedule.json'
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return []
    rows = []
    for raw in payload.get('games') or []:
        if not isinstance(raw, dict) or raw.get('postseason') is False:
            continue
        when = _pt(raw.get('date'))
        if when is None:
            continue
        if season and _int(raw.get('season')) not in (None, season):
            continue
        status = str(raw.get('status') or 'scheduled').strip().lower()
        if status in ('final', 'post', 'canceled', 'abandoned'):
            continue
        away, home = _side(raw.get('away') or raw.get('visitor_team')), _side(raw.get('home') or raw.get('home_team'))
        if not away['abbreviation'] or not home['abbreviation']:
            continue
        rows.append(_result(away, home, None, None, when, _int(raw.get('season')), None, status='scheduled'))
    rows.sort(key=lambda row: row['when'])
    return rows


def _seeds(teams: list[dict]) -> dict[str, dict]:
    found = {}
    for team in teams:
        if not isinstance(team, dict):
            continue
        abbr = str(team.get('abbreviation') or '').upper()
        seed = team.get('playoffSeed')
        if not abbr or not isinstance(seed, int):
            continue
        found[abbr] = {
            'seed': seed,
            'abbreviation': abbr,
            'name': team_names.public_name(str(team.get('name') or '')),
            'nick': _nick(str(team.get('name') or ''), ''),
        }
    return found


def _round_for(seed_a: int, seed_b: int) -> str:
    pair = tuple(sorted((seed_a, seed_b)))
    if pair in FIRST_PAIRS:
        return 'First round'
    same_half = (seed_a in HALF_A and seed_b in HALF_A) or (seed_a in HALF_B and seed_b in HALF_B)
    if same_half:
        return 'Semifinals'
    return 'Finals'


def _pair_key(row: dict) -> frozenset:
    return frozenset((row['away']['abbreviation'], row['home']['abbreviation']))


def _winner(row: dict) -> dict:
    if row['home_score'] > row['away_score']:
        return row['home']
    return row['away']


def _loser(row: dict) -> dict:
    if row['home_score'] > row['away_score']:
        return row['away']
    return row['home']


def count_wins(games: list[dict]) -> dict[str, int]:
    wins: dict[str, int] = {}
    for game in games:
        if game.get('status') != 'final':
            continue
        winner = _winner(game)['abbreviation']
        wins[winner] = wins.get(winner, 0) + 1
        other = _loser(game)['abbreviation']
        wins.setdefault(other, 0)
    return wins


def _lead_verb(nick: str) -> str:
    """Plural nicknames take 'lead'. Lynx does not end in s, but it is plural."""
    if nick.endswith('s') or nick == 'Lynx':
        return 'lead'
    return 'leads'


def score_phrase(teams: list[dict], wins: dict[str, int], needed: int) -> str:
    """'Valkyries lead 2-0', or 'Liberty won 2-0' once the series is over."""
    ordered = sorted(teams, key=lambda team: (-wins.get(team['abbreviation'], 0), team['seed'], team['nick']))
    leader, trailer = ordered[0], ordered[1]
    high = wins.get(leader['abbreviation'], 0)
    low = wins.get(trailer['abbreviation'], 0)
    if high == low:
        return f"{teams[0]['nick']} and {teams[1]['nick']} tied {high}-{low}"
    if high >= needed:
        return f"{leader['nick']} won {high}-{low}"
    return f"{leader['nick']} {_lead_verb(leader['nick'])} {high}-{low}"


def _day_label(day: dt.date) -> str:
    return f'{MONTHS[day.month]} {day.day}'


def _clock_label(moment: dt.datetime) -> str:
    local = moment.astimezone(PT)
    hour = local.hour % 12 or 12
    suffix = 'AM' if local.hour < 12 else 'PM'
    return (
        f"Next: {WEEKDAYS[local.weekday()]}, {MONTHS[local.month]} {local.day}, "
        f"{hour}:{local.minute:02d} {suffix} PT"
    )


def game_line(game: dict) -> str:
    winner = _winner(game)
    loser = _loser(game)
    high = game['home_score'] if winner is game['home'] else game['away_score']
    low = game['away_score'] if winner is game['home'] else game['home_score']
    overtime = ' OT' if game.get('overtime') else ''
    return f"{_day_label(game['day'])}: {winner['full_name']} {high}, {loser['full_name']} {low}{overtime}"


def build_board(results: list[dict], schedule: list[dict], teams: list[dict], now: dt.datetime | None = None) -> dict:
    seeds = _seeds(teams)
    groups: dict[frozenset, list] = {}
    for game in results:
        groups.setdefault(_pair_key(game), []).append(game)
    upcoming: dict[frozenset, list] = {}
    for game in schedule:
        upcoming.setdefault(_pair_key(game), []).append(game)
    moment = now or dt.datetime.now(PT)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=PT)
    series_rows = []
    for key, games in groups.items():
        games = sorted(games, key=lambda game: game['when'])
        sides = {}
        for game in games:
            sides[game['away']['abbreviation']] = game['away']
            sides[game['home']['abbreviation']] = game['home']
        paired = []
        for abbr, side in sides.items():
            seed = seeds.get(abbr)
            if not seed:
                raise CheckError(f'No playoff seed for {side["full_name"]}. The series was not published.')
            paired.append({**seed, 'full_name': side['full_name'], 'nick': side['nick'] or seed['nick']})
        paired.sort(key=lambda team: (team['seed'], team['name']))
        round_name = _round_for(paired[0]['seed'], paired[1]['seed'])
        needed = WINS_NEEDED[round_name]
        wins = count_wins(games)
        complete = max(wins.values() or [0]) >= needed
        nxt = ''
        next_day = None
        if not complete:
            later = [
                game for game in upcoming.get(key, [])
                if game['when'] >= moment - dt.timedelta(hours=6)
            ]
            later.sort(key=lambda game: game['when'])
            if later:
                nxt = _clock_label(later[0]['when'])
                next_day = later[0]['day']
        leader = max(paired, key=lambda team: (wins.get(team['abbreviation'], 0), -team['seed']))
        trailer = paired[0] if paired[1] is leader else paired[1]
        status = ''
        if complete:
            status = f"{leader['name']} advanced. {trailer['name']} eliminated."
        series_rows.append({
            'round': round_name,
            'needed': needed,
            'length': SERIES_LENGTH[round_name],
            'teams': paired,
            'wins': {team['abbreviation']: wins.get(team['abbreviation'], 0) for team in paired},
            'complete': complete,
            'score': score_phrase(paired, wins, needed),
            'status': status,
            'games': games,
            'lines': [game_line(game) for game in games],
            'next': nxt,
            'next_day': next_day.isoformat() if next_day else '',
        })
    rounds = []
    for name in ROUND_ORDER:
        chunk = [row for row in series_rows if row['round'] == name]
        chunk.sort(key=lambda row: row['teams'][0]['seed'])
        if chunk:
            rounds.append({'name': name, 'series': chunk})
    finals = [row for row in series_rows if row['round'] == 'Finals' and row['complete']]
    champion = ''
    if finals:
        winner = max(finals[0]['teams'], key=lambda team: finals[0]['wins'].get(team['abbreviation'], 0))
        champion = winner['name']
    active = bool(series_rows) and not champion
    return {
        'rounds': rounds,
        'champion': champion,
        'active': active,
        'show': bool(series_rows),
    }


def verify_board(board: dict) -> None:
    """Every published series score has to equal the finals stored on that series."""
    for rnd in board.get('rounds') or []:
        for series in rnd.get('series') or []:
            recounted = count_wins(series.get('games') or [])
            for team in series['teams']:
                abbr = team['abbreviation']
                if recounted.get(abbr, 0) != series['wins'].get(abbr, 0):
                    raise CheckError(
                        f"Series score does not match stored games for {team['name']}: "
                        f"score {series['wins'].get(abbr, 0)}, games {recounted.get(abbr, 0)}."
                    )
            expected = score_phrase(series['teams'], series['wins'], series['needed'])
            if series['score'] != expected:
                raise CheckError(
                    f"Series line {series['score']!r} does not match stored games ({expected})."
                )


def cross_check_table(table: dict, espn_table: dict) -> None:
    """Wins, losses, conference, and order. Home and road too, when both sides have them."""
    ours = table.get('teams') or []
    theirs = espn_table.get('teams') or []
    if [team['name'] for team in ours] != [team['name'] for team in theirs]:
        raise CheckError(
            'Cross-check disagrees with the standings order. '
            f"Stored: {', '.join(team['name'] for team in ours)}. "
            f"Cross-check: {', '.join(team['name'] for team in theirs)}."
        )
    by_name = {team['name']: team for team in theirs}
    for team in ours:
        other = by_name.get(team['name']) or {}
        if team.get('wins') != other.get('wins') or team.get('losses') != other.get('losses'):
            raise CheckError(
                f"Cross-check disagrees with the standings table: {team['name']} is "
                f"{team.get('wins')}-{team.get('losses')} in the stored table and "
                f"{other.get('wins')}-{other.get('losses')} in the cross-check."
            )
        if team.get('conference') != other.get('conference'):
            raise CheckError(
                f"Cross-check disagrees on the conference for {team['name']}: "
                f"{team.get('conference')} versus {other.get('conference')}."
            )
        for field, label in (('home', 'home record'), ('road', 'road record')):
            left, right = str(team.get(field) or '').replace('–', '-').replace('—', '-'), str(other.get(field) or '').replace('–', '-').replace('—', '-')
            if left and right and left != right:
                raise CheckError(
                    f"Cross-check disagrees on the {label} for {team['name']}: {left} versus {right}."
                )


def espn_events(payload: dict) -> list[dict]:
    """One scoreboard payload, reduced to finals and scheduled playoff games."""
    events = []
    for event in payload.get('events') or []:
        if not isinstance(event, dict):
            continue
        competitions = event.get('competitions') or []
        comp = competitions[0] if competitions and isinstance(competitions[0], dict) else {}
        status = ((comp.get('status') or {}).get('type') or {})
        state = str(status.get('state') or '')
        when = _pt(event.get('date') or comp.get('date'))
        if when is None:
            continue
        sides = []
        id_to_abbr = {}
        for row in comp.get('competitors') or []:
            if not isinstance(row, dict):
                continue
            team = row.get('team') or {}
            abbr = str(team.get('abbreviation') or '').upper()
            ident = str(team.get('id') or '')
            if ident:
                id_to_abbr[ident] = abbr
            sides.append({
                'abbreviation': abbr,
                'full_name': team_names.public_name(str(team.get('displayName') or team.get('name') or abbr)),
                'home': row.get('homeAway') == 'home',
                'score': _int(row.get('score')),
            })
        away = next((row for row in sides if not row['home']), None)
        home = next((row for row in sides if row['home']), None)
        if not away or not home:
            continue
        series = comp.get('series')
        if isinstance(series, list):
            series = next((row for row in series if str(row.get('type') or '').lower() == 'playoff'), None)
        series = series if isinstance(series, dict) else {}
        wins = {}
        for row in series.get('competitors') or []:
            if isinstance(row, dict):
                abbr = id_to_abbr.get(str(row.get('id') or ''))
                if abbr:
                    wins[abbr] = _int(row.get('wins')) or 0
        season = event.get('season') if isinstance(event.get('season'), dict) else {}
        playoff = season.get('type') in (3, '3') or str(series.get('type') or '').lower() == 'playoff' or bool(wins)
        if not playoff:
            continue
        length = _int(series.get('totalCompetitions'))
        events.append({
            'when': when,
            'day': when.date(),
            'state': state,
            'final': state == 'post' or str(status.get('name') or '').startswith('STATUS_FINAL'),
            'away': away['abbreviation'],
            'home': home['abbreviation'],
            'away_score': away['score'],
            'home_score': home['score'],
            'wins': wins,
            'completed': bool(series.get('completed')),
            'length': length,
            'pair': frozenset((away['abbreviation'], home['abbreviation'])),
        })
    return events


def cross_check_board(board: dict, events: list[dict]) -> None:
    """Stored finals, series wins, and round length against the cross-check."""
    ours = []
    for rnd in board.get('rounds') or []:
        for series in rnd.get('series') or []:
            ours.append(series)
    by_pair = {frozenset(team['abbreviation'] for team in series['teams']): series for series in ours}
    finals = [event for event in events if event.get('final')]
    seen = set()
    for event in finals:
        series = by_pair.get(event['pair'])
        if series is None:
            names = ' vs '.join(sorted(event['pair']))
            raise CheckError(
                f"Cross-check has a playoff final that is not in the stored games: {names} on {event['day'].isoformat()}."
            )
        match = None
        for game in series['games']:
            if game['day'] == event['day'] and _pair_key(game) == event['pair']:
                match = game
                break
        if match is None:
            names = ' vs '.join(team['name'] for team in series['teams'])
            raise CheckError(
                f"Cross-check has a playoff game on {event['day'].isoformat()} for {names} that is not in the stored games."
            )
        if match['away_score'] != event['away_score'] or match['home_score'] != event['home_score']:
            names = ' vs '.join(team['name'] for team in series['teams'])
            raise CheckError(
                f"Cross-check disagrees with a stored game ({names} on {event['day'].isoformat()}): "
                f"stored {match['away']['abbreviation']} {match['away_score']}, "
                f"{match['home']['abbreviation']} {match['home_score']}; "
                f"cross-check {event['away']} {event['away_score']}, {event['home']} {event['home_score']}."
            )
        seen.add((event['day'], event['pair']))
    for series in ours:
        for game in series['games']:
            if (game['day'], _pair_key(game)) not in seen:
                names = ' vs '.join(team['name'] for team in series['teams'])
                raise CheckError(
                    f"Stored playoff game has no cross-check final: {names} on {game['day'].isoformat()}."
                )
        latest = [event for event in events if event['pair'] == frozenset(team['abbreviation'] for team in series['teams']) and event.get('wins')]
        if not latest:
            names = ' vs '.join(team['name'] for team in series['teams'])
            raise CheckError(f"Cross-check has no series score for {names}.")
        latest.sort(key=lambda event: event['when'])
        current = latest[-1]
        for team in series['teams']:
            abbr = team['abbreviation']
            if current['wins'].get(abbr) != series['wins'].get(abbr):
                names = ' vs '.join(team['name'] for team in series['teams'])
                raise CheckError(
                    f"Cross-check disagrees with stored games: {names} is "
                    f"{series['score']} from the game files, and the cross-check series score does not match."
                )
        if current.get('length') and current['length'] != series['length']:
            names = ' vs '.join(team['name'] for team in series['teams'])
            raise CheckError(
                f"Cross-check disagrees on the series length for {names}: "
                f"stored round is best of {series['length']}, cross-check says {current['length']}."
            )
        if bool(current.get('completed')) != bool(series['complete']):
            names = ' vs '.join(team['name'] for team in series['teams'])
            state = 'over' if series['complete'] else 'still going'
            other = 'over' if current.get('completed') else 'still going'
            raise CheckError(
                f"Cross-check disagrees on whether {names} is finished: stored games say {state}, cross-check says {other}."
            )
        if series.get('next_day'):
            upcoming = [
                event for event in events
                if event['pair'] == frozenset(team['abbreviation'] for team in series['teams']) and not event.get('final')
            ]
            upcoming = [event for event in upcoming if event['when'] >= (latest[-1]['when'] if latest else event['when'])]
            if upcoming:
                upcoming.sort(key=lambda event: event['when'])
                if upcoming[0]['day'].isoformat() != series['next_day']:
                    names = ' vs '.join(team['name'] for team in series['teams'])
                    raise CheckError(
                        f"Cross-check disagrees on the next game for {names}: "
                        f"stored {series['next_day']}, cross-check {upcoming[0]['day'].isoformat()}."
                    )


def section_text(board: dict) -> str:
    """Plain text of the playoff section, in the same words as the page."""
    if not board or not board.get('show'):
        return ''
    lines = []
    if board.get('champion'):
        lines.append(f"Champion: {board['champion']}")
    for rnd in board.get('rounds') or []:
        lines.append(rnd['name'])
        for series in rnd['series']:
            heading = ' vs '.join(f"({team['seed']}) {team['name']}" for team in series['teams'])
            lines.append(heading)
            lines.append(series['score'])
            lines.extend(series['lines'])
            if series.get('next'):
                lines.append(series['next'])
            if series.get('status'):
                lines.append(series['status'])
    return '\n'.join(lines)


def render_html(board: dict, hrefs: dict[str, str] | None = None) -> str:
    if not board or not board.get('show'):
        return ''
    hrefs = hrefs or {}

    def link(name: str) -> str:
        href = hrefs.get(name) or ''
        safe = html.escape(team_names.public_name(name), quote=True)
        if not href:
            return safe
        return f'<a class="team-name" href="{html.escape(href, quote=True)}">{safe}</a>'

    def esc(value) -> str:
        return html.escape('' if value is None else str(value), quote=True)

    blocks = []
    if board.get('champion'):
        blocks.append(f'<p class="series-score" id="playoff-champion">Champion: {link(board["champion"])}</p>')
    for rnd in board.get('rounds') or []:
        cards = []
        for series in rnd['series']:
            heading = ' vs '.join(f"({team['seed']}) {link(team['name'])}" for team in series['teams'])
            items = ''.join(f'<li>{esc(line)}</li>' for line in series['lines'])
            nxt = f'<p class="series-next">{esc(series["next"])}</p>' if series.get('next') else ''
            status = f'<p class="series-status">{esc(series["status"])}</p>' if series.get('status') else ''
            cards.append(
                '<section class="conf-card">'
                f'<div class="conf-header"><h3>{heading}</h3></div>'
                f'<p class="series-score">{esc(series["score"])}</p>'
                f'<ul class="series-games">{items}</ul>'
                f'{nxt}{status}'
                '</section>'
            )
        blocks.append(
            '<div class="playoff-round">'
            f'<p class="eyebrow">{esc(rnd["name"])}</p>'
            f'<div class="conference-wrap">{"".join(cards)}</div>'
            '</div>'
        )
    inner = ''.join(blocks)
    return (
        '<section class="panel" id="playoffs">'
        '<div class="panel-head"><h2>Playoffs</h2></div>'
        f'{inner}'
        '</section>'
    )
