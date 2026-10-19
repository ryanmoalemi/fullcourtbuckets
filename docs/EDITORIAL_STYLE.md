# Full Court Buckets editorial style (from Ryan's Oct 9, 2026 edits)

Use this for every new preview, recap, feature and guide. It applies to the WNBA bot's drafts too.

## Rule #1: be the primary source (Ryan, Oct 19, 2026)
- Tier 1 reporters (NYT, ESPN, The Athletic, WSJ) must link the primary source of a fact, never an aggregator. So unless FCB is the primary source, they won't link to us.
- Every FCB piece needs something original that exists nowhere else: our own dataset, count, ledger, tracker, primary-document research or cross-dataset analysis. A page that only summarizes other sites doesn't meet the bar.
- Every fact we cite links its own primary source: the official league or team release, the official game record, a court, arbitration or SEC filing, a Secretary of State or trademark record, a municipal document, or an archive.org snapshot of one. Don't link an aggregator or a story that just repeats the fact.
- Cite CNBC, Sportico, Forbes and similar outlets only for their own proprietary work (valuations, net worths, original reporting). When no primary source exists, say so and cite the best contemporaneous report, labeled as a report.
- Data pages carry a Source column per row, a data dictionary, a downloadable file and a corrections address.
- This doesn't change the stats rule: never credit ESPN or the stats API; FCB gathers and verifies its own data.

## Headlines and openings
- Write headlines in sentence case. Lead with the result or the player plus the number ("Burton's late three and Stokes' block lift Valkyries over Aces 83-81"). Don't use all-caps score summaries or clickbait questions.
- Use the same headline in the H1, the news card, og/twitter titles and the JSON-LD headline. A title tag can be shortened, but its meaning can't change.
- The opening paragraph states what happened, meaning the score, the deciding play and the key number, in the first two sentences. Don't describe the page ("This article looks at...") and don't use teaser endings. Under Ryan's hook rule, include one surprising verified fact and one reason to keep reading. The reason has to be real, not manufactured suspense.

## Voice
- Direct and specific. Cut stock suspense and filler: "Here's the wild part", "The wild part?", "Like, really cold", "Game over.", "That shot felt like the moment X knew", "The fourth quarter was nuts". Replace each with the fact it hints at (time, score, run).
- No made-up crowd reactions, anonymous consensus, or claims about a player's motivation, anger, toughness or intent unless a source quotes it.
- Make an argument once. Don't restate the same comeback or trend in three ways.
- End without a generic question that repeats the headline. Invite comments only when there's a real, open basketball question.

## Claims and evidence
- Claim only what the cited evidence shows. Two games or a small sample can't predict a series or prove a trend, so say so in one plain line where it matters (plus-minus over two games, per-36 rates on few minutes, a four-game scoring streak).
- Use the right stat for the claim. Overall FG% isn't half-court efficiency, and a game spread isn't a series price.
- When a stat depends on a convention (team rebounds, team turnovers, rounding), add one line saying which convention is used. Don't change the image to match.
- Card and sales pieces: write "sale selected for this guide", never "highest/top verified sale" or "record", unless a documented search across marketplaces backs it up. One 1/1 sale says nothing about another player's value. Explain what each comparison can and can't tell a collector (set, parallel, serial number, grade, date).
- Award and roster facts link to the league or federation release. Historical claims ("no team has ever...") need a source the reader can open.
- Picks are opinions. Write them as "My pick is X" with one concrete reason, and keep them tied to the publish date once the game has been played.

## Recaps and player features
- The team recap covers the game. A player feature on the same game must have a different purpose (her full sequence, her trend) and shouldn't re-recite the box score.
- Use full stat lines only where they add something. Pick the 3-5 numbers that explain the result.
- Name late-game sequences precisely: clock, score, who did what.

## Sources and attribution (Ryan, Oct 9)
- Never credit ESPN (or any provider) as the stats source. FCB pays for its own data, so pages say FCB gathers and verifies its own data. ESPN box-score links already in older articles can stay. Don't add new "per ESPN box score" credits for stats.
- Injury, odds and news facts from other outlets keep their outlet credit and a timestamp (e.g. "ESPN injury report, 3:21 PM PT"). This is reporting attribution, not a stats-source credit.
- Don't claim on-site observation or interviews unless they happened.
- Keep the Ryan Moalemi byline linked to his author page and the existing short AI disclosure.

## Updates, dates and archives
- Never change the original publish date to look fresh. For a material correction, add the real update time and a one-line correction note saying what changed.
- After a game is played, add an archive note to its preview right below the byline: "This preview was published before the game. For the result, read our game recap." Link to the matching recap.
- Refresh injuries and odds only with a new timestamp.

## Betting content
- Keep it plain and educational: lines with source and time, "lines may move", no affiliate codes, rel=nofollow links, and the 21+ / Gamble responsibly / 1-800-GAMBLER line.

## In-body photos (Ryan, Oct 13)
- A photo in the body of a `/news/` article is 16:9, the same shape as the hero. The shared rule is on `figure.body-photo`: `aspect-ratio: 16/9` and `object-fit: cover`, full column width. That is what cuts the scroll on a phone. The class is added by `apply_body_photos` in `order_news_lead`.
- Set `object-position` on that image so the crop keeps every head fully in frame. The default is `center 20%`. Move it, for example to `center 0%`, when the head sits higher. Look at the crop before publishing. If a head is cut off, change the focal point. Do not publish a crop that slices a head.
- A screenshot or a chart can stay taller when the reader needs the detail. Mark the figure `no-crop` (a `screenshot`, `chart`, or `stat-board` figure is treated as `no-crop`). Do not crop those. They use `object-fit: contain`. On screens up to 900px wide the cap is `max-height: 70vh`. On wider screens the cap is `max-height: 720px`. If the image is still too tall to read inside that cap, export a shorter file. Do not hide labels or a face by cropping.
- This rule does not change the hero, the news-listing cards, or player pages. A card photo in a list article keeps the `card` class and stays whole, at the existing narrow width, because cropping the card hides the card.

## Data pages, charts and tools (Ryan, Oct 19, 2026)
- Data pages, charts and tools follow normal academic data-publication norms.
- Material that supports the data may sit above or near the table: methods, sources, the data-through date, definitions, and one key-fact line.
- News, game schedules, storylines and bullet lists never sit above a data table, chart or tool. They go below it.
- Mark the element that holds the table, chart or tool with `data-fcb-data-table`. `automation/test_data_table_first.py` fails the build if a list, chart, image, news answer block or more than 700 characters of text sits between the byline and that element.
