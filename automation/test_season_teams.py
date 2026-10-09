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

    def test_average_line_keeps_per_game_stats(self):
        payload = {
            "teams": {"seattle-storm": {"displayName": "Seattle Storm", "abbreviation": "SEA", "location": "Seattle", "name": "Storm"}},
            "categories": [{
                "name": "averages",
                "names": ["gamesPlayed", "avgMinutes", "avgPoints", "avgRebounds", "avgAssists", "avgFieldGoalsMade-avgFieldGoalsAttempted", "fieldGoalPct"],
                "statistics": [{
                    "teamSlug": "seattle-storm",
                    "season": {"year": 2010},
                    "stats": ["16", "6.8", "2.8", "1.3", "0.3", "1.0-2.8", "35.6"],
                }],
            }],
        }
        stints, _records = teams.parse_stints(payload, 2)
        self.assertEqual(stints[0]["games_played"], 16)
        self.assertEqual(stints[0]["pts"], 2.8)
        self.assertEqual(stints[0]["fgm"], 1)
        self.assertEqual(stints[0]["fga"], 2.8)
        self.assertEqual(stints[0]["fg_pct"], 35.6)

    def test_missing_regular_season_is_added_and_a_missed_playoff_is_not(self):
        storm = {"id": 9, "full_name": "Seattle Storm", "abbreviation": "SEA", "city": "Seattle", "name": "Storm", "conference": "Western Conference"}
        table = {
            "current_teams": {"seattle-storm": storm},
            "historical_teams": {},
            "playoff_teams": {"2010": ["seattle-storm"], "2016": ["seattle-storm"]},
            "players": {"270": {"status": "ok", "stints": [
                {"season": 2010, "season_type": 2, "games_played": 16, "team_slug": "seattle-storm", "pts": 2.8, "reb": 1.3, "ast": 0.3},
                {"season": 2015, "season_type": 2, "games_played": 26, "team_slug": "seattle-storm", "pts": 5.2},
                {"season": 2016, "season_type": 2, "games_played": 13, "team_slug": "seattle-storm", "pts": 4.1},
                {"season": 2010, "season_type": 3, "games_played": 4, "team_slug": "seattle-storm", "pts": 6},
                {"season": 2015, "season_type": 3, "games_played": 3, "team_slug": "seattle-storm", "pts": 5},
                {"season": 2016, "season_type": 3, "games_played": 2, "team_slug": "seattle-storm", "pts": 3},
            ]}},
        }
        existing = [{"player_id": 270, "season": 2015, "season_type": 2, "team": dict(storm), "games_played": 26, "pts": 5.19}]
        updated, report = teams.supplement_rows(existing, table, season_year=2015)
        self.assertEqual(updated, existing)
        self.assertEqual(report["filled"], [])
        updated, report = teams.supplement_rows([], table, season_year=2010)
        kinds = sorted((row["season"], row["season_type"], row["games_played"]) for row in updated)
        self.assertEqual(kinds, [(2010, 2, 16), (2010, 3, 4)])
        self.assertEqual(updated[0]["team"]["full_name"], "Seattle Storm")
        self.assertEqual(updated[0]["pts"], 2.8)
        updated, report = teams.supplement_rows([], table, season_year=2016)
        self.assertIn((2016, 3, 2), {(row["season"], row["season_type"], row["games_played"]) for row in updated})

    def test_confirmed_disagreement_uses_the_cross_check_line(self):
        storm = {"id": 9, "full_name": "Seattle Storm", "abbreviation": "SEA", "city": "Seattle", "name": "Storm", "conference": None}
        table = {
            "current_teams": {"seattle-storm": storm},
            "players": {"9": {
                "status": "ok",
                "confirmed_seasons": [2026],
                "stints": [
                    {"season": 2026, "season_type": 2, "games_played": 30, "team_slug": "seattle-storm", "pts": 10},
                ],
            }},
        }
        existing = [{"player_id": 9, "season": 2026, "season_type": 2, "team": dict(storm), "games_played": 20, "pts": 11}]
        updated, report = teams.supplement_rows(existing, table, season_year=2026)
        self.assertEqual(updated[0]["games_played"], 30)
        self.assertEqual(updated[0]["pts"], 10)
        self.assertTrue(updated[0]["gap_fill"])
        self.assertEqual(report["unresolved"], [])
        self.assertEqual(len(report["replaced"]), 1)

    def test_unresolved_mark_uses_the_cross_check_line(self):
        storm = {"id": 9, "full_name": "Seattle Storm", "abbreviation": "SEA", "city": "Seattle", "name": "Storm", "conference": None}
        table = {
            "current_teams": {"seattle-storm": storm},
            "players": {"9": {
                "status": "ok",
                "unresolved_seasons": [{"season": 2026, "feed_games": 10, "cross_check_games": 13, "game_log_games": 14}],
                "stints": [
                    {"season": 2026, "season_type": 2, "games_played": 13, "team_slug": "seattle-storm", "pts": 12.2},
                ],
            }},
        }
        existing = [{"player_id": 9, "season": 2026, "season_type": 2, "team": dict(storm), "games_played": 10, "pts": 14.4}]
        updated, report = teams.supplement_rows(existing, table, season_year=2026)
        self.assertEqual([row["games_played"] for row in updated], [13])
        self.assertEqual(report["unresolved"], [])

    def test_repeated_prior_season_with_no_cross_check_is_dropped(self):
        storm = {"id": 9, "full_name": "Seattle Storm", "abbreviation": "SEA", "city": "Seattle", "name": "Storm", "conference": None}
        table = {"current_teams": {"seattle-storm": storm}, "players": {"9": {"status": "ok", "stints": []}}}
        prior = [{"player_id": 9, "season": 2025, "season_type": 2, "team": dict(storm), "games_played": 38, "pts": 8.87, "reb": 1.97, "ast": 3.08, "min": 22.82}]
        existing = [{"player_id": 9, "season": 2026, "season_type": 2, "team": dict(storm), "games_played": 38, "pts": 8.87, "reb": 1.97, "ast": 3.08, "min": 22.82}]
        updated, report = teams.supplement_rows(existing, table, season_year=2026, prior_rows=prior)
        self.assertEqual(updated, [])
        self.assertEqual(len(report["dropped"]), 1)

    def test_confirmed_year_replaces_a_playoff_row_and_keeps_the_matching_regular_row(self):
        aces = {"id": 8, "full_name": "Las Vegas Aces", "abbreviation": "LV", "city": "Las Vegas", "name": "Aces", "conference": None}
        table = {
            "current_teams": {"las-vegas-aces": aces},
            "playoff_teams": {"2026": ["las-vegas-aces"]},
            "players": {"1": {
                "status": "ok",
                "confirmed_seasons": [2026],
                "stints": [
                    {"season": 2026, "season_type": 2, "games_played": 41, "team_slug": "las-vegas-aces", "pts": 26.17},
                    {"season": 2026, "season_type": 3, "games_played": 5, "team_slug": "las-vegas-aces", "pts": 28.8},
                ],
            }},
        }
        existing = [
            {"player_id": 1, "season": 2026, "season_type": 2, "team": dict(aces), "games_played": 41, "pts": 26.17},
            {"player_id": 1, "season": 2026, "season_type": 3, "team": dict(aces), "games_played": 4, "pts": 20},
        ]
        updated, report = teams.supplement_rows(existing, table, season_year=2026)
        regular = [row for row in updated if row["season_type"] == 2][0]
        playoff = [row for row in updated if row["season_type"] == 3][0]
        self.assertEqual(regular["pts"], 26.17)
        self.assertNotIn("gap_fill", regular)
        self.assertEqual(playoff["games_played"], 5)
        self.assertTrue(playoff["gap_fill"])
        self.assertEqual(report["unresolved"], [])

    def test_game_disagreement_is_not_overwritten(self):
        storm = {"id": 9, "full_name": "Seattle Storm", "abbreviation": "SEA", "city": "Seattle", "name": "Storm", "conference": None}
        table = {
            "current_teams": {"seattle-storm": storm},
            "players": {"9": {"status": "ok", "stints": [
                {"season": 2026, "season_type": 2, "games_played": 30, "team_slug": "seattle-storm", "pts": 10},
            ]}},
        }
        existing = [{"player_id": 9, "season": 2026, "season_type": 2, "team": dict(storm), "games_played": 20, "pts": 11}]
        updated, report = teams.supplement_rows(existing, table, season_year=2026)
        self.assertEqual(updated[0]["games_played"], 20)
        self.assertEqual(updated[0]["pts"], 11)
        self.assertEqual(report["unresolved"][0]["api_games"], 20)
        self.assertEqual(report["unresolved"][0]["cross_check_games"], 30)

    def test_a_missing_stint_is_added_when_the_other_matches(self):
        sparks = {"id": 12, "full_name": "Los Angeles Sparks", "abbreviation": "LA", "city": "Los Angeles", "name": "Sparks", "conference": None}
        aces = {"id": 8, "full_name": "Las Vegas Aces", "abbreviation": "LV", "city": "Las Vegas", "name": "Aces", "conference": None}
        table = {
            "current_teams": {"los-angeles-sparks": sparks, "las-vegas-aces": aces},
            "players": {"4": {"status": "ok", "stints": [
                {"season": 2024, "season_type": 2, "games_played": 10, "team_slug": "los-angeles-sparks", "pts": 8},
                {"season": 2024, "season_type": 2, "games_played": 12, "team_slug": "las-vegas-aces", "pts": 9},
            ]}},
        }
        existing = [{"player_id": 4, "season": 2024, "season_type": 2, "team": dict(sparks), "games_played": 10, "pts": 8}]
        updated, report = teams.supplement_rows(existing, table, season_year=2024)
        self.assertEqual(len(updated), 2)
        self.assertEqual(report["unresolved"], [])
        added = [row for row in updated if row["games_played"] == 12][0]
        self.assertEqual(added["team"]["full_name"], "Las Vegas Aces")

    def test_playoff_field_uses_conference_seeds_then_clincher(self):
        def entry(name, seed, clincher):
            return {"team": {"displayName": name}, "stats": [
                {"name": "playoffSeed", "value": seed},
                {"name": "clincher", "value": clincher},
            ]}
        early = {"children": [{"standings": {"entries": [
            entry("Seattle Storm", 1, None),
            entry("Minnesota Lynx", 5, 1),
        ]}}]}
        self.assertEqual(teams.playoff_teams_for_year(early, 2010), ["seattle-storm"])
        later = {"children": [{"standings": {"entries": [
            entry("Golden State Valkyries", 5, 1),
            entry("Washington Mystics", 4, 4),
        ]}}]}
        self.assertEqual(teams.playoff_teams_for_year(later, 2025), ["golden-state-valkyries"])

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
