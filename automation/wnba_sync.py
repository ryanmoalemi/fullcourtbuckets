#!/usr/bin/env python3
"""Server-side BALLDONTLIE WNBA importer. Python 3.11+, standard library only.

Only provider data goes into data/wnba. Credentials stay in the runner environment.
A failed fetch/validation never reaches git or the publication step.
"""
from __future__ import annotations
import argparse
import collections
import datetime as dt
import email.utils
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

import season_teams
import team_names

BASE = "https://api.balldontlie.io/wnba/v1/"
PUBLIC_SOURCE = "Full Court Buckets gathers its own game data and verifies it."
FIRST_YEAR = 2008
METRICS = ("min", "fgm", "fga", "fg_pct", "fg3m", "fg3a", "fg3_pct",
           "ftm", "fta", "ft_pct", "oreb", "dreb", "reb", "ast", "stl", "blk", "turnover", "pts")

class SyncError(RuntimeError):
    pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SyncError("API redirect rejected; no credential was forwarded.")

class Client:
    def __init__(self, key: str, interval: float = 0.2):
        if not key or not key.strip():
            raise SyncError("Add the repository Actions secret BALLDONTLIE_API_KEY before syncing.")
        self.key = key.strip()
        self.interval = max(0.11, interval)
        self.last_request = 0.0
        self.opener = urllib.request.build_opener(NoRedirect())

    def get(self, endpoint: str, params: dict | None = None) -> dict:
        if not re.fullmatch(r"[a-z_]+(?:/[a-z_]+)?", endpoint):
            raise SyncError("Invalid API endpoint.")
        url = BASE + endpoint + "?" + urllib.parse.urlencode(params or {}, doseq=True)
        for attempt in range(7):
            time.sleep(max(0, self.interval - (time.monotonic() - self.last_request)))
            request = urllib.request.Request(url, headers={
                "Authorization": self.key, "Accept": "application/json",
                "User-Agent": "FullCourtBuckets/1.0 (+https://fullcourtbuckets.com/)"})
            self.last_request = time.monotonic()
            try:
                with self.opener.open(request, timeout=45) as response:
                    payload = json.load(response)
                if not isinstance(payload, dict):
                    raise SyncError("Unexpected API response shape.")
                return payload
            except urllib.error.HTTPError as error:
                # Never log response bodies, request headers, or the API key.
                if error.code in (401, 403):
                    raise SyncError("BALLDONTLIE rejected authentication or WNBA endpoint access (401/403).") from None
                if error.code not in (429, 500, 502, 503, 504) or attempt == 6:
                    raise SyncError(f"BALLDONTLIE request failed with HTTP {error.code}.") from None
                retry = error.headers.get("Retry-After", "")
                try:
                    wait = float(retry)
                except ValueError:
                    try:
                        wait = (email.utils.parsedate_to_datetime(retry) - dt.datetime.now(dt.timezone.utc)).total_seconds()
                    except (ValueError, TypeError):
                        wait = 60 if error.code == 429 else 2 ** attempt
                if error.code == 429:
                    # Trial accounts are limited to 5 requests/minute. Adapt safely.
                    self.interval = max(self.interval, 12.2)
                time.sleep(min(600, max(1, wait)))
            except (urllib.error.URLError, TimeoutError):
                if attempt == 6:
                    raise SyncError("BALLDONTLIE is unreachable after retries.") from None
                time.sleep(2 ** attempt)
            except (ValueError, json.JSONDecodeError):
                raise SyncError("BALLDONTLIE returned invalid JSON.") from None
        raise SyncError("API retry limit reached.")

    def all(self, endpoint: str, params: dict | None = None) -> list[dict]:
        query = dict(params or {})
        query["per_page"] = 100
        result, seen = [], set()
        for _ in range(10000):
            payload = self.get(endpoint, query)
            rows = payload.get("data")
            if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
                raise SyncError(f"Invalid data array from {endpoint}.")
            result.extend(rows)
            meta = payload.get("meta") or {}
            if not isinstance(meta, dict):
                raise SyncError("Invalid pagination metadata.")
            cursor = meta.get("next_cursor")
            if cursor is None:
                return result
            if not rows or str(cursor) in seen:
                raise SyncError("Empty or repeating pagination cursor; refusing partial data.")
            seen.add(str(cursor))
            query["cursor"] = cursor
        raise SyncError("Pagination safety limit reached.")

