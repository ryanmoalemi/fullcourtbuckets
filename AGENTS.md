# Full Court Buckets: repository working instructions

## Current owner-required portrait source and style standard (2026-09-28)

The owner approved the latest realistic Aaliyah Nye illustration and instructed ChatGPT to find the real source photograph next time, own source selection and quality review, and ALWAYS use the uploaded Cameron Brink example to remember how every illustration should look. This section supersedes conflicting older portrait-art instructions below. It does not restart autonomous publishing, change existing task schedules, or change the current owner/Cursor publication arrangement.

### Mandatory style reference, every time

Use the actual owner-supplied `Cameron Brink EXAMPLE.png` as the visual STYLE reference before every new player illustration, not just a remembered written description. This specific example controls realism, subtle illustrated finish, natural skin texture, lighting, edge treatment, framing, head/shoulder scale and white jersey with black trim. Do not use the previous rejected cartoon/vector versions or substitute a different Cameron image.

Exact reference identification:
- Conversation attachment: `file_00000000c17081fd8f8c652cab2353b8`.
- Original filename: `Cameron Brink EXAMPLE.png`.
- SHA-256: `3d1710770d628376ef4119d8965b26c34ec91c600061cea66fdb3c49b11409c5`.
- Original bytes: 2,301,344; PNG, 1254 x 1254, RGBA, alpha extrema 0-255, decoded and hashed on 2026-09-28.
- The attachment was mounted at `/mnt/data/Cameron Brink EXAMPLE.png` for this instruction update. This is a session path, not a permanent Drive or repository asset. A Drive upload attempt returned a file-reference validation error; no durable Drive image copy was established in this update. Do not invent one or describe a different existing Cameron draft as this example. Retrieve the exact attachment or another verified copy with the same hash when required.

Cameron's example is for STYLE ONLY. Never transfer her face, complexion, eye color, hair or facial proportions onto another player.

### Source, generate, review

1. Find ONE clear real photograph of the requested player before generating, without making the owner find it. Prefer a photo attached to a named official WNBA/team/college player profile. Use a user-supplied real photo as the primary source when provided. Confirm the source's caption/player name and official profile ID; do not guess an unknown person's identity from pixels. Save the actual source URL/reference and inspect the photo, not just its search snippet.
2. Use that player's real photo for likeness and the exact Cameron example for visual style. Additional official photographs may clarify source attribution or visible details, but do not average unrelated faces or delay a clear one-photo task by rebuilding the publication pipeline. One real-photo source replaces the earlier name-only/generic-face generation process.
3. Generate one player, head and shoulders/upper chest, with realistic proportions and faithful visible features from the source. Preserve complexion, facial structure and hairstyle rather than inventing generic glamour features. Use natural lighting and subtle realistic illustration, NOT heavy comic outlines, flat vector shading or exaggerated/cartoon anatomy.
4. Keep the standardized plain white basketball top with black trim, genuine transparent background and high-resolution original PNG. No names, text, team/sponsor/league logos, numbers, scenery, halos or poster graphics inside the image. Remove logos from any retained headband. No added jewelry; follow the established no-jewelry standard unless the owner requests otherwise. Keep a little space above the hair and the same compact shoulder crop as the example. Never stretch, upscale a thumbnail or reduce quality for transport.
5. Check source attribution against the official WNBA/team profile, then review the output's visible features against the actual source and its rendering/framing against the Cameron example. These are separate source-provenance and visual-quality checks, NOT facial recognition or proof of identity. Do not claim that reference photos were inspected or a check passed unless it actually occurred. Reject obvious departures instead of presenting a generic portrait with a player's name.
6. When generating in chat, include the requested player's NAME in chat text, not in the image, and no filesystem path. Put the name immediately before the image-generation call when an empty final response is required. Show only the requested accepted illustration; do not repeat previously completed players or publish without the currently applicable authorization.

This is a saved art/source procedure, not a guarantee of likeness or copyright clearance. No live player image, template, sports data or publication configuration was changed by this instruction update.

## Latest portrait authorization

The owner approved the three latest portraits (Paige Bueckers, Kelsey Plum, Aliyah Boston), then said: "all 3 are good you can work on your own now". The earlier per-player approval pause is therefore superseded for this rollout. Read `.github/PORTRAIT_AUTOPILOT.md` and `content/portrait-autopilot.json` FIRST. Generate one player at a time, quality-check, publish the original, verify the live page, and save progress without routine owner approval requests. The FCB portrait rollout task is enabled for approximately hourly continuation. Older paused/review-pending records are historical unless the latest owner instruction changes this again. No new paid services, credential changes, account-privilege changes or unrelated website edits are authorized.

