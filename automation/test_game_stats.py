"""Game-stat pipeline tests. No API key and no network."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

import offline_tests
import game_stats as g
import wnba_sync as sync

offline_tests.install()

ROOT = Path(__file__).resolve().parents[1]
DAY = dt.date(2026, 10, 4)
NOW = dt.datetime(2026, 10, 5, 3, tzinfo=dt.timezone.utc)
NY = {"id": 9, "abbreviation": "NY", "full_name": "New York Liberty", "name": "Liberty", "city": "New York"}
ATL = {"id": 4, "abbreviation": "ATL", "full_name": "Atlanta Dream", "name": "Dream", "city": "Atlanta"}


def _athlete(name, stats, did_not_play=False, reason=""):
    return {
        "athlete": {"displayName": name, "id": 7},
        "didNotPlay": did_not_play,
        "reason": reason,
        "stats": stats,
    }


def summary(pts=19):
    labels = ["MIN", "PTS", "FG", "3PT", "FT", "REB", "AST", "TO", "STL", "BLK", "OREB", "DREB", "PF", "+/-"]
    return {
        "header": {
            "id": "401918295",
            "season": {"year": 2026, "type": 3},
            "competitions": [{
                "date": "2026-10-04T18:00:00Z",
                "status": {"type": {"state": "post", "name": "STATUS_FINAL"}},
                "competitors": [
                    {"homeAway": "away", "score": "19", "team": {"id": "9", "abbreviation": "NY", "displayName": "New York Liberty"},
                     "linescores": [{"displayValue": "10"}, {"displayValue": "9"}]},
                    {"homeAway": "home", "score": "17", "team": {"id": "20", "abbreviation": "ATL", "displayName": "Atlanta Dream"},
                     "linescores": [{"displayValue": "8"}, {"displayValue": "9"}]},
                ],
                "series": [
                    {"type": "season", "summary": "ATL wins series 2-1", "completed": True, "totalCompetitions": 3, "competitors": []},
                    {"type": "playoff", "title": "Playoff Series", "summary": "ATL leads series 1-0", "completed": False,
                     "totalCompetitions": 5, "competitors": [{"id": "20", "wins": 1}, {"id": "9", "wins": 0}]},
                ],
            }],
        },
        "boxscore": {
            "teams": [
                {"homeAway": "away", "team": {"abbreviation": "NY"}, "statistics": [
                    {"name": "fieldGoalsMade-fieldGoalsAttempted", "displayValue": "6-13"},
                    {"name": "threePointFieldGoalsMade-threePointFieldGoalsAttempted", "displayValue": "1-4"},
                    {"name": "freeThrowsMade-freeThrowsAttempted", "displayValue": "6-6"},
                    {"name": "totalRebounds", "displayValue": "2"},
                    {"name": "offensiveRebounds", "displayValue": "1"},
                    {"name": "defensiveRebounds", "displayValue": "1"},
                    {"name": "assists", "displayValue": "3"},
                    {"name": "steals", "displayValue": "0"},
                    {"name": "blocks", "displayValue": "1"},
                    {"name": "turnovers", "displayValue": "2"},
                    {"name": "fouls", "displayValue": "3"},
                ]},
                {"homeAway": "home", "team": {"abbreviation": "ATL"}, "statistics": [
                    {"name": "fieldGoalsMade-fieldGoalsAttempted", "displayValue": "6-10"},
                    {"name": "threePointFieldGoalsMade-threePointFieldGoalsAttempted", "displayValue": "1-2"},
                    {"name": "freeThrowsMade-freeThrowsAttempted", "displayValue": "4-6"},
                    {"name": "totalRebounds", "displayValue": "7"},
                    {"name": "offensiveRebounds", "displayValue": "4"},
                    {"name": "defensiveRebounds", "displayValue": "3"},
                    {"name": "assists", "displayValue": "2"},
                    {"name": "steals", "displayValue": "1"},
                    {"name": "blocks", "displayValue": "0"},
                    {"name": "turnovers", "displayValue": "1"},
                    {"name": "fouls", "displayValue": "2"},
                ]},
            ],
            "players": [
                {"team": {"abbreviation": "NY"}, "statistics": [{"labels": labels, "athletes": [
                    _athlete("Breanna Stewart", ["40", str(pts), "6-13", "1-4", "6-6", "2", "3", "2", "0", "1", "1", "1", "3", "4"]),
                    _athlete("Anneli Maley", [], did_not_play=True, reason="COACH'S DECISION"),
                ]}]},
                {"team": {"abbreviation": "ATL"}, "statistics": [{"labels": labels, "athletes": [
                    _athlete("Angel Reese", ["34:00", "17", "6-10", "1-2", "4-6", "7", "2", "1", "1", "0", "4", "3", "2", "7"]),
                ]}]},
            ],
        },
    }


def scoreboard():
    return {"events": [{
        "id": "401918295",
        "date": "2026-10-04T18:00:00Z",
        "season": {"year": 2026, "type": 3},
        "competitions": [{
            "status": {"type": {"state": "post", "name": "STATUS_FINAL"}},
            "competitors": [
                {"homeAway": "away", "score": "19", "team": {"abbreviation": "NY", "displayName": "New York Liberty"}},
                {"homeAway": "home", "score": "17", "team": {"abbreviation": "ATL", "displayName": "Atlanta Dream"}},
            ],
            "series": {"type": "playoff", "summary": "ATL leads series 1-0", "completed": False},
        }],
    }]}


def bdl_rows():
    game = {
        "id": 100, "date": "2026-10-04T18:00:00Z", "season": 2026, "postseason": True,
        "status_state": "final", "visitor_team": NY, "home_team": ATL, "away_score": 19, "home_score": 17,
    }
    players = [
        {"player": {"id": 1, "first_name": "Breanna", "last_name": "Stewart"}, "team": NY, "game": {"id": 100},
         "min": "40", "pts": 19, "reb": 2, "ast": 3, "oreb": 1, "dreb": 1, "stl": 0, "blk": 1,
         "turnover": 2, "pf": 3, "fgm": 6, "fga": 13, "fg3m": 1, "fg3a": 4, "ftm": 6, "fta": 6, "plus_minus": 4},
        {"player": {"id": 2, "first_name": "Angel", "last_name": "Reese"}, "team": ATL, "game": {"id": 100},
         "min": "34", "pts": 17, "reb": 7, "ast": 2, "oreb": 4, "dreb": 3, "stl": 1, "blk": 0,
         "turnover": 1, "pf": 2, "fgm": 6, "fga": 10, "fg3m": 1, "fg3a": 2, "ftm": 4, "fta": 6, "plus_minus": 7},
    ]
    teams = [
        {"team": NY, "game": {"id": 100}, "fgm": 6, "fga": 13, "fg3m": 1, "fg3a": 4, "ftm": 6, "fta": 6,
         "oreb": 1, "dreb": 1, "reb": 2, "ast": 3, "stl": 0, "blk": 1, "turnovers": 2, "fouls": 3},
        {"team": ATL, "game": {"id": 100}, "fgm": 6, "fga": 10, "fg3m": 1, "fg3a": 2, "ftm": 4, "fta": 6,
         "oreb": 4, "dreb": 3, "reb": 7, "ast": 2, "stl": 1, "blk": 0, "turnovers": 1, "fouls": 2},
    ]
    plays = [
        {"order": 1, "period": 1, "away_score": 10, "home_score": 8},
        {"order": 2, "period": 2, "away_score": 19, "home_score": 17},
    ]
    standings = [
        {"team": NY, "season": 2026, "wins": 10, "losses": 8, "playoff_seed": 4, "conference": "Eastern Conference"},
        {"team": ATL, "season": 2026, "wins": 12, "losses": 6, "playoff_seed": 2, "conference": "Eastern Conference"},
    ]
    return {"games": [game], "player_stats": players, "team_stats": teams, "plays": plays, "standings": standings}


class FakeBdl:
    def __init__(self, rows=None, fail=()):
        self.rows = rows or {}
        self.fail = set(fail)

    def all(self, endpoint, params=None):
        if endpoint in self.fail:
            raise sync.SyncError("synthetic outage")
        return list(self.rows.get(endpoint, []))


def fetch_ok(url):
    if "summary" in url:
        return summary()
    if "scoreboard" in url:
        return scoreboard()
    raise AssertionError(url)


class Tests(unittest.TestCase):
    def test_aliases_and_file_name(self):
        self.assertEqual(g.parse_teams("nyl, atl"), ["NY", "ATL"])
        self.assertEqual(g.canonical("LVA"), "LV")
        self.assertEqual(g.game_slug(DAY, {"abbreviation": "NY"}, {"abbreviation": "ATL"}), "2026-10-04-ny-atl")
        self.assertEqual(g.game_slug(DAY, {"abbreviation": "../x"}, {"abbreviation": "ATL"}), "2026-10-04-tbd-atl")

    def test_minutes_and_names(self):
        self.assertTrue(g.minutes_equal("34", "34:00"))
        self.assertFalse(g.minutes_equal("34", "33:30"))
        self.assertEqual(g.name_key("A'ja Wilson"), g.name_key("A’ja Wilson"))
        self.assertEqual(g.name_key("Te-Hina Paopao"), "tehinapaopao")

    def test_quarters_from_plays_have_no_gaps(self):
        rows = g.periods_from_plays([
            {"order": 1, "period": 1, "away_score": 10, "home_score": 8},
            {"order": 2, "period": 2, "away_score": 19, "home_score": 17},
        ])
        self.assertEqual(rows, [{"period": 1, "away": 10, "home": 8}, {"period": 2, "away": 9, "home": 9}])
        self.assertIsNone(g.periods_from_plays([
            {"order": 1, "period": 1, "away_score": 10, "home_score": 8},
            {"order": 2, "period": 3, "away_score": 19, "home_score": 17},
        ]))
        self.assertEqual(g.choose_periods([("plays", rows)], 19, 17)[0], "plays")
        self.assertEqual(g.choose_periods([("plays", rows)], 20, 17), (None, None))

    def test_quarters_ignore_a_late_out_of_order_play(self):
        # Aces at Valkyries, 2026-10-04: a second-quarter substitution came back
        # last in the feed with the 25-34 score from 3:42 of the second quarter.
        rows = g.periods_from_plays([
            {"order": 1, "period": 1, "away_score": 18, "home_score": 22},
            {"order": 2, "period": 2, "away_score": 25, "home_score": 34},
            {"order": 3, "period": 2, "away_score": 31, "home_score": 34},
            {"order": 4, "period": 3, "away_score": 48, "home_score": 56},
            {"order": 5, "period": 4, "away_score": 60, "home_score": 71},
            {"order": 6, "period": 2, "away_score": 25, "home_score": 34},
        ])
        self.assertEqual(rows, [
            {"period": 1, "away": 18, "home": 22},
            {"period": 2, "away": 13, "home": 12},
            {"period": 3, "away": 17, "home": 22},
            {"period": 4, "away": 12, "home": 15},
        ])

    def test_http_classification_does_not_need_a_key(self):
        self.assertEqual(g.classify_http(200, ""), "allowed")
        self.assertEqual(g.classify_http(400, "game_id is required"), "allowed")
        self.assertEqual(g.classify_http(401, "Please upgrade your plan"), "denied")
        self.assertEqual(g.classify_http(403, ""), "denied")
        self.assertEqual(g.classify_http(404, ""), "not_found")

    def test_crosscheck_lists_each_field(self):
        espn = g.parse_summary(summary())
        primary = g.build_bdl_document(
            bdl_rows()["games"][0], [g.provider_player(row) for row in bdl_rows()["player_stats"]],
            bdl_rows()["team_stats"], bdl_rows()["plays"], [], [], bdl_rows()["standings"], "2026-10-04T00:00:00+00:00",
        )
        g.apply_espn(primary, espn)
        self.assertTrue(primary["crosscheck"]["matched"])
        self.assertEqual(primary["crosscheck"]["mismatches"], [])
        self.assertEqual(primary["periods_source"], "plays")
        self.assertEqual(primary["standings"]["source"], "balldontlie")
        espn["players"][0]["pts"] = 18
        again = g.crosscheck(primary, espn)
        self.assertEqual(again["mismatches"][0]["field"], "player.NY.Breanna Stewart.pts")
        self.assertEqual(again["mismatches"][0]["balldontlie"], 19)
        self.assertEqual(again["mismatches"][0]["espn"], 18)
        espn["players"][0]["fgm"] = 1
        fields = [row["field"] for row in g.crosscheck(primary, espn)["mismatches"]]
        self.assertIn("player.NY.Breanna Stewart.fgm", fields)
        self.assertIn("player.NY.Breanna Stewart.pts", fields)
        espn["players"][0]["fgm"] = 6
        espn["away"]["totals"]["reb"] = 9
        fields = [row["field"] for row in g.crosscheck(primary, espn)["mismatches"]]
        self.assertIn("team.NY.reb", fields)

    def test_dnp_is_not_a_mismatch(self):
        espn = g.parse_summary(summary())
        self.assertTrue(any(row["name"] == "Anneli Maley" and row["did_not_play"] for row in espn["players"]))
        primary = g.build_bdl_document(
            bdl_rows()["games"][0], [g.provider_player(row) for row in bdl_rows()["player_stats"]],
            bdl_rows()["team_stats"], bdl_rows()["plays"], [], [], [], "2026-10-04T00:00:00+00:00",
        )
        result = g.crosscheck(primary, espn)
        self.assertFalse(any("Maley" in row["field"] for row in result["mismatches"]))

    def test_pipeline_matches_without_a_key(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            code = g.run(
                root, NOW, dates=[DAY], client=FakeBdl(bdl_rows()), fetch=fetch_ok,
                access={"key_present": True, "endpoints": {}},
            )
            self.assertEqual(code, 0)
            path = root / "data" / "games" / "2026-10-04-ny-atl.json"
            doc = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(doc["source"], "balldontlie")
            self.assertFalse(doc["fallback"])
            self.assertEqual(doc["away"]["score"], 19)
            self.assertEqual(doc["home"]["score"], 17)
            self.assertTrue(doc["crosscheck"]["matched"])
            text = path.with_suffix(".md").read_text(encoding="utf-8")
            self.assertIn("Matched.", text)
            self.assertIn("6-10 FG", text)
            self.assertIn("+7", text)
            self.assertIn("Play-by-play: 2 plays", text)
            self.assertEqual(len(doc["plays"]), 2)
            self.assertEqual(doc["plays"][0]["away_score"], 10)
            self.assertFalse(doc["overtime"])
            self.assertEqual(doc["plays_status"], "included")
            index = json.loads((root / "data" / "games" / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(index["games"][0]["path"], "data/games/2026-10-04-ny-atl.json")
            self.assertEqual(index["games"][0]["matchup"], "ny-at-atl")
            self.assertEqual(index["games"][0]["mismatch_count"], 0)
            self.assertIn(g.PUBLIC_SOURCE_NOTE, text)
            self.assertNotIn("balldontlie", text)
            self.assertNotIn("\u2014", text)
            self.assertNotIn("synthetic-key", text)
            first = doc["checked_at"]
            path.with_suffix(".md").write_text(text.replace(g.PUBLIC_SOURCE_NOTE, "Source: vendor."), encoding="utf-8")
            again = g.run(
                root, NOW + dt.timedelta(hours=2), dates=[DAY], client=FakeBdl(bdl_rows()), fetch=fetch_ok,
                access={"key_present": True, "endpoints": {}},
            )
            self.assertEqual(again, 0)
            refreshed = path.with_suffix(".md").read_text(encoding="utf-8")
            self.assertIn(g.PUBLIC_SOURCE_NOTE, refreshed)
            self.assertNotIn("Source: vendor.", refreshed)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["checked_at"], first)

    def test_fallback_when_balldontlie_is_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            code = g.run(root, NOW, dates=[DAY], fetch=fetch_ok)
            self.assertEqual(code, 0)
            doc = json.loads((root / "data" / "games" / "2026-10-04-ny-atl.json").read_text(encoding="utf-8"))
            self.assertEqual(doc["source"], "espn")
            self.assertTrue(doc["fallback"])
            self.assertIn("not set", doc["fallback_reason"])
            text = (root / "data" / "games" / "2026-10-04-ny-atl.md").read_text(encoding="utf-8")
            self.assertIn("FLAG: the site's own feed did not supply this game. Numbers are from the official box score.", text)
            self.assertIn(g.PUBLIC_SOURCE_NOTE, text)
            self.assertNotIn("balldontlie", text)
            self.assertFalse(doc["crosscheck"]["compared"])

    def test_both_sources_down_is_not_silent(self):
        def down(_url):
            raise g.EspnError("down", code=503)
        with tempfile.TemporaryDirectory() as folder:
            code = g.run(
                Path(folder), NOW, dates=[DAY], espn_id="401918295",
                client=FakeBdl(fail={"games"}), fetch=down,
                access={"key_present": True, "endpoints": {"games": {"status": "allowed", "http": 200}}},
            )
            self.assertEqual(code, 1)

    def test_offseason_schedule_writes_nothing(self):
        def down(_url):
            raise AssertionError("offseason should not call ESPN")
        rows = {"games": [{"date": "2009-07-19", "status_state": "final"}]}
        with tempfile.TemporaryDirectory() as folder:
            code = g.run(
                Path(folder), dt.datetime(2009, 12, 1, tzinfo=dt.timezone.utc),
                scheduled=True, client=FakeBdl(rows), fetch=down,
            )
            self.assertEqual(code, 0)
            self.assertFalse((Path(folder) / "data" / "games").exists())

    def test_refuses_to_write_the_key(self):
        key = "synthetic-key-do-not-commit-123456"
        rows = bdl_rows()
        rows["player_stats"][0]["player"]["last_name"] = key
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(g.GameStatsError):
                g.run(
                    Path(folder), NOW, key=key, dates=[DAY], client=FakeBdl(rows), fetch=fetch_ok,
                    access={"key_present": True, "endpoints": {}},
                )
            games = list((Path(folder) / "data" / "games").glob("2026-10-04-*.json"))
            self.assertEqual(games, [])

    def test_audit_catches_a_planted_key(self):
        key = "synthetic-key-do-not-commit-123456"
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "data" / "games" / "2026-10-04-ny-atl.json"
            target.parent.mkdir(parents=True)
            target.write_text('{"note": "%s"}\n' % key, encoding="utf-8")
            with self.assertRaises(g.GameStatsError):
                g.audit_tree(root, key)
            target.write_text('{"source": "balldontlie"}\n', encoding="utf-8")
            g.audit_tree(root, key)

    def test_team_filter(self):
        espn = g.parse_summary(summary())
        other = g.parse_summary(summary())
        other["espn_game_id"] = "401918296"
        other["away"]["abbreviation"] = "LV"
        other["home"]["abbreviation"] = "GS"
        games = [espn, other]
        self.assertEqual([row["espn_game_id"] for row in games if g.wanted(row, ["NYL"], "")], ["401918295"])
        self.assertEqual([row["espn_game_id"] for row in games if g.wanted(row, ["LV", "GS"], "")], ["401918296"])
        self.assertEqual([row["espn_game_id"] for row in games if g.wanted(row, [], "401918296")], ["401918296"])

    def test_style_guide_and_workflow(self):
        guide = (ROOT / "docs" / "style-guide.md").read_text(encoding="utf-8")
        self.assertIn("data/games/", guide)
        self.assertIn("data/games/index.json", guide)
        self.assertIn(g.PUBLIC_SOURCE_NOTE, guide)
        self.assertNotIn("balldontlie", guide.lower())
        self.assertIn("ESPN is the cross-check", guide)
        self.assertIn("ESPN box-score link", guide)
        self.assertIn("mismatch", guide.lower())
        workflow = (ROOT / ".github" / "workflows" / "fcb-game-stats.yml").read_text(encoding="utf-8")
        self.assertIn("BALLDONTLIE_API_KEY", workflow)
        self.assertNotIn("echo \"$BALLDONTLIE_API_KEY\"", workflow)
        self.assertNotIn("echo $BALLDONTLIE_API_KEY", workflow)
        self.assertIn("America/Los_Angeles", workflow)
        self.assertGreaterEqual(workflow.count("cron:"), 5)
        self.assertIn("espn_game_id", workflow)
        self.assertIn("workflow_dispatch", workflow)
        self.assertIn("git pull --rebase origin main", workflow)
        self.assertNotIn("upload-pages-artifact", workflow)
        self.assertNotIn("deploy-pages", workflow)
        dispatcher = (ROOT / ".github" / "workflows" / "dispatch-game-stats.yml").read_text(encoding="utf-8")
        self.assertIn("fcb-game-stats.yml/dispatches", dispatcher)
        self.assertNotIn("BALLDONTLIE_API_KEY", dispatcher)
        updater = (ROOT / ".github" / "workflows" / "fcb-wnba.yml").read_text(encoding="utf-8")
        self.assertIn("data/games", updater)
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("data/games", attributes)
        self.assertIn("export-ignore", attributes)
        writer = (ROOT / "docs" / "STATS_SOURCE.md").read_text(encoding="utf-8")
        self.assertIn("data/games/", writer)
        self.assertIn("data/games/index.json", writer)
        self.assertIn(g.PUBLIC_SOURCE_NOTE, writer)
        self.assertIn("ESPN", writer)
        self.assertIn("cross-check", writer.lower())
        self.assertIn("never name or link", writer.lower())
        self.assertNotIn("balldontlie", writer.lower())
        self.assertNotIn("api.balldontlie.io", writer.lower())


if __name__ == "__main__":
    unittest.main()
