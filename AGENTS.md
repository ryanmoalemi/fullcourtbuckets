# Full Court Buckets: repository working instructions

## Authorized website work

The owner manages fullcourtbuckets.com through ChatGPT and has authorized implementing requested website changes, committing to this repository, and publishing them. Do the authorized work through the connected GitHub tools instead of handing the owner code to paste into an editor. This document records the working process; it does not grant or alter account permissions, override a later owner instruction, or bypass platform confirmations.

Production repository: `ryanmoalemi/fullcourtbuckets`. Production branch: `main`. The default branch may be `master`, which contains obsolete unrelated content. Never merge or deploy that content.

## Standing owner instruction: handle the complete publication

The owner explicitly directed: "remember always get your github write publish permissions don't ask me to post anything". For each authorized website task, discover the connected GitHub read/write tools, read the current target files, and perform the upload, commit, publication and live verification here. Do not send the owner code, filenames or steps to post manually when the connected tools can do the work. Do not ask them to resend an approved original already available in the conversation or preserved Drive master.

Missing tools from an initial tool list are not evidence of read-only access. Discover the appropriate action and attempt the authorized write before making any access claim. A failed image download is a transport error, not proof of missing GitHub permission. Use the established whole-file uploader in `.github/PORTRAIT_UPLOAD.md`; do not rebuild it per player. Do not claim permanent privileges or attempt to grant yourself account permissions. Request owner intervention only after an actual tool error establishes an authorization step that cannot be completed with available tools.

## Read, write, and verify

1. Discover the connected GitHub read and write tools at the start of a website task. Missing tools in the initial tool list do not establish read-only access. Do not claim that writes are unavailable without attempting an appropriate authorized write and checking its actual error.
2. Read the current main branch and relevant files. Use `update_file` with the current blob SHA for a text replacement, or `create_blob`, `create_tree`, `create_commit`, and `update_ref` for an atomic multi-file change. Never force-push or discard concurrent edits.
3. Preserve domain settings, credentials, unrelated content, valid player IDs, statistics, and the separate statistics updater. Do not purchase services or change account privileges without authorization.
4. Run relevant tests. Verify the deployment and the actual live page and image before reporting a change as live. Generating an image, saving a local file, making an unreferenced Git blob, and committing code are not the same as publishing.
5. Report the actual blocker if a write or deployment fails. Do not ask the owner to reconnect GitHub when existing write access works. Do not claim that repository instructions create permanent permissions or guarantee future tool availability.

## Approved player-page design

The current Caitlin Clark page is the approved compact desktop/mobile layout. Preserve its purple gradient, circles, faint outlined number, side-by-side mobile name and portrait, and statistics directly beneath the hero. No square number card behind the head and no visible caption below the portrait. Names, team information, jersey numbers, and statistics remain HTML. Keep image provenance in metadata and source notes.

Read the existing implementation before changing it. The established pipeline is `automation/build_players.py`, `automation/apply_portraits.py`, then `automation/rollout_player_design.py`. Do not create a competing layout implementation.

## Portrait quality and original-file handling

The owner approved a sharper replacement for Angel Reese after the published 192x192 thumbnail appeared blurry. Caitlin's approved asset is 640x650, but that is a historical export size, not a reason to shrink new originals. The latest owner-approved process is to keep the full-resolution PNG unchanged in `images/players/<exact-page-slug>/portrait.png`. The folder mapper handles metadata; the existing responsive CSS supplies the compact proportional crop. No per-player template edits, resizing, recompression, stretching, embedded text or background graphics.

Future portraits must originate from full-resolution generated art, normally at least 1024 pixels on each side, and must not be published as 160px, 192px, 256px, or other undersized hero thumbnails. Upscaling a thumbnail does not satisfy this rule. Use real alpha transparency; verify actual decoded dimensions, alpha and file hashes rather than trusting a filename or manifest. Do not reduce quality to fit tool arguments. Preserve each master under a unique player-ID/slug/checksum filename so later generations cannot overwrite it.

Do not describe old under-resolution portraits as fixed merely because this policy exists. Update each actual asset and verify it. Follow the owner's latest request about inspecting one player at a time before expanding a rollout.

## Latest approval loop and mandatory browser evidence

Read `automation/PORTRAIT_PUBLISHING.md`, `.github/PORTRAIT_UPLOAD.md`, `content/portrait-review-status.json` and that player's review/upload receipt before continuing. The normal process is one generated image, owner approval, upload the unchanged original, verify publication, then the next image. Keep the older bulk task paused unless the owner explicitly changes that instruction.

Earlier Aja missing-source and corruption notes are historical: her later approved white-top original, Breanna's approved original and Sabrina's approved original were uploaded and verified. Do not request them again or regenerate completed images. Reconcile current receipts and actual live pages before repeating any upload. A stale pending status alone is not proof that a file failed to publish.

Every portrait publication must pass `automation/verify_portraits.py`: decode the real bytes, enforce the approved player-ID/name/slug/checksum mapping, and check actual public image decoding and hashes in Chromium and WebKit at desktop and phone viewports. Inspect the live screenshots in that run's `portrait-live-verification` artifact. A GitHub commit, green deployment step, HTTP 200, or manifest dimensions alone is not sufficient. A valid placeholder is not a completed portrait. Never advance the approval loop by claiming a missing approved replacement is live.
