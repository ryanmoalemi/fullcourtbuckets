# Full Court Buckets style guide

Read `docs/EDITORIAL_STYLE.md` before writing or editing a `/news/` article. This file is the page order and lead-photo rules. The editorial guide is the headline, voice, evidence, source, archive, and betting rules.

## News article lead

Checked on a 390px-wide phone on October 4, 2026. ESPN, The Athletic, and AP each put the headline above the lead photo, and the photo was still on screen without scrolling. On ESPN and The Athletic the credit sits under the photo and the byline sits under that. AP does the same when the story has a lead photo.

Every `/news/` article uses that order:

1. Headline (H1). A short category line may sit above it.
2. Lead photo, the same width as the headline and the body, with a short credit line under it.
3. Byline and date.
4. Hook paragraph, then the body.

The lead photo is the article column at every breakpoint, including a lead that also has the `card` class. Later card photos in a list stay narrow. The lead does not grow to the viewport and it does not overflow sideways. Every lead uses one ratio, 16:9, with `aspect-ratio: 16/9` and `object-fit: cover`. The default crop is `object-position: center 20%`, so a face in a portrait photo stays in frame. Set `imageFocal` on that article (a CSS object-position such as `center 12%`) when the crop needs to move. The build measures a face when `imageFocal` is missing.

`automation/news_heroes.py` writes a real 16:9 WebP for the hero: `hero-1200.webp` (1200×675) and `hero-2x.webp` when the source is wide enough to make one without upscaling. A source narrower than 1200 stays at its own 16:9 size (`hero-16x9.webp`). The original file remains `image` for listings. `imageHero` is the lead file. The credit line stays under the photo.

On a 390px-wide phone, the headline, the photo, the byline, and the start of the hook are all on the first screen.

Keep the image `width` and `height` (the hero file's real pixels, 1200 and 675 for the standard file). The lead image uses `fetchpriority="high"` and is not lazy-loaded. Later images in the story stay lazy. The shared rules live in `assets/news-lead.css`. `order_news_lead` in `prepare_article_page` inlines them and applies this order.

## List articles

A numbered list reads straight through. The reader sees the headline, then the lead image, then the byline, then item 1.

Use this order:

1. Title (H1)
2. Lead image, the same width as the column, 16:9, with a short credit line under it
3. Byline and date
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
