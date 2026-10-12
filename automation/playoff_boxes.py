"""Bring playoff season lines up to the completed box scores on disk.

The season aggregate can lag a game that is already final. For a player who
stayed with one club, the cross-check used to keep that short count and its
averages, so the game never reached the player page. Completed boxes are the
record of who played and who did not. This module adds the missing games and
recomputes the averages from the counting totals.

Averages are stored so the integer total can be recovered and shown with
half-up rounding. Pages do not name where a number came from.
"""
from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo

import per_game

PACIFIC = ZoneInfo("America/Los_Angeles")
COUNTING = (
    "min", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta",
    "oreb", "dreb", "reb", "ast", "stl", "blk", "turnover", "pts",
)
BOX_FIELDS = {
    "min": "minutes",
    "fgm": "fgm",
    "fga": "fga",
    "fg3m": "fg3m",
    "fg3a": "fg3a",
    "ftm": "ftm",
    "fta": "fta",
    "oreb": "oreb",
    "dreb": "dreb",
    "reb": "reb",
    "ast": "ast",
    "stl": "stl",
    "blk": "blk",
    "turnover": "turnovers",
    "pts": "pts",
}
PERCENTAGES = (("fgm", "fga", "fg_pct"), ("fg3m", "fg3a", "fg3_pct"), ("ftm", "fta", "ft_pct"))
TEAM_KEYS = ("id", "full_name", "abbreviation", "city", "name", "conference")
SKIP_FILES = {"index.json", "balldontlie-endpoints.json"}


def load_games(root: Path) -> list[dict]:
    """Final playoff boxes saved by the game ingest. Regular season is ignored."""
    folder = Path(root) / "data" / "games"
    if not folder.is_dir():
        return []
    games = []
    for path in sorted(folder.glob("*.json")):
        if path.name in SKIP_FILES:
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(document, dict) or document.get("postseason") is not True:
            continue
        if not str(document.get("status") or "").strip().lower().startswith("final"):
            continue
        if not isinstance(document.get("players"), list):
            continue
        if not isinstance(document.get("away"), dict) or not isinstance(document.get("home"), dict):
            continue
        games.append(document)
    return games


