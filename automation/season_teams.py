#!/usr/bin/env python3
"""Replace a season row's team with the club from that season.

BALLDONTLIE season rows often repeat one club for every year. ESPN's public
athlete season stats name the club for each season and stint. A row is
relabeled only when its season, competition, and games played match one stint.
A row whose games played equal the sum of several stints names each of those clubs.
"""
from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SEARCH_URL = "https://site.web.api.espn.com/apis/search/v2"
SEARCH_V3_URL = "https://site.web.api.espn.com/apis/common/v3/search"
STATS_URL = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/wnba/athletes/{athlete_id}/stats"
SOURCE = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/wnba/athletes/{id}/stats"
HISTORICAL_ID_START = 200
USER_AGENT = "FullCourtBuckets/1.0"
STANDINGS_URL = "https://site.api.espn.com/apis/v2/sports/basketball/wnba/standings?season={year}"
CORE_TEAMS_URL = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/wnba/seasons/{year}/teams?limit=40"
CORE_ROSTER_URL = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/wnba/seasons/{year}/teams/{team_id}/athletes?limit=40"
CORE_ATHLETE_URL = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/wnba/seasons/{year}/athletes/{athlete_id}"
CORE_ATHLETES_URL = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/wnba/athletes?limit=400"
CORE_ATHLETE_ROOT_URL = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/wnba/athletes/{athlete_id}"
CORE_ATHLETE_SEASONS_URL = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/wnba/athletes/{athlete_id}/seasons?limit=40"
CORE_SEASON_STATS_URL = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/wnba/seasons/{year}/types/{kind}/athletes/{athlete_id}/statistics/0"
CORE_TEAM_URL = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/wnba/seasons/{year}/teams/{team_id}"
GAMELOG_URL = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/wnba/athletes/{athlete_id}/gamelog?season={year}"
CORE_STAT_FIELDS = {
    "gamesPlayed": "games_played",
    "avgMinutes": "min",
    "avgPoints": "pts",
    "avgOffensiveRebounds": "oreb",
    "avgDefensiveRebounds": "dreb",
    "avgRebounds": "reb",
    "avgAssists": "ast",
    "avgSteals": "stl",
    "avgBlocks": "blk",
    "avgTurnovers": "turnover",
    "fieldGoalPct": "fg_pct",
    "threePointFieldGoalPct": "fg3_pct",
    "freeThrowPct": "ft_pct",
    "avgFieldGoalsMade": "fgm",
    "avgFieldGoalsAttempted": "fga",
    "avgThreePointFieldGoalsMade": "fg3m",
    "avgThreePointFieldGoalsAttempted": "fg3a",
    "avgFreeThrowsMade": "ftm",
    "avgFreeThrowsAttempted": "fta",
}
STAT_FIELDS = {
    "gamesPlayed": "games_played",
    "avgMinutes": "min",
    "avgPoints": "pts",
    "avgOffensiveRebounds": "oreb",
    "avgDefensiveRebounds": "dreb",
    "avgRebounds": "reb",
    "avgAssists": "ast",
    "avgSteals": "stl",
    "avgBlocks": "blk",
    "avgTurnovers": "turnover",
    "fieldGoalPct": "fg_pct",
    "threePointFieldGoalPct": "fg3_pct",
    "freeThrowPct": "ft_pct",
}
STAT_SPLITS = {
    "avgFieldGoalsMade-avgFieldGoalsAttempted": ("fgm", "fga"),
    "avgThreePointFieldGoalsMade-avgThreePointFieldGoalsAttempted": ("fg3m", "fg3a"),
    "avgFreeThrowsMade-avgFreeThrowsAttempted": ("ftm", "fta"),
}
METRIC_KEYS = (
    "min", "fgm", "fga", "fg_pct", "fg3m", "fg3a", "fg3_pct",
    "ftm", "fta", "ft_pct", "oreb", "dreb", "reb", "ast", "stl", "blk", "turnover", "pts",
)


def lookup_path(root: Path) -> Path:
    return Path(root) / "data" / "wnba" / "season-teams.json"


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode().casefold()
    text = text.replace("'", "").replace("’", "")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def athlete_id(item: dict) -> int | None:
    uid = str(item.get("uid") or "")
    match = re.search(r"a:(\d+)", uid)
    if not match:
        link = ((item.get("link") or {}).get("web")) or ""
        match = re.search(r"/id/(\d+)/", str(link))
    if not match:
        return None
    return int(match.group(1))


def search_hits(payload: dict) -> list[dict]:
    hits = []
    for group in payload.get("results") or []:
        if not isinstance(group, dict) or group.get("type") != "player":
            continue
        for item in group.get("contents") or []:
            if isinstance(item, dict):
                hits.append(item)
    return hits


def needs_refetch(status: str) -> bool:
    """A missing, failed, or unresolved lookup is tried again. A stored match is left alone.

    Search used to answer no-match, and duplicate names were stored as
    ambiguous-name, without another attempt. Both are looked up again.
    """
    text = str(status or "")
    if text in {"no-match", "ambiguous-name", "ambiguous-match", "stint-mismatch"}:
        return True
    return not text or text.startswith("error")


def v3_hits(payload: dict) -> list[dict]:
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def pick_v3_candidates(items: list[dict], name: str) -> list[int]:
    """Basketball athlete ids with this exact name. The league label is not trusted."""
    wanted = normalize_name(name).split()
    if not wanted:
        return []
    found = []
    for item in items:
        sport = str(item.get("sport") or "").casefold()
        if sport and sport != "basketball":
            continue
        if normalize_name(item.get("displayName") or "").split() != wanted:
            continue
        try:
            athlete = int(str(item.get("id")))
        except (TypeError, ValueError):
            continue
        if athlete not in found:
            found.append(athlete)
    return found


def pick_hit(hits: list[dict], name: str) -> dict | None:
    """One WNBA player whose name contains the query, or an exact match."""
    wanted = normalize_name(name).split()
    if not wanted:
        return None
    wnba = []
    for item in hits:
        league = str(item.get("defaultLeagueSlug") or "").casefold()
        link = str(((item.get("link") or {}).get("web")) or "").casefold()
        if league == "wnba" or "/wnba/" in link:
            wnba.append(item)
    exact = [item for item in wnba if normalize_name(item.get("displayName") or "").split() == wanted]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None
    contained = [
        item for item in wnba
        if all(token in normalize_name(item.get("displayName") or "").split() for token in wanted)
    ]
    if len(contained) == 1:
        return contained[0]
    return None


