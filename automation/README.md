# Full Court Buckets: chat-managed WNBA website

## Verified operating status

The private BALLDONTLIE Actions secret is connected. The first authenticated import and GitHub Pages deployment succeeded on 2026-09-16 UTC (September 15 Pacific). It returned 562 player records with available season statistics spanning 2008-2026.

The static player-page builder is connected and deployed. The public directory at https://fullcourtbuckets.com/wnba/ and sample profiles /wnba/caitlin-clark/ and /wnba/sue-bird/ were fetched from the live domain and verified after deployment. Snapshot counts can change; inspect data/wnba/status.json and data/wnba/site-build.json for the current status. This does not certify every statistic independently of the provider or guarantee every historical player is covered.

## Safe repository layout

Production: branch `main`, GitHub Pages, fullcourtbuckets.com. Default branch: `master`, containing obsolete unrelated ADU content. Never overwrite main with master, change CNAME, delete unrelated content, or migrate hosting without authorization.

The workflow `.github/workflows/fcb-wnba.yml` exists on both branches. The default-branch scheduled job dispatches main's workflow. If main becomes the default later, its workflow runs directly.

## Daily/weekly automation

GitHub Actions checks the league schedule at approximately 04:17 America/Los_Angeles daily. Statistics and listed team data refresh daily in-season and every seven days after the previous successful refresh in the offseason. A short schedule check still runs daily in the offseason. Season inference uses the current-year schedule with seven days before the first game and 28 days after the last scheduled game; this grace accommodates incomplete playoff scheduling. Missing schedule data conservatively keeps daily refreshes. Scheduling is best effort, not an exact-time SLA.

The importer refreshes current and previous seasons and one rotating historical year. It retries rate limits and temporary server errors. Only validated imports are committed. Missing keys, failed tests, unsafe data, or failed page validation prevent that run's publication. The last deployed site remains available. Review Actions failures; no separate maintenance or alert-delivery service is connected.

After a successful importer step, the builder regenerates pages from the verified local snapshot, even when an API refresh is not yet due. This supports code changes and recovery from failed deployments. Explicit Pages deployment is required because commits made with GITHUB_TOKEN do not trigger normal branch builds.

## Editing through chat

- `automation/wnba_sync.py`: API importer and permanent provider-ID mapping.
- `automation/build_players.py`: shared static page generator and directory.
- `automation/players.css`, `automation/players.js`: shared presentation sources.
- `wnba/{slug}/index.html`: generated output; do not hand-edit.
- `/wnba/`: searchable player directory. Homepage has a Players navigation link.
- `/player-sitemap.xml`: generated profile sitemap, referenced in robots.txt.

Use the GitHub connection in this chat to edit sources on main, inspect Actions runs, and verify deployed output. A commit changing an automation file triggers tests/build/deployment. Unchanged data will keep its original source-check timestamp rather than pretending a new import happened.

## Credentials

`BALLDONTLIE_API_KEY` is already saved as a private repository Actions secret. Do not request it again unless the workflow actually reports a credential problem. Never paste its value in chat, code, issues, public URLs, browser JavaScript, or logs. The Actions runner uses it privately; the chat connector cannot retrieve the secret value.

## Data boundaries

Coverage starts in 2008. Regular season and playoffs are separate. Missing values are not zero. Team stints are not summed with combined rows. Rounded season averages are not used to invent exact career totals or career averages. Source-check timestamps are not guaranteed game-data cutoffs.

Not listed active does not mean retired. A changed team field does not establish a trade, signing, waiver claim, or effective date. Invalid biography fields are hidden instead of guessed; the initial provider response included a college name in a weight field. Recent game logs contain explicitly completed games in a labeled 35-day window, not complete career game histories.

News and confirmed transaction feeds are NOT connected. Player photographs, additional verified biographies, awards, and pre-2008 statistics are not supplied by this implementation. The player header uses jersey-number artwork, not a player photograph.

## Tests and public health

Run `python -m unittest discover -s automation -p 'test_*.py' -v` and `node --check automation/players.js`. There are 26 importer tests and 14 builder tests. The production workflow's test step and 562-page/sitemap validation succeeded. Local Chromium checks covered 360, 390, 768, and 1440 pixel widths with synthetic data, search, active/archive filtering, and season selection.

Data health: `/data/wnba/status.json`. Page-build health: `/data/wnba/site-build.json`. Additional implementation notes: `automation/PLAYER_PAGES.md`.

Provider docs: https://wnba.balldontlie.io/ and https://www.balldontlie.io/openapi/wnba.yml
