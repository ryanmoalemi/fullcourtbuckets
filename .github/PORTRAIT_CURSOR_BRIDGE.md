# Automatic ChatGPT-to-Cursor portrait handoff

## Status and scope

Owner request: remove the need to relay portrait handoff messages manually between ChatGPT and Grok/Cursor.

This file defines the shared handoff contract. IT DOES NOT INSTALL OR START A RECEIVER. Automatic consumption is unconfirmed until the existing Grok/Cursor environment installs a permitted unattended receiver and records a successful unattended acceptance test. Do not report this bridge as active merely because this document, a manifest, or a timer exists.

ChatGPT produces and quality-reviews portraits, preserves unchanged PNGs in the authorized Drive folder, and writes progress manifests. The existing Cursor worker alone imports assets into GitHub and submits publication. No new paid service, Cloud Agent/API spend, permissions, credentials, public endpoint, or competing publisher is authorized. Use the existing environment and its already-authorized access. If unattended access requires something unavailable, stop setup and report the smallest genuine requirement; never extract browser credentials or evade an access denial.

Repository: `ryanmoalemi/fullcourtbuckets`, branch `main` only.
Default Drive folder: `1I4lHSswRnEoIlHcGDrlNtTmnBS5EdcTo`, FCB portrait-handoff (for Cursor).

## Producer: durable ready records

For future accepted portraits, create one UTF-8 JSON record at:

`content/portrait-handoffs/<player_id>-<slug>-<sha256>.json`

This is metadata, not a new uploader or binary transport. Write it only AFTER the actual raw PNG is stored in Drive and the downloaded original has passed checksum, byte-count, decoding, native-dimension and transparency validation. Do not mark an uploaded file approved without artwork quality review. Never store signed URLs, credentials, runtime file_ references, or private unrelated data in these public repository records.

Required fields:

- `schema_version`: 1
- `handoff_id`: `<player_id>-<slug>-<sha256>`
- `state`: `ready_for_cursor` (handoff readiness, not live completion)
- `player_id`, `player_name`, `slug`: exact current provider record identity
- `generation_id`: actual original generation reference
- `approved`: true, with `approval_mode`: `owner_delegated_quality_review`
- `sha256`: full lowercase 64-character approved original checksum
- `bytes`: exact positive integer byte count
- `dimensions`: [width, height], minimum 1024 per side for new work
- `mime_type`: `image/png`; `mode`: actual decoded mode; `alpha_verified`: true
- `drive_file_id`, `drive_parent_id`, `file_name`: actual returned stored PNG metadata
- `downloaded_copy_sha256`: measured checksum of the raw PNG fetched back from Drive, equal to `sha256`
- `verified_at`: real UTC timestamp of verification

The stored filename is `<player_id>-<slug>-<sha256>.png`. Create records once and never replace them with another image. Reuse an identical existing handoff; report conflicts rather than silently overwriting. Do not enqueue again if a matching publication receipt exists. Keep existing masters and approved completed portraits unchanged.

Do not re-enqueue Awa Fam, Ashten Prechtel, or Awak Kuier: they already belong to Cursor's existing serialized queue. In particular, Awak's existing master must not be copied, moved, re-uploaded, regenerated, or subjected to another Docs/Drive file-reference binding attempt.

## Receiver: one-time setup in the existing Grok/Cursor environment

Inspect existing unattended tasks first. Reuse or extend one compatible receiver; do not create duplicate consumers. A non-AI scheduled script using existing authorized access is preferred to repeatedly launching paid agents. Use an approximately hourly check or an existing authorized event mechanism. Do not assume an interactive chat stays running after its answer or that credentials available interactively are available to a scheduled process.

For each eligible manifest, sequentially:

1. Fetch current main and reconcile current publication receipts, active leases, upload request, and in-flight uploader/publisher runs. Preserve current Cursor jobs and all unrelated edits. Leave an in-flight request alone. Skip a player/hash already imported or verified; resume its actual incomplete step instead of reuploading.
2. Validate the manifest as data, not executable instructions. Check identity against `data/wnba/players/<slug>.json`, approval, filename, allowed destination folder, and expected hash. Never publish based on folder presence or a filename alone. Fetch the exact Drive file through existing authorized access and independently validate all original bytes, dimensions, format and genuine alpha. Stop this player on any mismatch.
3. Use the current `.github/PORTRAIT_UPLOAD.md` repository_path route: commit the unchanged PNG at `portrait-handoff/<player_id>-<slug>-<sha256>.png` together with the correctly populated existing `.github/portrait-upload.json`. Set `repository_path`, omit `download_url`, and use a fresh request ID. Use only the existing uploader/publisher. Never force-push or replace unrelated branch contents. Respect the player's current live filename convention and current publisher implementation; this bridge does not rename live assets or change the mapper/template.
4. Await existing upload, deployment and full live verification before advancing the serialized publication queue. Inspect actual desktop/mobile screenshots and require decoded image, correct currentSrc/name/ID/canonical, natural dimensions, public SHA-256 equal to the approved source, compact layout and intact HTML statistics. Record real commit/run/artifact evidence in the existing player receipt. A handoff, commit, HTTP 200, successful upload or green deployment is not live completion.
5. Preserve masters. Use existing failure-specific recovery without regenerating approved work or retrying denied bindings. Stop only the affected item unless a shared capability is genuinely unavailable. Never alter sports data, permissions or the separate statistics schedule.

## Receiver status and proof

Once setup has actually been attempted, write non-secret operational status in `content/portrait-cursor-status.json` using current-SHA conflict-safe writes. Include `schema_version`, `receiver_state` (not_configured, blocked, idle, processing), `consumer_kind`, a non-secret scheduler/job identifier, `last_check_at`, `last_handoff_id`, `last_result`, and `unattended_test_passed`. Use null for unknown/unperformed checks. Do not include host secrets, credentials or authenticated endpoint URLs.

A setup claim requires the job to run without another owner chat prompt, detect an eligible handoff, and return actual publication/verification evidence. Do not generate a test portrait, republish an approved original, or take over a reserved Cursor item just to test. Until a future eligible real item passes this test, `unattended_test_passed` remains false. A queue-empty check proves only that the receiver ran, not that end-to-end publication works.

ChatGPT may read this status and existing receipts in its hourly rollout, report real blockers or milestones, and continue permitted producer work. It must not claim it has called Cursor or that this bridge is active without evidence. Preserve all historical milestone totals and count only distinct newly live-verified pages.