def parse_stints(payload: dict, season_type: int) -> tuple[list[dict], dict]:
    """Season stints plus ESPN team records keyed by slug. Combined totals are omitted."""
    if not isinstance(payload, dict):
        return [], {}
    teams = payload.get("teams") if isinstance(payload.get("teams"), dict) else {}
    stints = []
    for category in payload.get("categories") or []:
        if not isinstance(category, dict) or category.get("name") != "averages":
            continue
        for row in category.get("statistics") or []:
            if not isinstance(row, dict):
                continue
            slug = str(row.get("teamSlug") or "").strip()
            label = str(row.get("displayName") or "")
            if not slug or "total" in slug.casefold() or "total" in label.casefold():
                continue
            team = teams.get(slug)
            if not isinstance(team, dict):
                continue
            season = row.get("season") if isinstance(row.get("season"), dict) else {}
            year = season.get("year")
            stats = row.get("stats") or []
            if isinstance(year, bool) or not isinstance(year, int) or not stats:
                continue
            parsed = _stat_line(category.get("names") or [], stats)
            games = parsed.get("games_played")
            if games is None:
                try:
                    games = int(str(stats[0]))
                except (TypeError, ValueError):
                    continue
            if isinstance(games, float) and games.is_integer():
                games = int(games)
            if isinstance(games, bool) or not isinstance(games, int):
                continue
            stint = {
                "season": year,
                "season_type": season_type,
                "games_played": games,
                "team_slug": slug,
            }
            for key in METRIC_KEYS:
                if key in parsed:
                    stint[key] = parsed[key]
            stints.append(stint)
    return stints, {slug: team for slug, team in teams.items() if isinstance(team, dict)}


def _stat_number(raw):
    text = str(raw).strip().replace(",", "")
    if text in ("", "-", "--", "—"):
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    if value != value or value in (float("inf"), float("-inf")):
        return None
    if value.is_integer():
        return int(value)
    return value


def _stat_line(names: list, stats: list) -> dict:
    """Map one averages row onto stored season fields. Missing cells stay absent."""
    parsed = {}
    for index, name in enumerate(names):
        if index >= len(stats):
            break
        if name in STAT_SPLITS:
            text = str(stats[index])
            if "-" not in text:
                continue
            made, attempted = text.split("-", 1)
            left, right = _stat_number(made), _stat_number(attempted)
            made_key, attempted_key = STAT_SPLITS[name]
            if left is not None:
                parsed[made_key] = left
            if right is not None:
                parsed[attempted_key] = right
            continue
        field = STAT_FIELDS.get(name)
        if not field:
            continue
        value = _stat_number(stats[index])
        if value is not None:
            parsed[field] = value
    return parsed


def _team_name(team: dict) -> str:
    return str(team.get("displayName") or team.get("full_name") or "").strip()


def catalog_teams(bdl_teams: list[dict], espn_teams: dict, historical: dict) -> tuple[dict, dict]:
    """Map ESPN slugs to stored team objects. Unknown names get a stable id at 200 or above."""
    by_name = {}
    used_ids = set()
    for team in bdl_teams:
        if not isinstance(team, dict):
            continue
        name = str(team.get("full_name") or "").strip()
        if name:
            by_name[name.casefold()] = team
        if isinstance(team.get("id"), int) and not isinstance(team.get("id"), bool):
            used_ids.add(team["id"])
    current = {}
    for slug, raw in espn_teams.items():
        name = _team_name(raw)
        match = by_name.get(name.casefold())
        if match:
            current[slug] = {
                "id": match.get("id"),
                "full_name": match.get("full_name"),
                "abbreviation": match.get("abbreviation"),
                "city": match.get("city"),
                "name": match.get("name"),
                "conference": match.get("conference"),
            }
            continue
        if slug not in historical:
            next_id = HISTORICAL_ID_START
            while next_id in used_ids:
                next_id += 1
            used_ids.add(next_id)
            historical[slug] = {
                "id": next_id,
                "full_name": name,
                "abbreviation": raw.get("abbreviation"),
                "city": raw.get("location"),
                "name": raw.get("name") or raw.get("shortDisplayName"),
                "conference": None,
            }
    return current, historical


def team_for_slug(slug: str, table: dict) -> dict | None:
    current = table.get("current_teams") if isinstance(table.get("current_teams"), dict) else {}
    historical = table.get("historical_teams") if isinstance(table.get("historical_teams"), dict) else {}
    team = current.get(slug) or historical.get(slug)
    if not isinstance(team, dict) or not str(team.get("full_name") or "").strip():
        return None
    return dict(team)


def drop_copied_playoff_stints(stints: list[dict]) -> list[dict]:
    """Drop playoff stints that repeat that season's regular-season games and clubs.

    A year is removed only when every playoff stint matches the regular-season
    stints for that year. A real playoff series with different games stays.
    """
    regular = {}
    for item in stints:
        if isinstance(item, dict) and item.get("season_type") == 2:
            regular.setdefault(item.get("season"), []).append(item)
    kept = []
    for item in stints:
        if not isinstance(item, dict) or item.get("season_type") != 3:
            kept.append(item)
            continue
        year = item.get("season")
        playoff = [
            row for row in stints
            if isinstance(row, dict) and row.get("season_type") == 3 and row.get("season") == year
        ]
        signature = sorted((row.get("games_played"), row.get("team_slug")) for row in playoff)
        baseline = sorted((row.get("games_played"), row.get("team_slug")) for row in regular.get(year, []))
        if signature and signature == baseline:
            continue
        kept.append(item)
    return kept


def player_stints(table: dict, player_id) -> list[dict]:
    players = table.get("players") if isinstance(table.get("players"), dict) else {}
    entry = players.get(str(player_id))
    if not isinstance(entry, dict):
        return []
    stints = entry.get("stints")
    rows = [item for item in stints if isinstance(item, dict)] if isinstance(stints, list) else []
    return drop_copied_playoff_stints(rows)


