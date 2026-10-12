"""Playoff lines have to include every completed box, except games the player did not play."""
import json
from pathlib import Path
import tempfile
import unittest

import per_game
import playoff_boxes as boxes


def team(abbr, name, ident):
    return {"id": ident, "abbreviation": abbr, "full_name": name, "name": name.split()[-1], "city": name.split()[0], "conference": "Eastern Conference"}


EX = team("EX", "Example Club", 1)
OT = team("OT", "Other Club", 2)


def player_line(name, ident, abbr, points, minutes="20", dnp=False):
    return {
        "player_id": ident,
        "name": name,
        "team": abbr,
        "did_not_play": dnp,
        "minutes": "0" if dnp else minutes,
        "pts": 0 if dnp else points,
        "reb": 0 if dnp else 4,
        "oreb": 0 if dnp else 1,
        "dreb": 0 if dnp else 3,
        "ast": 0 if dnp else 2,
        "stl": 0 if dnp else 1,
        "blk": 0,
        "turnovers": 0 if dnp else 1,
        "fouls": 0,
        "fgm": 0 if dnp else 3,
        "fga": 0 if dnp else 8,
        "fg3m": 0,
        "fg3a": 0 if dnp else 2,
        "ftm": 0 if dnp else 1,
        "fta": 0 if dnp else 2,
        "plus_minus": 0,
    }


def game(day, ident, home, away, players, overtime=False):
    return {
        "date": day,
        "status": "final",
        "season": 2026,
        "postseason": True,
        "balldontlie_game_id": ident,
        "away": {**away, "score": 80},
        "home": {**home, "score": 90},
        "players": players,
        "overtime": overtime,
    }


def season_row(games_played, points):
    return {
        "player_id": 7,
        "season": 2026,
        "season_type": 3,
        "team": dict(EX),
        "games_played": games_played,
        "min": 20.0,
        "fgm": 3.0,
        "fga": 8.0,
        "fg_pct": 37.5,
        "fg3m": 0.0,
        "fg3a": 2.0,
        "fg3_pct": 0.0,
        "ftm": 1.0,
        "fta": 2.0,
        "ft_pct": 50.0,
        "oreb": 1.0,
        "dreb": 3.0,
        "reb": 4.0,
        "ast": 2.0,
        "stl": 1.0,
        "blk": 0.0,
        "turnover": 1.0,
        "pts": points,
    }


def null_log(day, ident):
    row = logged(day, ident, 0)
    row["pts"] = None
    row["minutes"] = "0"
    row["reb"] = None
    row["ast"] = None
    row["stl"] = None
    row["blk"] = None
    row["turnover"] = None
    return row


def logged(day, ident, points):
    stamp = f"{day}T19:00:00.000Z"
    return {
        "game_id": ident,
        "player_id": 7,
        "date": stamp,
        "season": 2026,
        "postseason": True,
        "team": dict(EX),
        "home_team": dict(EX),
        "visitor_team": dict(OT),
        "home_score": 90,
        "away_score": 80,
        "minutes": "20",
        "pts": float(points),
        "reb": 4.0,
        "ast": 2.0,
        "stl": 1.0,
        "blk": 0.0,
        "turnover": 1.0,
    }


