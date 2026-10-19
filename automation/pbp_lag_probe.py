#!/usr/bin/env python3
"""Live-lag probe for Finals Game 2 (ESPN-style id 401918306): one fetch of the
stats feed's game record and play-by-play, logging only non-secret metrics.
Writes probe.json and appends a row to the GitHub job summary. Never writes the site.
The API key is read from BALLDONTLIE_API_KEY and never printed."""
import datetime as dt, json, os, sys
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).parent))
import wnba_sync as sync

PT = ZoneInfo("America/Los_Angeles")
STOP_AFTER = dt.date(2026, 10, 20)  # PT; does nothing after this date
TEAMS = {"ATL", "GS", "GSV"}
GAME_KEYS = ("id", "date", "datetime", "status", "period", "time", "postseason",
             "home_score", "away_score", "visitor_score", "status_state", "home_team_score", "visitor_team_score")


def abbr(team):
    return (team or {}).get("abbreviation") if isinstance(team, dict) else None


def main():
    now = dt.datetime.now(dt.timezone.utc)
    out = {"fetched_utc": now.isoformat(timespec="seconds"),
           "fetched_pt": now.astimezone(PT).isoformat(timespec="seconds"), "espn_game_id": "401918306"}
    if now.astimezone(PT).date() > STOP_AFTER and os.environ.get("FORCE") != "1":
        out["skipped"] = "after Oct 20, 2026 PT; probe disabled"
        return finish(out)
    try:
        client = sync.Client(os.environ.get("BALLDONTLIE_API_KEY", ""))
        games = client.all("games", {"dates[]": ["2026-10-19", "2026-10-20"]})
        game = next((g for g in games if {abbr(g.get("home_team")), abbr(g.get("visitor_team"))} <= TEAMS), None)
        if not game:
            out["error"] = f"Game 2 not found in games for Oct 19-20 ({len(games)} games returned)"
            return finish(out)
        out["game"] = {k: game.get(k) for k in GAME_KEYS if k in game}
        out["game_fields"] = sorted(game.keys())
        out["home"], out["away"] = abbr(game.get("home_team")), abbr(game.get("visitor_team"))
        t0 = dt.datetime.now(dt.timezone.utc)
        plays = client.all("plays", {"game_id": game["id"]})
        out["plays_fetch_seconds"] = round((dt.datetime.now(dt.timezone.utc) - t0).total_seconds(), 2)
        out["play_count"] = len(plays)
        if plays:
            plays.sort(key=lambda p: (p.get("order") is None, p.get("order") or 0))
            last = plays[-1]
            out["last_play"] = {"order": last.get("order"), "period": last.get("period"), "clock": last.get("clock"),
                                "type": last.get("type"), "text": str(last.get("text") or "")[:80],
                                "away_score": last.get("away_score", last.get("visitor_score")), "home_score": last.get("home_score")}
            out["play_fields"] = sorted(last.keys())
            for k in ("wallclock", "time_actual", "created_at", "updated_at", "timestamp"):
                if k in last:
                    out["last_play"][k] = last[k]
    except sync.SyncError as exc:
        out["error"] = str(exc)
    except Exception as exc:  # never include request details
        out["error"] = f"{type(exc).__name__}"
    return finish(out)


def finish(out):
    Path("probe.json").write_text(json.dumps(out, indent=1, default=str))
    g, lp = out.get("game", {}), out.get("last_play", {})
    row = (f"| {out['fetched_pt']} | {out['fetched_utc']} | {g.get('status', '')} | {g.get('period', '')} | {g.get('time', '')} | "
           f"{lp.get('period', '')} {lp.get('clock', '')} | {str(lp.get('text', '')).replace('|', '/')} | {out.get('play_count', '')} | "
           f"{lp.get('away_score', g.get('away_score', g.get('visitor_score', '')))}-{lp.get('home_score', g.get('home_score', ''))} | {out.get('error') or out.get('skipped') or ''} |")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write("| Fetched PT | Fetched UTC | Status | Period | Clock | Last play | Last play text | Plays | Score ATL-GS | Note |\n"
                    "|---|---|---|---|---|---|---|---|---|---|\n" + row + "\n")
    print(row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