def _games(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _row_from_stint(player_id, stint: dict, table: dict) -> dict | None:
    team = team_for_slug(stint.get("team_slug"), table)
    games = _games(stint.get("games_played"))
    year = stint.get("season")
    kind = stint.get("season_type")
    if team is None or games is None or isinstance(year, bool) or not isinstance(year, int):
        return None
    if kind not in (2, 3):
        return None
    row = {
        "player_id": player_id,
        "season": year,
        "season_type": kind,
        "team": team,
        "games_played": games,
    }
    for key in METRIC_KEYS:
        row[key] = stint.get(key)
    # The paid feed did not have this row. A later sync must not treat it as a feed row
    # when it checks that the feed itself did not shrink.
    row["gap_fill"] = True
    return row


def _team_name(row_or_team: dict | None) -> str:
    if not isinstance(row_or_team, dict):
        return ""
    team = row_or_team.get("team") if isinstance(row_or_team.get("team"), dict) else row_or_team
    if not isinstance(team, dict):
        return ""
    return str(team.get("full_name") or team.get("name") or "").strip().casefold()


def _match_stints(api_rows: list[dict], stints: list[dict], table: dict) -> tuple[list[dict], str | None]:
    """Return stints the feed does not already cover, or a reason they cannot be reconciled."""
    if not api_rows:
        return list(stints), None
    api_games = sum(row.get("games_played") or 0 for row in api_rows)
    cross_games = sum(item.get("games_played") or 0 for item in stints)
    if api_games == cross_games:
        return [], None
    unused = list(stints)
    conflict = False
    for row in api_rows:
        name = _team_name(row)
        by_team = [
            item for item in unused
            if name and _team_name(team_for_slug(item.get("team_slug"), table)) == name
        ]
        if len(by_team) == 1:
            if by_team[0].get("games_played") == row.get("games_played"):
                unused.remove(by_team[0])
                continue
            conflict = True
            unused.remove(by_team[0])
            continue
        games = _games(row.get("games_played"))
        by_games = [item for item in unused if item.get("games_played") == games]
        if len(by_games) == 1:
            unused.remove(by_games[0])
            continue
        return [], "games played do not match"
    if conflict or not unused:
        return [], "games played do not match"
    return unused, None


def _prior_season_copy(api_rows: list[dict], prior_rows: list[dict]) -> bool:
    """True when this season's only feed row repeats the previous season's line."""
    if len(api_rows) != 1 or len(prior_rows) != 1:
        return False
    current, prior = api_rows[0], prior_rows[0]
    if _team_name(current) != _team_name(prior):
        return False
    return all(current.get(key) == prior.get(key) for key in ("games_played", "pts", "reb", "ast", "min"))


def _marked_years(entry: dict, key: str) -> set[int]:
    years = set()
    for item in entry.get(key) or []:
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            years.add(item)
        elif isinstance(item, dict) and isinstance(item.get("season"), int) and not isinstance(item.get("season"), bool):
            years.add(item["season"])
    return years


def _same_coverage(api_rows: list[dict], stints: list[dict], table: dict) -> bool:
    if sum(row.get("games_played") or 0 for row in api_rows) != sum(item.get("games_played") or 0 for item in stints):
        return False
    api_teams = sorted(_team_name(row) for row in api_rows)
    stint_teams = sorted(_team_name(team_for_slug(item.get("team_slug"), table)) for item in stints)
    return api_teams == stint_teams


def supplement_rows(
    rows: list[dict],
    table: dict,
    playoff_teams: dict | None = None,
    season_year: int | None = None,
    prior_rows: list[dict] | None = None,
) -> tuple[list[dict], dict]:
    """Add regular-season stints the feed lacks. Real playoff stints are added only for playoff teams.

    The feed stays in place when games played disagree, unless that season was already
    investigated. confirmed_seasons replaces the feed with the cross-check line.
    unresolved_seasons does the same and stays on the record as an exact count we could
    not confirm. rejected_seasons, and a feed row that only repeats the previous season
    when the cross-check has no such season, are removed.
    """
    playoff_teams = playoff_teams if isinstance(playoff_teams, dict) else table.get("playoff_teams") or {}
    grouped = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        grouped.setdefault((row.get("player_id"), row.get("season"), row.get("season_type")), []).append(row)
    prior_grouped = {}
    for row in prior_rows or []:
        if isinstance(row, dict):
            prior_grouped.setdefault((row.get("player_id"), row.get("season_type")), []).append(row)
    additions = []
    replaced = []
    dropped = []
    unresolved = []
    seen = set()
    player_ids = {row.get("player_id") for row in rows if isinstance(row, dict)}
    players = table.get("players") if isinstance(table.get("players"), dict) else {}
    for key in players:
        try:
            player_ids.add(int(key))
        except (TypeError, ValueError):
            continue
    for player_id in player_ids:
        if isinstance(player_id, bool) or not isinstance(player_id, int):
            continue
        entry = players.get(str(player_id)) if isinstance(players.get(str(player_id)), dict) else {}
        identities = []
        for stint in player_stints(table, player_id):
            year = stint.get("season")
            kind = stint.get("season_type")
            if not isinstance(year, int) or isinstance(year, bool) or year < 2008 or kind not in (2, 3):
                continue
            if season_year is not None and year != season_year:
                continue
            identities.append((player_id, year, kind))
        for identity in grouped:
            if identity[0] == player_id and (season_year is None or identity[1] == season_year):
                identities.append(identity)
        for identity in identities:
            if identity in seen:
                continue
            seen.add(identity)
            player_id, year, kind = identity
            available = [
                item for item in player_stints(table, player_id)
                if item.get("season") == year and item.get("season_type") == kind
            ]
            if kind == 3:
                allowed = playoff_teams.get(str(year)) or playoff_teams.get(year) or []
                allowed = set(allowed)
                available = [item for item in available if item.get("team_slug") in allowed]
            current_rows = grouped.get(identity, [])
            if kind == 2 and current_rows and not available and (
                year in _marked_years(entry, "rejected_seasons")
                or _prior_season_copy(current_rows, prior_grouped.get((player_id, kind), []))
            ):
                for row in current_rows:
                    if row in rows:
                        rows.remove(row)
                dropped.extend(current_rows)
                continue
            if not available:
                continue
            line_years = _marked_years(entry, "confirmed_seasons") | _marked_years(entry, "unresolved_seasons")
            if current_rows and year in line_years and not _same_coverage(current_rows, available, table):
                for row in current_rows:
                    if row in rows:
                        rows.remove(row)
                for stint in available:
                    row = _row_from_stint(player_id, stint, table)
                    if row is not None:
                        replaced.append(row)
                continue
            extra, reason = _match_stints(current_rows, available, table)
            if reason:
                api_games = sum(row.get("games_played") or 0 for row in grouped.get(identity, []))
                cross_games = sum(item.get("games_played") or 0 for item in available)
                unresolved.append({
                    "player_id": player_id,
                    "season": year,
                    "season_type": kind,
                    "api_games": api_games,
                    "cross_check_games": cross_games,
                    "reason": reason,
                })
                continue
            for stint in extra:
                row = _row_from_stint(player_id, stint, table)
                if row is None:
                    unresolved.append({
                        "player_id": player_id,
                        "season": year,
                        "season_type": kind,
                        "api_games": sum(item.get("games_played") or 0 for item in grouped.get(identity, [])),
                        "cross_check_games": stint.get("games_played"),
                        "reason": "club could not be matched",
                    })
                    continue
                additions.append(row)
    return [*rows, *additions, *replaced], {
        "filled": additions,
        "replaced": replaced,
        "dropped": dropped,
        "unresolved": unresolved,
    }


def _slugify_team(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalize_name(name)).strip("-")


def _standings_rows(payload: dict) -> list[dict]:
    found = []

    def walk(node):
        if not isinstance(node, dict):
            return
        for entry in (node.get("standings") or {}).get("entries") or []:
            if isinstance(entry, dict):
                found.append(entry)
        for child in node.get("children") or []:
            walk(child)

    walk(payload)
    return found


def playoff_teams_for_year(payload: dict, year: int) -> list[str]:
    """Team slugs that made the playoffs. Top four conference seeds through 2024.

    From 2025 on, an eliminated club is the one whose clincher is 4. Earlier
    clincher values are not reliable on their own.
    """
    slugs = []
    for entry in _standings_rows(payload):
        team = entry.get("team") if isinstance(entry.get("team"), dict) else {}
        stats = {}
        for item in entry.get("stats") or []:
            if isinstance(item, dict):
                stats[item.get("name")] = item.get("value")
        seed = stats.get("playoffSeed")
        clincher = stats.get("clincher")
        if year <= 2024:
            made = isinstance(seed, (int, float)) and not isinstance(seed, bool) and 1 <= int(seed) <= 4
        else:
            made = clincher is not None and clincher != 4
        if not made:
            continue
        name = str(team.get("displayName") or team.get("name") or "").strip()
        slug = str(team.get("slug") or "").strip() or _slugify_team(name)
        if slug and slug not in slugs:
            slugs.append(slug)
    return slugs


def fetch_playoff_teams(years: range | list[int]) -> dict:
    found = {}
    for year in years:
        try:
            payload = _request_json(STANDINGS_URL.format(year=year))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
            continue
        slugs = playoff_teams_for_year(payload, year)
        if slugs:
            found[str(year)] = slugs
    return found


def _joined_team(options: list[dict], table: dict) -> dict | None:
    """One label for a row that adds several stints together."""
    names = []
    for item in options:
        team = team_for_slug(item.get("team_slug"), table)
        name = str((team or {}).get("full_name") or "").strip()
        if name and name not in names:
            names.append(name)
    if len(names) < 2:
        return None
    if len(names) == 2:
        label = f"{names[0]} and {names[1]}"
    else:
        label = ", ".join(names[:-1]) + ", and " + names[-1]
    return {"id": None, "full_name": label, "abbreviation": None, "city": None, "name": label, "conference": None}


def select_team(row: dict, stints: list[dict], table: dict):
    """Return ('keep', None) or ('replace', team)."""
    year = row.get("season")
    kind = row.get("season_type")
    games = row.get("games_played")
    if isinstance(games, bool) or not isinstance(games, int):
        return "keep", None
    options = [
        item for item in stints
        if item.get("season") == year and item.get("season_type") == kind
        and isinstance(item.get("games_played"), int) and not isinstance(item.get("games_played"), bool)
    ]
    if not options:
        return "keep", None
    exact = [item for item in options if item["games_played"] == games]
    if len(exact) == 1:
        team = team_for_slug(exact[0].get("team_slug"), table)
        return ("replace", team) if team else ("keep", None)
    if len(exact) > 1:
        return "keep", None
    if len(options) > 1 and sum(item["games_played"] for item in options) == games:
        team = _joined_team(options, table)
        return ("replace", team) if team else ("keep", None)
    return "keep", None


def _matching_stint(row: dict, stints: list[dict]) -> dict | None:
    """The one stint with this season, competition, and games played."""
    year = row.get("season")
    kind = row.get("season_type")
    games = row.get("games_played")
    if isinstance(games, bool) or not isinstance(games, int):
        return None
    exact = [
        item for item in stints
        if item.get("season") == year and item.get("season_type") == kind and item.get("games_played") == games
    ]
    if len(exact) == 1:
        return exact[0]
    return None


def _line_from_stint(row: dict, stint: dict, team: dict) -> dict:
    """Replace a feed row whose club was not that season's club.

    The paid feed often repeats the latest club and a rounded average. When one
    stint matches the games played, that stint is the season line.
    """
    updated = {**row, "team": team}
    if "pts" not in stint:
        return updated
    for key in METRIC_KEYS:
        if key in stint and stint.get(key) is not None:
            updated[key] = stint[key]
    updated["gap_fill"] = True
    return updated


def correct_rows(rows: list[dict], table: dict) -> tuple[list[dict], dict]:
    """Relabel season rows. A correction that would duplicate a season key is reverted."""
    if not table:
        return rows, {"replaced": 0, "cleared": 0, "reverted": 0}
    updated = []
    actions = []
    for row in rows:
        if not isinstance(row, dict):
            updated.append(row)
            actions.append("keep")
            continue
        stints = player_stints(table, row.get("player_id"))
        status, team = select_team(row, stints, table)
        if status == "replace" and team:
            current = row.get("team") if isinstance(row.get("team"), dict) else {}
            same = current.get("id") == team.get("id") and current.get("full_name") == team.get("full_name")
            if same:
                updated.append(row)
                actions.append("keep")
            else:
                stint = _matching_stint(row, stints)
                if stint is not None:
                    updated.append(_line_from_stint(row, stint, team))
                else:
                    updated.append({**row, "team": team})
                actions.append("replace")
        else:
            updated.append(row)
            actions.append("keep")
    seen = {}
    replaced = cleared = reverted = 0
    for index, row in enumerate(updated):
        if not isinstance(row, dict):
            continue
        key = (
            row.get("player_id"),
            row.get("season"),
            row.get("season_type"),
            (row.get("team") or {}).get("id") if isinstance(row.get("team"), dict) else None,
        )
        if key in seen and actions[index] != "keep":
            updated[index] = rows[index]
            actions[index] = "revert"
            reverted += 1
            continue
        if key in seen and actions[seen[key]] != "keep":
            previous = seen[key]
            updated[previous] = rows[previous]
            actions[previous] = "revert"
            reverted += 1
        seen[key] = index
    for action in actions:
        if action == "replace":
            replaced += 1
        elif action == "clear":
            cleared += 1
    return updated, {"replaced": replaced, "cleared": cleared, "reverted": reverted}


def _request_json(url: str, timeout: float = 25) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("ESPN response was not an object.")
    return payload


_LEAGUE_INDEX: dict[str, list[int]] | None = None
_TEAM_CACHE: dict[tuple[int, str], dict] = {}


def league_name_index() -> dict[str, list[int]]:
    """Normalized display name to athlete ids in the WNBA athlete directory."""
    global _LEAGUE_INDEX
    if _LEAGUE_INDEX is not None:
        return _LEAGUE_INDEX
    payload = _request_json(CORE_ATHLETES_URL)
    refs = []
    for item in payload.get("items") or []:
        if isinstance(item, dict) and item.get("$ref"):
            refs.append(item["$ref"])

    def load(ref: str) -> tuple[int, str] | None:
        try:
            athlete = _request_json(ref)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
            return None
        try:
            athlete_id = int(str(athlete.get("id")))
        except (TypeError, ValueError):
            return None
        label = normalize_name(athlete.get("displayName") or athlete.get("fullName") or "")
        if not label:
            return None
        return athlete_id, label

    index: dict[str, list[int]] = {}
    with ThreadPoolExecutor(max_workers=12) as pool:
        for loaded in pool.map(load, refs):
            if not loaded:
                continue
            athlete_id, label = loaded
            bucket = index.setdefault(label, [])
            if athlete_id not in bucket:
                bucket.append(athlete_id)
    _LEAGUE_INDEX = index
    return index


def athlete_season_years(espn_id: int) -> list[int]:
    payload = _request_json(CORE_ATHLETE_SEASONS_URL.format(athlete_id=espn_id))
    years = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("$ref") or "").split("/seasons/")[-1].split("?")[0]
        if text.isdigit():
            year = int(text)
            if year not in years:
                years.append(year)
    return years


