# Full Court Buckets style guide

## News article lead

Checked on a 390px-wide phone on October 4, 2026. ESPN, The Athletic, and AP each put the headline above the lead photo, and the photo was still on screen without scrolling. On ESPN and The Athletic the credit sits under the photo and the byline sits under that. AP does the same when the story has a lead photo.

Every `/news/` article uses that order:

1. Headline (H1). A short category line may sit above it.
2. Lead photo, full width, with a short credit line under it.
3. Byline and date.
4. Hook paragraph, then the body.

The lead photo has to be visible at 390px without scrolling. Keep the image `width` and `height`. The lead image uses `fetchpriority="high"` and is not lazy-loaded. Later images in the story stay lazy. `order_news_lead` in `prepare_article_page` applies this order.

## List articles

A numbered list reads straight through. The reader sees the headline, then the lead image, then the byline, then item 1.

Use this order:

1. Title (H1)
2. Lead image, full width, with a short credit line under it
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
