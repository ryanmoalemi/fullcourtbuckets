# Full Court Buckets editorial style (from Ryan's Oct 9, 2026 edits)

Use this for every new preview, recap, feature and guide. It applies to the WNBA bot's drafts too.

## Rule #1: be the primary source (Ryan, Oct 19, 2026)
- Tier 1 reporters (NYT, ESPN, The Athletic, WSJ) must link the primary source of a fact, never an aggregator. So unless FCB is the primary source, they won't link to us.
- Every FCB piece needs something original that exists nowhere else: our own dataset, count, ledger, tracker, primary-document research or cross-dataset analysis. A page that only summarizes other sites doesn't meet the bar.
- Every fact we cite links its own primary source: the official league or team release, the official game record, a court, arbitration or SEC filing, a Secretary of State or trademark record, a municipal document, or an archive.org snapshot of one. Don't link an aggregator or a story that just repeats the fact.
- Cite CNBC, Sportico, Forbes and similar outlets only for their own proprietary work (valuations, net worths, original reporting). When no primary source exists, say so and cite the best contemporaneous report, labeled as a report.
- Data pages carry a Source column per row, a data dictionary, a downloadable file and a corrections address.
- This doesn't change the stats rule: never credit ESPN or the stats API; FCB gathers and verifies its own data.

## Where to watch (Ryan, Oct 24, 2026)

- Every game preview, recap "next game" note, play-by-play page, live homepage story and schedule table must name both TV and streaming, written as `TV: NBC. Streaming: Peacock.` Never list the TV network alone.
- Use only the official broadcaster or league release (NBC Sports, USA Sports/Versant, WNBA.com) and link it in a new tab.
- 2026 Finals: Games 1 and 4 are TV: NBC. Streaming: Peacock. Games 2, 3 and 5-7 are TV: USA Network (simulcast on CNBC). Streaming: Peacock.
- `automation/build_pbp.py` refuses to build a play-by-play page unless the game in `data/pbp-games.json` has both `tv` and `stream`.

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
- The photo file itself is 16:9 too (Ryan, Oct 19). Every lead and body photo is cropped to a 16:9 landscape file (ratio 1.74 to 1.80) with heads in frame before it is published, and the `<img>` width/height match the file. CSS cover is a backstop, not the crop. No title text on photos. Screenshots and charts may be taller, but crop them as short as the reader allows. `automation/test_photo_aspect.py` fails on any other shape.
- This rule does not change the hero, the news-listing cards, or player pages. A card photo in a list article keeps the `card` class and stays whole, at the existing narrow width, because cropping the card hides the card.

## Data pages, charts and tools (Ryan, Oct 19, 2026)
- Data pages, charts and tools follow normal academic data-publication norms.
- Material that supports the data may sit above or near the table: methods, sources, the data-through date, definitions, and one key-fact line.
- News, game schedules, storylines and bullet lists never sit above a data table, chart or tool. They go below it.
- Mark the element that holds the table, chart or tool with `data-fcb-data-table`. `automation/test_data_table_first.py` fails the build if a list, chart, image, news answer block or more than 700 characters of text sits between the byline and that element.

## Standing article rules (Ryan, Oct 27, 2026)
Learned from the Finals Game 5 recap. They apply to every article and data page.

1. **Verify every outside number.** A number from another outlet, an AI tool, or our own earlier draft is checked against the official box score or another primary source before it is used. If it cannot be verified, drop it.
2. **Original data hooks only where they earn a link.** Use FCB's own datasets and tools for a data angle only when a journalist would genuinely link to it. When you do, put the table high on the page (see "Data pages, charts and tools") with methods, sources, a data-through date, and a CSV download.
3. **Scope every claim to the data.** Write "since 2002" or "in our 2002-2026 database", not "ever" or "all-time", unless the record is attributed to a source that says so. Never write "guaranteed". For records, quote the official wording (league, team, or broadcaster release).
4. **Research before writing.** Check what is trending on X, Reddit, and in the news, and read that day's articles on the topic (older ones too, when useful). Add every idea that truly improves our story, after verifying it.
5. **Check the live page after publishing.** Confirm the title and meta, internal links, play-by-play links, and CSV downloads on the public URL. A `data/seo-meta.json` override needs a manual publish run, because the publish workflow skips `data/`.
6. **Never ask for credit or attribution.** Say the data is free to use. FCB's own data, charts, embeds, CSVs and dataset metadata use CC0 (public domain dedication, https://creativecommons.org/publicdomain/zero/1.0/), labeled "Free to use and republish (CC0)" (Ryan, Oct 27). Never use CC BY for FCB data. Third-party photo credits keep their own CC BY / CC BY-SA labels.
7. **SEO structure on every page.** SEO meta (title, description, canonical, social tags), a visible breadcrumb trail with matching BreadcrumbList JSON-LD, one H1, and clear H2/H3 subheads.

`automation/test_article_rules.py` checks the mechanical parts on every published `/news/` article: "guaranteed", unscoped "ever"/"all-time" claims, credit or attribution requests, FCB data labeled CC BY instead of CC0, `google.com/search` links, and missing title, description, canonical, breadcrumbs, BreadcrumbList JSON-LD, or H1/H2 structure.