def _team_record(year: int, team_id: str) -> dict:
    key = (year, str(team_id))
    if key in _TEAM_CACHE:
        return _TEAM_CACHE[key]
    payload = _request_json(CORE_TEAM_URL.format(year=year, team_id=team_id))
    record = {
        "slug": str(payload.get("slug") or "").strip(),
        "displayName": payload.get("displayName") or payload.get("name"),
        "abbreviation": payload.get("abbreviation"),
        "location": payload.get("location"),
        "name": payload.get("name") or payload.get("shortDisplayName"),
    }
    _TEAM_CACHE[key] = record
    return record


def _year_stints(espn_id: int, year: int) -> tuple[list[dict], dict]:
    """Regular-season and playoff stints for one year, from the game log and season statistics."""
    try:
        clubs = clubs_from_gamelog(_request_json(GAMELOG_URL.format(athlete_id=espn_id, year=year)))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        clubs = {}
    stints = []
    teams = {}
    for kind, bucket in clubs.items():
        slugs = {}
        for team_id in bucket:
            try:
                record = _team_record(year, team_id)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
                continue
            if not record.get("slug"):
                continue
            slugs[team_id] = record["slug"]
            teams[record["slug"]] = record
        try:
            line = statistics_line(_request_json(CORE_SEASON_STATS_URL.format(year=year, kind=kind, athlete_id=espn_id)))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
            line = {}
        for stint in stints_from_clubs(year, bucket, line, slugs):
            stint["season_type"] = kind
            stints.append(stint)
    return stints, teams