def load(path: Path, default):
    return json.loads(path.read_text()) if path.exists() else default

def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)

def identifier(value) -> int:
    if isinstance(value, bool) or not str(value).isdigit() or int(value) <= 0:
        raise SyncError("Missing or invalid permanent provider ID.")
    return int(value)

def number(value, *, percentage=False):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise SyncError("Boolean in a numeric statistics field.")
    try:
        value = float(value)
    except (ValueError, TypeError):
        raise SyncError("Invalid numeric statistic.") from None
    if not math.isfinite(value) or value < 0 or (percentage and value > 100):
        raise SyncError("Out-of-range statistic.")
    return value

def team(value):
    if not value:
        return None
    if not isinstance(value, dict):
        raise SyncError("Invalid team object.")
    return team_names.apply({k: value.get(k) for k in ("id", "full_name", "abbreviation", "city", "name", "conference")})

# A stored weight must be a plausible number of pounds. The provider snapshot
# put the college name in weight and left college null. Height and jersey were not shifted.
MIN_POUNDS = 80
MAX_POUNDS = 400
_POUNDS_RE = re.compile(r"^(\d{2,3}(?:\.\d+)?)\s*(?:lbs?\.?|pounds?)?$", re.I)
_CANONICAL_POUNDS_RE = re.compile(r"^\d{2,3}(?:\.\d+)? lbs$")
_HEIGHT_RE = re.compile(r"""^\d'\s*\d{1,2}"$""")
_BLANK_BIO = frozenset({"", "--", "—", "-", "n/a", "na", "none"})


def _blank_bio(value) -> bool:
    if value is None:
        return True
    return str(value).strip().casefold() in _BLANK_BIO


def normalize_pounds(value):
    """Canonical '157 lbs' when value is 80–400 pounds. None otherwise."""
    if _blank_bio(value):
        return None
    text = str(value).strip()
    match = _POUNDS_RE.fullmatch(text)
    if not match:
        return None
    number = float(match.group(1))
    if number < MIN_POUNDS or number > MAX_POUNDS:
        return None
    if _CANONICAL_POUNDS_RE.fullmatch(text):
        return text
    shown = str(int(number)) if number == int(number) else format(number, "g")
    return f"{shown} lbs"


def plausible_pounds(value) -> bool:
    """True when weight is absent or a plausible number of pounds."""
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return normalize_pounds(value) is not None


def _school_name(value):
    """A college string. A number of pounds, a placeholder, or a shifted jersey is not one."""
    if _blank_bio(value) or normalize_pounds(value) is not None:
        return None
    text = str(value).strip()
    if len(text) > 80 or len(re.findall(r"[A-Za-z]", text)) < 3:
        return None
    return text


def normalize_bio(value: dict) -> dict:
    """Split height, weight, and college. A school name in weight moves to college.

    A real pound value stays on weight. A placeholder is cleared. No pound value
    is invented when the feed did not provide one.
    """
    if not isinstance(value, dict):
        raise SyncError("Invalid player biography.")
    weight = normalize_pounds(value.get("weight"))
    college = _school_name(value.get("college"))
    if weight is None and college is None:
        college = _school_name(value.get("weight"))
    if weight is None and college is None:
        weight = normalize_pounds(value.get("college"))
    height = value.get("height")
    height_text = "" if height is None else str(height).strip()
    height = height_text if _HEIGHT_RE.fullmatch(height_text) else None
    jersey = value.get("jersey_number")
    jersey_text = "" if jersey is None else str(jersey).strip()
    jersey = jersey_text if re.fullmatch(r"\d{1,2}", jersey_text) else None
    return {
        "position": value.get("position"),
        "position_abbreviation": value.get("position_abbreviation"),
        "height": height,
        "weight": weight,
        "jersey_number": jersey,
        "college": college,
    }


