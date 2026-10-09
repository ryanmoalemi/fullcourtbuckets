"""Per-season team matching. Fixtures only, no network."""
import json
from pathlib import Path
import tempfile
import unittest

import offline_tests
import season_teams as teams

offline_tests.install()

SPARKS = {"id": 12, "full_name": "Los Angeles Sparks", "abbreviation": "LA", "city": "Los Angeles", "name": "Sparks", "conference": "Western Conference"}
ACES = {"id": 8, "full_name": "Las Vegas Aces", "abbreviation": "LV", "city": "Las Vegas", "name": "Aces", "conference": "Western Conference"}
STARS = {"id": 200, "full_name": "San Antonio Stars", "abbreviation": "SA", "city": "San Antonio", "name": "Stars", "conference": None}

TABLE = {
    "current_teams": {
        "los-angeles-sparks": SPARKS,
        "las-vegas-aces": ACES,
        "phoenix-mercury": {"id": 10, "full_name": "Phoenix Mercury", "abbreviation": "PHX", "city": "Phoenix", "name": "Mercury", "conference": "Western Conference"},
    },
    "historical_teams": {"san-antonio-stars": STARS},
    "players": {
        "488": {
            "name": "Kelsey Plum",
            "status": "ok",
            "stints": [
                {"season": 2017, "season_type": 2, "games_played": 31, "team_slug": "san-antonio-stars"},
                {"season": 2025, "season_type": 2, "games_played": 43, "team_slug": "los-angeles-sparks"},
                {"season": 2026, "season_type": 2, "games_played": 12, "team_slug": "los-angeles-sparks"},
                {"season": 2026, "season_type": 2, "games_played": 5, "team_slug": "phoenix-mercury"},
            ],
        }
    },
}


def row(year, games, team=SPARKS, kind=2):
    return {"player_id": 488, "season": year, "season_type": kind, "team": dict(team), "games_played": games, "pts": 10}


