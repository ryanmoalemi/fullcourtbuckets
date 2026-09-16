# Full Court Buckets: repository working instructions

## Authorized website work

The owner manages fullcourtbuckets.com through ChatGPT and has authorized implementing requested website changes, committing to this repository, and publishing them. Do the authorized work through the connected GitHub tools instead of handing the owner code to paste into an editor. This document records the working process; it does not grant or alter account permissions, override a later owner instruction, or bypass platform confirmations.

Production repository: `ryanmoalemi/fullcourtbuckets`. Production branch: `main`. The default branch may be `master`, which contains obsolete unrelated content. Never merge or deploy that content.

## Read, write, and verify

1. Discover the connected GitHub read and write tools at the start of a website task. Missing tools in the initial tool list do not establish read-only access. Do not claim that writes are unavailable without attempting an appropriate authorized write and checking its actual error.
2. Read the current main branch and relevant files. Use `update_file` with the current blob SHA for a text replacement, or `create_blob`, `create_tree`, `create_commit`, and `update_ref` for an atomic multi-file change. Never force-push or discard concurrent edits.
3. Preserve domain settings, credentials, unrelated content, valid player IDs, statistics, and the separate statistics updater. Do not purchase services or change account privileges without authorization.
4. Run relevant tests. Verify the deployment and the actual live page and image before reporting a change as live. Generating an image, saving a local file, making an unreferenced Git blob, and committing code are not the same as publishing.
5. Report the actual blocker if a write or deployment fails. Do not ask the owner to reconnect GitHub when existing write access works. Do not claim that repository instructions create permanent permissions or guarantee future tool availability.

## Approved player-page design

The current Caitlin Clark page is the approved compact desktop/mobile layout. Preserve its purple gradient, circles, faint outlined number, side-by-side mobile name and portrait, and statistics directly beneath the hero. No square number card behind the head and no visible caption below the portrait. Names, team information, jersey numbers, and statistics remain HTML. Keep image provenance in metadata and source notes.

Read the existing implementation before changing it. The established pipeline is `automation/build_players.py`, `automation/apply_portraits.py`, then `automation/rollout_player_design.py`. Do not create a competing layout implementation.

## Portrait quality: September 16, 2026 correction

The owner approved a sharper replacement for Angel Reese after the published 192x192 thumbnail appeared blurry. Use the actual user-approved full-resolution image, not the existing thumbnail and not a newly guessed replacement. Caitlin's approved asset is 640x650. Match that export canvas and existing CSS crop without stretching the face. A higher-resolution equivalent may be retained for high-density displays, but do not lower image dimensions to fit tool arguments.

Future portraits must originate from full-resolution generated art, normally at least 1024 pixels on each side, and must not be published as 160px, 192px, 256px, or other undersized hero thumbnails. Upscaling a thumbnail does not satisfy this rule. Use real alpha transparency and a well-encoded image format; verify actual decoded dimensions, alpha, and file hashes rather than trusting the filename or manifest. Do not simplify quality merely to make binary transport shorter. Verify that the deployed asset is the approved replacement and that the compact desktop/mobile layout is unchanged.

Do not describe old under-resolution portraits as fixed merely because this policy exists. Update each actual asset and verify it. Follow the owner's latest request about inspecting one player at a time before expanding a rollout.