def player(value):
    pid = identifier(value.get("id"))
    first, last = str(value.get("first_name") or "").strip(), str(value.get("last_name") or "").strip()
    if not first and not last:
        raise SyncError("Player record without a name.")
    return {"id": pid, "first_name": first, "last_name": last,
            **normalize_bio(value),
            "team": team(value.get("team"))}

def stable_slug(pid: int, name: str, registry: dict) -> str:
    key = str(pid)
    if key in registry:
        result = registry[key]
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", result):
            raise SyncError("Invalid existing player slug.")
        return result
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9]+", "-", ascii_name.replace("'", "").replace("’", "")).strip("-") or f"player-{pid}"
    used = set(registry.values())
    result = base if base not in used else f"{base}-{pid}"
    if result in used:
        raise SyncError("Player URL collision; refusing to overwrite another profile.")
    registry[key] = result
    return result

def season_rows(rows: list[dict], year: int) -> list[dict]:
    result = {}
    for raw in rows:
        if int(raw.get("season", -1)) != year:
            raise SyncError("API returned the wrong season for a season-filtered request.")
        kind = int(raw.get("season_type", -1))
        if kind not in (2, 3):
            raise SyncError("Unknown competition type; refusing to mix preseason and WNBA records.")
        pid = identifier((raw.get("player") or {}).get("id"))
        gp = number(raw.get("games_played"))
        if gp is None or gp != int(gp):
            raise SyncError("Invalid games-played value.")
        row = {"player_id": pid, "season": year, "season_type": kind,
               "team": team(raw.get("team")), "games_played": int(gp),
               **{k: number(raw.get(k), percentage=k.endswith("_pct")) for k in METRICS}}
        if gp == 0:
            continue
        # Keep team stints and a provider aggregate separate. Never sum them.
        key = (pid, year, kind, (row["team"] or {}).get("id"))
        if key in result and row != result[key]:
            raise SyncError("Conflicting duplicate season row.")
        result[key] = row
    return drop_copied_playoff_rows(list(result.values()))


def drop_copied_playoff_rows(rows: list[dict]) -> list[dict]:
    """Drop a playoff line that repeats the regular-season line for that player and year."""
    regular = {}
    for row in rows:
        if isinstance(row, dict) and row.get("season_type") == 2:
            regular.setdefault((row.get("player_id"), row.get("season")), []).append(row)
    kept = []
    for row in rows:
        if isinstance(row, dict) and row.get("season_type") == 3:
            peers = regular.get((row.get("player_id"), row.get("season")), [])
            if any(_same_stat_line(row, peer) for peer in peers):
                continue
        kept.append(row)
    return kept


def _same_stat_line(left: dict, right: dict) -> bool:
    fields = ("games_played", "min", "pts", "reb", "ast", "stl", "blk", "turnover",
              "fgm", "fga", "fg_pct", "fg3m", "fg3a", "fg3_pct", "ftm", "fta", "ft_pct")
    return all(left.get(field) == right.get(field) for field in fields)

def date_of(value):
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None

def is_final(game: dict) -> bool:
    if "status_state" in game:
        return game["status_state"] == "final"
    return str(game.get("status", "")).strip().lower() in ("post", "final", "final/ot", "final/2ot")

def in_season(games: list[dict], today: dt.date) -> bool:
    usable = [g for g in games if g.get("status_state") not in ("canceled", "abandoned")]
    dates = [date_of(g.get("date")) for g in usable]
    dates = [d for d in dates if d]
    if not dates:
        # A missing schedule must not silently disable daily updates.
        return True
    first, last = min(dates), max(dates)
    # Starts a week before scheduled games; 28-day grace covers later playoff scheduling.
    return first - dt.timedelta(days=7) <= today <= last + dt.timedelta(days=28)