## Authorized website work

The owner manages fullcourtbuckets.com through ChatGPT and has authorized requested website changes, repository commits and publication. Do that work through connected GitHub tools instead of handing the owner code or images to post. These instructions document authorization, not account permissions, and do not bypass platform confirmations.

Production repository: `ryanmoalemi/fullcourtbuckets`. Production branch: `main`. The default may be `master` with obsolete unrelated ADU content. Never merge or deploy it. Do not republish ADU articles. Former ADU URLs that still exist at the same path on sandiegoadubuilder.com are noindex redirect stubs to that site (GitHub Pages cannot send an HTTP 301) and stay out of sitemaps, internal links, and JSON-LD. A former ADU URL that is not on that site stays a real 404.

## Adding an article

Every post is published at `/news/<slug>/`. The slug does not change. Add `news/<slug>/index.html` (and its images) and one `articles.json` entry with `slug`, `url` (`/news/<slug>/`), `title`, `description`, `category`, `date` (`YYYY-MM-DD`), `image`, and `imageAlt`. Do not publish a new post at the site root.

The `/news/` hub lists every article from `articles.json`, newest first, with the date, title, one-line summary, and thumbnail. Link the new post from that hub. The generator rebuilds the hub, so do not hand-edit the list. The same generator adds the byline under the headline on every post: "By Ryan Moalemi", with the headshot linked to `/authors/ryan-moalemi/` in the same tab. It also rebuilds that author page, newest first, from `articles.json`. Article JSON-LD `author` is that Person. `publisher` stays Full Court Buckets. Add `<meta name="author" content="Ryan Moalemi">`. The main menu links to `/news/` only. Do not list individual posts or the author page in the menu. Breadcrumbs on the post are Home > News > Post, both in the visible trail and in `BreadcrumbList` JSON-LD. The article JSON-LD `url` and `mainEntityOfPage` use the `/news/<slug>/` URL.

The homepage sorts `articles.json` by date, features the newest story, and lists older stories below. Do not hand-edit the homepage story cards. Add the new `/news/<slug>/` URL and `/news/` to `sitemap.xml` and `pages-sitemap.xml`. Do not list a root post URL.

GitHub Pages has no server redirects. When a post leaves an old root URL, leave a redirect stub at that old path: meta refresh `0`, `rel=canonical` to the new URL, `noindex`, and `location.replace` to the new URL.

On-site navigation opens in the same tab. Do not put `target="_blank"` on menu links, footer links, breadcrumbs, news hub `.news-item` cards, homepage story cards, player cards, team cards, standings links, or other hub and index links. `target="_blank" rel="noopener"` stays on external outbound links and on links inside article body prose, including photo captions and the first player or team mention in a story.

## Angel Reese card collection

Ryan's personal collection lives at `/authors/ryan-moalemi/ryans-angel-reese-cards/`. It is not an article. Do not add it to `articles.json` or the main menu.

The only source for cards, prices, comps, and notes is `data/reese-cards.json`. To add a card or update a value, edit that file and run `python automation/build_reese_cards.py`. The generator rewrites the collection page, the teaser on `/authors/ryan-moalemi/`, the "Ryan's Angel Reese card collection" link on `/wnba/angel-reese/`, and the sitemap entries. Do not hand-edit the HTML.

`current_value` is a number, or the string `unknown` when no verified sale exists. Unknown cards stay on the page with an asterisk and are left out of paid, value, and change. `price_paid_total` is the eBay order total (item + shipping + tax). Put slab photos in `images/reese-cards/` and point `photo.front` and `photo.back` at those files. Omit `back` when the listing has no back photo. Label those photos "Photo: eBay seller listing of this card". The hero credit (photographer, license, Wikimedia link) is the `HERO` block in `automation/build_reese_cards.py`.

## Player pages

Link the first body-text mention of each player in every article to the existing page at `/wnba/<slug>/`, with `target="_blank" rel="noopener"`. Do not link player names to WNBA.com. Do not create a separate `/players/` system. Use the slug already published in `wnba/<slug>/index.html` and `data/wnba/players-index.json`. If that page does not exist, leave the name as plain text. Do not create a new player page for an article mention.

When a player's saved `current_team` changes from one non-null team to a different non-null team, `automation/wnba_sync.py` prepends a `team_changes` entry on `data/wnba/players/<slug>.json`: `from`, `to`, and `date` (the America/Los_Angeles calendar date, `YYYY-MM-DD`). Newest stays first. The player page shows a small label `Team change`, then `Joined the <To Team> from the <From Team> on <Mon D, YYYY>` (for example, `Joined the Sparks from the Liberty on Oct 3, 2026`). Do not write Moved. The feed does not say whether it was a trade, a signing, or a waiver claim. Do not record a null transition, including a player leaving or returning to the active feed. Keep earlier entries. Do not loosen the active-player shrink guard for this.

