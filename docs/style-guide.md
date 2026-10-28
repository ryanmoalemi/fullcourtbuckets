# Full Court Buckets style guide

Read `docs/EDITORIAL_STYLE.md` before writing or editing a `/news/` article. This file is the page order and lead-photo rules. The editorial guide is the headline, voice, evidence, source, archive, and betting rules.

## News article lead

Every `/news/` article uses this order. `order_news_lead` applies it, including on a page that is rebuilt later:

1. Headline (H1). A short category line may sit above it.
2. Byline and date, directly under the H1: photo, name, and date on one row.
3. Archive note, when the story is a preview whose game date has passed. It stays immediately under the byline.
4. Lead photo, the same width as the headline and the body, with a short credit line under it.
5. Quick-cite box, when the page has one. It follows the hero, above the hook.
6. Hook paragraph, then the body.

The lead photo is the article column at every breakpoint, including a lead that also has the `card` class. Later card photos in a list stay narrow. The lead does not grow to the viewport and it does not overflow sideways. Every lead uses one ratio, 16:9, with `aspect-ratio: 16/9` and `object-fit: cover`. The default crop is `object-position: center 20%`, so a face in a portrait photo stays in frame. Set `imageFocal` on that article (a CSS object-position such as `center 12%`) when the crop needs to move. The build measures a face when `imageFocal` is missing.

`automation/news_heroes.py` writes a real 16:9 WebP for the hero: `hero-1200.webp` (1200×675) and `hero-2x.webp` when the source is wide enough to make one without upscaling. A source narrower than 1200 stays at its own 16:9 size (`hero-16x9.webp`). The original file remains `image` for listings. `imageHero` is the lead file. The credit line stays under the photo.

On a 390px-wide phone the headline and the byline come first, then the photo.

## Byline on every authored page

The same byline rule applies outside `/news/` wherever a page shows the author byline. The photo, the name, and the date sit directly under the H1. The hero image comes after that row. A quick-cite box, when the page has one, still follows the hero. This covers the card collection, the viewership tracker, and any generated page. `order_news_lead`, the viewership renderer, and `build_reese_cards._hero` emit that order. `automation/test_byline_order.py` checks the published pages and those generators on every test run.

The author profile is the bio itself. The portrait sits directly under the H1, and the bio follows the portrait.

## Body photos

A later photo in the article is also 16:9 and the width of the column. The figure class is `body-photo`. `object-fit` is `cover`. Set `object-position` on the image so heads stay fully in frame. The default is `center 20%`.

A screenshot or a chart is the exception. Mark it `no-crop` (or `screenshot`, `chart`, or `stat-board`). Those are not cropped: `object-fit` is `contain`, `max-height` is `70vh` up to 900px wide, and `720px` above that. The full rule is in `docs/EDITORIAL_STYLE.md`. Card photos in a list article stay on the card rule.

