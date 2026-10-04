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
STATS_URL = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/wnba/athletes/{athlete_id}/stats"
SOURCE = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/wnba/athletes/{id}/stats"
HISTORICAL_ID_START = 200
USER_AGENT = "FullCourtBuckets/1.0"


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
            try:
                games = int(str(stats[0]))
            except (TypeError, ValueError):
                continue
            stints.append({
                "season": year,
                "season_type": season_type,
                "games_played": games,
                "team_slug": slug,
            })
    return stints, {slug: team for slug, team in teams.items() if isinstance(team, dict)}


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


def player_stints(table: dict, player_id) -> list[dict]:
    players = table.get("players") if isinstance(table.get("players"), dict) else {}
    entry = players.get(str(player_id))
    if not isinstance(entry, dict):
        return []
    stints = entry.get("stints")
    return [item for item in stints if isinstance(item, dict)] if isinstance(stints, list) else []


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
        status, team = select_team(row, player_stints(table, row.get("player_id")), table)
        if status == "replace" and team:
            current = row.get("team") if isinstance(row.get("team"), dict) else {}
            same = current.get("id") == team.get("id") and current.get("full_name") == team.get("full_name")
            if same:
                updated.append(row)
                actions.append("keep")
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


def fetch_player(name: str, retries: int = 3) -> tuple[int | None, list[dict], dict, str]:
    """Return espn id, stints, team records, and a status string."""
    query = urllib.parse.urlencode({"query": name, "limit": 5, "type": "player"})
    search_url = SEARCH_URL + "?" + query
    last_error = ""
    for attempt in range(retries):
        try:
            found = pick_hit(search_hits(_request_json(search_url)), name)
            if not found:
                return None, [], {}, "no-match"
            espn_id = athlete_id(found)
            if not espn_id:
                return None, [], {}, "no-id"
            stints = []
            teams = {}
            for kind in (2, 3):
                stats_url = STATS_URL.format(athlete_id=espn_id) + "?" + urllib.parse.urlencode({"seasontype": kind})
                parsed, team_records = parse_stints(_request_json(stats_url), kind)
                stints.extend(parsed)
                teams.update(team_records)
            return espn_id, stints, teams, "ok"
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


def refresh(root: Path, workers: int = 6) -> dict:
    """Fetch per-season clubs for every stored player. Duplicate names are skipped."""
    root = Path(root)
    data = root / "data" / "wnba"
    teams_doc = json.loads((data / "teams.json").read_text(encoding="utf-8"))
    bdl_teams = teams_doc.get("teams") or []
    profiles = []
    names = {}
    for path in sorted((data / "players").glob("*.json")):
        profile = json.loads(path.read_text(encoding="utf-8"))
        player = profile.get("player") or {}
        player_id = player.get("id")
        name = f"{player.get('first_name') or ''} {player.get('last_name') or ''}".strip()
        if not isinstance(player_id, int) or isinstance(player_id, bool) or not name:
            continue
        profiles.append((player_id, name))
        names.setdefault(normalize_name(name), []).append(player_id)
    ambiguous = {player_id for ids in names.values() if len(ids) > 1 for player_id in ids}
    existing = load_table(root)
    players = existing.get("players") if isinstance(existing.get("players"), dict) else {}
    historical = existing.get("historical_teams") if isinstance(existing.get("historical_teams"), dict) else {}
    current = existing.get("current_teams") if isinstance(existing.get("current_teams"), dict) else {}
    pending = []
    for player_id, name in profiles:
        if player_id in ambiguous:
            continue
        status = str((players.get(str(player_id)) or {}).get("status") or "")
        if not status or status.startswith("error"):
            pending.append((player_id, name))
    print(f"Season teams: {len(pending)} to fetch, {len(players)} already stored, {len(ambiguous)} ambiguous names skipped.")

    def job(item):
        player_id, name = item
        espn_id, stints, teams, status = fetch_player(name)
        return player_id, name, espn_id, stints, teams, status

    done = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(job, item) for item in pending]
        for future in as_completed(futures):
            player_id, name, espn_id, stints, teams, status = future.result()
            mapped_current, historical = catalog_teams(bdl_teams, teams, historical)
            current.update(mapped_current)
            players[str(player_id)] = {
                "name": name,
                "espn_id": espn_id,
                "status": status,
                "stints": stints,
            }
            done += 1
            if done % 40 == 0 or done == len(pending):
                _write(lookup_path(root), _document(players, current, historical, ambiguous, profiles))
                print(f"Season teams stored {done}/{len(pending)}")
    for player_id in ambiguous:
        name = next(label for pid, label in profiles if pid == player_id)
        players[str(player_id)] = {"name": name, "espn_id": None, "status": "ambiguous-name", "stints": []}
    document = _document(players, current, historical, ambiguous, profiles)
    _write(lookup_path(root), document)
    return document


def _document(players, current, historical, ambiguous, profiles) -> dict:
    unmatched = [
        {"id": int(player_id), "name": entry.get("name"), "status": entry.get("status")}
        for player_id, entry in sorted(players.items(), key=lambda item: int(item[0]))
        if entry.get("status") != "ok"
    ]
    return {
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
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    missing = not lookup_path(args.root).is_file()
    if args.refresh or (missing and not args.apply):
        table = refresh(args.root, args.workers)
    else:
        table = load_table(args.root)
    if args.apply or (missing and not args.refresh):
        apply_snapshot(args.root, table)
    else:
        print(f"Matched {table.get('matched_count')} players in {lookup_path(args.root)}.")


if __name__ == "__main__":
    main()
