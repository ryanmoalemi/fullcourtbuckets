#!/usr/bin/env bash
# Live play-by-play loop. One pass (LOOP=0) or poll every POLL_SECONDS (default 30) until Final
# or stop_after_pt in data/live-pbp.json. Commits only when the play count changes, and pushes at
# most once per MIN_PUSH_SECONDS (default 60) so GitHub Pages builds keep up.
# Guards: build_pbp refuses a 'not started' page once plays exist; pbp_guard.py check runs before every push.
set -u
cfg() { python3 -c "import json;print(json.load(open('data/live-pbp.json'))['$1'])"; }
N=$(cfg game_number); D=$(cfg date); SID=$(cfg site_id); GJ=$(cfg game_json); PD=$(cfg page_dir); STOP=$(cfg stop_after_pt)
TEAMS=$(python3 -c "import json;print(','.join(json.load(open('data/live-pbp.json'))['teams']))")
POLL=${POLL_SECONDS:-30}; MINPUSH=${MIN_PUSH_SECONDS:-60}; PAGE="$PD/play-by-play/index.html"
export LIVE_PBP_PATH_FILE="${RUNNER_TEMP:-/tmp}/live_pbp_path"
DRY=${DRY_RUN:-0}; last_push=0; pending=0
git config user.name 'Full Court Buckets updater'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
now() { TZ=America/Los_Angeles date '+%-I:%M:%S %p PT'; }
push() {
  python automation/pbp_guard.py check "$PAGE" "$GJ" || { echo "$(now) GUARD blocked commit ($1)"; git checkout -q -- data "$PD" 2>/dev/null; return 1; }
  git add -A -- data "$PD"
  git diff --cached --quiet && { echo "$(now) no change"; return 0; }
  git commit -qm "Game $N play-by-play: $1"
  [ "$DRY" = 1 ] && { echo "$(now) DRY RUN: committed locally, not pushed ($1)"; last_push=$(date +%s); return 0; }
  for a in 1 2 3 4 5; do git pull -q --rebase --autostash origin main && git push -q origin HEAD:main && { echo "$(now) pushed $1"; last_push=$(date +%s); return 0; }; git rebase --abort 2>/dev/null; sleep $((a*3)); done
  return 1
}
while :; do
  [ "$DRY" = 1 ] || git pull -q --rebase --autostash origin main 2>/dev/null || git rebase --abort 2>/dev/null
  python -u automation/live_pbp.py; rc=$?
  [ -s "$LIVE_PBP_PATH_FILE" ] && GJ=$(cat "$LIVE_PBP_PATH_FILE")
  if [ $rc -eq 0 ]; then
    if python automation/build_pbp.py --game-id $SID --game-json $GJ --live && python automation/game_stats.py --audit-secrets >/dev/null; then
      pending=1
    else git checkout -q -- data "$PD" 2>/dev/null; fi
  elif [ $rc -eq 10 ]; then
    if GAME_STATS_DATE=$D GAME_STATS_TEAMS=$TEAMS GAME_STATS_ESPN_ID=$SID python -u automation/game_stats.py \
      && python automation/game_stats.py --audit-secrets \
      && FJ=$(python automation/pbp_guard.py resolve $SID) && GJ=$FJ \
      && python automation/build_pbp.py --game-id $SID --game-json "$FJ" \
      && push "final"; then echo FINAL_DONE; exit 0; fi
    echo "$(now) final build failed (score check or guard); will retry"; git checkout -q -- data "$PD" 2>/dev/null
  fi
  if [ $pending = 1 ] && [ $(( $(date +%s) - last_push )) -ge $MINPUSH ]; then push "live update" && pending=0; fi
  [ "${LOOP:-0}" = 1 ] || { [ $pending = 1 ] && push "live update"; exit 0; }
  [ "$(TZ=America/Los_Angeles date +%Y%m%d%H%M)" -ge $STOP ] && { [ $pending = 1 ] && push "live update"; echo 'past stop time, stopping'; exit 0; }
  sleep $POLL
done
