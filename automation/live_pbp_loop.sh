#!/usr/bin/env bash
# One pass (LOOP=0) or loop every ~5 min (LOOP=1) until Final or stop_after_pt in data/live-pbp.json.
set -u
cfg() { python3 -c "import json;print(json.load(open('data/live-pbp.json'))['$1'])"; }
N=$(cfg game_number); D=$(cfg date); SID=$(cfg site_id); GJ=$(cfg game_json); PD=$(cfg page_dir); STOP=$(cfg stop_after_pt)
git config user.name 'Full Court Buckets updater'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
push() {
  git add -A -- data $PD
  git status --short
  git diff --cached --quiet && { echo "$(TZ=America/Los_Angeles date '+%-I:%M:%S %p PT') no change"; return 0; }
  git commit -qm "Game $N play-by-play: $1"
  for a in 1 2 3 4 5; do git pull -q --rebase --autostash origin main && git push -q origin HEAD:main && { echo "$(TZ=America/Los_Angeles date '+%-I:%M:%S %p PT') pushed $1"; return 0; }; git rebase --abort 2>/dev/null; sleep $((a*3)); done
  return 1
}
while :; do
  git pull -q --rebase --autostash origin main 2>/dev/null || git rebase --abort 2>/dev/null
  python -u automation/live_pbp.py; rc=$?
  if [ $rc -eq 0 ]; then
    python automation/build_pbp.py --game-id $SID --game-json $GJ --live \
      && python automation/game_stats.py --audit-secrets >/dev/null && push "live update"
  elif [ $rc -eq 10 ]; then
    GAME_STATS_DATE=$D GAME_STATS_TEAMS=ATL,GS GAME_STATS_ESPN_ID=$SID python -u automation/game_stats.py \
      && python automation/game_stats.py --audit-secrets \
      && python automation/build_pbp.py --game-id $SID --game-json $GJ \
      && push "final" && { echo FINAL_DONE; gh workflow disable fcb-live-pbp.yml --repo "$GITHUB_REPOSITORY" || true; exit 0; }
    echo "final build failed (score check?); will retry"
  fi
  [ "${LOOP:-0}" = 1 ] || exit 0
  [ "$(TZ=America/Los_Angeles date +%Y%m%d%H%M)" -ge $STOP ] && { echo 'past 9 PM PT, stopping'; exit 0; }
  sleep 270
done