Keep the image `width` and `height` (the hero file's real pixels, 1200 and 675 for the standard file). The lead image uses `fetchpriority="high"` and is not lazy-loaded. Later images in the story stay lazy. The shared rules live in `assets/news-lead.css`. `order_news_lead` in `prepare_article_page` inlines them and applies this order.

## List articles

A numbered list reads straight through. The reader sees the headline, then the byline, then the lead image, then item 1.

Use this order:

1. Title (H1)
2. Byline and date, directly under the H1
3. Lead image, the same width as the column, 16:9, with a short credit line under it
4. One short intro paragraph (see Hooks)
5. Items 1 through 10. Each item is the heading, then the card image, then one price line, then that item's text.
6. After the last item, only fine print: the research note, the how-made note, and image credits. Do not add a bottom-line section.

Do not put a ranking table, a checklist, or a sales grid in the body of a list article.

## Hooks

Every article opens with one short intro paragraph, usually two or three sentences. It has to do three jobs:

1. Say what the article is.
2. Give the reader one verified fact the headline did not already give them.
3. Tease something later in the piece so the reader keeps going.

The tease has to be true, and the article has to pay it off. Do not invent a number or hide the subject with a false cliffhanger. Roy Peter Clark calls the lead a flashlight: it shows what is coming. A nut graf can live in the same short paragraph. Leave one real question open, then answer it in the body. Stay on the title. Do not open a side topic. No em dashes.

## Game stats for recaps and posts

Recaps and posts take the score, quarter scores, team totals, and player box from `data/games/<YYYY-MM-DD>-<away>-<home>.json`. The list of those files is `data/games/index.json`. ESPN is the cross-check, stored on the same file under `crosscheck`. The short read is the `.md` file next to the JSON. The ESPN box-score link in that file can stay on the article.

The article source note says: Full Court Buckets gathers its own game data and verifies it against official box scores. Do not name or link the data vendor in the article, the source note, or any other published page text.

Any mismatch must be resolved before review. If `crosscheck.mismatches` is not empty, do not pick the number that sounds better. If `source` is `espn` and `fallback` is true, the site's own feed did not supply the game. Say so in the draft, and do not treat that file as the primary box. A file whose cross-check did not run is not ready either.

## Standing article rules

The seven standing rules (verify outside numbers, original data hooks only where a journalist would link, scoped claims, research X/Reddit/news first, live-page check after publishing, never ask for credit, SEO meta plus breadcrumbs and H1/H2) are in `docs/EDITORIAL_STYLE.md` under "Standing article rules". `automation/test_article_rules.py` enforces the mechanical parts.

## Tables and charts in articles (Ryan, Oct. 27, 2026)

- Introduce every table or chart with one or two natural sentences in the article's voice: what it shows and the takeaway, ending in a lead-in such as "Here's every champion since 2002 by Finals scoring:". No "Key finding:" or "Key fact:" labels.
- The table or chart comes right after its lead-in. Never push it down.
- Data-through date, methods, source and the CC0 download go in a small, muted caption directly below the table: "Source: WNBA.com box scores. Data through Oct. 26, 2026. Methods: ... Download CSV (CC0)." Never between a heading and its table.
- In `content/articles/*/article.md`, a paragraph starting with "Data through", "Methods:", "Source:"/"Sources:" or "Download (CC0):" is moved below the section's table by `automation/publish_articles.py` and rendered as `<p class="table-note" data-fcb-dynamic="data-note">` (time-sensitive). Hand-built pages use the same class.
- Wide tables scroll sideways inside the column on phones with edge shadows and a visible "Scroll for more columns →" hint (`assets/site-nav.css`, `assets/site-nav.js`). No column may be hidden without that cue.
- Enforced by `automation/test_article_data_notes.py`.

## Keys to victory and other list-style sections (Ryan, Oct 27, 2026)
- Give each group its own H3 (`### Atlanta Dream`, `### Golden State Valkyries`), then each item its own H4 with a short, scannable label (`#### Push the pace`, `#### Hold Atlanta to 64 or fewer`).
- Under each H4, write one or two sentences with the stat that backs it. Don't repeat the label as the first words.
- The methods/data note goes once, at the end of the section, not between the H2 and the first item.
- If the page has a table of contents, list the H3s in it.

## Photos throughout articles (Ryan, Oct 27, 2026)
- Photos in the body are encouraged, not just the hero. Put them where they fit the text (a player next to her key, the arena next to the schedule).
- Every photo is 16:9, the same as the hero. Crop with `automation/crop_16x9.py`, save a 1600x900 `.jpg` and `.webp` in `images/articles/<slug>/`, and check that no head is cut off.
- Use only licensed images (Wikimedia Commons CC BY / CC BY-SA / CC0 or similar, or ones already in the repo). Credit each one in the hero style: `Photo: Author, LICENSE, via Wikimedia Commons`, with the file and license links, plus descriptive alt text.
- In `article.md`, one line: `!photo: /images/articles/<slug>/<name>.jpg | alt | Photo: Author, LICENSE, via Wikimedia Commons | file URL | license URL | focal`.
- Never put a photo between a heading and its table.

## Readability review before publish (Ryan, Oct 27, 2026)
Every new article runs the GPT + Gemini readability review before it is published. See `docs/READABILITY_REVIEW.md`.
