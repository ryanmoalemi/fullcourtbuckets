"""Bring saved player profiles up to the final playoff boxes on disk.

The game-stats workflow commits new final boxes to data/games between nightly
updater runs. The updater's own sync reconciles profiles, but it runs after the
test step, and the build refuses to publish when a playoff line is behind the
boxes. Running this first keeps a newly recorded game from blocking the whole
updater. It only adds games the line has not counted (idempotent), and it never
touches anything except season_stats and recent_completed_games.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import playoff_boxes  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def reconcile(root: Path = ROOT) -> list[str]:
    games = playoff_boxes.load_games(root)
    changed = []
    if not games:
        return changed
    for path in sorted((Path(root) / "data" / "wnba" / "players").glob("*.json")):
        text = path.read_text(encoding="utf-8")
        try:
            profile = json.loads(text)
        except json.JSONDecodeError:
            continue
        player = profile.get("player") if isinstance(profile.get("player"), dict) else {}
        pid = player.get("id")
        stats = profile.get("season_stats")
        recent = profile.get("recent_completed_games")
        if not isinstance(stats, list) or not isinstance(recent, list):
            continue
        before = json.dumps([stats, recent], sort_keys=True)
        playoff_boxes.reconcile_player(pid, stats, recent, games)
        if json.dumps([stats, recent], sort_keys=True) == before:
            continue
        indent = 2 if text.startswith("{\n") else None
        out = json.dumps(profile, ensure_ascii=False, indent=indent)
        if text.endswith("\n"):
            out += "\n"
        path.write_text(out, encoding="utf-8")
        changed.append(path.name)
    return changed


if __name__ == "__main__":
    names = reconcile()
    print(f"Reconciled playoff lines in {len(names)} profile(s).")
    for name in names:
        print(" ", name)
