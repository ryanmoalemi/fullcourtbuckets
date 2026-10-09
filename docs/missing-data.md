# Missing data

Approved questions that were skipped, or answered only as far as the files go.
Nothing here was guessed from memory.

## A'ja Wilson

- Career points total: `career_totals_complete` is false and the season rows are per-game averages. Averages were not turned into a career total.
- Is A'ja Wilson injured?: the Plum and Clark pages ask an injury question, but those items have empty `sources` and the player file has no injury status. The question was not copied.

## Kelsey Plum

- Championships: her player file has no championship field, and the FAQ file has no official citation for a title count. The question was skipped.
- Last game points: the newest completed game (2026-09-25T02:00:00.000Z) does not have a points total. The A'ja Wilson and Caitlin Clark last-game answers are used only when the game table has points. This one was skipped.

## Caitlin Clark

- Card content: the only card collection on file is `data/reese-cards.json` (Ryan's Angel Reese cards). No Caitlin Clark card page or card count is stored, so no card link was added.

## Team pages

- Head coach and owner: `data/wnba/teams.json` has no coach or owner fields, and no official source file is in the repo. Those fields were not added. Most minutes is a separate line, taken from 2026 regular-season minutes on the roster.

## Standings

- Standings refresh time: the approved line "standings refresh daily at 6:45 AM PT" was not published. .github/workflows/fcb-wnba.yml rebuilds standings at 4:17 AM PT (cron 17 4 * * * America/Los_Angeles). The 6:45 AM PT job is the FAQ consistency check, and it does not rebuild standings.