def should_refresh(last_success, today: dt.date, active: bool, force=False) -> bool:
    last = date_of(last_success)
    return force or last is None or (today - last).days >= (1 if active else 7)

def team_key(team):
    """Identity of a non-null team. Same id is the same team even if the name changes."""
    if not isinstance(team, dict):
        return None
    raw = team.get("id")
    if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0:
        return ("id", raw)
    if isinstance(raw, str) and raw.isdigit() and int(raw) > 0:
        return ("id", int(raw))
    name = str(team.get("full_name") or team.get("name") or "").strip()
    return ("name", name.casefold()) if name else None

def team_label(team) -> str:
    if not isinstance(team, dict):
        return ""
    return str(team.get("full_name") or team.get("name") or "").strip()

def pt_date(now: dt.datetime) -> str:
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    return now.astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat()

def prior_team_changes(profile) -> list:
    raw = profile.get("team_changes") if isinstance(profile, dict) else None
    if not isinstance(raw, list):
        return []
    kept = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        src, dst, day = entry.get("from"), entry.get("to"), entry.get("date")
        if src and dst and day:
            kept.append({"from": str(src), "to": str(dst), "date": str(day)})
    return kept

def stats_fingerprint(stats, games) -> str:
    """Stable comparison of the numbers a page would show. Ignores check time and roster text."""
    return json.dumps(
        {"games": games, "stats": stats},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str,
    )

def stats_updated_stamp(previous, stats, games, stamp: str) -> str:
    """Keep the previous stats date unless season lines or the game log actually changed."""
    if isinstance(previous, dict) and stats_fingerprint(previous.get("season_stats"), previous.get("recent_completed_games")) == stats_fingerprint(stats, games):
        kept = previous.get("stats_updated_at") or previous.get("checked_at")
        if isinstance(kept, str) and kept.strip():
            return kept
    return stamp

def merge_team_changes(previous, current_team, now: dt.datetime) -> list:
    """Newest-first history. Null transitions are not moves and are not recorded."""
    history = prior_team_changes(previous)
    previous_team = previous.get("current_team") if isinstance(previous, dict) else None
    old_key, new_key = team_key(previous_team), team_key(current_team)
    if not old_key or not new_key or old_key == new_key:
        return history
    src, dst = team_label(previous_team), team_label(current_team)
    if not src or not dst:
        return history
    return [{"from": src, "to": dst, "date": pt_date(now)}, *history]

def provider_rows(rows: list) -> list:
    """Feed rows only. Gap fills are re-applied after each sync and are not part of the shrink check."""
    return [row for row in rows if not (isinstance(row, dict) and row.get("gap_fill") is True)]


def guard_shrink(old: list, new: list, label: str) -> None:
    if old and len(new) < len(old) * 0.8:
        raise SyncError(f"Unexpected drop in {label}; keeping the previous published snapshot.")

