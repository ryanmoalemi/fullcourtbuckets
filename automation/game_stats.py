#!/usr/bin/env python3
"""WNBA game boxes for recaps. balldontlie is the source. ESPN is the cross-check.

The API key stays in the environment. This module never prints it, writes it, or
puts it in a URL. Tests call the pure builders and a fake client, so they run
with no key and no network.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

import wnba_sync as sync

PT = ZoneInfo("America/Los_Angeles")
ESPN_HOSTS = (
    "https://site.web.api.espn.com",
    "https://site.api.espn.com",
)
USER_AGENT = "FullCourtBuckets/1.0 (+https://fullcourtbuckets.com/)"
OPENAPI = "https://www.balldontlie.io/openapi/wnba.yml"
SERIES_REASON = "The WNBA API has no series endpoint. Series text in the cross-check is from ESPN."
GAME_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*$")

# Public WNBA paths from the OpenAPI. Item URLs such as games/{id} are the same
# resources as the collections, so they are not probed separately.
PROBE_ENDPOINTS = (
    "teams",
    "players",
    "players/active",
    "games",
    "player_stats",
    "team_stats",
    "player_season_stats",
    "team_season_stats",
    "standings",
    "player_injuries",
    "plays",
    "player_game_advanced_stats",
    "team_game_advanced_stats",
    "player_season_advanced_stats",
    "team_season_advanced_stats",
    "player_shot_locations",
    "team_shot_locations",
    "odds",
    "odds/opening",
    "odds/player_props",
    "odds/player_props/opening",
)
BOX_ENDPOINTS = frozenset({
    "games", "player_stats", "team_stats", "standings", "plays",
    "team_game_advanced_stats", "player_game_advanced_stats",
})
ALIASES = {
    "NYL": "NY", "NYK": "NY",
    "LVA": "LV", "GSV": "GS", "GSW": "GS",
    "CONN": "CON", "PHO": "PHX", "WAS": "WSH",
}
TEAM_FIELDS = (
    "fgm", "fga", "fg3m", "fg3a", "ftm", "fta",
    "oreb", "dreb", "reb", "ast", "stl", "blk", "turnovers", "fouls", "pts",
)
TEAM_COMPARE = (
    "fgm", "fga", "fg3m", "fg3a", "ftm", "fta",
    "oreb", "dreb", "reb", "ast", "stl", "blk", "turnovers", "fouls",
)
PLAYER_COMPARE = ("pts", "reb", "ast", "minutes")
PLAYER_FIELDS = (
    "minutes", "pts", "reb", "oreb", "dreb", "ast", "stl", "blk",
    "turnovers", "fouls", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "plus_minus",
)
ESPN_TEAM_NAMES = {
    "fieldGoalsMade-fieldGoalsAttempted": ("fgm", "fga"),
    "threePointFieldGoalsMade-threePointFieldGoalsAttempted": ("fg3m", "fg3a"),
    "freeThrowsMade-freeThrowsAttempted": ("ftm", "fta"),
    "totalRebounds": "reb",
    "offensiveRebounds": "oreb",
    "defensiveRebounds": "dreb",
    "assists": "ast",
    "steals": "stl",
    "blocks": "blk",
    "turnovers": "turnovers",
    "fouls": "fouls",
    "rebounds": "reb",
    "fieldGoalsMade": "fgm",
    "fieldGoalsAttempted": "fga",
    "threePointFieldGoalsMade": "fg3m",
    "threePointFieldGoalsAttempted": "fg3a",
    "freeThrowsMade": "ftm",
    "freeThrowsAttempted": "fta",
}
ESPN_LABELS = {
    "MIN": "minutes", "PTS": "pts", "REB": "reb", "AST": "ast", "TO": "turnovers",
    "STL": "stl", "BLK": "blk", "OREB": "oreb", "DREB": "dreb", "PF": "fouls",
    "+/-": "plus_minus",
}


class GameStatsError(RuntimeError):
    pass


class EspnError(GameStatsError):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


def canonical(value) -> str:
    text = re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()
    return ALIASES.get(text, text)


def parse_teams(value) -> list[str]:
    found = []
    for part in re.split(r"[\s,;/]+", str(value or "").strip()):
        if not part:
            continue
        abbr = canonical(part)
        if not re.fullmatch(r"[A-Z0-9]{2,12}", abbr):
            raise GameStatsError(f"Team abbreviation {part!r} is not usable.")
        if abbr not in found:
            found.append(abbr)
    if len(found) > 8:
        raise GameStatsError("Pass at most eight team abbreviations.")
    return found


def parse_day(value) -> dt.date:
    text = str(value or "").strip()
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        raise GameStatsError("Date must be YYYY-MM-DD.") from None


def parse_espn_id(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if not re.fullmatch(r"\d{5,12}", text):
        raise GameStatsError("ESPN game id must be digits.")
    return text


def game_day(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    if "T" in raw:
        try:
            moment = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            moment = None
        if moment is not None:
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=dt.timezone.utc)
            return moment.astimezone(PT).date()
    try:
        return dt.date.fromisoformat(raw[:10])
    except ValueError:
        return None


def as_signed(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip().replace("+", "")
        if text in ("", "--", "-"):
            return None
        value = text
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if number == int(number):
        return int(number)
    return number


def name_key(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode().lower()
    text = text.replace("'", "").replace("'", "").replace(".", "")
    return re.sub(r"[^a-z0-9]+", "", text)


def minute_parts(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if ":" in text:
        try:
            nums = [int(bit) for bit in text.split(":")]
        except ValueError:
            return ("raw", text)
        total = 0
        for num in nums:
            total = total * 60 + num
        return ("seconds", total)
    try:
        number = float(text)
    except ValueError:
        return ("raw", text)
    if not math.isfinite(number):
        return ("raw", text)
    if number == int(number):
        return ("seconds", int(number) * 60)
    return ("seconds", int(round(number * 60)))


def minutes_equal(left, right) -> bool:
    return minute_parts(left) == minute_parts(right)


def numbers_equal(left, right) -> bool:
    if left is None and right is None:
        return True
    a, b = as_signed(left), as_signed(right)
    if a is None or b is None:
        return str(left).strip() == str(right).strip()
    return a == b


def minute_text(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if ":" in text:
        return text
    number = as_signed(text)
    if isinstance(number, int):
        return str(number)
    if isinstance(number, float):
        return str(number)
    return text


def redact(text, key) -> str:
    if not key or len(key) < 12 or not text or key not in text:
        return text
    return text.replace(key, "[redacted]")


def file_token(team) -> str:
    abbr = canonical((team or {}).get("abbreviation"))
    if re.fullmatch(r"[A-Z0-9]{2,12}", abbr):
        return abbr.lower()
    ident = (team or {}).get("id")
    if isinstance(ident, int) and not isinstance(ident, bool) and ident > 0:
        return f"t{ident}"
    return "tbd"


def game_slug(day, away, home) -> str:
    slug = f"{day.isoformat()}-{file_token(away)}-{file_token(home)}"
    if not GAME_NAME.fullmatch(slug):
        raise GameStatsError("Refusing an unsafe game file name.")
    return slug


def box_url(espn_id):
    if espn_id and re.fullmatch(r"\d{5,12}", str(espn_id)):
        return f"https://www.espn.com/wnba/boxscore/_/gameId/{espn_id}"
    return None


def wanted(game, teams, espn_id) -> bool:
    if espn_id:
        return str(game.get("espn_game_id") or "") == espn_id
    if not teams:
        return True
    abbrs = {
        canonical(game["away"]["abbreviation"]),
        canonical(game["home"]["abbreviation"]),
    }
    needed = {canonical(team) for team in teams}
    if len(needed) >= 2:
        return needed <= abbrs
    return bool(needed & abbrs)


def classify_http(code, detail) -> str:
    text = str(detail or "").lower()
    denied_words = ("upgrade", "not authorized", "unauthorized", "forbidden", "subscription", "your plan")
    if code in (400, 401, 402, 403, 404) and any(word in text for word in denied_words):
        return "denied"
    if code == 200:
        return "allowed"
    if code == 400:
        return "allowed"
    if code == 404:
        return "not_found"
    if code in (401, 402, 403):
        return "denied"
    if code == 429:
        return "rate_limited"
    return "error"


def endpoint_allowed(access, name) -> bool:
    row = (access.get("endpoints") or {}).get(name) or {}
    if not row:
        return True
    return row.get("status") in ("allowed", "not_found", "error", "rate_limited")


def periods_sum(periods, away_score, home_score) -> bool:
    if not periods or away_score is None or home_score is None:
        return False
    if any(row.get("away") is None or row.get("home") is None for row in periods):
        return False
    numbers = [row.get("period") for row in periods]
    if numbers != list(range(1, len(periods) + 1)):
        return False
    return sum(row["away"] for row in periods) == away_score and sum(row["home"] for row in periods) == home_score


def choose_periods(candidates, away_score, home_score):
    """First candidate whose quarters add up to the final, with no gaps."""
    for name, periods in candidates:
        if periods_sum(periods, away_score, home_score):
            return name, periods
    return None, None


def periods_from_plays(plays):
    if not isinstance(plays, list):
        return None
    latest = {}
    for play in plays:
        if not isinstance(play, dict):
            continue
        period = as_signed(play.get("period"))
        if not isinstance(period, int) or period <= 0:
            continue
        order = as_signed(play.get("order")) or 0
        home = as_signed(play.get("home_score"))
        away = as_signed(play.get("away_score"))
        if away is None:
            away = as_signed(play.get("visitor_score"))
        if home is None or away is None:
            continue
        current = latest.get(period)
        if current is None or order >= current[0]:
            latest[period] = (order, home, away)
    if not latest:
        return None
    ordered = sorted(latest)
    if ordered != list(range(1, ordered[-1] + 1)):
        return None
    rows, prev_home, prev_away = [], 0, 0
    for period in ordered:
        _, home, away = latest[period]
        rows.append({"period": period, "away": away - prev_away, "home": home - prev_home})
        prev_home, prev_away = home, away
    if any(row["away"] < 0 or row["home"] < 0 for row in rows):
        return None
    return rows


def _pts_of(stats):
    if not isinstance(stats, dict):
        return None
    for key, value in stats.items():
        if str(key).lower() in ("pts", "points", "pts_total"):
            return as_signed(value)
    return None


def _abbr_of(row):
    team = row.get("team") if isinstance(row, dict) else None
    if isinstance(team, dict):
        return canonical(team.get("abbreviation"))
    return ""


def periods_from_advanced(rows, away_abbr, home_abbr, *, sum_players=False):
    """Quarter points from advanced rows. period 0 is the full game and is ignored."""
    if not isinstance(rows, list):
        return None
    away_abbr, home_abbr = canonical(away_abbr), canonical(home_abbr)
    buckets = {}
    seen_players = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        period = as_signed(row.get("period"))
        if not isinstance(period, int) or period <= 0:
            continue
        abbr = _abbr_of(row)
        points = _pts_of(row.get("stats"))
        if points is None or abbr not in (away_abbr, home_abbr):
            continue
        if sum_players:
            player = row.get("player") if isinstance(row.get("player"), dict) else {}
            marker = (period, abbr, player.get("id"))
            if marker in seen_players and seen_players[marker] != points:
                return None
            seen_players[marker] = points
            slot = buckets.setdefault(period, {away_abbr: 0, home_abbr: 0, "seen": set()})
            if marker not in slot["seen"]:
                slot[abbr] += points
                slot["seen"].add(marker)
        else:
            slot = buckets.setdefault(period, {})
            if abbr in slot and slot[abbr] != points:
                return None
            slot[abbr] = points
    if not buckets:
        return None
    ordered = sorted(buckets)
    if ordered != list(range(1, ordered[-1] + 1)):
        return None
    built = []
    for period in ordered:
        slot = buckets[period]
        if away_abbr not in slot or home_abbr not in slot:
            return None
        built.append({"period": period, "away": slot[away_abbr], "home": slot[home_abbr]})
    return built


def team_view(raw):
    raw = raw if isinstance(raw, dict) else {}
    try:
        parsed = sync.team(raw) if raw else None
    except sync.SyncError:
        parsed = None
    parsed = parsed or {}
    abbr = canonical(parsed.get("abbreviation") or raw.get("abbreviation"))
    return {
        "id": parsed.get("id") if isinstance(parsed.get("id"), int) else as_signed(raw.get("id")),
        "abbreviation": abbr,
        "full_name": parsed.get("full_name") or raw.get("full_name") or raw.get("displayName") or abbr,
        "name": parsed.get("name") or raw.get("name"),
        "city": parsed.get("city") or raw.get("city"),
        "conference": parsed.get("conference") or raw.get("conference"),
    }


def empty_totals():
    return {key: None for key in TEAM_FIELDS}


def player_shell(name, team, player_id=None, espn_player_id=None, did_not_play=False):
    row = {
        "player_id": player_id,
        "espn_player_id": espn_player_id,
        "name": name,
        "team": team,
        "did_not_play": bool(did_not_play),
    }
    row.update({key: None for key in PLAYER_FIELDS})
    return row


def provider_player(raw):
    player = raw.get("player") if isinstance(raw.get("player"), dict) else {}
    team = team_view(raw.get("team"))
    first = str(player.get("first_name") or "").strip()
    last = str(player.get("last_name") or "").strip()
    name = (first + " " + last).strip() or str(player.get("display_name") or "").strip()
    try:
        player_id = sync.identifier(player.get("id"))
    except sync.SyncError:
        player_id = None
    row = player_shell(name, team["abbreviation"], player_id=player_id)
    mapping = {
        "min": "minutes", "minutes": "minutes", "pts": "pts", "reb": "reb", "oreb": "oreb",
        "dreb": "dreb", "ast": "ast", "stl": "stl", "blk": "blk", "turnover": "turnovers",
        "turnovers": "turnovers", "pf": "fouls", "fouls": "fouls", "fgm": "fgm", "fga": "fga",
        "fg3m": "fg3m", "fg3a": "fg3a", "ftm": "ftm", "fta": "fta", "plus_minus": "plus_minus",
    }
    for source, target in mapping.items():
        if source not in raw or raw.get(source) is None:
            continue
        if target == "minutes":
            row[target] = minute_text(raw.get(source))
        else:
            row[target] = as_signed(raw.get(source))
    row["did_not_play"] = _did_not_play(row)
    return row


def _did_not_play(row) -> bool:
    if row.get("did_not_play"):
        return True
    minutes = minute_parts(row.get("minutes"))
    no_time = minutes is None or minutes == ("seconds", 0)
    quiet = all(row.get(key) in (None, 0) for key in ("pts", "reb", "ast", "fga", "fta"))
    return bool(no_time and quiet and row.get("minutes") in (None, "0", "00", "0:00", "00:00"))


def sum_players(players, key):
    active = [row for row in players if not row.get("did_not_play")]
    if not active or any(row.get(key) is None for row in active):
        return None
    total = sum(row[key] for row in active)
    return int(total) if total == int(total) else total


def totals_from_players(players):
    totals = empty_totals()
    for key in TEAM_FIELDS:
        totals[key] = sum_players(players, key)
    return totals


def totals_from_team_row(raw):
    totals = empty_totals()
    mapping = {
        "fgm": "fgm", "fga": "fga", "fg3m": "fg3m", "fg3a": "fg3a", "ftm": "ftm", "fta": "fta",
        "oreb": "oreb", "dreb": "dreb", "reb": "reb", "ast": "ast", "stl": "stl", "blk": "blk",
        "turnovers": "turnovers", "turnover": "turnovers", "fouls": "fouls", "pf": "fouls", "pts": "pts",
    }
    for source, target in mapping.items():
        if source in raw and raw.get(source) is not None:
            totals[target] = as_signed(raw.get(source))
    return totals


def row_game_id(raw):
    game = raw.get("game") if isinstance(raw, dict) else None
    if isinstance(game, dict):
        try:
            return sync.identifier(game.get("id"))
        except sync.SyncError:
            return None
    try:
        return sync.identifier(raw.get("game_id")) if isinstance(raw, dict) else None
    except sync.SyncError:
        return None


def standing_view(raw):
    team = team_view(raw.get("team"))
    return {
        "abbreviation": team["abbreviation"],
        "full_name": team["full_name"],
        "team_id": team["id"],
        "season": as_signed(raw.get("season")),
        "conference": raw.get("conference"),
        "wins": as_signed(raw.get("wins")),
        "losses": as_signed(raw.get("losses")),
        "win_percentage": as_signed(raw.get("win_percentage")),
        "games_behind": as_signed(raw.get("games_behind")),
        "home_record": raw.get("home_record"),
        "away_record": raw.get("away_record"),
        "conference_record": raw.get("conference_record"),
        "playoff_seed": as_signed(raw.get("playoff_seed")),
    }


def split_made(value):
    text = str(value or "").strip()
    if "-" not in text:
        return None, None
    made, attempts = text.split("-", 1)
    return as_signed(made), as_signed(attempts)


def espn_totals(statistics):
    totals = empty_totals()
    for stat in statistics or []:
        if not isinstance(stat, dict):
            continue
        name = str(stat.get("name") or "")
        display = stat.get("displayValue")
        if display is None:
            display = stat.get("value")
        mapped = ESPN_TEAM_NAMES.get(name)
        if isinstance(mapped, tuple):
            made, attempts = split_made(display)
            totals[mapped[0]] = made if made is not None else totals[mapped[0]]
            totals[mapped[1]] = attempts if attempts is not None else totals[mapped[1]]
        elif isinstance(mapped, str) and totals.get(mapped) is None:
            totals[mapped] = as_signed(display)
    return totals


def espn_side(competitor):
    team = competitor.get("team") if isinstance(competitor.get("team"), dict) else {}
    abbr = canonical(team.get("abbreviation"))
    lines = []
    for row in competitor.get("linescores") or []:
        if isinstance(row, dict):
            lines.append(as_signed(row.get("value") if row.get("value") is not None else row.get("displayValue")))
    return {
        "id": as_signed(team.get("id")),
        "abbreviation": abbr,
        "full_name": team.get("displayName") or team.get("name") or abbr,
        "name": team.get("shortDisplayName") or team.get("name"),
        "home": competitor.get("homeAway") == "home",
        "score": as_signed(competitor.get("score")),
        "lines": lines,
        "totals": empty_totals(),
    }


def _series_rows(value):
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def pick_series(value):
    rows = _series_rows(value)
    for kind in ("playoff", "postseason"):
        for row in rows:
            if str(row.get("type") or "").lower() == kind:
                return row
    return rows[-1] if rows else None


def series_view(raw, id_to_abbr):
    if not isinstance(raw, dict):
        return None
    teams = []
    for row in raw.get("competitors") or []:
        if not isinstance(row, dict):
            continue
        ident = str(row.get("id") or "")
        teams.append({
            "abbreviation": id_to_abbr.get(ident) or id_to_abbr.get(as_signed(ident)),
            "wins": as_signed(row.get("wins")),
        })
    return {
        "source": "espn",
        "type": raw.get("type"),
        "title": raw.get("title"),
        "summary": raw.get("summary"),
        "completed": bool(raw.get("completed")),
        "games": as_signed(raw.get("totalCompetitions")),
        "teams": [row for row in teams if row.get("abbreviation")],
    }


def parse_scoreboard_event(event):
    if not isinstance(event, dict):
        return None
    competitions = event.get("competitions") or []
    comp = competitions[0] if competitions and isinstance(competitions[0], dict) else {}
    status = ((comp.get("status") or {}).get("type") or {})
    sides = [espn_side(row) for row in comp.get("competitors") or [] if isinstance(row, dict)]
    away = next((row for row in sides if not row["home"]), None)
    home = next((row for row in sides if row["home"]), None)
    if not away or not home:
        return None
    season = event.get("season") if isinstance(event.get("season"), dict) else {}
    series = pick_series(comp.get("series"))
    id_to_abbr = {str(row["id"]): row["abbreviation"] for row in sides if row.get("id") is not None}
    day = game_day(event.get("date") or comp.get("date"))
    final = str(status.get("state") or "") == "post" or str(status.get("name") or "").startswith("STATUS_FINAL")
    periods = []
    if len(away["lines"]) == len(home["lines"]) and away["lines"]:
        periods = [
            {"period": index, "away": a, "home": h}
            for index, (a, h) in enumerate(zip(away["lines"], home["lines"]), start=1)
        ]
    return {
        "espn_game_id": str(event.get("id") or ""),
        "date": day,
        "season": as_signed(season.get("year")) or (day.year if day else None),
        "postseason": season.get("type") in (3, "3") or str((series or {}).get("type") or "").lower() == "playoff",
        "final": final,
        "from_summary": False,
        "away": away,
        "home": home,
        "periods": periods,
        "players": [],
        "series": series_view(series, id_to_abbr),
    }


def parse_summary(payload):
    if not isinstance(payload, dict):
        raise EspnError("ESPN summary was not an object.")
    header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
    competitions = header.get("competitions") or []
    comp = competitions[0] if competitions and isinstance(competitions[0], dict) else {}
    status = ((comp.get("status") or {}).get("type") or {})
    sides = [espn_side(row) for row in comp.get("competitors") or [] if isinstance(row, dict)]
    away = next((row for row in sides if not row["home"]), None)
    home = next((row for row in sides if row["home"]), None)
    if not away or not home:
        raise EspnError("ESPN summary had no two-team game.")
    box = payload.get("boxscore") if isinstance(payload.get("boxscore"), dict) else {}
    for team_row in box.get("teams") or []:
        if not isinstance(team_row, dict):
            continue
        side = away if team_row.get("homeAway") == "away" else home if team_row.get("homeAway") == "home" else None
        if side is None:
            abbr = canonical((team_row.get("team") or {}).get("abbreviation"))
            side = away if abbr == away["abbreviation"] else home if abbr == home["abbreviation"] else None
        if side is not None:
            side["totals"] = espn_totals(team_row.get("statistics"))
            if side["totals"].get("pts") is None:
                side["totals"]["pts"] = side["score"]
    players = []
    for group in box.get("players") or []:
        if not isinstance(group, dict):
            continue
        abbr = canonical((group.get("team") or {}).get("abbreviation"))
        tables = group.get("statistics") or []
        table = tables[0] if tables and isinstance(tables[0], dict) else {}
        labels = [str(label) for label in table.get("labels") or []]
        for athlete in table.get("athletes") or []:
            if not isinstance(athlete, dict):
                continue
            person = athlete.get("athlete") if isinstance(athlete.get("athlete"), dict) else {}
            name = str(person.get("displayName") or "").strip()
            row = player_shell(
                name, abbr, espn_player_id=as_signed(person.get("id")),
                did_not_play=bool(athlete.get("didNotPlay")),
            )
            stats = athlete.get("stats") or []
            paired = dict(zip(labels, stats))
            for label, key in ESPN_LABELS.items():
                if label not in paired:
                    continue
                if key == "minutes":
                    row[key] = minute_text(paired[label])
                else:
                    row[key] = as_signed(paired[label])
            for label, made_key, att_key in (("FG", "fgm", "fga"), ("3PT", "fg3m", "fg3a"), ("FT", "ftm", "fta")):
                if label in paired:
                    row[made_key], row[att_key] = split_made(paired[label])
            if athlete.get("didNotPlay"):
                row["did_not_play"] = True
            else:
                row["did_not_play"] = _did_not_play(row)
            if athlete.get("reason") and row["did_not_play"]:
                row["did_not_play_reason"] = str(athlete.get("reason"))
            players.append(row)
    season = header.get("season") if isinstance(header.get("season"), dict) else {}
    series = pick_series(comp.get("series"))
    id_to_abbr = {str(row["id"]): row["abbreviation"] for row in sides if row.get("id") is not None}
    day = game_day(comp.get("date"))
    periods = []
    if len(away["lines"]) == len(home["lines"]) and away["lines"]:
        periods = [
            {"period": index, "away": a, "home": h}
            for index, (a, h) in enumerate(zip(away["lines"], home["lines"]), start=1)
        ]
    final = str(status.get("state") or "") == "post" or str(status.get("name") or "").startswith("STATUS_FINAL")
    return {
        "espn_game_id": str(header.get("id") or comp.get("id") or ""),
        "date": day,
        "season": as_signed(season.get("year")) or (day.year if day else None),
        "postseason": season.get("type") in (3, "3") or str((series or {}).get("type") or "").lower() == "playoff",
        "final": final,
        "from_summary": True,
        "away": away,
        "home": home,
        "periods": periods,
        "players": players,
        "series": series_view(series, id_to_abbr),
    }


def crosscheck(primary, espn):
    mismatches = []
    unavailable = []

    def compare(field, left, right, *, minutes=False):
        if left is None and right is None:
            return
        equal = minutes_equal(left, right) if minutes else numbers_equal(left, right)
        if not equal:
            mismatches.append({"field": field, "balldontlie": left, "espn": right})

    compare("score.away", primary["away"]["score"], espn["away"]["score"])
    compare("score.home", primary["home"]["score"], espn["home"]["score"])
    if primary.get("periods"):
        left = {row["period"]: row for row in primary["periods"]}
        right = {row["period"]: row for row in espn.get("periods") or []}
        for period in sorted(set(left) | set(right)):
            compare(f"period.{period}.away", (left.get(period) or {}).get("away"), (right.get(period) or {}).get("away"))
            compare(f"period.{period}.home", (left.get(period) or {}).get("home"), (right.get(period) or {}).get("home"))
    else:
        unavailable.append({"field": "periods", "reason": "balldontlie did not return quarter scores"})
    for side in ("away", "home"):
        abbr = primary[side]["abbreviation"]
        for key in TEAM_COMPARE:
            compare(f"team.{abbr}.{key}", primary[side]["totals"].get(key), espn[side]["totals"].get(key))
    if not espn.get("from_summary"):
        unavailable.append({"field": "players", "reason": "ESPN summary was unavailable"})
        return _crosscheck_result(espn, mismatches, unavailable, players_compared=False)
    left_players = {}
    for row in primary["players"]:
        if row.get("did_not_play"):
            continue
        left_players.setdefault(name_key(row.get("name")), []).append(row)
    right_players = {}
    for row in espn.get("players") or []:
        if row.get("did_not_play"):
            continue
        right_players.setdefault(name_key(row.get("name")), []).append(row)
    for key, rows in sorted(right_players.items()):
        found = left_players.get(key) or []
        label = rows[0].get("name") or key
        team = rows[0].get("team") or ""
        if len(found) != 1 or len(rows) != 1:
            mismatches.append({
                "field": f"player.{team}.{label}",
                "balldontlie": None if not found else "ambiguous",
                "espn": label,
            })
            continue
        for stat in PLAYER_COMPARE:
            compare(
                f"player.{team}.{label}.{stat}",
                found[0].get(stat), rows[0].get(stat), minutes=stat == "minutes",
            )
    for key, rows in sorted(left_players.items()):
        if key in right_players:
            continue
        label = rows[0].get("name") or key
        mismatches.append({
            "field": f"player.{rows[0].get('team')}.{label}",
            "balldontlie": label,
            "espn": None,
        })
    return _crosscheck_result(espn, mismatches, unavailable, players_compared=True)


def _crosscheck_result(espn, mismatches, unavailable, players_compared):
    compared = True
    matched = not mismatches and players_compared
    note = "Matched ESPN on the final, quarters, team totals, and each player's points, rebounds, assists, and minutes."
    if mismatches:
        note = "ESPN disagrees with balldontlie. Resolve every field before review."
    elif not players_compared:
        note = "Player lines were not cross-checked."
        matched = False
    elif unavailable:
        note = "Compared fields matched. Some balldontlie fields were not available to compare."
    return {
        "source": "espn",
        "espn_game_id": espn.get("espn_game_id"),
        "compared": compared,
        "matched": matched,
        "players_compared": players_compared,
        "mismatches": mismatches,
        "unavailable": unavailable,
        "espn_series": espn.get("series"),
        "note": note,
    }


def unchecked_crosscheck(espn, note):
    return {
        "source": "espn",
        "espn_game_id": (espn or {}).get("espn_game_id"),
        "compared": False,
        "matched": False,
        "players_compared": False,
        "mismatches": [],
        "unavailable": [],
        "espn_series": (espn or {}).get("series"),
        "note": note,
    }


def points_consistent(doc) -> bool:
    for side in ("away", "home"):
        players = [row for row in doc["players"] if row.get("team") == doc[side]["abbreviation"] and not row.get("did_not_play")]
        if not players:
            return False
        total = sum_players(players, "pts")
        if total is None or total != doc[side]["score"]:
            return False
    return True


def period_phrase(doc) -> str:
    periods = doc.get("periods") or []
    if not periods:
        return "Quarters were not on balldontlie."
    away, home = doc["away"]["abbreviation"], doc["home"]["abbreviation"]
    bits = []
    for row in periods:
        label = f"Q{row['period']}" if row["period"] <= 4 else ("OT" if row["period"] == 5 else f"{row['period'] - 4}OT")
        bits.append(f"{label} {away} {row['away']}, {home} {row['home']}")
    return "Quarters: " + ". ".join(bits) + "."


def shooting(totals, made, attempts):
    if totals.get(made) is None or totals.get(attempts) is None:
        return "n/a"
    return f"{totals[made]}-{totals[attempts]}"


def team_phrase(team) -> str:
    totals = team.get("totals") or {}
    return (
        f"{team.get('full_name')}: {shooting(totals, 'fgm', 'fga')} FG, "
        f"{shooting(totals, 'fg3m', 'fg3a')} 3P, {shooting(totals, 'ftm', 'fta')} FT, "
        f"{totals.get('reb')} rebounds ({totals.get('oreb')} offensive, {totals.get('dreb')} defensive), "
        f"{totals.get('ast')} assists, {totals.get('turnovers')} turnovers"
    )


def markdown(doc) -> str:
    away, home = doc["away"], doc["home"]
    lines = [f"# {away.get('full_name')} at {home.get('full_name')}", ""]
    if doc.get("fallback"):
        lines.append("FLAG: balldontlie did not supply this game. Numbers are from ESPN.")
        lines.append("")
    flag_lines = []
    for flag in doc.get("flags") or []:
        if flag in ("fallback_espn", "crosscheck_mismatch"):
            continue
        if flag == "espn_crosscheck_unavailable":
            flag_lines.append("FLAG: ESPN cross-check did not run.")
        elif flag == "balldontlie_not_marked_final":
            flag_lines.append("FLAG: balldontlie has not marked this game final.")
        elif flag == "player_points_do_not_sum_to_score":
            flag_lines.append("FLAG: player points do not add up to the score.")
        else:
            flag_lines.append(f"FLAG: {flag.replace('_', ' ')}.")
    if flag_lines:
        lines.extend(flag_lines)
        lines.append("")
    when = doc.get("date") or ""
    lines.append(f"{when}. Final. Source: {doc.get('source')}.")
    lines.append("")
    lines.append(f"{home.get('full_name')} {home.get('score')}, {away.get('full_name')} {away.get('score')}.")
    lines.append("")
    lines.append(period_phrase(doc))
    lines.append("")
    lines.append("## Team totals")
    lines.append("")
    lines.append(f"- {team_phrase(away)}")
    lines.append(f"- {team_phrase(home)}")
    lines.append("")
    lines.append("## Players")
    lines.append("")
    for team_abbr in (away["abbreviation"], home["abbreviation"]):
        group = [row for row in doc["players"] if row.get("team") == team_abbr]
        group.sort(key=lambda row: (-(row.get("pts") or 0), row.get("name") or ""))
        for row in group:
            if row.get("did_not_play"):
                reason = f" ({row['did_not_play_reason']})" if row.get("did_not_play_reason") else ""
                lines.append(f"- {row.get('name')}, {team_abbr}: did not play{reason}")
            else:
                lines.append(
                    f"- {row.get('name')}, {team_abbr}: {row.get('minutes')} MIN, "
                    f"{row.get('pts')} PTS, {row.get('reb')} REB, {row.get('ast')} AST"
                )
    lines.append("")
    lines.append("## ESPN cross-check")
    lines.append("")
    cross = doc.get("crosscheck") or {}
    if doc.get("fallback"):
        lines.append("Not run. This file is the ESPN fallback, so there is no second source.")
    elif cross.get("matched") and not cross.get("mismatches"):
        lines.append(f"ESPN game {cross.get('espn_game_id')}. Matched.")
    elif cross.get("mismatches"):
        lines.append("FLAG: ESPN cross-check has mismatches. Resolve them before review.")
        lines.append("")
        for row in cross["mismatches"]:
            lines.append(f"- {row['field']}: balldontlie {row['balldontlie']}, ESPN {row['espn']}")
    else:
        lines.append(cross.get("note") or "ESPN cross-check did not run.")
    for row in cross.get("unavailable") or []:
        lines.append(f"Not compared: {row.get('field')}. {row.get('reason')}")
    series = (cross.get("espn_series") or {}).get("summary")
    if series:
        lines.append("")
        lines.append(f"Series on ESPN: {series}. {SERIES_REASON}")
    standings = doc.get("standings") or {}
    if standings.get("source") == "balldontlie" and standings.get("teams"):
        lines.append("")
        bits = []
        for row in standings["teams"]:
            bits.append(f"{row.get('full_name')} {row.get('wins')}-{row.get('losses')}")
        lines.append("Standings on balldontlie: " + "; ".join(bits) + ".")
    elif standings.get("reason"):
        lines.append("")
        lines.append(f"Standings: {standings['reason']}")
    if doc.get("espn_box_score"):
        lines.append("")
        lines.append(f"ESPN box: {doc['espn_box_score']}")
    lines.append("")
    return "\n".join(lines)


def summary_block(doc, slug) -> str:
    away, home = doc["away"], doc["home"]
    lines = [
        f"### {slug}",
        f"Source: {doc.get('source')}.",
        f"{home.get('full_name')} {home.get('score')}, {away.get('full_name')} {away.get('score')}.",
        period_phrase(doc),
        team_phrase(away),
        team_phrase(home),
    ]
    if doc.get("fallback"):
        lines.insert(2, "FLAG: balldontlie did not supply this game. Numbers are from ESPN.")
        lines.append(f"Reason: {doc.get('fallback_reason')}")
    cross = doc.get("crosscheck") or {}
    if doc.get("fallback"):
        lines.append("ESPN cross-check: not run. This file is the ESPN fallback.")
    elif cross.get("matched"):
        lines.append(f"ESPN {cross.get('espn_game_id')}: matched.")
    elif cross.get("mismatches"):
        lines.append(f"FLAG: ESPN {cross.get('espn_game_id')} mismatches:")
        for row in cross["mismatches"]:
            lines.append(f"- {row['field']}: balldontlie {row['balldontlie']}, ESPN {row['espn']}")
    else:
        lines.append("FLAG: ESPN cross-check did not run. " + str(cross.get("note") or ""))
    if cross.get("unavailable"):
        for row in cross["unavailable"]:
            lines.append(f"Unavailable: {row['field']}. {row['reason']}")
    return "\n".join(lines)


def stable(doc):
    copy = json.loads(json.dumps(doc))
    copy.pop("checked_at", None)
    return copy


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def save_pair(path: Path, doc, text_md, key) -> bool:
    payload = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    if key and len(key) >= 12 and (key in payload or key in text_md):
        raise GameStatsError("Refusing to write a file that contains the API key.")
    md_path = path.with_suffix(".md")
    if path.exists() and md_path.exists():
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = None
        if previous is not None and stable(previous) == stable(doc):
            return False
    atomic_write(md_path, text_md)
    atomic_write(path, payload)
    return True


def existing_slugs(root: Path) -> dict:
    found = {}
    folder = root / "data" / "games"
    if not folder.exists():
        return found
    for path in folder.glob("*.json"):
        if path.name == "balldontlie-endpoints.json":
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        key = None
        if doc.get("balldontlie_game_id"):
            key = f"bdl:{doc['balldontlie_game_id']}"
        elif doc.get("espn_game_id"):
            key = f"espn:{doc['espn_game_id']}"
        found[path.stem] = key
    return found


def assign_slug(root, day, away, home, game_key) -> str:
    base = game_slug(day, away, home)
    current = existing_slugs(root)
    if base not in current or current[base] in (None, game_key):
        return base
    suffix = re.sub(r"[^a-z0-9]+", "", game_key.lower())[:16] or "2"
    slug = f"{base}-{suffix}"
    if not GAME_NAME.fullmatch(slug):
        raise GameStatsError("Refusing an unsafe game file name.")
    return slug


def side_block(team, score, totals, totals_from):
    block = {
        "id": team.get("id"),
        "abbreviation": team.get("abbreviation"),
        "full_name": team.get("full_name"),
        "name": team.get("name"),
        "score": score,
        "totals": totals,
        "totals_from": totals_from,
    }
    return block


def build_bdl_document(game, players, team_rows, plays, team_advanced, player_advanced, standings, stamp):
    away_team = team_view(game.get("visitor_team"))
    home_team = team_view(game.get("home_team"))
    try:
        game_id = sync.identifier(game.get("id"))
    except sync.SyncError:
        return None
    away_players = [row for row in players if row.get("team") == away_team["abbreviation"]]
    home_players = [row for row in players if row.get("team") == home_team["abbreviation"]]
    if not away_players and not home_players:
        return None
    team_by_abbr = {}
    for raw in team_rows:
        abbr = team_view(raw.get("team"))["abbreviation"]
        if abbr:
            team_by_abbr[abbr] = raw
    def pack(team, pool):
        raw = team_by_abbr.get(team["abbreviation"])
        if raw:
            return totals_from_team_row(raw), "team_stats"
        return totals_from_players(pool), "player_sum"
    away_totals, away_from = pack(away_team, away_players)
    home_totals, home_from = pack(home_team, home_players)
    away_score = as_signed(game.get("away_score"))
    home_score = as_signed(game.get("home_score"))
    if away_totals.get("pts") is None:
        away_totals["pts"] = away_score
    if home_totals.get("pts") is None:
        home_totals["pts"] = home_score
    source, periods = choose_periods([
        ("team_game_advanced_stats", periods_from_advanced(team_advanced, away_team["abbreviation"], home_team["abbreviation"])),
        ("plays", periods_from_plays(plays)),
        ("player_game_advanced_stats", periods_from_advanced(
            player_advanced, away_team["abbreviation"], home_team["abbreviation"], sum_players=True,
        )),
    ], away_score, home_score)
    ordered = away_players + home_players
    ordered.sort(key=lambda row: (0 if row.get("team") == away_team["abbreviation"] else 1, -(row.get("pts") or 0), row.get("name") or ""))
    series = {"source": "unavailable", "reason": SERIES_REASON}
    for key in ("series", "series_summary", "playoff_series"):
        if game.get(key):
            series = {"source": "balldontlie", "detail": game.get(key)}
            break
    standings_block = {"source": "unavailable", "reason": "BALLDONTLIE standings was not available on this plan or for this season."}
    if standings:
        wanted_abbrs = {away_team["abbreviation"], home_team["abbreviation"]}
        rows = [standing_view(row) for row in standings if team_view(row.get("team"))["abbreviation"] in wanted_abbrs]
        if rows:
            standings_block = {"source": "balldontlie", "season": rows[0].get("season"), "teams": rows}
    day = game_day(game.get("date"))
    doc = {
        "schema_version": 1,
        "source": "balldontlie",
        "fallback": False,
        "flags": [],
        "checked_at": stamp,
        "date": day.isoformat() if day else None,
        "status": "final" if sync.is_final(game) else str(game.get("status_state") or game.get("status") or ""),
        "season": as_signed(game.get("season")),
        "postseason": bool(game.get("postseason")),
        "balldontlie_game_id": game_id,
        "espn_game_id": None,
        "espn_box_score": None,
        "away": side_block(away_team, away_score, away_totals, away_from),
        "home": side_block(home_team, home_score, home_totals, home_from),
        "periods": periods,
        "periods_source": source,
        "players": ordered,
        "standings": standings_block,
        "series": series,
        "crosscheck": unchecked_crosscheck(None, "ESPN game not matched yet."),
    }
    if not sync.is_final(game):
        doc["flags"].append("balldontlie_not_marked_final")
    if not points_consistent(doc):
        doc["flags"].append("player_points_do_not_sum_to_score")
    return doc


def apply_espn(doc, espn):
    if not espn:
        doc["crosscheck"] = unchecked_crosscheck(None, "No ESPN game matched this balldontlie final.")
        doc["flags"].append("espn_crosscheck_unavailable")
        return doc
    doc["espn_game_id"] = espn.get("espn_game_id")
    doc["espn_box_score"] = box_url(espn.get("espn_game_id"))
    if not espn.get("from_summary"):
        doc["crosscheck"] = unchecked_crosscheck(espn, "ESPN summary was unavailable, so this balldontlie box was not cross-checked.")
        doc["flags"].append("espn_crosscheck_unavailable")
        return doc
    doc["crosscheck"] = crosscheck(doc, espn)
    if doc["crosscheck"]["mismatches"]:
        doc["flags"].append("crosscheck_mismatch")
    elif not doc["crosscheck"]["matched"]:
        doc["flags"].append("espn_crosscheck_unavailable")
    return doc


def build_fallback(espn, reason, stamp):
    away, home = espn["away"], espn["home"]
    players = list(espn.get("players") or [])
    players.sort(key=lambda row: (0 if row.get("team") == away["abbreviation"] else 1, -(row.get("pts") or 0), row.get("name") or ""))
    doc = {
        "schema_version": 1,
        "source": "espn",
        "fallback": True,
        "fallback_reason": reason,
        "flags": ["fallback_espn"],
        "checked_at": stamp,
        "date": espn["date"].isoformat() if espn.get("date") else None,
        "status": "final",
        "season": espn.get("season"),
        "postseason": bool(espn.get("postseason")),
        "balldontlie_game_id": None,
        "espn_game_id": espn.get("espn_game_id"),
        "espn_box_score": box_url(espn.get("espn_game_id")),
        "away": side_block(
            {"id": away.get("id"), "abbreviation": away["abbreviation"], "full_name": away["full_name"], "name": away.get("name")},
            away.get("score"), away.get("totals") or empty_totals(), "espn",
        ),
        "home": side_block(
            {"id": home.get("id"), "abbreviation": home["abbreviation"], "full_name": home["full_name"], "name": home.get("name")},
            home.get("score"), home.get("totals") or empty_totals(), "espn",
        ),
        "periods": espn.get("periods"),
        "periods_source": "espn",
        "players": players,
        "standings": {"source": "unavailable", "reason": "Fallback file. Standings were not taken from ESPN into the primary block."},
        "series": {"source": "unavailable", "reason": SERIES_REASON},
        "crosscheck": unchecked_crosscheck(espn, "This file is the ESPN fallback, so there is no second source to compare."),
    }
    doc["crosscheck"]["espn_series"] = espn.get("series")
    return doc


def read_error_detail(error) -> str:
    try:
        raw = error.read(500)
    except Exception:
        return ""
    text = raw.decode("utf-8", "replace")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return ""
    if isinstance(payload, dict):
        message = payload.get("error") or payload.get("message") or ""
        return str(message)[:180]
    return ""


def probe_once(client, endpoint, params):
    if endpoint not in PROBE_ENDPOINTS:
        raise GameStatsError("Invalid API endpoint.")
    url = sync.BASE + endpoint
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    for attempt in range(4):
        time.sleep(max(0, client.interval - (time.monotonic() - client.last_request)))
        request = urllib.request.Request(url, headers={
            "Authorization": client.key,
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        })
        client.last_request = time.monotonic()
        try:
            with client.opener.open(request, timeout=45) as response:
                response.read()
            return 200, ""
        except sync.SyncError:
            return 0, "redirect rejected"
        except urllib.error.HTTPError as error:
            detail = redact(read_error_detail(error), client.key)
            if error.code == 429:
                client.interval = max(client.interval, 12.2)
            if error.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(min(30, 2 ** attempt))
                continue
            return error.code, detail
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3:
                return 0, "unreachable"
            time.sleep(2 ** attempt)
    return 0, "unreachable"


def probe_params(day: dt.date) -> dict:
    iso = day.isoformat()
    year = day.year
    window = {"start_date": iso, "end_date": iso, "per_page": 1}
    return {
        "teams": {},
        "players": {"per_page": 1},
        "players/active": {"per_page": 1},
        "games": dict(window),
        "player_stats": dict(window),
        "team_stats": dict(window),
        "player_season_stats": {"season": year, "season_type": 2, "per_page": 1},
        "team_season_stats": {"season": year, "season_type": 2, "per_page": 1},
        "standings": {"season": year},
        "player_injuries": {"per_page": 1},
        "plays": {"game_id": 1},
        "player_game_advanced_stats": dict(window),
        "team_game_advanced_stats": dict(window),
        "player_season_advanced_stats": {"season": year, "season_type": "regular", "per_page": 1},
        "team_season_advanced_stats": {"season": year, "season_type": "regular", "per_page": 1},
        "player_shot_locations": {"season": year, "per_page": 1},
        "team_shot_locations": {"season": year, "per_page": 1},
        "odds": {"dates": [iso], "per_page": 1},
        "odds/opening": {"dates": [iso], "per_page": 1},
        "odds/player_props": {"game_id": 1},
        "odds/player_props/opening": {"game_id": 1},
    }


def probe_access(client, day: dt.date) -> dict:
    endpoints = {}
    for name in PROBE_ENDPOINTS:
        code, detail = probe_once(client, name, probe_params(day)[name])
        endpoints[name] = {"status": classify_http(code, detail), "http": code}
        if detail and endpoints[name]["status"] != "allowed":
            endpoints[name]["detail"] = detail
        print(f"endpoint {name}: {endpoints[name]['status']} HTTP {code}")
    return {
        "key_present": True,
        "series_endpoint": False,
        "series_note": SERIES_REASON,
        "openapi": OPENAPI,
        "endpoints": endpoints,
    }


def access_fingerprint(doc) -> dict:
    endpoints = {
        name: {"status": (row or {}).get("status"), "http": (row or {}).get("http")}
        for name, row in sorted((doc.get("endpoints") or {}).items())
    }
    return {
        "key_present": doc.get("key_present"),
        "series_endpoint": doc.get("series_endpoint"),
        "endpoints": endpoints,
    }


def save_access(root: Path, access, stamp, key) -> bool:
    doc = {
        "checked_at": stamp,
        "provider": "balldontlie",
        "base": sync.BASE,
        "key_present": bool(access.get("key_present")),
        "series_endpoint": False,
        "series_note": SERIES_REASON,
        "openapi": OPENAPI,
        "used_for_game_files": sorted(BOX_ENDPOINTS),
        "endpoints": access.get("endpoints") or {},
    }
    if access.get("note"):
        doc["note"] = access["note"]
    path = root / "data" / "games" / "balldontlie-endpoints.json"
    payload = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    if key and len(key) >= 12 and key in payload:
        raise GameStatsError("Refusing to write a file that contains the API key.")
    if path.exists():
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = None
        if previous is not None and access_fingerprint(previous) == access_fingerprint(doc):
            return False
    atomic_write(path, payload)
    return True


def get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
    })
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            code = getattr(response, "status", 200)
    except urllib.error.HTTPError as error:
        raise EspnError(f"ESPN HTTP {error.code}.", code=error.code) from None
    except (urllib.error.URLError, TimeoutError):
        raise EspnError("ESPN was unreachable.") from None
    if raw[:2] == b"\x1f\x8b":
        import gzip
        raw = gzip.decompress(raw)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise EspnError("ESPN returned invalid JSON.") from None
    if not isinstance(payload, dict):
        raise EspnError("ESPN returned an unexpected payload.")
    if code and code >= 400:
        raise EspnError(f"ESPN HTTP {code}.", code=code)
    return payload


def fetch_first(fetch, urls):
    error = None
    for url in urls:
        try:
            payload = fetch(url)
        except EspnError as exc:
            error = exc
            continue
        if isinstance(payload, dict):
            return payload
        error = EspnError("ESPN returned an unexpected payload.")
    raise error or EspnError("ESPN request failed.")


def scoreboard_urls(day: dt.date):
    stamp = day.strftime("%Y%m%d")
    path = f"/apis/site/v2/sports/basketball/wnba/scoreboard?dates={stamp}"
    return [host + path for host in ESPN_HOSTS]


def summary_urls(espn_id: str):
    path = f"/apis/site/v2/sports/basketball/wnba/summary?event={espn_id}"
    return [host + path for host in ESPN_HOSTS]


def safe_all(client, endpoint, params):
    try:
        return client.all(endpoint, params), None
    except sync.SyncError as exc:
        return None, str(exc)


def bdl_players_for(rows, game_id):
    found = []
    for raw in rows or []:
        if row_game_id(raw) != game_id:
            continue
        player = provider_player(raw)
        if player.get("name"):
            found.append(player)
    return found


def match_bdl(espn_game, bdl_games):
    want_away = canonical(espn_game["away"]["abbreviation"])
    want_home = canonical(espn_game["home"]["abbreviation"])
    target = espn_game.get("date")
    ranked = []
    for game in bdl_games or []:
        away = canonical((game.get("visitor_team") or {}).get("abbreviation"))
        home = canonical((game.get("home_team") or {}).get("abbreviation"))
        if away != want_away or home != want_home:
            continue
        day = game_day(game.get("date"))
        if day is None or target is None or abs((day - target).days) > 1:
            continue
        ranked.append((day == target, sync.is_final(game), game))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return ranked[0][2]


def emit(text, key=""):
    text = redact(text, key)
    print(text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(text)
            if not text.endswith("\n"):
                handle.write("\n")


def audit_tree(root: Path, key: str) -> None:
    if not key or len(key) < 12:
        return
    folder = root / "data" / "games"
    if not folder.exists():
        return
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        if key in path.read_text(encoding="utf-8", errors="replace"):
            raise GameStatsError("Refusing to commit game stats that contain the API key.")


def _pt_today(now: dt.datetime) -> dt.date:
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    return now.astimezone(PT).date()


def run(root: Path, now: dt.datetime, *, key="", dates=None, teams=None, espn_id="",
        scheduled=False, client=None, fetch=None, access=None) -> int:
    """Write game files. Returns 0 when every selected final was saved or none were final."""
    fetch = fetch or get_json
    teams = list(teams or [])
    espn_id = parse_espn_id(espn_id)
    stamp = now.astimezone(dt.timezone.utc).isoformat(timespec="seconds")
    today = _pt_today(now)
    explicit_dates = list(dates or [])
    if not explicit_dates:
        explicit_dates = [today - dt.timedelta(days=1), today]
    if client is None and key.strip():
        client = sync.Client(key.strip())
    if scheduled and not dates and not teams and not espn_id:
        season_rows, season_error = (None, "no client")
        if client is not None:
            season_rows, season_error = safe_all(client, "games", {"seasons[]": [today.year]})
        if season_rows is not None and not sync.in_season(season_rows, today):
            emit("Offseason. No game file written. The morning-after window is closed.")
            return 0
        if season_error and client is not None:
            emit("Schedule check failed. Continuing so a final is not skipped.")
    if access is None:
        if client is None:
            access = {
                "key_present": False,
                "series_endpoint": False,
                "endpoints": {},
                "note": "BALLDONTLIE_API_KEY was not set. Game files from this run are ESPN fallbacks.",
            }
        else:
            try:
                access = probe_access(client, explicit_dates[-1])
            except GameStatsError as exc:
                access = {"key_present": True, "series_endpoint": False, "endpoints": {}, "note": str(exc)}
    endpoint_changed = save_access(root, access, stamp, key)
    lines = ["## WNBA game stats", "", "### balldontlie endpoints"]
    if not access.get("key_present"):
        lines.append("The API key was not set. ESPN fallback is in effect.")
    elif not access.get("endpoints"):
        lines.append(access.get("note") or "Endpoint probe did not return a result.")
    else:
        allowed = [name for name, row in access["endpoints"].items() if row.get("status") == "allowed"]
        denied = [name for name, row in access["endpoints"].items() if row.get("status") == "denied"]
        other = [f"{name} ({row.get('status')})" for name, row in access["endpoints"].items() if row.get("status") not in ("allowed", "denied")]
        lines.append("Allowed: " + (", ".join(allowed) if allowed else "none") + ".")
        lines.append("Denied: " + (", ".join(denied) if denied else "none") + ".")
        if other:
            lines.append("Other: " + ", ".join(other) + ".")
        if access["endpoints"] and all(row.get("status") == "denied" for row in access["endpoints"].values()):
            lines.append("Every probed endpoint was denied. The key was rejected or this plan has no WNBA access.")
    lines.append("Series: no series endpoint in the WNBA API.")
    lines.append("")

    espn_games = []
    scoreboard_errors = []
    for day in explicit_dates:
        try:
            payload = fetch_first(fetch, scoreboard_urls(day))
        except EspnError as exc:
            scoreboard_errors.append(str(day))
            print(f"ESPN scoreboard {day} failed ({exc}).")
            continue
        for event in payload.get("events") or []:
            parsed = parse_scoreboard_event(event)
            if parsed and parsed.get("espn_game_id"):
                espn_games.append(parsed)
    id_error = False
    if espn_id and espn_id not in {game["espn_game_id"] for game in espn_games}:
        try:
            espn_games.append(parse_summary(fetch_first(fetch, summary_urls(espn_id))))
        except EspnError as exc:
            id_error = True
            print(f"ESPN summary {espn_id} failed ({exc}).")
    by_id = {}
    for game in espn_games:
        current = by_id.get(game["espn_game_id"])
        if current is None or (game.get("from_summary") and not current.get("from_summary")):
            by_id[game["espn_game_id"]] = game
    selected = [game for game in by_id.values() if game.get("final") and wanted(game, teams, espn_id)]
    if len(selected) > 40:
        raise GameStatsError("Refusing to write more than 40 games in one run.")
    enriched = []
    for game in selected:
        if game.get("from_summary") or not game.get("espn_game_id"):
            enriched.append(game)
            continue
        try:
            enriched.append(parse_summary(fetch_first(fetch, summary_urls(game["espn_game_id"]))))
        except EspnError as exc:
            print(f"ESPN summary {game['espn_game_id']} failed ({exc}).")
            enriched.append(game)
    selected = enriched

    bdl_games, player_rows, team_rows = [], [], []
    standings, bdl_error = [], None
    if client is None:
        bdl_error = "BALLDONTLIE_API_KEY was not set."
    else:
        start = min(explicit_dates) - dt.timedelta(days=1)
        end = max(explicit_dates) + dt.timedelta(days=1)
        window = {"start_date": start.isoformat(), "end_date": end.isoformat()}
        if endpoint_allowed(access, "games"):
            bdl_games, bdl_error = safe_all(client, "games", window)
            bdl_games = bdl_games or []
        else:
            bdl_error = "BALLDONTLIE games is not on this plan."
        if bdl_games and endpoint_allowed(access, "player_stats"):
            player_rows, error = safe_all(client, "player_stats", window)
            if error and not bdl_error:
                bdl_error = error
            player_rows = player_rows or []
        if bdl_games and endpoint_allowed(access, "team_stats"):
            team_rows, _error = safe_all(client, "team_stats", window)
            team_rows = team_rows or []
        if endpoint_allowed(access, "standings"):
            standings, _error = safe_all(client, "standings", {"season": explicit_dates[-1].year})
            standings = standings or []
    covered = set()
    written = []
    failures = []
    changed = endpoint_changed

    def extra_box(game_id):
        plays, team_rows_adv, player_rows_adv = [], [], []
        if client is None:
            return plays, team_rows_adv, player_rows_adv
        if endpoint_allowed(access, "plays"):
            plays, _error = safe_all(client, "plays", {"game_id": game_id})
            plays = plays or []
        if endpoint_allowed(access, "team_game_advanced_stats"):
            team_rows_adv, _error = safe_all(client, "team_game_advanced_stats", {"game_ids[]": [game_id]})
            team_rows_adv = team_rows_adv or []
        if endpoint_allowed(access, "player_game_advanced_stats"):
            player_rows_adv, _error = safe_all(client, "player_game_advanced_stats", {"game_ids[]": [game_id]})
            player_rows_adv = player_rows_adv or []
        return plays, team_rows_adv, player_rows_adv

    def persist(doc, away_team, home_team, game_key):
        nonlocal changed
        day = game_day(doc.get("date"))
        if not isinstance(day, dt.date):
            failures.append(game_key)
            return
        slug = assign_slug(root, day, away_team, home_team, game_key)
        path = root / "data" / "games" / f"{slug}.json"
        text = markdown(doc)
        if save_pair(path, doc, text, key):
            changed = True
        written.append((slug, doc))

    for espn in selected:
        matched = match_bdl(espn, bdl_games) if bdl_games else None
        doc = None
        if matched is not None:
            try:
                game_id = sync.identifier(matched.get("id"))
            except sync.SyncError:
                game_id = None
            if game_id is not None:
                covered.add(game_id)
                players = bdl_players_for(player_rows, game_id)
                teams_for_game = [row for row in team_rows if row_game_id(row) == game_id]
                plays, team_rows_adv, player_rows_adv = extra_box(game_id)
                doc = build_bdl_document(matched, players, teams_for_game, plays, team_rows_adv, player_rows_adv, standings, stamp)
                if doc is not None:
                    apply_espn(doc, espn)
                    persist(doc, doc["away"], doc["home"], f"bdl:{game_id}")
        if doc is None:
            if espn.get("from_summary"):
                reason = bdl_error or "balldontlie had no matching final with a player box"
                doc = build_fallback(espn, reason, stamp)
                persist(doc, doc["away"], doc["home"], f"espn:{espn.get('espn_game_id')}")
            else:
                failures.append(espn.get("espn_game_id") or "unknown")

    if not espn_id and bdl_games:
        for game in bdl_games:
            if not sync.is_final(game):
                continue
            day = game_day(game.get("date"))
            if day not in explicit_dates:
                continue
            try:
                game_id = sync.identifier(game.get("id"))
            except sync.SyncError:
                continue
            if game_id in covered:
                continue
            away = team_view(game.get("visitor_team"))
            home = team_view(game.get("home_team"))
            if teams and not wanted({"away": away, "home": home, "espn_game_id": ""}, teams, ""):
                continue
            players = bdl_players_for(player_rows, game_id)
            plays, team_rows_adv, player_rows_adv = extra_box(game_id)
            doc = build_bdl_document(
                game, players, [row for row in team_rows if row_game_id(row) == game_id],
                plays, team_rows_adv, player_rows_adv, standings, stamp,
            )
            if doc is None:
                failures.append(f"bdl:{game_id}")
                continue
            apply_espn(doc, None)
            persist(doc, doc["away"], doc["home"], f"bdl:{game_id}")

    if written:
        lines.append("### Games")
        lines.append("")
        for slug, doc in written:
            lines.append(summary_block(doc, slug))
            lines.append("")
    else:
        lines.append("No final games written.")
    if failures:
        lines.append("FLAG: no source had a usable box for: " + ", ".join(str(item) for item in failures) + ".")
    if not written and scoreboard_errors and bdl_error:
        lines.append("FLAG: ESPN and balldontlie both failed, so this run could not tell whether games were final.")
    if id_error and not any(doc.get("espn_game_id") == espn_id for _slug, doc in written):
        lines.append(f"FLAG: ESPN game {espn_id} could not be loaded.")
    emit("\n".join(lines), key)
    if failures or (not written and scoreboard_errors and bdl_error) or (id_error and not written):
        return 1
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Pull WNBA game boxes for recaps.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--date", action="append", default=[])
    parser.add_argument("--teams", default="")
    parser.add_argument("--espn-game-id", default="")
    parser.add_argument("--scheduled", action="store_true")
    parser.add_argument("--audit-secrets", action="store_true")
    args = parser.parse_args(argv)
    key = os.environ.get("BALLDONTLIE_API_KEY", "")
    if args.audit_secrets:
        try:
            audit_tree(args.root, key)
        except GameStatsError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0
    def from_env(name):
        text = os.environ.get(name, "").strip()
        return "" if text.lower() == "null" else text

    dates = list(args.date)
    env_date = from_env("GAME_STATS_DATE")
    if env_date and not dates:
        dates = [env_date]
    teams_text = args.teams or from_env("GAME_STATS_TEAMS")
    espn_id = args.espn_game_id or from_env("GAME_STATS_ESPN_ID")
    scheduled = args.scheduled or from_env("GAME_STATS_SCHEDULED").lower() in ("1", "true", "yes")
    try:
        parsed_dates = [parse_day(value) for value in dates]
        return run(
            args.root,
            dt.datetime.now(dt.timezone.utc),
            key=key,
            dates=parsed_dates,
            teams=parse_teams(teams_text),
            espn_id=espn_id,
            scheduled=scheduled,
        )
    except GameStatsError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