class PlayoffBoxTests(unittest.TestCase):
    def test_missing_final_is_added_and_the_average_rounds_half_up(self):
        # 120 points in five games, then a 16-point game. 136 / 6 is 22.7.
        stats = [season_row(5, 24.0)]
        recent = [logged("2026-10-0%d" % number, 100 + number, 24) for number in range(1, 6)]
        # The stored log dates are only a stand-in. The sixth game is the box.
        final = game(
            "2026-10-09",
            106,
            EX,
            OT,
            [player_line("Example Player", 7, "EX", 16, minutes="29"), player_line("Bench Player", 8, "EX", 0, dnp=True)],
        )
        created = boxes.reconcile_player(7, stats, recent, [final])
        self.assertEqual(created, [])
        self.assertEqual(stats[0]["games_played"], 6)
        self.assertEqual(per_game.counting_total(stats[0]["pts"], 6), 136)
        self.assertEqual(per_game.shown_average(stats[0]["pts"], 6), "22.7")
        self.assertEqual(per_game.counting_total(stats[0]["min"], 6), 129)
        self.assertEqual(len(recent), 6)
        again = [dict(row) for row in stats]
        recent_again = [dict(game_row) for game_row in recent]
        boxes.reconcile_player(7, stats, recent, [final])
        self.assertEqual(stats[0]["games_played"], again[0]["games_played"])
        self.assertEqual(stats[0]["pts"], again[0]["pts"])
        self.assertEqual(len(recent), len(recent_again))

    def test_a_dnp_does_not_add_a_game_and_the_check_allows_it(self):
        stats = [season_row(1, 10.0)]
        recent = [logged("2026-10-01", 201, 10)]
        played = game("2026-10-01", 201, EX, OT, [player_line("Example Player", 7, "EX", 10)])
        missed = game("2026-10-09", 202, EX, OT, [player_line("Example Player", 7, "EX", 0, dnp=True)])
        boxes.reconcile_player(7, stats, recent, [played, missed])
        self.assertEqual(stats[0]["games_played"], 1)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(root, stats, recent, [played, missed])
            self.assertEqual(boxes.count_problems(root), [])

    def test_check_fails_until_the_played_game_is_on_the_line(self):
        stats = [season_row(1, 10.0)]
        recent = [logged("2026-10-01", 301, 10)]
        played = game("2026-10-01", 301, EX, OT, [player_line("Example Player", 7, "EX", 10)])
        extra = game("2026-10-09", 302, OT, EX, [player_line("Example Player", 7, "EX", 16, minutes="29:30")])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write(root, stats, recent, [played, extra])
            problems = boxes.count_problems(root)
            self.assertEqual(len(problems), 1)
            self.assertIn("1 games", problems[0])
            self.assertIn("2 played", problems[0])
            self.assertIn("0 DNP", problems[0])
            loaded = boxes.load_games(root)
            boxes.reconcile_player(7, stats, recent, loaded)
            self.assertEqual(stats[0]["games_played"], 2)
            self.assertEqual(per_game.counting_total(stats[0]["min"], 2), 50)
            self._write(root, stats, recent, [played, extra])
            self.assertEqual(boxes.count_problems(root), [])

    def test_null_log_rows_do_not_dilute_a_later_played_game(self):
        # Three scoring games (2, 9, 2) and two placeholders with no points.
        # A later game with zero points is played. It must not turn the line into six games.
        stats = [season_row(3, 4.33)]
        recent = [
            logged("2026-09-27", 601, 2),
            null_log("2026-09-30", 602),
            null_log("2026-10-02", 604),
            logged("2026-10-04", 603, 9),
            logged("2026-10-07", 605, 2),
        ]
        final = game("2026-10-09", 606, EX, OT, [player_line("Example Player", 7, "EX", 0, minutes="12")])
        boxes.reconcile_player(7, stats, recent, [final])
        self.assertEqual(stats[0]["games_played"], 4)
        self.assertEqual(per_game.counting_total(stats[0]["pts"], 4), 13)
        self.assertEqual(len(recent), 6)
        again = stats[0]["games_played"]
        boxes.reconcile_player(7, stats, recent, [final])
        self.assertEqual(stats[0]["games_played"], again)
        self.assertEqual(len(recent), 6)

    def test_a_dnp_already_in_the_log_does_not_change_a_matching_line(self):
        stats = [season_row(3, 17.0)]
        recent = [
            logged("2026-09-27", 501, 17),
            logged("2026-09-30", 502, 17),
            logged("2026-10-04", 503, 17),
            null_log("2026-10-07", 504),
        ]
        played = [
            game(day, ident, EX, OT, [player_line("Example Player", 7, "EX", 17)])
            for day, ident in (("2026-09-27", 501), ("2026-09-30", 502), ("2026-10-04", 503))
        ]
        missed = [
            game("2026-10-07", 504, EX, OT, [player_line("Example Player", 7, "EX", 0, dnp=True)]),
            game("2026-10-09", 505, EX, OT, [player_line("Example Player", 7, "EX", 0, dnp=True)]),
        ]
        boxes.reconcile_player(7, stats, recent, played + missed)
        self.assertEqual(stats[0]["games_played"], 3)
        self.assertEqual(stats[0]["pts"], 17.0)
        self.assertEqual(len(recent), 4)

    def test_a_null_log_row_is_not_a_game_the_line_already_has(self):
        # One scored game on the line, one empty log row, and a later 8-point game.
        stats = [season_row(1, 5.0)]
        recent = [null_log("2026-09-29", 701), logged("2026-10-07", 702, 5)]
        extra = game("2026-10-09", 703, EX, OT, [player_line("Example Player", 7, "EX", 8)])
        boxes.reconcile_player(7, stats, recent, [extra])
        self.assertEqual(stats[0]["games_played"], 2)
        self.assertEqual(per_game.counting_total(stats[0]["pts"], 2), 13)
        boxes.reconcile_player(7, stats, recent, [extra])
        self.assertEqual(stats[0]["games_played"], 2)

    def test_a_line_ahead_of_its_log_is_not_counted_twice(self):
        stats = [season_row(2, 13.0)]
        recent = [logged("2026-10-01", 401, 10)]
        first = game("2026-10-01", 401, EX, OT, [player_line("Example Player", 7, "EX", 10)])
        second = game("2026-10-09", 402, EX, OT, [player_line("Example Player", 7, "EX", 16)])
        boxes.reconcile_player(7, stats, recent, [first, second])
        self.assertEqual(stats[0]["games_played"], 2)
        self.assertEqual(len(recent), 2)
        self.assertEqual(per_game.counting_total(stats[0]["pts"], 2), 26)

    def _write(self, root: Path, stats, recent, games):
        player_dir = root / "data" / "wnba" / "players"
        player_dir.mkdir(parents=True, exist_ok=True)
        profile = {
            "player": {"id": 7, "first_name": "Example", "last_name": "Player"},
            "slug": "example-player",
            "season_stats": stats,
            "recent_completed_games": recent,
        }
        (player_dir / "example-player.json").write_text(json.dumps(profile), encoding="utf-8")
        game_dir = root / "data" / "games"
        game_dir.mkdir(parents=True, exist_ok=True)
        for document in games:
            name = f"{document['date']}-{document['balldontlie_game_id']}.json"
            (game_dir / name).write_text(json.dumps(document), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
