# Full Court Buckets: Chat-managed WNBA data integration

## Current phase

The server-side BALLDONTLIE GOAT importer, offline tests, and daily/weekly scheduling are being installed. A private API key and a successful live run are still required. This phase publishes the shared data feed; it does not yet publish or wire the earlier downloadable player-page template. Do not describe the profile pages, licensed news, confirmed transactions, or complete career totals as connected.

## One-time private credential

In this repository, open Settings > Secrets and variables > Actions > New repository secret.
Name: `BALLDONTLIE_API_KEY`. Value: the API key from the user's BALLDONTLIE dashboard.
Never paste the key into chat, source files, frontend JavaScript, issue comments, logs, or a public URL.
The GitHub integration can read/write repository files but cannot retrieve the private secret's value. The Actions runner consumes it privately.

## Important repository layout

Production website: branch `main`, GitHub Pages, domain fullcourtbuckets.com.
Default branch at installation: `master`, containing obsolete unrelated ADU content.
Do not overwrite main with master, change CNAME, delete the repository, or migrate hosting.
The identical `.github/workflows/fcb-wnba.yml` must exist on both branches. The default-branch scheduled run dispatches execution on main, so Pages deployments originate from the correct source branch. If main becomes the default later, its workflow runs directly.

## Schedule

GitHub Actions checks at about 04:17 America/Los_Angeles, daily. The importer uses current-year league schedule data, not fixed season months. Full refresh is daily during the season and every seven days after the previous successful refresh in the offseason. A short schedule check still runs daily in the offseason. Season inference includes a 28-day playoff scheduling grace period. A missing schedule is treated conservatively as daily, never silently as offseason. Scheduling is best effort, not an exact-time SLA.

The first valid run imports the available 2008-current season statistics with explicit year and competition filters. Later runs refresh current and previous seasons, plus one rotating historical year. Trial rate limits are handled by backing off on 429 responses. No extra paid services are created.

## Public outputs

- `data/wnba/status.json`: actual last successful refresh, scope, health.
- `data/wnba/players-index.json`: stable player IDs and URLs.
- `data/wnba/players/{slug}.json`: profile data, source season averages, separate recent completed games.
- `data/wnba/id-map.json`: permanent provider ID-to-slug mapping.
- `data/wnba/seasons/{year}.json`: source season records.
- `data/wnba/teams.json`: team reference data.

The profile template must consume these JSON files or build static HTML from them. The source can be inspected from this chat using GitHub reads. It must never call BALLDONTLIE directly from the visitor's browser.

## Data rules

Missing values remain null. Regular season and playoffs are separate. Do not turn rounded season averages into exact totals or average them to invent career statistics. Team stints are retained separately; never sum a combined row and its stints. Statistics before 2008 are out of scope. An inactive-feed absence does not prove retirement. A changed team field does not establish the transaction type or effective date. No player images, birthdays, draft details, awards, news, or trade stories are fabricated.

Partial imports and suspicious feed drops stop before git commit/deployment. HTTP failures are retried; credentials are not logged. Last successful output is retained. Recent logs contain only games explicitly marked final and cover a labeled 35-day window, not all historical games. Successful weekly commits provide repository activity; monitor GitHub's public-repository schedule inactivity rules.

## Operating from chat

Use GitHub tools to modify files on main and inspect Actions runs. To trigger a fresh test without the editor, modify an `automation/` file such as `automation/run-request.json`, or run the workflow with `workflow_dispatch`. That write is not a substitute for credential setup.

Before calling the integration live, verify: secret accepted, 2008+ import succeeds, field mappings match actual output, Pages deployment succeeds, public JSON is reachable, and a player-page adapter is connected and tested. Preserve the approved template design and existing site content when doing that next phase.

Tests: `python -m unittest discover -s automation -p 'test_*.py' -v`
Documentation: https://wnba.balldontlie.io/ and https://www.balldontlie.io/openapi/wnba.yml