def _positive_int(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    number = int(value)
    return number if number > 0 else None


def _whole(value) -> int | None:
    """Whole number, including zero. Missing or fractional values stay missing."""
    if isinstance(value, bool) or value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not value.is_integer():
            return None
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
        return int(text)
    return None


def whole_minutes(value) -> int | None:
    """Minutes played, rounded half up when the box uses clock time."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if ":" in text:
        try:
            nums = [int(bit) for bit in text.split(":")]
        except ValueError:
            return None
        seconds = 0
        for num in nums:
            seconds = seconds * 60 + num
        return int((Decimal(seconds) / Decimal(60)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    number = _whole(text)
    if number is not None:
        return number
    try:
        parsed = Decimal(text)
    except Exception:
        return None
    return int(parsed.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def store_average(total: int, games: int):
    """Short decimal that still recovers this integer total."""
    if games <= 0:
        return None
    for places in ("0.01", "0.001", "0.0001", "0.00001", "0.000001"):
        shown = (Decimal(int(total)) / Decimal(int(games))).quantize(Decimal(places), rounding=ROUND_HALF_UP)
        candidate = float(shown)
        if per_game.counting_total(candidate, games) == int(total):
            return candidate
    return float(Decimal(int(total)) / Decimal(int(games)))


def store_percent(made: int, attempted: int):
    if attempted <= 0:
        return None
    shown = (Decimal(100) * Decimal(int(made)) / Decimal(int(attempted))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return float(shown)


def box_counting(player: dict) -> dict:
    counted = {}
    for field, source in BOX_FIELDS.items():
        if field == "min":
            counted[field] = whole_minutes(player.get("minutes"))
        else:
            counted[field] = _whole(player.get(source))
    return counted


def log_counting(game: dict) -> dict:
    counted = {field: None for field in COUNTING}
    counted["min"] = whole_minutes(game.get("minutes"))
    for field in ("pts", "reb", "ast", "stl", "blk", "turnover"):
        counted[field] = _whole(game.get(field))
    return counted


def _abbr(team) -> str:
    if not isinstance(team, dict):
        return ""
    return str(team.get("abbreviation") or "").strip().upper()


def pacific_day(value) -> str:
    text = str(value or "").strip()
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return text
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text[:10]
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(PACIFIC).date().isoformat()


def game_timestamp(day: str) -> str:
    """Noon Pacific, stored in UTC, so the page shows the game's calendar day."""
    local = dt.datetime.fromisoformat(str(day)[:10]).replace(tzinfo=PACIFIC, hour=12)
    return local.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def box_game_id(document: dict):
    primary = document.get("balldontlie_game_id")
    if isinstance(primary, int) and not isinstance(primary, bool) and primary > 0:
        return primary
    espn = document.get("espn_game_id")
    if isinstance(espn, int) and not isinstance(espn, bool) and espn > 0:
        return espn
    if isinstance(espn, str) and espn.isdigit():
        return int(espn)
    return None


def same_game(logged: dict, document: dict) -> bool:
    ident = box_game_id(document)
    if ident is not None and logged.get("game_id") == ident:
        return True
    if pacific_day(logged.get("date")) != str(document.get("date") or "")[:10]:
        return False
    logged_sides = {_abbr(logged.get("home_team")), _abbr(logged.get("visitor_team"))}
    box_sides = {_abbr(document.get("home")), _abbr(document.get("away"))}
    return bool(logged_sides - {""}) and logged_sides == box_sides


def _known_team(side: dict, known: list[dict]) -> dict:
    abbr = _abbr(side)
    for item in known:
        if isinstance(item, dict) and _abbr(item) == abbr and (item.get("full_name") or item.get("name")):
            return {key: item.get(key) for key in TEAM_KEYS}
    return {key: side.get(key) for key in TEAM_KEYS}


def _refresh_percentages(row: dict) -> None:
    games = row.get("games_played")
    if not isinstance(games, int) or games <= 0:
        return
    for made_key, attempt_key, pct_key in PERCENTAGES:
        made = per_game.counting_total(row.get(made_key), games) if row.get(made_key) is not None else None
        attempted = per_game.counting_total(row.get(attempt_key), games) if row.get(attempt_key) is not None else None
        if made is None or attempted is None:
            continue
        row[pct_key] = store_percent(made, attempted)


def _bump(row: dict, counting: dict) -> None:
    old = row.get("games_played")
    if not isinstance(old, int) or isinstance(old, bool) or old < 0:
        old = 0
    new = old + 1
    for field in COUNTING:
        addition = counting.get(field)
        current = row.get(field)
        if old <= 0 or current is None:
            if addition is None:
                continue
            row[field] = store_average(int(addition), new)
            continue
        total = per_game.counting_total(current, old)
        if total is None:
            continue
        if addition is None:
            row[field] = store_average(total, new)
        else:
            row[field] = store_average(total + int(addition), new)
    row["games_played"] = new
    _refresh_percentages(row)


def _blank_row(player_id: int, season: int, team: dict) -> dict:
    row = {
        "player_id": player_id,
        "season": season,
        "season_type": 3,
        "team": team,
        "games_played": 0,
        "gap_fill": True,
    }
    for field in COUNTING:
        row[field] = None
    for _made, _attempt, pct_key in PERCENTAGES:
        row[pct_key] = None
    return row


def _log_row(player_id: int, document: dict, player: dict, counting: dict, known: list[dict]) -> dict:
    away = _known_team(document.get("away") or {}, known)
    home = _known_team(document.get("home") or {}, known)
    abbr = str(player.get("team") or "").strip().upper()
    team = home if _abbr(home) == abbr else away
    minutes = counting.get("min")
    return {
        "game_id": box_game_id(document),
        "player_id": player_id,
        "date": game_timestamp(str(document.get("date") or "")),
        "season": document.get("season"),
        "postseason": True,
        "team": team,
        "home_team": home,
        "visitor_team": away,
        "home_score": _whole((document.get("home") or {}).get("score")),
        "away_score": _whole((document.get("away") or {}).get("score")),
        "minutes": None if minutes is None else str(minutes),
        "pts": None if counting.get("pts") is None else float(counting["pts"]),
        "ast": None if counting.get("ast") is None else float(counting["ast"]),
        "reb": None if counting.get("reb") is None else float(counting["reb"]),
        "stl": None if counting.get("stl") is None else float(counting["stl"]),
        "blk": None if counting.get("blk") is None else float(counting["blk"]),
        "turnover": None if counting.get("turnover") is None else float(counting["turnover"]),
    }


def _played_stat(game: dict) -> bool:
    """A log row that records a game the player took the floor for.

    A missing point total is a did-not-play placeholder. Zero points is a game.
    """
    points = game.get("pts")
    if points is not None and not isinstance(points, bool):
        return True
    minutes = whole_minutes(game.get("minutes"))
    return minutes is not None and minutes > 0


def _apply_log_counting(row: dict, counting: dict) -> None:
    minutes = counting.get("min")
    if row.get("minutes") in (None, "", "0") and minutes:
        row["minutes"] = str(minutes)
    for field in ("pts", "ast", "reb", "stl", "blk", "turnover"):
        if row.get(field) is None and counting.get(field) is not None:
            row[field] = float(counting[field])


def _upsert_log(recent: list, player_id: int, document: dict, player: dict, counting: dict, known: list[dict]) -> None:
    for item in recent:
        if isinstance(item, dict) and same_game(item, document):
            if not _played_stat(item):
                _apply_log_counting(item, counting)
            return
    recent.append(_log_row(player_id, document, player, counting, known))


def reconcile_player(player_id: int, stats: list, recent: list, games: list[dict]) -> list[dict]:
    """Add final playoff games the season line has not counted. Returns created rows.

    The season list and the recent-game list are updated in place. A second call
    with the same boxes does not count a game twice.
    """
    if isinstance(player_id, bool) or not isinstance(player_id, int):
        return []
    grouped: dict[tuple, list] = {}
    for document in games:
        season = document.get("season")
        if isinstance(season, bool) or not isinstance(season, int):
            continue
        for player in document.get("players") or []:
            if not isinstance(player, dict) or player.get("player_id") != player_id:
                continue
            if player.get("did_not_play"):
                continue
            abbr = str(player.get("team") or "").strip().upper()
            grouped.setdefault((season, abbr), []).append((document, player))
    if not grouped:
        return []
    known = []
    for row in stats:
        if isinstance(row, dict) and isinstance(row.get("team"), dict):
            known.append(row["team"])
    for game in recent:
        if isinstance(game, dict):
            for key in ("team", "home_team", "visitor_team"):
                if isinstance(game.get(key), dict):
                    known.append(game[key])
    created = []
    changes = False
    for (season, abbr), appearances in grouped.items():
        rows = [
            row for row in stats
            if isinstance(row, dict) and row.get("season") == season and row.get("season_type") == 3
            and (_abbr(row.get("team")) == abbr or (_abbr(row.get("team")) == "" and len(grouped) == 1))
        ]
        logged = [
            game for game in recent
            if isinstance(game, dict) and game.get("postseason") is True and game.get("season") == season
            and (_abbr(game.get("team")) == abbr or (_abbr(game.get("team")) == "" and len(grouped) == 1))
        ]
        logged.sort(key=lambda game: str(game.get("date") or ""))
        row = rows[0] if len(rows) == 1 else None
        if row is None and len(rows) > 1:
            continue
        games_played = row.get("games_played") if row else 0
        if not isinstance(games_played, int) or isinstance(games_played, bool) or games_played < 0:
            games_played = 0
        # A placeholder with no points is not a game the line already counted.
        # Match played boxes against rows that actually record stats.
        played_log = [game for game in logged if _played_stat(game)]
        unmatched = [
            (document, player) for document, player in appearances
            if not any(same_game(game, document) for game in played_log)
        ]
        if row is None:
            side = next(
                (document.get("home") if _abbr(document.get("home")) == abbr else document.get("away")
                 for document, _player in appearances),
                {},
            )
            row = _blank_row(player_id, season, _known_team(side or {}, known))
            stats.append(row)
            created.append(row)
            games_played = 0
            changes = True
        if games_played < len(played_log):
            # The newest played log rows are the games the aggregate has not counted.
            for extra in played_log[games_played:]:
                match = next(((document, player) for document, player in appearances if same_game(extra, document)), None)
                if match is None:
                    _bump(row, log_counting(extra))
                else:
                    _bump(row, box_counting(match[1]))
            games_played = row.get("games_played")
            if not isinstance(games_played, int) or isinstance(games_played, bool) or games_played < 0:
                games_played = 0
            changes = True
        if unmatched:
            ordered = sorted(unmatched, key=lambda item: str(item[0].get("date") or ""))
            if games_played <= len(played_log):
                bump_these, log_only = ordered, []
            elif games_played >= len(played_log) + len(ordered):
                # The aggregate already includes every box that is missing from the log.
                bump_these, log_only = [], ordered
            else:
                lead = games_played - len(played_log)
                bump_these, log_only = ordered[lead:], ordered[:lead]
            for document, player in bump_these:
                counting = box_counting(player)
                _bump(row, counting)
                _upsert_log(recent, player_id, document, player, counting, known)
            for document, player in log_only:
                _upsert_log(recent, player_id, document, player, box_counting(player), known)
            changes = True
    if changes:
        recent.sort(key=lambda game: str(game.get("date") or ""), reverse=True)
    return created


def _profiles(root: Path) -> list[dict]:
    folder = Path(root) / "data" / "wnba" / "players"
    if not folder.is_dir():
        return []
    found = []
    for path in sorted(folder.glob("*.json")):
        try:
            profile = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(profile, dict):
            found.append(profile)
    return found


def _profile_name(profile: dict) -> str:
    player = profile.get("player") if isinstance(profile.get("player"), dict) else {}
    return (str(player.get("first_name") or "") + " " + str(player.get("last_name") or "")).strip() or str(profile.get("slug") or "player")


def count_problems(root: Path) -> list[str]:
    """Lines with fewer playoff games than the player actually played.

    Did-not-play lines are not games played. A player who misses one game of a
    six-game run can have a line of five. A line below the played appearances
    is behind the boxes.
    """
    games = load_games(root)
    if not games:
        return []
    team_games: dict[tuple, int] = {}
    played: dict[tuple, int] = {}
    dnps: dict[tuple, int] = {}
    names: dict[tuple, str] = {}
    for document in games:
        season = document.get("season")
        if isinstance(season, bool) or not isinstance(season, int):
            continue
        sides = []
        for key in ("away", "home"):
            abbr = _abbr(document.get(key))
            if abbr:
                sides.append(abbr)
                team_games[(season, abbr)] = team_games.get((season, abbr), 0) + 1
        seen = set()
        for player in document.get("players") or []:
            if not isinstance(player, dict):
                continue
            abbr = str(player.get("team") or "").strip().upper()
            ident = player.get("player_id")
            if isinstance(ident, bool) or not isinstance(ident, int) or abbr not in sides:
                continue
            key = (season, abbr, ident)
            if key in seen:
                continue
            seen.add(key)
            names.setdefault(key, str(player.get("name") or ident))
            if player.get("did_not_play"):
                dnps[key] = dnps.get(key, 0) + 1
            else:
                played[key] = played.get(key, 0) + 1
    by_player: dict[tuple, int] = {}
    labels: dict[int, str] = {}
    for profile in _profiles(root):
        player = profile.get("player") if isinstance(profile.get("player"), dict) else {}
        ident = player.get("id")
        if isinstance(ident, bool) or not isinstance(ident, int):
            continue
        labels[ident] = _profile_name(profile)
        for row in profile.get("season_stats") or []:
            if not isinstance(row, dict) or row.get("season_type") != 3:
                continue
            season = row.get("season")
            abbr = _abbr(row.get("team"))
            games_played = row.get("games_played")
            if isinstance(season, bool) or not isinstance(season, int) or not abbr:
                continue
            if isinstance(games_played, bool) or not isinstance(games_played, int):
                continue
            bucket = (season, abbr, ident)
            by_player[bucket] = by_player.get(bucket, 0) + games_played
    problems = []
    for key, appearances in sorted(played.items(), key=lambda item: (item[0][0], item[0][1], names.get(item[0], ""))):
        season, abbr, ident = key
        recorded = by_player.get(key, 0)
        if recorded >= appearances:
            continue
        inactive = dnps.get(key, 0)
        team_total = team_games.get((season, abbr), appearances + inactive)
        name = labels.get(ident) or names.get(key) or str(ident)
        problems.append(
            f"{name}: {season} {abbr} playoff line has {recorded} games; "
            f"the club played {team_total}, and the boxes list {appearances} played and {inactive} DNP."
        )
    return problems


def require_counts(root: Path) -> None:
    problems = count_problems(root)
    if not problems:
        return
    preview = "\n".join(problems[:40])
    extra = f"\n... and {len(problems) - 40} more." if len(problems) > 40 else ""
    raise RuntimeError("Playoff game counts are behind the box scores.\n" + preview + extra)
