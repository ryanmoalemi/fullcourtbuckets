#!/usr/bin/env bash
# One pass (LOOP=0) or loop every ~5 min (LOOP=1) until Final or 9:00 PM PT Oct 19, 2026.
set -u
git config user.name 'Full Court Buckets updater'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
push() {
  git add -A -- data wnba/finals/2026/game-2
  git status --short
  git diff --cached --quiet && { echo "$(TZ=America/Los_Angeles date '+%-I:%M:%S %p PT') no change"; return 0; }
  git commit -qm "Game 2 play-by-play: $1"
  for a in 1 2 3 4 5; do git pull -q --rebase --autostash origin main && git push -q origin HEAD:main && { echo "$(TZ=America/Los_Angeles date '+%-I:%M:%S %p PT') pushed $1"; return 0; }; git rebase --abort 2>/dev/null; sleep $((a*3)); done
  return 1
}
while :; do
  git pull -q --rebase --autostash origin main 2>/dev/null || git rebase --abort 2>/dev/null
  python -u automation/live_pbp.py; rc=$?
  if [ $rc -eq 0 ]; then
    python automation/build_pbp.py --game-id 401918306 --game-json data/games/2026-10-19-atl-gs.json --live \
      && python automation/game_stats.py --audit-secrets >/dev/null && push "live update"
  elif [ $rc -eq 10 ]; then
    GAME_STATS_DATE=2026-10-19 GAME_STATS_TEAMS=ATL,GS GAME_STATS_ESPN_ID=401918306 python -u automation/game_stats.py \
      && python automation/game_stats.py --audit-secrets \
      && python automation/build_pbp.py --game-id 401918306 --game-json data/games/2026-10-19-atl-gs.json \
      && push "final" && { echo FINAL_DONE; gh workflow disable fcb-live-pbp.yml --repo "$GITHUB_REPOSITORY" || true; exit 0; }
    echo "final build failed (score check?); will retry"
  fi
  [ "${LOOP:-0}" = 1 ] || exit 0
  [ "$(TZ=America/Los_Angeles date +%Y%m%d%H%M)" -ge 202610192100 ] && { echo 'past 9 PM PT, stopping'; exit 0; }
  sleep 270
done