def fetch_core_career(espn_id: int) -> tuple[list[dict], dict]:
    """Season stints when the common season-stats feed has none."""
    stints = []
    teams = {}
    for year in athlete_season_years(espn_id):
        year_stints, year_teams = _year_stints(espn_id, year)
        stints.extend(year_stints)
        teams.update(year_teams)
    return stints, teams


def omitted_core_stints(espn_id: int, existing: list[dict]) -> tuple[list[dict], dict]:
    """Years on the athlete's season list that this feed never stored."""
    have = {
        item.get("season")
        for item in existing
        if isinstance(item, dict) and item.get("season_type") == 2 and item.get("team_slug") not in {"west", "east"}
    }
    stints = []
    teams = {}
    for year in athlete_season_years(espn_id):
        if year in have:
            continue
        year_stints, year_teams = _year_stints(espn_id, year)
        stints.extend(year_stints)
        teams.update(year_teams)
    return stints, teams


def _identity_name(espn_id: int) -> str:
    try:
        payload = _request_json(CORE_ATHLETE_ROOT_URL.format(athlete_id=espn_id))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        return ""
    return str(payload.get("displayName") or payload.get("fullName") or "")


def _matching_identity(name: str, candidate_ids: list[int]) -> int | None:
    """A WNBA athlete record with this name and no season stats yet."""
    matched = []
    for espn_id in candidate_ids:
        label = _identity_name(espn_id)
        if not label:
            continue
        if espn_id not in directory_candidates({normalize_name(label): [espn_id]}, name):
            continue
        if espn_id not in matched:
            matched.append(espn_id)
    if len(matched) == 1:
        return matched[0]
    return None


def fetch_wnba_stints(espn_id: int) -> tuple[list[dict], dict]:
    """Season stints from the WNBA athlete feed. An id with no stints is not a match."""
    stints = []
    teams = {}
    for kind in (2, 3):
        stats_url = STATS_URL.format(athlete_id=espn_id) + "?" + urllib.parse.urlencode({"seasontype": kind})
        parsed, team_records = parse_stints(_request_json(stats_url), kind)
        stints.extend(parsed)
        teams.update(team_records)
    return stints, teams


def _ref_id(ref: str) -> int | None:
    match = re.search(r"/(\d+)(?:\?|$)", str(ref or ""))
    if not match:
        return None
    return int(match.group(1))


def _feed_number(value) -> int | float:
    number = float(value)
    if number.is_integer():
        return int(number)
    return round(number, 1)


def _close_first(left: str, right: str) -> bool:
    if left == right:
        return bool(left)
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    return len(shorter) >= 3 and longer.startswith(shorter)


def directory_candidates(index: dict, name: str) -> list[int]:
    """Athlete ids from the WNBA directory. A unique last name is still a candidate.

    The common search can label a WNBA player with another league, or return
    nobody. The directory name is confirmed later, when season stats exist or
    the athlete record is in this league.
    """
    wanted = normalize_name(name).split()
    if not wanted:
        return []
    exact = []
    for athlete in index.get(" ".join(wanted), []):
        if athlete not in exact:
            exact.append(athlete)
    if exact:
        return exact
    last = wanted[-1]
    first = wanted[0]
    close = []
    last_hits = []
    for label, ids in index.items():
        parts = str(label).split()
        if not parts or parts[-1] != last:
            continue
        for athlete in ids:
            if athlete not in last_hits:
                last_hits.append(athlete)
        if _close_first(parts[0], first):
            for athlete in ids:
                if athlete not in close:
                    close.append(athlete)
    if close:
        return close
    if len(last_hits) == 1:
        return last_hits
    return []


def gamelog_season_kind(label: str) -> int | None:
    text = str(label or "").casefold()
    if "postseason" in text or "playoff" in text:
        return 3
    if "regular" in text:
        return 2
    return None


def _all_star_club(info: dict) -> bool:
    abbreviation = str(info.get("abbreviation") or "").casefold()
    return bool(info.get("all_star")) or abbreviation in {"west", "east"}


def clubs_from_gamelog(payload: dict) -> dict[int, dict[str, dict]]:
    """Season type to team id to games in that game log. Preseason is omitted.

    Month splits are added together. The team on each game is the club for
    that game; the athlete record's current club is not.
    """
    events = payload.get("events") if isinstance(payload.get("events"), dict) else {}
    found: dict[int, dict[str, dict]] = {}
    for block in payload.get("seasonTypes") or []:
        if not isinstance(block, dict):
            continue
        kind = gamelog_season_kind(block.get("displayName"))
        if kind not in (2, 3):
            continue
        bucket = found.setdefault(kind, {})
        for category in block.get("categories") or []:
            if not isinstance(category, dict):
                continue
            for event in category.get("events") or []:
                if not isinstance(event, dict):
                    continue
                raw = events.get(str(event.get("eventId") or ""))
                if not isinstance(raw, dict):
                    continue
                team = raw.get("team") if isinstance(raw.get("team"), dict) else {}
                team_id = str(team.get("id") or "")
                if not team_id:
                    continue
                row = bucket.setdefault(team_id, {
                    "count": 0,
                    "abbreviation": team.get("abbreviation"),
                    "all_star": bool(team.get("isAllStar")),
                })
                row["count"] += 1
    return found


def statistics_line(payload: dict) -> dict:
    """Per-game line from a core season statistic. Totals stay off the row."""
    splits = payload.get("splits") if isinstance(payload, dict) and isinstance(payload.get("splits"), dict) else {}
    parsed = {}
    for category in splits.get("categories") or []:
        if not isinstance(category, dict):
            continue
        for stat in category.get("stats") or []:
            if not isinstance(stat, dict):
                continue
            field = CORE_STAT_FIELDS.get(stat.get("name"))
            value = stat.get("value")
            if not field or isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            parsed[field] = _feed_number(value)
    return parsed


def stints_from_clubs(year: int, clubs: dict[str, dict], line: dict, team_slug: dict[str, str]) -> list[dict]:
    """One stint per club. A single club uses the season statistic's games and averages."""
    real = {team_id: info for team_id, info in clubs.items() if not _all_star_club(info)}
    if not real:
        return []
    stints = []
    if len(real) == 1:
        team_id, info = next(iter(real.items()))
        slug = team_slug.get(team_id)
        games = line.get("games_played") or info.get("count")
        if not slug or not isinstance(games, int) or isinstance(games, bool) or games <= 0:
            return []
        stint = {"season": year, "games_played": games, "team_slug": slug}
        for key in METRIC_KEYS:
            if key in line and line.get(key) is not None:
                stint[key] = line[key]
        stints.append(stint)
        return stints
    for team_id, info in real.items():
        slug = team_slug.get(team_id)
        games = info.get("count")
        if not slug or not isinstance(games, int) or games <= 0:
            continue
        stints.append({"season": year, "games_played": games, "team_slug": slug})
    return stints


