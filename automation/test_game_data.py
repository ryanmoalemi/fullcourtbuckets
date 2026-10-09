"""Checks every stored game file in data/games. No network.

A failure here fails the site build, so a game file with wrong quarters
cannot reach an article or a stat board.
"""
import json
from pathlib import Path
import unittest

import game_stats as g

ROOT = Path(__file__).resolve().parents[1]
SKIP = {"index.json", "balldontlie-endpoints.json"}


def game_files():
    folder = ROOT / "data" / "games"
    for path in sorted(folder.glob("*.json")):
        if path.name in SKIP:
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(doc, dict) and "away" in doc and "home" in doc:
            yield path, doc


class GameDataTests(unittest.TestCase):
    def test_there_are_game_files(self):
        self.assertTrue(list(game_files()))

    def test_quarters_add_up_to_the_final(self):
        for path, doc in game_files():
            with self.subTest(game=path.name):
                periods = doc.get("periods") or []
                if doc.get("status") != "final" or not periods:
                    continue
                self.assertTrue(
                    g.periods_sum(periods, doc["away"]["score"], doc["home"]["score"]),
                    f"{path.name}: quarters do not add up to {doc['away']['score']}-{doc['home']['score']}",
                )

    def test_quarters_match_the_play_by_play(self):
        for path, doc in game_files():
            with self.subTest(game=path.name):
                if doc.get("periods_source") != "plays" or not doc.get("plays"):
                    continue
                self.assertEqual(doc.get("periods"), g.periods_from_plays(doc["plays"]), path.name)

    def test_no_score_or_quarter_mismatch_with_espn(self):
        for path, doc in game_files():
            with self.subTest(game=path.name):
                cross = doc.get("crosscheck") or {}
                bad = [
                    row for row in cross.get("mismatches") or []
                    if str(row.get("field", "")).startswith(("period.", "score."))
                ]
                self.assertEqual(bad, [], f"{path.name}: ESPN disagrees on the score or quarters")
                self.assertNotIn("crosscheck_mismatch", doc.get("flags") or [], path.name)

    def test_index_matches_the_files(self):
        index = json.loads((ROOT / "data/games/index.json").read_text(encoding="utf-8"))
        rows = {row["slug"]: row for row in index["games"]}
        for path, doc in game_files():
            with self.subTest(game=path.name):
                row = rows.get(path.stem)
                self.assertIsNotNone(row, path.name)
                cross = doc.get("crosscheck") or {}
                self.assertEqual(row["away_score"], doc["away"]["score"])
                self.assertEqual(row["home_score"], doc["home"]["score"])
                self.assertEqual(row["crosscheck_matched"], bool(cross.get("matched")))
                self.assertEqual(row["mismatch_count"], len(cross.get("mismatches") or []))


if __name__ == "__main__":
    unittest.main()
