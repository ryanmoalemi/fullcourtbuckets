# Current portrait authorization: autonomous publication

LATEST OWNER INSTRUCTION: After reviewing the three portraits for Paige Bueckers, Kelsey Plum and Aliyah Boston, the owner said: "all 3 are good you can work on your own now". This explicitly replaces the earlier per-image approval pause for the remaining player-illustration rollout. Generate, quality-check, upload and verify without requesting routine approval or asking the owner to post files/code. Account privileges are unchanged; discover and use the connected GitHub write tools. No new paid subscriptions, credential changes, or unrelated site edits are authorized.

## Uniform artwork, one player per generation

Exactly one intended player, frontal head/shoulders and upper chest, recognizable individual likeness, natural expression, realistic proportions, crisp polished illustrated shading. Plain white basketball top with black trim. Genuine transparent background. No text, jersey number, team/sponsor logos, poster, website screenshot, frame or scenery. Match the recent approved originals, not any rejected poster. Prefer the approved Sabrina/Paige/Kelsey/Aliyah source style. Use a reference only when actual usable bytes are available and rights permit it. Never copy one player's face onto another or identify an unfamiliar person from an image.

Generate ONE player per image call. Preserve the resulting original immediately under a unique ID-slug-SHA256 filename. Require real PNG decoding, RGBA transparency, and at least 1024 pixels per side. Keep all original bytes: no thumbnail export, resizing, recompression, or upscaling. Reject wrong subjects/formats. Up to two corrective attempts, then park the player with the precise blocker rather than repeating indefinitely. User authorization replaces repeated approvals, not quality review.

## Existing publication route only

Read .github/PORTRAIT_UPLOAD.md and the current upload request/workflow. Use the existing `portrait-upload.yml`, not a new uploader per player.

Preferred order for an accepted original: (1) Drive master with the exact runtime `file_...` reference, (2) temporary-Doc `insertInlineImage` using that SAME reference in the request placeholder and `image_uris`, then the exact returned `imageProperties.sourceUri` as `download_url`, (3) Google-independent GitHub handoff: put the original at `portrait-handoff/<player_id>-<slug>-<sha256>.png` and set `repository_path` on the existing upload request. The uploader preserves identical bytes in `images/players/<exact-slug>/portrait.png` and `portrait-masters/<player_id>-<slug>-<sha256>.png`.

Player folder and permanent provider ID must agree. Use sourceUri, never Google's resampled contentUri; do not mistake a transfer HTTP 403 for missing GitHub rights. Create a fresh signed-URL handoff only when the uploader can run promptly. Keep a Drive master if one exists; delete only a temporary Docs handoff after transfer. The GitHub handoff file is deleted by the uploader after it copies the bytes.

Do not retry a BLOCKED_FILE_REFERENCE against the same runtime `file_...` on the hourly backoff clock. Classify with `automation/portrait_recovery.py`, capture a redacted envelope, and leave the hourly task enabled for other players. One later successful portrait is not proof the error is fixed. Do not generate additional portraits solely to probe a binding denial once two accepted originals are already waiting without stored bytes.

The existing folder mapper and fcb-wnba workflow handle publication and checks. Do not change the compact desktop/mobile layout or the statistics updater. All names, teams and numbers remain HTML; gradient, circles and faint outline number stay in CSS. No visible image caption or square number card. No long torso panel.

## Verify, then advance

Do not overlap uploads or submit another request while a previous upload/publication needs reconciliation. Inspect current receipt and live file first. A queue record, image generation, Git blob, commit, HTTP 200, or deployment step alone is not proof of completion. Require successful public Chromium/WebKit checks at 1365x850, 390x844 and 320x568; exact SHA256 and natural dimensions must match the original, correct name/ID/canonical/currentSrc, one decoded image, compact side-by-side layout and statistics underneath. Inspect actual screenshots. Do not claim all stats fit on the smallest phone if they do not.

Record evidence in content/portrait-upload-receipts/<slug>.json and progress in content/portrait-autopilot.json. Resume incomplete approved uploads before new generation. Never regenerate a completed full-quality original. Old 160/192/256/480px hero files are NOT complete under this standard merely because a legacy test exemption lets them render. Replace those next, active players before archive players. Preserve completed Caitlin/Angel/Aja/Breanna/Sabrina/Napheesa and subsequent verified high-resolution artwork.

## Current three approved originals

- Paige Bueckers, ID 741: c4b68851366ecdc836e942f04ae299123ebffbeadd54180fe8d15729170fd0e0. Drive master 19bAJb4DeK8eMP-hGYCjwLiF1wtnOTKLG. This latest approved sample supersedes older unpublished Paige drafts.
- Kelsey Plum, ID 488: b46c4f2ba0a9912697e39009a81cf3307fd7c85ebdbb238583e78ef52052c144. Drive master 1rh5Ugf0ZNEcFqfewmoaR9mMFE9d-AVwa.
- Aliyah Boston, ID 676: 9902c6e799e1fc9126b2bb40c5caf41b0ee7ee42eed6240b07f158a4365acd03. Drive master 1D9lgZNnJ7PKGCOLoMIgPm3vrXiSbm5sq.

All three are separate 1254x1254 transparent PNGs approved together. Preserve their originals. Check live receipts before repeating their uploads.

## Scheduled continuation and reporting

The FCB portrait rollout task may continue approximately hourly, up to three separate portraits per run, finishing and verifying each before starting another. Persist a short-lived lease and stop conflicting runs. Send a progress update after ten newly verified portraits, final completion, or an actionable blocker; no individual approval requests. If a tool is unavailable, record the real error, do not pretend to publish, and pause only if the capability blocks all work. Do not touch the WNBA statistics schedule. Disable the task after the existing archive is complete. No overnight completion guarantee.