def merge_stints(existing: list[dict], extra: list[dict]) -> list[dict]:
    """Add season clubs the stored feed does not already have.

    An all-star row does not block the regular-season club for that year.
    A club that is already stored is left as it is.
    """
    keys = {
        (item.get("season"), item.get("season_type"), item.get("team_slug"))
        for item in existing
        if isinstance(item, dict)
    }
    merged = list(existing)
    for item in extra:
        if not isinstance(item, dict):
            continue
        key = (item.get("season"), item.get("season_type"), item.get("team_slug"))
        if key in keys:
            continue
        merged.append(item)
        keys.add(key)
    return merged


def fits_hints(stints: list[dict], hints: list[dict]) -> bool:
    """True when every stored season row has the same games as these stints."""
    if not hints:
        return True
    for hint in hints:
        year = hint.get("season")
        kind = hint.get("season_type")
        games = hint.get("games_played")
        if not isinstance(games, int) or isinstance(games, bool):
            continue
        matched = [
            item for item in stints
            if item.get("season") == year and item.get("season_type") == kind
        ]
        if not matched:
            return False
        if sum(item.get("games_played") or 0 for item in matched) != games:
            return False
    return True


def disagreement_years(stints: list[dict], hints: list[dict]) -> list[int]:
    """Regular seasons whose games do not match the only confirmed athlete.

    A season split across clubs is one total. It is not a disagreement when the
    rows add up to that total.
    """
    totals = {}
    for hint in hints:
        if hint.get("season_type") != 2:
            continue
        year = hint.get("season")
        games = hint.get("games_played")
        if isinstance(year, bool) or not isinstance(year, int):
            continue
        if isinstance(games, bool) or not isinstance(games, int):
            continue
        totals[year] = totals.get(year, 0) + games
    years = []
    for year, games in totals.items():
        matched = [
            item for item in stints
            if item.get("season") == year and item.get("season_type") == 2
        ]
        if not matched:
            continue
        if sum(item.get("games_played") or 0 for item in matched) != games:
            years.append(year)
    return sorted(years)


def _candidate_ids(name: str) -> list[int]:
    """Athlete ids to confirm against WNBA season stats.

    The v2 search often returns no WNBA hit: the player is tagged with another
    league, or the link is not a WNBA page, or the result list is empty. The
    common search still returns an id. A name match is only a candidate until
    the WNBA season feed has stints for it.
    """
    found_ids = []
    query = urllib.parse.urlencode({"query": name, "limit": 5, "type": "player"})
    hits = search_hits(_request_json(SEARCH_URL + "?" + query))
    picked = pick_hit(hits, name)
    if picked:
        espn_id = athlete_id(picked)
        if espn_id:
            found_ids.append(espn_id)
    wanted = normalize_name(name).split()
    for item in hits:
        if normalize_name(item.get("displayName") or "").split() != wanted:
            continue
        espn_id = athlete_id(item)
        if espn_id and espn_id not in found_ids:
            found_ids.append(espn_id)
    if not found_ids:
        v3_query = urllib.parse.urlencode({"query": name, "limit": 20, "type": "player"})
        found_ids = pick_v3_candidates(v3_hits(_request_json(SEARCH_V3_URL + "?" + v3_query)), name)
    try:
        for athlete in directory_candidates(league_name_index(), name):
            if athlete not in found_ids:
                found_ids.append(athlete)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
        pass
    return found_ids


_ROSTER_INDEX: dict[int, dict[str, list[int]]] = {}


def roster_name_index(year: int) -> dict[str, list[int]]:
    """Normalized name to athlete ids from the roster feed for that season.

    The franchise list follows the season. The athlete list on each franchise
    does not: it returns the current roster. An id is still only a match after
    the WNBA season feed has stints for it, so a current namesake without those
    stints is ignored.
    """
    if year in _ROSTER_INDEX:
        return _ROSTER_INDEX[year]
    teams_payload = _request_json(CORE_TEAMS_URL.format(year=year))
    team_ids = []
    for item in teams_payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        team_id = _ref_id(item.get("$ref"))
        if team_id and team_id not in team_ids:
            team_ids.append(team_id)

    def roster(team_id: int) -> list[int]:
        try:
            payload = _request_json(CORE_ROSTER_URL.format(year=year, team_id=team_id))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
            return []
        ids = []
        for item in payload.get("items") or []:
            if not isinstance(item, dict):
                continue
            athlete = _ref_id(item.get("$ref"))
            if athlete and athlete not in ids:
                ids.append(athlete)
        return ids

    athlete_ids = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for ids in pool.map(roster, team_ids):
            for athlete in ids:
                if athlete not in athlete_ids:
                    athlete_ids.append(athlete)

    def load(athlete_id: int) -> tuple[int, str]:
        try:
            payload = _request_json(CORE_ATHLETE_URL.format(year=year, athlete_id=athlete_id))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
            return athlete_id, ""
        if not isinstance(payload, dict):
            return athlete_id, ""
        return athlete_id, normalize_name(payload.get("displayName") or payload.get("fullName") or "")

    index: dict[str, list[int]] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for athlete_id, label in pool.map(load, athlete_ids):
            if not label:
                continue
            bucket = index.setdefault(label, [])
            if athlete_id not in bucket:
                bucket.append(athlete_id)
    _ROSTER_INDEX[year] = index
    return index


def _confirm_ids(candidate_ids: list[int]) -> list[tuple[int, list[dict], dict]]:
    confirmed = []
    for espn_id in candidate_ids:
        stints = []
        teams = {}
        try:
            stints, teams = fetch_wnba_stints(espn_id)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
            stints, teams = [], {}
        if not stints:
            try:
                stints, teams = fetch_core_career(espn_id)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
                stints, teams = [], {}
        if stints:
            confirmed.append((espn_id, stints, teams))
    return confirmed


def _choose_confirmed(confirmed, hints):
    """One athlete, or none when several confirmed ids still fit the stored rows."""
    fitting = [item for item in confirmed if fits_hints(item[1], hints)]
    if len(fitting) == 1:
        return fitting[0]
    if len(fitting) > 1:
        return None
    if len(confirmed) == 1:
        return confirmed[0]
    return None


