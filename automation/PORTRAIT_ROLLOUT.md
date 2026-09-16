# Unattended portrait batches: standing user authorization

## Scope and current status

The owner approved the final compact Caitlin Clark desktop/mobile sample and explicitly authorized batches of ten for ALL existing player pages, including live publication, without further approval. Active players first, then prominent archive players, then the remaining archive. No new subscriptions, funded API services, credential changes, unrelated edits or changed sports facts are authorized.

A ChatGPT task named `FCB portrait rollout` is scheduled approximately hourly starting at 01:00 America/Los_Angeles on September 16, 2026, with at most 72 runs. The first unattended image-generation/upload/deployment cycle has not yet been verified. Scheduling alone is not proof of generation capability or completed portraits. There is no paid image API connected. BALLDONTLIE remains for statistics only.

## Preserve the existing deployed layout

Production repository: `ryanmoalemi/fullcourtbuckets`, branch `main`. Never merge or deploy obsolete `master` website content. Preserve concurrent changes and never force-push.

The existing `rollout_player_design.py` already applies the compact format across the archive. Do not create a competing layout implementation. Existing pipeline:

1. `python automation/build_players.py`
2. `python automation/apply_portraits.py`
3. `python automation/rollout_player_design.py`

Read `automation/ILLUSTRATION_ROLLOUT.md` and the current scripts for design details. The reference image is the actual file `images/players/caitlin-clark-portrait-v2.avif`; retrieve it from the repository rather than assuming that old chat-local files are available.

Use compact head/shoulder illustrations, purple gradient, circles and faint outlined number, no square card, side-by-side mobile name and image, and the stats strip immediately below. No tall torso panel. Portraits need native transparency, clean upper-arm continuity at the lower crop, and bottom/right alignment. No visible caption under the image. All names, team information and statistics stay HTML. Keep provenance in source notes and metadata. Preserve the approved Caitlin artwork.

## Queue, generation and publication

`data/wnba/illustration-queue.json` is the builder-generated missing-art inventory. `content/player-illustrations.json` is the permanent image manifest. `content/portrait-rollout.json` is the persistent executor ledger. Do not use a compiled queue's existence as evidence that image generation has begun.

Run `python automation/portrait_queue.py --limit 10` on current files for the next batch. It selects IDs only; it does not generate or publish. Resume `current_batch` first. Claim a batch with a short-lived timestamped lease in the ledger; do not overlap another run's unexpired lease. Reconcile approved-but-not-live-verified images before generating replacements. Existing duplicate names with different IDs require review, never automatic merging.

Use an actually available image-generation tool to create a separate original likeness of each intended player in the approved style. Do not copy stock photos without suitable rights, create generic faces, or reuse Caitlin's face. Match the style, not the identity of the example. Self-check identity, transparency, anatomy, cropping and artifacts; retry or park questionable work. The user's standing approval replaces further user approvals, not this quality review.

Optimize to a real transparent AVIF/WebP/PNG. Decode and verify the bytes. Upload real binary content with GitHub's blob tool and the specified encoding; a path string or text renamed as an image is not an upload. Append exact player-ID, name and slug mappings to the existing manifest. Commit assets and mappings together on the freshest main tree, without force. Save partially finished work so it can resume.

Run the repository tests and existing builder. Confirm Actions deployment succeeds and fetch each changed LIVE page and image before marking it published. Check actual HTML name, correct asset, lack of square/caption and appropriate crop. Use a real browser for visual checks when available; never invent screenshots or measurements.

Each published ledger record needs the ID, slug, asset, live URL, live_verified=true, commit and deployment-run evidence. Record attempts and blockers. Only one portrait was verified at setup: Caitlin. Do not call scheduled, drafted or merely committed images published.

## Failures, cost and completion

If the scheduled run lacks image generation, binary upload, GitHub writes, or the reference asset, keep the live site intact and record the exact blocker. Report it once rather than requesting repeated approvals. If a missing capability blocks every next batch, pause this portrait task rather than loop uselessly. Temporary rate limits can wait for a subsequent run. Do not silently buy an image API service or expose credentials to make it work.

Set scheduled_execution_verified=true only after a real scheduled batch has generated, uploaded, deployed and verified its portraits. Update any builder-reported generation flags from actual executor evidence, not wishful constants. Leave the separate daily/weekly WNBA statistics updater running. Disable the portrait task when the existing queue is verified complete and report actual published/remaining counts. No guaranteed overnight completion was established.