class SeasonTeamTests(unittest.TestCase):
    def test_name_match_accepts_a_longer_display_name(self):
        hit = {"displayName": "Skylar Diggins-Smith", "defaultLeagueSlug": "wnba", "uid": "s:40~l:59~a:3142320"}
        other = {"displayName": "Skylar Diggins-Jones", "defaultLeagueSlug": "wnba", "uid": "s:40~l:59~a:9"}
        self.assertEqual(teams.pick_hit([hit], "Skylar Diggins"), hit)
        self.assertIsNone(teams.pick_hit([hit, other], "Skylar Diggins"))
        self.assertEqual(teams.athlete_id(hit), 3142320)

    def test_totals_row_is_not_a_stint(self):
        payload = {
            "teams": {"las-vegas-aces": {"displayName": "Las Vegas Aces", "abbreviation": "LV", "location": "Las Vegas", "name": "Aces"}},
            "categories": [{"name": "averages", "statistics": [
                {"teamSlug": "las-vegas-aces", "season": {"year": 2022}, "stats": ["36"]},
                {"displayName": "2022  Totals", "teamSlug": "2022 Totals", "season": {"year": 2022}, "stats": ["36"]},
            ]}],
        }
        stints, records = teams.parse_stints(payload, 2)
        self.assertEqual(stints, [{"season": 2022, "season_type": 2, "games_played": 36, "team_slug": "las-vegas-aces"}])
        self.assertIn("las-vegas-aces", records)

    def test_games_played_picks_the_matching_stint(self):
        corrected, counts = teams.correct_rows([
            row(2017, 31),
            row(2025, 43),
            row(2026, 12),
        ], TABLE)
        self.assertEqual(corrected[0]["team"]["full_name"], "San Antonio Stars")
        self.assertEqual(corrected[1]["team"]["full_name"], "Los Angeles Sparks")
        self.assertEqual(corrected[2]["team"]["full_name"], "Los Angeles Sparks")
        self.assertEqual(counts["replaced"], 1)

    def test_combined_games_name_every_club(self):
        corrected, counts = teams.correct_rows([row(2026, 17)], TABLE)
        self.assertEqual(corrected[0]["team"]["full_name"], "Los Angeles Sparks and Phoenix Mercury")
        self.assertIsNone(corrected[0]["team"]["id"])
        self.assertEqual(counts["replaced"], 1)

    def test_unknown_player_is_unchanged(self):
        original = row(2017, 31)
        original["player_id"] = 1
        corrected, counts = teams.correct_rows([original], TABLE)
        self.assertEqual(corrected[0]["team"]["full_name"], "Los Angeles Sparks")
        self.assertEqual(counts["replaced"], 0)

    def test_colliding_correction_is_reverted(self):
        first = row(2017, 31)
        second = row(2017, 31, team=ACES)
        second["pts"] = 11
        corrected, counts = teams.correct_rows([first, second], TABLE)
        self.assertEqual(corrected[0]["team"]["id"], 200)
        self.assertEqual(corrected[1]["team"]["id"], 8)
        self.assertEqual(counts["reverted"], 1)

    def test_historical_name_gets_a_stable_id(self):
        historical = {}
        current, historical = teams.catalog_teams(
            [SPARKS],
            {"san-antonio-stars": {"displayName": "San Antonio Stars", "abbreviation": "SA", "location": "San Antonio", "name": "Stars"}},
            historical,
        )
        self.assertEqual(historical["san-antonio-stars"]["id"], 200)
        self.assertNotIn("san-antonio-stars", current)
        again, historical = teams.catalog_teams(
            [SPARKS],
            {"san-antonio-stars": {"displayName": "San Antonio Stars", "abbreviation": "SA", "location": "San Antonio", "name": "Stars"}},
            historical,
        )
        self.assertEqual(historical["san-antonio-stars"]["id"], 200)
        self.assertEqual(again, {})

    def test_copied_playoff_stints_are_dropped(self):
        stints = [
            {"season": 2010, "season_type": 2, "games_played": 16, "team_slug": "seattle-storm"},
            {"season": 2015, "season_type": 2, "games_played": 26, "team_slug": "seattle-storm"},
            {"season": 2016, "season_type": 2, "games_played": 13, "team_slug": "seattle-storm"},
            {"season": 2010, "season_type": 3, "games_played": 16, "team_slug": "seattle-storm"},
            {"season": 2015, "season_type": 3, "games_played": 26, "team_slug": "seattle-storm"},
            {"season": 2016, "season_type": 3, "games_played": 13, "team_slug": "seattle-storm"},
            {"season": 2018, "season_type": 2, "games_played": 34, "team_slug": "seattle-storm"},
            {"season": 2018, "season_type": 3, "games_played": 5, "team_slug": "seattle-storm"},
        ]
        kept = teams.drop_copied_playoff_stints(stints)
        self.assertEqual(
            [(row["season"], row["season_type"]) for row in kept],
            [(2010, 2), (2015, 2), (2016, 2), (2018, 2), (2018, 3)],
        )
        table = {"players": {"270": {"status": "ok", "stints": stints}}}
        self.assertEqual(
            [row["season_type"] for row in teams.player_stints(table, 270) if row["season"] == 2015],
            [2],
        )

    def test_apply_updates_season_and_profile(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            season = root / "data" / "wnba" / "seasons"
            player = root / "data" / "wnba" / "players"
            season.mkdir(parents=True)
            player.mkdir(parents=True)
            (season / "2017.json").write_text(json.dumps([row(2017, 31)]), encoding="utf-8")
            profile = {"player": {"id": 488}, "season_stats": [row(2017, 31)]}
            (player / "kelsey-plum.json").write_text(json.dumps(profile), encoding="utf-8")
            teams._write(teams.lookup_path(root), TABLE)
            totals = teams.apply_snapshot(root)
            stored = json.loads((player / "kelsey-plum.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["season_stats"][0]["team"]["full_name"], "San Antonio Stars")
            cached = json.loads((season / "2017.json").read_text(encoding="utf-8"))
            self.assertEqual(cached[0]["team"]["full_name"], "San Antonio Stars")
            self.assertEqual(totals["players"], 1)


if __name__ == "__main__":
    unittest.main()