def fetch_player(name: str, retries: int = 3, years: list[int] | None = None, hints: list[dict] | None = None) -> tuple[int | None, list[dict], dict, str]:
    """Return espn id, stints, team records, and a status string.

    Search ids and directory ids are confirmed on WNBA season stats. When that
    feed is empty, the season game log supplies the club. Stored rows separate
    two athletes who share a name. A failed lookup stays eligible for the next sync.
    """
    hints = hints or []
    last_error = ""
    for attempt in range(retries):
        try:
            candidate_ids = _candidate_ids(name)
            confirmed = _confirm_ids(candidate_ids)
            if not confirmed and years:
                for year in sorted({year for year in years if isinstance(year, int) and year >= 2008}, reverse=True):
                    try:
                        index = roster_name_index(year)
                    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
                        continue
                    confirmed = _confirm_ids(index.get(normalize_name(name), []))
                    if confirmed:
                        break
            chosen = _choose_confirmed(confirmed, hints)
            if chosen:
                espn_id, stints, teams = chosen
                try:
                    extra, extra_teams = omitted_core_stints(espn_id, stints)
                except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
                    extra, extra_teams = [], {}
                teams = {**teams, **extra_teams}
                return espn_id, merge_stints(stints, extra), teams, "ok"
            if len(confirmed) > 1:
                return None, [], {}, "ambiguous-match"
            identity = _matching_identity(name, candidate_ids)
            if identity:
                return identity, [], {}, "ok"
            return None, [], {}, "no-match"
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            last_error = str(exc)
            time.sleep(0.4 * (attempt + 1))
    return None, [], {}, "error: " + last_error[:180]


def load_table(root: Path) -> dict:
    path = lookup_path(root)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _known_teams(teams: dict, current: dict, historical: dict) -> dict:
    """Team records the table does not already have. Known clubs keep their stored ids."""
    return {
        slug: raw
        for slug, raw in teams.items()
        if slug not in current and slug not in historical
    }


def _store_lookup(players, player_id, name, espn_id, stints, status, hints, current, historical, bdl_teams, teams):
    mapped_current, historical = catalog_teams(bdl_teams, _known_teams(teams, current, historical), historical)
    current.update(mapped_current)
    previous = players.get(str(player_id)) if isinstance(players.get(str(player_id)), dict) else {}
    stored = {
        "name": name,
        "espn_id": espn_id,
        "status": status,
        "stints": stints,
    }
    for key in ("confirmed_seasons", "rejected_seasons", "unresolved_seasons"):
        if key in previous:
            stored[key] = previous[key]
    if status == "ok":
        marked = disagreement_years(stints, hints)
        if marked:
            stored["confirmed_seasons"] = sorted(set(_marked_years(stored, "confirmed_seasons")) | set(marked))
    players[str(player_id)] = stored
    return historical


def refresh(root: Path, workers: int = 6) -> dict:
    """Fetch per-season clubs. A failed or duplicate-name lookup is tried again."""
    root = Path(root)
    data = root / "data" / "wnba"
    teams_doc = json.loads((data / "teams.json").read_text(encoding="utf-8"))
    bdl_teams = teams_doc.get("teams") or []
    profiles = []
    names = {}
    years_by_id = {}
    hints_by_id = {}
    for path in sorted((data / "players").glob("*.json")):
        profile = json.loads(path.read_text(encoding="utf-8"))
        player = profile.get("player") or {}
        player_id = player.get("id")
        name = f"{player.get('first_name') or ''} {player.get('last_name') or ''}".strip()
        if not isinstance(player_id, int) or isinstance(player_id, bool) or not name:
            continue
        profiles.append((player_id, name))
        names.setdefault(normalize_name(name), []).append(player_id)
        years = []
        hints = []
        for row in profile.get("season_stats") or []:
            if not isinstance(row, dict):
                continue
            year = row.get("season")
            if isinstance(year, int) and not isinstance(year, bool) and year not in years:
                years.append(year)
            if row.get("season_type") in (2, 3) and isinstance(row.get("games_played"), int):
                hints.append({
                    "season": year,
                    "season_type": row.get("season_type"),
                    "games_played": row.get("games_played"),
                })
        years_by_id[player_id] = years
        hints_by_id[player_id] = hints
    ambiguous = {player_id for ids in names.values() if len(ids) > 1 for player_id in ids}
    existing = load_table(root)
    players = existing.get("players") if isinstance(existing.get("players"), dict) else {}
    historical = existing.get("historical_teams") if isinstance(existing.get("historical_teams"), dict) else {}
    current = existing.get("current_teams") if isinstance(existing.get("current_teams"), dict) else {}
    playoff_teams = existing.get("playoff_teams") if isinstance(existing.get("playoff_teams"), dict) else None
    pending = []
    for player_id, name in profiles:
        status = str((players.get(str(player_id)) or {}).get("status") or "")
        if needs_refetch(status):
            pending.append((player_id, name, years_by_id.get(player_id) or [], hints_by_id.get(player_id) or []))
    print(f"Season teams: {len(pending)} to fetch, {len(players)} already stored, {len(ambiguous)} duplicate names included.")
    if not pending:
        return existing if existing else _document(players, current, historical, ambiguous, profiles, playoff_teams)

    def job(item):
        player_id, name, years, hints = item
        espn_id, stints, teams, status = fetch_player(name, years=years, hints=hints)
        return player_id, name, espn_id, drop_copied_playoff_stints(stints), teams, status, hints

    done = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(job, item) for item in pending]
        for future in as_completed(futures):
            player_id, name, espn_id, stints, teams, status, hints = future.result()
            historical = _store_lookup(
                players, player_id, name, espn_id, stints, status, hints,
                current, historical, bdl_teams, teams,
            )
            done += 1
            if done % 40 == 0 or done == len(pending):
                _write(lookup_path(root), _document(players, current, historical, ambiguous, profiles, playoff_teams))
                print(f"Season teams stored {done}/{len(pending)}")
    document = _document(players, current, historical, ambiguous, profiles, playoff_teams)
    _write(lookup_path(root), document)
    return document


def backfill_omitted(players, current, historical, bdl_teams, hints_by_id, workers: int = 6) -> int:
    """Add seasons the common feed skipped for athletes we already matched."""
    pending = []
    for player_id, entry in players.items():
        if not isinstance(entry, dict) or entry.get("status") != "ok" or not entry.get("espn_id"):
            continue
        pending.append((str(player_id), entry))

    def job(item):
        player_id, entry = item
        try:
            extra, teams = omitted_core_stints(entry["espn_id"], entry.get("stints") or [])
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
            return player_id, [], {}
        return player_id, extra, teams

    filled = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(job, item) for item in pending]
        for future in as_completed(futures):
            player_id, extra, teams = future.result()
            if not extra:
                continue
            entry = players[player_id]
            merged = drop_copied_playoff_stints(merge_stints(entry.get("stints") or [], extra))
            historical = _store_lookup(
                players,
                int(player_id),
                entry.get("name"),
                entry.get("espn_id"),
                merged,
                "ok",
                hints_by_id.get(int(player_id)) or [],
                current,
                historical,
                bdl_teams,
                teams,
            )
            filled += 1
    return filled


def _document(players, current, historical, ambiguous, profiles, playoff_teams=None) -> dict:
    unmatched = [
        {"id": int(player_id), "name": entry.get("name"), "status": entry.get("status")}
        for player_id, entry in sorted(players.items(), key=lambda item: int(item[0]))
        if entry.get("status") != "ok"
    ]
    document = {
        "source": SOURCE,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "player_count": len(profiles),
        "matched_count": sum(1 for entry in players.values() if entry.get("status") == "ok"),
        "unmatched": unmatched,
        "ambiguous_name_count": len(ambiguous),
        "current_teams": current,
        "historical_teams": historical,
        "players": players,
    }
    if isinstance(playoff_teams, dict) and playoff_teams:
        document["playoff_teams"] = playoff_teams
    return document


