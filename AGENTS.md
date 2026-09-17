# Full Court Buckets: repository working instructions

## Latest portrait authorization

The owner approved the three latest portraits (Paige Bueckers, Kelsey Plum, Aliyah Boston), then said: "all 3 are good you can work on your own now". The earlier per-player approval pause is therefore superseded for this rollout. Read `.github/PORTRAIT_AUTOPILOT.md` and `content/portrait-autopilot.json` FIRST. Generate one player at a time, quality-check, publish the original, verify the live page, and save progress without routine owner approval requests. The FCB portrait rollout task is enabled for approximately hourly continuation. Older paused/review-pending records are historical unless the latest owner instruction changes this again. No new paid services, credential changes, account-privilege changes or unrelated website edits are authorized.

## Authorized website work

The owner manages fullcourtbuckets.com through ChatGPT and has authorized requested website changes, repository commits and publication. Do that work through connected GitHub tools instead of handing the owner code or images to post. These instructions document authorization, not account permissions, and do not bypass platform confirmations.

Production repository: `ryanmoalemi/fullcourtbuckets`. Production branch: `main`. The default may be `master` with obsolete unrelated content. Never merge or deploy it.

## Standing owner instruction: handle the complete publication

The owner directed: "remember always get your github write publish permissions don't ask me to post anything". Discover and use the connected read/write tools, read the current target files, and perform uploads, commits, publication and live verification here. Do not ask the owner to post code, manually upload approved files, or resend originals already in the conversation or preserved Drive storage.

Missing tools in the initial list are not proof of read-only access. Discover and attempt the appropriate authorized write before making an access claim. A file-download failure is a transport error, not a GitHub permission error. Use `.github/PORTRAIT_UPLOAD.md`, not new per-player infrastructure. Never claim permanent privileges or grant yourself permissions. Request owner intervention only when an actual error establishes a necessary authorization step unavailable through the connected tools.

## Read, write, and verify

1. Discover current tools and read current main and the relevant records. Use update_file with the current blob SHA, or create_blob/create_tree/create_commit/update_ref for atomic multi-file edits. Never force-push or discard concurrent changes.
2. Preserve domain, hosting, credentials, unrelated content, permanent IDs, sports data and the daily/weekly statistics updater. Do not buy additional services.
3. Run relevant existing tests. Verify deployment and actual public pages/images. Generation, local saves, Git blobs, commits, successful HTTP responses and deployment steps alone are not proof of publication.
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
