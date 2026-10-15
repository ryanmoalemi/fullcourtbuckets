# Updating the 2026 WNBA Finals ratings tracker

The public page is [/news/2026-wnba-finals-ratings-tracker/](/news/2026-wnba-finals-ratings-tracker/). Do not type viewer numbers or the "Last updated" date into the HTML. Change the data file, then regenerate.

## Data file

`data/viewership-attendance.json`

2026 Finals games are objects in `games` whose `game` value is `Finals Game 1` through `Finals Game 4`. Games 5, 6, and 7 stay off this list until the WNBA release gives them a date. The tracker still shows those three rows as "Not listed" for date and tip time, on USA and Peacock.

Fields to edit on a Finals game:

| Field | What it is |
| --- | --- |
| `date` | Game date, `YYYY-MM-DD`. |
| `venue` | Arena name. |
| `network` | Who airs it. Games 2, 3, 5, 6, and 7 are `USA and Peacock`. Game 4 is `NBC and Peacock`. Game 1 is `NBC, Peacock`. |
| `tip_et` | Tip time, Eastern and Pacific. |
| `viewers` | Average viewers as an integer, or `null` until a release exists. |
| `viewers_source` | URL of the network release that printed the average. |
| `viewers_source_date` | Date on that release, `YYYY-MM-DD`. |
| `peak_viewers` | Peak audience as an integer, when the same release prints one. |
| `peak_viewers_source` | URL for the peak. Use the average's release when it is the same document. |
| `peak_viewers_source_date` | Date on that release. |
| `schedule_source` | URL for the date, tip, and venue when no audience is out yet. |
| `schedule_source_date` | Date on the schedule source. |

The game-by-game table on the news page is `FINALS_TRACKER_ROWS` in `automation/citation.py`. After the JSON change, set the matching row's network, overnight rating, average viewers, and peak viewers to the same facts. Dates and tip times for games 5-7 stay `Not listed`.

## Source requirements

- Wait until the network that aired the game releases the number. That is usually within 1 to 2 days of the game.
- Put average viewers, peak audience, and overnight rating on the tracker only when that release includes them.
- The source link has to be the network's own release. Do not fill a cell from a recap, a social post, or another outlet's paraphrase.
- Leave a cell as `Pending tip-off` when the release does not print that figure. Do not estimate it.
- Full Court Buckets gathers and verifies its own data. Name the network release. Do not credit a stats API.

## Last updated

The callout after the quick cite says `Last updated:` plus a date. `citation.finals_tracker_updated()` reads it from this data file:

- If `data/viewership-attendance.json` has uncommitted changes, the date is the file's modification time.
- Otherwise the date is the git commit date of the last commit that changed the file.

Do not hardcode the date in Python or HTML.

## Social card

`automation/build_finals_ratings_tracker.py` draws `images/articles/2026-wnba-finals-ratings-tracker/social-card.webp` at 1200×630. The title is `2026 WNBA Finals Ratings Tracker`. Until a Finals game has a released audience, the headline stat is `51 telecasts topped 1M viewers in 2026 (up from 19)`.

A released audience is an integer `viewers` value on a `Finals Game N` row in the JSON file. The newest `date` wins, and the card headline becomes `Game N averaged X million viewers`. Pending cells stay off the card.

That file is the page's `og:image` and `twitter:image` only. It is not in the article body. The news listing still uses `ratings-sheet.webp`. Nightly hero generation skips this slug so it does not replace the social card with a crop of the pending-counts sheet.

## Page order

Headline, byline, one-line summary, the game-by-game ratings table, the quick-cite box, then the update callout. Game notes and the longer intro stay after the callout. There is no hero in the body.

## Regenerate

From the repo root:

```bash
python automation/build_finals_ratings_tracker.py
python automation/build_viewership_attendance.py
```

The first command rewrites the ratings tracker, its CSV (`news/2026-wnba-finals-ratings-tracker/finals-ratings.csv`), and the listings that point at the story. The second rewrites `/wnba/viewership-attendance/` from the same JSON file.

Check:

```bash
python -m unittest discover -s automation -p 'test_citation.py' -v
python -m unittest discover -s automation -p 'test_viewership_attendance.py' -v
```