def needs_stat_lines(table: dict) -> bool:
    players = table.get("players") if isinstance(table.get("players"), dict) else {}
    for entry in players.values():
        if not isinstance(entry, dict):
            continue
        for item in entry.get("stints") or []:
            if isinstance(item, dict) and "pts" not in item:
                return True
    return False


def enrich_stat_lines(root: Path, workers: int = 6) -> dict:
    """Re-fetch per-season averages for stored players whose stints only have games played."""
    root = Path(root)
    table = load_table(root)
    players = table.get("players") if isinstance(table.get("players"), dict) else {}
    teams_doc = json.loads((root / "data" / "wnba" / "teams.json").read_text(encoding="utf-8"))
    bdl_teams = teams_doc.get("teams") or []
    historical = table.get("historical_teams") if isinstance(table.get("historical_teams"), dict) else {}
    current = table.get("current_teams") if isinstance(table.get("current_teams"), dict) else {}
    pending = []
    for player_id, entry in players.items():
        if not isinstance(entry, dict) or entry.get("status") != "ok" or not entry.get("espn_id"):
            continue
        stints = entry.get("stints") or []
        if stints and any(isinstance(item, dict) and "pts" not in item for item in stints):
            pending.append((str(player_id), entry))
    print(f"Season stat lines: {len(pending)} players to fetch.")

    def job(item):
        player_id, entry = item
        last_error = ""
        for attempt in range(3):
            try:
                stints = []
                teams = {}
                for kind in (2, 3):
                    stats_url = STATS_URL.format(athlete_id=entry["espn_id"]) + "?" + urllib.parse.urlencode({"seasontype": kind})
                    parsed, team_records = parse_stints(_request_json(stats_url), kind)
                    stints.extend(parsed)
                    teams.update(team_records)
                return player_id, drop_copied_playoff_stints(stints), teams, "ok"
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
                last_error = str(exc)
                time.sleep(0.4 * (attempt + 1))
        return player_id, entry.get("stints") or [], {}, "error: " + last_error[:180]

    done = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(job, item) for item in pending]
        for future in as_completed(futures):
            player_id, stints, teams, status = future.result()
            mapped_current, historical = catalog_teams(bdl_teams, teams, historical)
            current.update(mapped_current)
            entry = players[player_id]
            if status == "ok":
                entry["stints"] = stints
            done += 1
            if done % 40 == 0 or done == len(pending):
                table["current_teams"] = current
                table["historical_teams"] = historical
                _write(lookup_path(root), table)
                print(f"Season stat lines stored {done}/{len(pending)}")
    years = sorted({
        item.get("season")
        for entry in players.values()
        if isinstance(entry, dict)
        for item in entry.get("stints") or []
        if isinstance(item, dict) and isinstance(item.get("season"), int) and item.get("season") >= 2008
    })
    fetched = fetch_playoff_teams(years)
    if fetched:
        stored = table.get("playoff_teams") if isinstance(table.get("playoff_teams"), dict) else {}
        stored.update(fetched)
        table["playoff_teams"] = stored
    table["current_teams"] = current
    table["historical_teams"] = historical
    _write(lookup_path(root), table)
    return table


def apply_supplements(root: Path, table: dict | None = None) -> dict:
    """Write missing season rows into season files and player profiles."""
    root = Path(root)
    table = load_table(root) if table is None else table
    data = root / "data" / "wnba"
    report = {"filled": [], "replaced": [], "dropped": [], "unresolved": [], "profiles": 0}
    stored = {}
    for path in sorted((data / "seasons").glob("*.json")):
        try:
            season_year = int(path.stem)
        except ValueError:
            continue
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            continue
        stored[season_year] = rows
    for season_year in sorted(stored):
        updated, part = supplement_rows(
            stored[season_year],
            table,
            season_year=season_year,
            prior_rows=stored.get(season_year - 1, []),
        )
        report["filled"].extend(part["filled"])
        report["replaced"].extend(part["replaced"])
        report["dropped"].extend(part["dropped"])
        report["unresolved"].extend(part["unresolved"])
        stored[season_year] = updated
    for season_year, updated in stored.items():
        path = data / "seasons" / f"{season_year}.json"
        current = json.loads(path.read_text(encoding="utf-8"))
        if updated != current:
            _write(path, updated)
    by_player = {}
    for rows in stored.values():
        for row in rows:
            if isinstance(row, dict):
                by_player.setdefault(row.get("player_id"), []).append(row)

    def season_key(row):
        return (-(row.get("season") or 0), row.get("season_type") or 0, str((row.get("team") or {}).get("id")))

    for path in sorted((data / "players").glob("*.json")):
        profile = json.loads(path.read_text(encoding="utf-8"))
        player = profile.get("player") if isinstance(profile.get("player"), dict) else {}
        player_id = player.get("id")
        existing = profile.get("season_stats") if isinstance(profile.get("season_stats"), list) else []
        if player_id not in by_player and not existing:
            continue
        season_rows = sorted(by_player.get(player_id, []), key=season_key)
        if season_rows == existing:
            continue
        profile["season_stats"] = season_rows
        _write(path, profile)
        report["profiles"] += 1
    print(
        f"Filled {len(report['filled'])} season rows, replaced {len(report['replaced'])}, "
        f"dropped {len(report['dropped'])}, across {report['profiles']} players. "
        f"Unresolved {len(report['unresolved'])}."
    )
    return report


def apply_snapshot(root: Path, table: dict | None = None) -> dict:
    """Write corrected teams into season files and player profiles."""
    root = Path(root)
    table = load_table(root) if table is None else table
    data = root / "data" / "wnba"
    totals = {"replaced": 0, "cleared": 0, "reverted": 0, "files": 0}
    players_touched = set()
    for path in sorted((data / "seasons").glob("*.json")):
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            continue
        corrected, counts = correct_rows(rows, table)
        for key in ("replaced", "cleared", "reverted"):
            totals[key] += counts[key]
        if corrected != rows:
            _write(path, corrected)
            totals["files"] += 1
            for before, after in zip(rows, corrected):
                if before != after and isinstance(after, dict):
                    players_touched.add(after.get("player_id"))
    for path in sorted((data / "players").glob("*.json")):
        profile = json.loads(path.read_text(encoding="utf-8"))
        rows = profile.get("season_stats")
        if not isinstance(rows, list):
            continue
        corrected, counts = correct_rows(rows, table)
        if corrected != rows:
            profile["season_stats"] = corrected
            _write(path, profile)
            totals["files"] += 1
    totals["players"] = len(players_touched)
    print(
        f"Season team rows replaced {totals['replaced']}, cleared {totals['cleared']}, "
        f"reverted {totals['reverted']}, players {totals['players']}."
    )
    return totals


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--enrich", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    missing = not lookup_path(args.root).is_file()
    if args.enrich:
        table = enrich_stat_lines(args.root, args.workers)
    elif args.refresh or (missing and not args.apply):
        table = refresh(args.root, args.workers)
    else:
        table = load_table(args.root)
    if args.apply or (missing and not args.refresh):
        apply_snapshot(args.root, table)
        apply_supplements(args.root, table)
    else:
        print(f"Matched {table.get('matched_count')} players in {lookup_path(args.root)}.")


if __name__ == "__main__":
    main()
