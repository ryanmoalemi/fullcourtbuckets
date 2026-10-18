# Publishing an article

Commit one folder. GitHub Actions builds the page on the next push to `main`. No API key, no paid service, and no shared template edit.

```
content/articles/<slug>/
  article.md
  photo.jpg
```

`slug` is the folder name and the front-matter `slug`. The public URL is `/news/<slug>/`. A root redirect is written at `/<slug>/`.

`photo.jpg` is the only photo. It is already cropped to 16:9. The action writes `hero-1200.webp`, `hero-2x.webp`, and `og-1200.webp`. Nothing is drawn on the image.

## article.md

```markdown
---
title: "Headline used as the H1"
slug: example-recap
date: 2026-10-17
description: "One or two sentences for the card, meta description, and social text."
category: news
tags:
  - finals
teams:
  - atlanta-dream
  - golden-state-valkyries
hero_alt: "Who is in the photo, and what they are wearing"
photo_credit: "Photo: Jane Photographer, CC BY-SA 4.0, via Wikimedia Commons"
photo_credit_url: "https://commons.wikimedia.org/wiki/File:Example.jpg"
license_url: "https://creativecommons.org/licenses/by-sa/4.0/"
focal_y: 20
ticker: "Optional one-line score for the bar under the header."
---

The first paragraph is the lead. Link a [team](/wnba/teams/atlanta-dream/) or a [player](/wnba/angel-reese/) in the markdown. Do not add links the sentence did not already have.

## A section

- **One number.** The rest of the bullet.
```

Required: `title`, `slug`, `date`, `description`, `hero_alt`, `photo_credit`, and `photo.jpg`.

`category` is the label above the headline. `teams` are team-page slugs, and they decide which roster pages list the story.

`tags` stay in the file for you. The page does not print them.

`focal_y` is how far down the frame the crop sits, as a percent. `20` is the site default and keeps a head near the top of the frame. Leave it out to keep that default. The social image uses the same point. The action never puts type on the photo.

`card_title` and `social_title` are optional. Leave them out. The H1, the card, the og/twitter title, and the schema headline then all use `title`. The editorial check rejects a social title that does not match the H1, and the action will not commit that page.

`photo_credit` should read `Photo: Name, LICENSE, via Wikimedia Commons`. The name and “Wikimedia Commons” link to `photo_credit_url`. The license name links to `license_url`.

The body is markdown: `##` sections, `-` lists, `**bold**`, and `[label](/path/)` links. A paragraph that mentions DraftKings, betting odds, or a moneyline gets the site line `21+. Gamble responsibly. 1-800-GAMBLER.` under it. Do not credit ESPN or a stats vendor. That fails the editorial check and nothing is committed.

`ticker` is the optional “Now” line under the header. Set it when the story has a score. If you leave it out, a new page says “WNBA news, analysis and commentary.” Editing a page that already has a line leaves that line in place.

## What the action updates

On a push to `main` that touches `content/articles/**`, `.github/workflows/publish-articles.yml` runs `automation/publish_articles.py`, then the editorial, image-focal, news-lead, and team-coverage checks. If a check fails, the job stops and does not commit. If they pass, it commits the generated files and Pages deploys as usual. Push the folder straight to `main`. The action writes the HTML. If `main` is protected, let the GitHub Actions bot push without a review, or the generated commit will be rejected.

Generated each time, only when something changed:

- `news/<slug>/index.html` on the existing article chrome. The byline sits under the H1 and above the hero. The caption sits under the hero. The latest-news block, schema, and og/twitter tags are the same ones the other recaps use.
- `/<slug>/index.html` redirect.
- `images/articles/<slug>/` hero, 2x, and og files.
- `articles.json`, `news/index.html`, the homepage cards, `authors/ryan-moalemi/index.html`, `feed.xml`, `pages-sitemap.xml`, `search-index.json`, `sitemap/index.html`, the team pages those slugs match, and the latest-news lines on other posts.

Editing `article.md` or replacing `photo.jpg` and pushing to `main` regenerates that story. A second run with the same folder produces no diff.

The worked example is `content/articles/dream-valkyries-finals-game-1-recap/`. Regenerating it matches the live Game 1 recap.
