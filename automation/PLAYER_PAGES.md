# Full Court Buckets player pages

## Shared data and shared template

The authenticated BALLDONTLIE import completed on 2026-09-16 UTC with 562 player records across 2008-2026. This is a snapshot count, not a promise that the provider covers every player ever.

`wnba_sync.py` imports and validates the data. `build_players.py` converts it into static, crawlable HTML at `/wnba/{permanent-slug}/`. `/wnba/` is the searchable player directory. `automation/players.css` and `automation/players.js` are the shared presentation sources; edits here affect every generated page after the next successful build. Do not manually edit generated HTML.

Each run tests the importer and builder, imports data when due, rebuilds profiles, validates the sitemap, commits changed outputs, and explicitly deploys GitHub Pages. The production branch is `main`; the default branch is currently `master`. Its schedule dispatches main's workflow. Leave unrelated old files and CNAME unchanged.

Full statistics refresh is daily in-season and every seven days in the offseason. The scheduler checks the league schedule daily at approximately 04:17 Pacific, with a 28-day playoff scheduling grace period. A missing schedule conservatively means daily. The wrapper may rebuild/redeploy unchanged valid pages between offseason data refreshes so failed deployments can recover. Scheduled execution is best effort.

## Important data limits

- Source season figures are per-game averages. No invented complete career totals or means of rounded season averages.
- Regular season and playoffs remain separate. Multiple team stints are never summed together with aggregate rows. If a latest-season aggregate is ambiguous, the hero omits its headline numbers and retains the separate table rows.
- Missing statistical values remain missing, not zero.
- Invalid biography fields are omitted. For example, the live provider returned `Iowa` in a weight field while college was null. The builder does not pretend that text is a weight or silently reclassify it as a verified college field.
- Archive means not listed in the active feed, not confirmed retired. Team changes are not classified as trades or signings without a transaction source.
- No automatic news feed is connected. No unlicensed player headshots are published. The number artwork retains the player-template design without pretending to be a photograph.
- Source freshness is labeled as an API snapshot check, not a guaranteed latest-game cutoff. The recent game log has an explicit 35-day window and final-game filtering.

## Tests and verification

Run `python -m unittest discover -s automation -p 'test_*.py' -v` and `node --check automation/players.js`. The 14 builder tests supplement the 26 importer tests. Local Chromium rendering was checked at 360, 390, 768, and 1440 pixels with synthetic data, plus search and season filters. Live output still requires verification after deployment.

Public health: `/data/wnba/status.json` for the data import; `/data/wnba/site-build.json` for generated profiles. The player sitemap is `/player-sitemap.xml` and is referenced by robots.txt. Homepage changes are limited to adding a Players navigation link.

API keys stay in `BALLDONTLIE_API_KEY`, a private GitHub Actions secret. They are not requested in chat, embedded in browser JavaScript, stored in generated files, or exposed in logs.

Use the GitHub connection in this chat to edit sources, inspect runs, and troubleshoot. Successful credential integration is not a promise of permanently maintenance-free third-party APIs.