def run(root: Path, client: Client, now: dt.datetime, force=False, season_team_table=None) -> bool:
    data = root / "data" / "wnba"
    state = load(data / "sync-state.json", {})
    today = now.astimezone(ZoneInfo("America/Los_Angeles")).date()
    schedule = client.all("games", {"seasons[]": [today.year]})
    active_season = in_season(schedule, today)
    if not should_refresh(state.get("last_success"), today, active_season, force):
        print("Offseason cadence: previous successful refresh is less than seven days old.")
        return False
    players = {identifier(p.get("id")): player(p) for p in client.all("players")}
    active_players = {identifier(p.get("id")): player(p) for p in client.all("players/active")}
    if not players or not active_players:
        raise SyncError("Empty player or active-player feed; existing data was retained.")
    guard_shrink(state.get("player_ids", []), list(players), "player inventory")
    guard_shrink(state.get("active_ids", []), list(active_players), "active-player feed")
    # Explicit current active records win over historical nested player.team objects.
    players.update(active_players)
    all_teams = [team(t) for t in client.all("teams")]
    if not all_teams:
        raise SyncError("Empty teams feed.")
    seasons = {}
    for year in range(FIRST_YEAR, today.year + 1):
        cache = data / "seasons" / f"{year}.json"
        old = load(cache, [])
        rotate = FIRST_YEAR + (today.toordinal() // 7) % max(1, today.year - FIRST_YEAR)
        refresh = not cache.exists() or year >= today.year - 1 or year == rotate
        if refresh:
            raw = []
            for kind in (2, 3):
                batch = client.all("player_season_stats", {"season": year, "season_type": kind})
                if any(int(r.get("season_type", -1)) != kind for r in batch):
                    raise SyncError("Competition filter was not honored by the provider.")
                raw.extend(batch)
            rows = season_rows(raw, year)
            guard_shrink(provider_rows(old), rows, f"{year} season rows")
            if year < today.year and not rows:
                raise SyncError(f"No historical records returned for {year}; initial import is incomplete.")
            seasons[year] = rows
        else:
            seasons[year] = old
    if season_team_table:
        seasons = {
            year: season_teams.correct_rows(rows, season_team_table)[0]
            for year, rows in seasons.items()
        }
        filled = replaced = dropped = unresolved = 0
        for year, rows in seasons.items():
            updated, report = season_teams.supplement_rows(
                rows, season_team_table, season_year=year, prior_rows=seasons.get(year - 1, [])
            )
            seasons[year] = updated
            filled += len(report["filled"])
            replaced += len(report["replaced"])
            dropped += len(report["dropped"])
            unresolved += len(report["unresolved"])
        if filled or replaced or dropped or unresolved:
            print(
                f"Filled {filled} missing season rows, replaced {replaced}, "
                f"dropped {dropped}. Unresolved game counts: {unresolved}."
            )
    # A recent log, not a falsely complete career game archive.
    start = today - dt.timedelta(days=35)
    recent_games = client.all("games", {"start_date": start.isoformat(), "end_date": today.isoformat()})
    finals = {identifier(g.get("id")): g for g in recent_games if is_final(g)}
    logs = collections.defaultdict(list)
    raw_logs = client.all("player_stats", {"start_date": start.isoformat(), "end_date": today.isoformat()}) if finals else []
    seen_logs = {}
    for raw in raw_logs:
        gid = identifier((raw.get("game") or {}).get("id"))
        if gid not in finals:
            continue
        pid = identifier((raw.get("player") or {}).get("id"))
        game = finals[gid]
        row = {"game_id": gid, "player_id": pid, "date": game.get("date"),
               "season": game.get("season"), "postseason": game.get("postseason"),
               "team": team(raw.get("team")), "home_team": team(game.get("home_team")),
               "visitor_team": team(game.get("visitor_team")),
               "home_score": game.get("home_score"), "away_score": game.get("away_score"),
               "minutes": raw.get("min"),
               **{k: number(raw.get(k)) for k in ("pts", "ast", "reb", "stl", "blk", "turnover")}}
        key = (pid, gid)
        if key in seen_logs and seen_logs[key] != row:
            raise SyncError("Conflicting duplicate player/game statistics.")
        seen_logs[key] = row
    for (pid, _), row in seen_logs.items():
        logs[pid].append(row)
    by_player = collections.defaultdict(list)
    for rows in seasons.values():
        for row in rows:
            by_player[row["player_id"]].append(row)
    registry = load(data / "id-map.json", {})
    if len(set(registry.values())) != len(registry):
        raise SyncError("Existing identity map contains duplicate URLs.")
    stamp = now.astimezone(dt.timezone.utc).isoformat(timespec="seconds")
    directory, profiles = [], {}
    old_directory = load(data / "players-index.json", {}).get("players", [])
    for pid, p in sorted(players.items()):
        if pid not in by_player and pid not in active_players:
            continue  # Players entirely outside the 2008+ scope are not newly published.
        name = (p["first_name"] + " " + p["last_name"]).strip()
        slug = stable_slug(pid, name, registry)
        stats = sorted(by_player[pid], key=lambda r: (-r["season"], r["season_type"], str((r["team"] or {}).get("id"))))
        recent = sorted(logs[pid], key=lambda r: str(r.get("date") or ""), reverse=True)
        # Absence from active feed is NOT evidence of retirement or free agency.
        active = pid in active_players
        current_team = p["team"] if active else None
        previous = load(data / "players" / f"{slug}.json", None)
        changes = merge_team_changes(previous, current_team, now)
        item = {"id": pid, "slug": slug, "name": name, "active_in_provider_feed": active,
                "current_team": current_team, "path": f"/wnba/{slug}/", "data_path": f"/data/wnba/players/{slug}.json"}
        directory.append(item)
        profile = {"schema_version": 1, "provider": "Full Court Buckets", "source": PUBLIC_SOURCE,
            "checked_at": stamp, "stats_updated_at": stats_updated_stamp(previous, stats, recent, stamp),
            "coverage_start": FIRST_YEAR, "career_totals_complete": False,
            "player": p, "slug": slug, "active_in_provider_feed": active, "current_team": current_team,
            "season_stats": stats, "recent_completed_games": recent,
            "game_log_window_start": start.isoformat(),
            "notes": ["Statistics from 2008 onward; not complete all-time career totals.",
                      "Season figures are provider per-game averages; shooting percentages are on a 0-100 scale.",
                      "Team stints and aggregate rows must never be summed together.",
                      "A season row uses the club from that season when games played matches one stint.",
                      "Not listed active does not establish retirement, a trade, or free agency.",
                      "News and confirmed transaction feeds are not included in this API integration."]}
        if changes:
            profile["team_changes"] = changes
        profiles[slug] = profile
    guard_shrink(old_directory, directory, "published player inventory")
    if not directory:
        raise SyncError("No eligible players; refusing empty publication.")
    # Publication workflow only commits after this entire function and all validation succeed.
    for year, rows in seasons.items():
        write(data / "seasons" / f"{year}.json", rows)
    for slug, profile in profiles.items():
        write(data / "players" / f"{slug}.json", profile)
    write(data / "id-map.json", registry)
    write(data / "teams.json", {"checked_at": stamp, "teams": all_teams})
    write(data / "players-index.json", {"checked_at": stamp, "players": sorted(directory, key=lambda p: p["name"].casefold())})
    write(data / "status.json", {"status": "ok", "last_success": stamp, "provider": "Full Court Buckets",
          "coverage_start": FIRST_YEAR, "seasons": list(seasons), "player_count": len(directory),
          "cadence": "daily" if active_season else "weekly", "in_season": active_season,
          "source_data_through": None, "news_connected": False, "transactions_connected": False})
    write(data / "sync-state.json", {"last_success": stamp, "player_ids": sorted(players), "active_ids": sorted(active_players)})
    print(f"Validated {len(directory)} player records, {len(seasons)} seasons. No credentials saved.")
    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        client = Client(os.environ.get("BALLDONTLIE_API_KEY", ""))
        season_teams.refresh(args.root)
        season_team_table = season_teams.load_table(args.root)
        if season_team_table.get("players"):
            print(f"Per-season teams loaded for {season_team_table.get('matched_count')} players.")
            if season_teams.needs_stat_lines(season_team_table):
                season_team_table = season_teams.enrich_stat_lines(args.root)
            if not season_team_table.get("playoff_teams"):
                years = range(FIRST_YEAR, dt.datetime.now(dt.timezone.utc).year + 1)
                season_team_table["playoff_teams"] = season_teams.fetch_playoff_teams(years)
                season_teams._write(season_teams.lookup_path(args.root), season_team_table)
        changed = run(args.root, client, dt.datetime.now(dt.timezone.utc), args.force, season_team_table or None)
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                f.write("changed=" + str(changed).lower() + "\n")
        return 0
    except SyncError as error:
        print(f"Sync stopped: {error}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