## Standing owner instruction: handle the complete publication

The owner directed: "remember always get your github write publish permissions don't ask me to post anything". Discover and use the connected read/write tools, read the current target files, and perform uploads, commits, publication and live verification here. Do not ask the owner to post code, manually upload approved files, or resend originals already in the conversation or preserved Drive storage.

Missing tools in the initial list are not proof of read-only access. Discover and attempt the appropriate authorized write before making an access claim. A file-download failure is a transport error, not a GitHub permission error. Use `.github/PORTRAIT_UPLOAD.md`, not new per-player infrastructure. Never claim permanent privileges or grant yourself permissions. Request owner intervention only when an actual error establishes a necessary authorization step unavailable through the connected tools.

## Read, write, and verify

1. Discover current tools and read current main and the relevant records. Use update_file with the current blob SHA, or create_blob/create_tree/create_commit/update_ref for atomic multi-file edits. Never force-push or discard concurrent changes.
2. Preserve domain, hosting, credentials, unrelated content, permanent IDs, sports data and the daily/weekly statistics updater. Do not buy additional services.
3. Run relevant existing tests. Verify deployment and actual public pages/images. Generation, local saves, Git blobs, commits, successful HTTP responses and deployment steps alone are not proof of publication. Verification scripts must use headless browsers. Those browsers are not counted in Google Analytics: the shared gtag snippet does not load when `navigator.webdriver` is set, the user agent looks like a headless browser or bot, or the window size is 0.
4. Report real blockers accurately. Do not request reconnection when existing writes work, or claim repository notes guarantee future tool availability.

## Approved uniform artwork and page design

Use one recognizable editorial head-and-shoulders/upper-chest illustration, natural expression, realistic proportions, crisp polished shading, plain WHITE basketball top with BLACK trim, and genuine transparent background. No lettering, logos, jersey numbers, poster, scenery, webpage graphics or frame within the image. Generate one person per call, not grids. Preserve recent approved source files as style references, never copy their faces to other identities. Self-review the intended likeness and format; park bad results instead of publishing a wrong person or repeatedly generating posters.

The approved compact desktop/mobile template stays unchanged: purple gradient, circles, faint outlined number, side-by-side mobile name and portrait, and stats directly below. No square number card or visible portrait caption. Names, teams, jersey numbers and statistics remain HTML; provenance remains in source notes/metadata. Do not create a competing page-layout implementation.

## Full-resolution original handling

Preserve every generated master immediately under a unique player-ID/slug/SHA256 filename and in connected Drive. Require a genuine transparent PNG normally at least 1024px on both sides. Publish the whole original unchanged to `images/players/<exact-slug>/portrait.png`; the existing folder mapper and responsive crop handle it. No resizing, recompression, stretching, thumbnail export or upscaling. Caitlin's historical 640x650 export is not an instruction to shrink new originals.

The old 160/192/256/480px portraits remain unfinished under the improved quality standard even when a historical exception allows them to render. Replace them next for active players, then finish other active players and the archive. Preserve already verified full-quality artwork. Reconcile receipts/live files before repeating work; a stale pending record is not proof of failure.

## Existing whole-file upload and mandatory checks

Read `.github/PORTRAIT_UPLOAD.md` and the current upload request/workflow. Use the existing Drive/temporary-native-Doc sourceUri handoff and portrait-upload.yml. Do not use a resampled Google contentUri, expired/guessed URLs, manual base64 chunks or a new workflow per player. Preserve the master and delete only the temporary handoff Doc after transfer. Serialize uploads and reconcile publication before submitting the next request.

The existing pipeline is build_players.py, apply_portraits.py with folder mapping, then rollout_player_design.py. Every publication must pass verify_portraits.py with actual image decoding, approved ID/name/slug/checksum binding, public file hashes, and Chromium/WebKit desktop/mobile checks. Inspect actual selected-player screenshots in the portrait-live-verification artifact. A placeholder is not a completed portrait. Record precise results and do not claim the whole stats strip fits on all phones when it does not.

## Autonomous progress

Save results, leases and blockers in content/portrait-autopilot.json and per-player upload receipts. Up to three players per scheduled run, generated and published sequentially. Notify after ten newly verified portraits, completion, or an actionable blocker, not for routine approval. If a capability is actually unavailable, keep live pages intact, record the error and pause when it blocks all progress. Disable the portrait task when the existing queue is complete; leave the statistics updater running.
