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

The shared sheet is `FINALS_TRACKER_ROWS` in `automation/citation.py`. The news page shows a compact four-game table derived from those rows. After the JSON change, set the matching row's network, overnight rating, average viewers, and peak viewers to the same facts. Dates and tip times for games 5-7 stay `Not listed` on the shared sheet. The news page folds those three games into the footnote.

## Source requirements

- Wait until the network that aired the game releases the number. That is usually within 1 to 2 days of the game.
- Put average viewers, peak audience, and overnight rating on the tracker only when that release includes them.
- The source link has to be the network's own release. Do not fill a cell from a recap, a social post, or another outlet's paraphrase.
- Leave a cell as `Pending tip-off` when the release does not print that figure. Do not estimate it.
- Full Court Buckets gathers and verifies its own data. Name the network release. Do not credit a stats API.

## Last updated

The callout in the sources section says `Last updated:` plus a date. `citation.finals_tracker_updated()` reads it from this data file and converts the instant to America/Los_Angeles:

- If `data/viewership-attendance.json` has uncommitted changes, the date is the file's modification time in Pacific Time.
- Otherwise the date is the git commit instant of the last commit that changed the file, also in Pacific Time.

A change just after midnight UTC still shows the previous Pacific calendar day. Do not hardcode the date in Python or HTML. Date-only article publish dates are already calendar days and are not shifted.

## Card and social image

The homepage card and the og/twitter image are one photo: Angel Reese of the Atlanta Dream, May 27, 2026. Photo: John Mac, CC BY-SA 4.0, via Wikimedia Commons (`File:Angel_Reese_Dream_2.jpg`).

`automation/build_finals_ratings_tracker.py` writes `matchup-1200.webp` at 1200×675 for the card and `matchup-og.webp` at 1200×630 for og:image and twitter:image. The crop centers her face. There is no text or gradient on the photo. The photo is not in the article body. The credit sits with the sources. Nightly hero generation skips this slug so it does not recrop the face.

## Page order

For a journalist, top to bottom:

1. Headline and byline.
2. One-line stat. With no released Finals audience it reads `Game 1 Sat Oct 17, 12:30 PM PT on NBC/Peacock; ratings pending` plus the 2025 Finals average. After a release it names that game's audience and keeps the 2025 benchmark.
3. Compact ratings table. Dates are `Sat 10/17`. Matchups are `ATL @ GSV`. Networks are `NBC/Peacock`. Tip times are `3:30 / 12:30 PM`, or `1:00 PM / 10:00 AM` when the meridians differ. Empty audience cells say `Pending`. Games 5-7 are one footnote line, with the venues and the Oct. 13 source note.
4. Cite this, Download CSV, and Embed. Those last two jump to the sections further down.
5. Past Finals averages: 2022 534K, 2023 728K, 2024 1.6M, 2025 1.5M.
6. Fast facts.
7. Benchmarks, search interest, and the full Finals history table.
8. Network note, photo credit, embed code, CSV, and the update callout.

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
