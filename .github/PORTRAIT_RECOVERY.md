# Portrait recovery procedure

Owner request, 2026-09-17: fix routine blockers autonomously and report actual live progress. This procedure supplements PORTRAIT_AUTOPILOT.md; it does not grant permissions, remove approval-quality checks, or authorize bypassing a connector's access or security restrictions. Use the existing uploader, folders, publisher and verifier. Do not create new per-player infrastructure.

## Before work: reconcile, protect, and claim

1. Read the current main branch, autopilot ledger, recovery incidents, upload request and the selected player's receipt. Respect an unexpired worker lease. Do not overwrite another run's state or start a competing publication.
2. Compare the saved original checksum, repository file and live verification evidence. A stale pending/blocked record may already have a successful publication. Reconcile it, not reupload or regenerate it.
3. Never regenerate the approved completed Caitlin Clark, Angel Reese, A'ja Wilson, Breanna Stewart, Sabrina Ionescu, Napheesa Collier, Paige Bueckers, Kelsey Plum, Aliyah Boston or later completed portraits. Caitlin and Angel's explicitly approved historical 640x650 files are protected exceptions. The newer minimum-size rule is for new work, not permission to redo approved finished work. Protect by permanent ID and approved hash, not surname.
4. Preserve the original PNG and its player-ID/slug/hash mapping before attempting transport. Keep a durable Drive master and enough evidence to resume from the failed step.

## Failure-specific recovery

### Ordinary missing, stale or invalid file reference

Confirm the actual error and schema. Fetch the exact preserved Drive master through the connected download action, use its returned mounted file path/reference as required by the destination action, and verify checksum, byte count, dimensions and alpha. Retry the supported upload with that current reference once. Do not guess paths or label another image as the source. Do not regenerate or resize.

BLOCKED_FILE_REFERENCE is NOT automatically a stale-path error. If the error indicates a security, egress or authorization restriction, stop that denied operation. Do not evade the restriction by copying/renaming the file, changing hostnames, converting signed URLs, using a different endpoint, or relabeling its provenance. Record the restriction and continue only independent work permitted by the tools. Request the smallest necessary owner action when the connector actually requires it.

### Expired signed URL or download HTTP 403

Read the failure, check expiration, and distinguish source-storage denial from GitHub authorization. When ordinary expiration is established, obtain a fresh original-file URL through the supported connector handoff and submit promptly through the existing upload request. Use only the exact URL returned by the tool. Never replace an oaiusercontent hostname with an inferred blob-storage hostname. Never use Google's resampled contentUri. One immediate fresh-link retry; then defer the same preserved master. An unexplained repeated 403 is not permission to bypass the access check.

### Rate limit, timeout, service unavailable or HTTP 5xx

Honor Retry-After where available. Make no more than one bounded retry in the current run. Otherwise persist a next_retry_at timestamp for the next eligible scheduled run. Do not create a new image to fix a networking error.

### GitHub tool discovery, authorization and SHA conflicts

Discover the actual write action and attempt the authorized operation before describing access as read-only. A missing action in the initial list is not an access denial. For a normal 409/non-fast-forward conflict, reread current content/ref and merge only the intended changes, then retry at most twice with the newest SHA. Never force-push. A genuine permission/re-authentication requirement must be reported accurately, without attempting to grant privileges or exposing credentials.

### Failed deployment or live-image check

Determine whether upload, build, deployment, propagation or image verification failed. Resume only that step using the existing image. Check the exact versioned image path, browser decode, player ID/name/canonical, dimensions and public SHA256. Allow a bounded propagation recheck. Do not count a successful upload as a successful live page. Do not remove or lower an image-integrity check to make a run pass.

If a bad replacement is actually live, restore only that player's previously verified image/mapping using the latest branch state and the existing publication route, then verify the restored public page. Never roll back the whole repository, change sports data or discard concurrent edits. If safe restoration cannot be established, report the affected public page and preserve evidence.

### Wrong likeness, wrong format, inadequate resolution or corrupt bytes

Do not publish it. Allow at most two corrective generations for that player, each with a unique filename. Then park ONLY that player for later review and continue another eligible player. Never shrink originals, upscale thumbnails, add a poster background or relax the uniform portrait specification to solve a failure. File-transfer failures never justify regenerating an already accepted master.

## Retry queue rather than global shutdown

Persist each unresolved incident under content/portrait-recovery-incidents/<exact-player-slug>.json with player_id, stage, error_code, attempt_count, first_seen_at, last_attempt_at, next_retry_at, preserved_master_id, source_sha256, affected_live_page, resolution_status and notified_status. Do not store signed URLs, tokens or credentials in incident logs.

Use backoff of 1 hour, 2 hours, 4 hours, then at most once every 8 hours for repeated transient failures. Eligibility is evaluated in the existing hourly task; do not invent sub-hour scheduled checks. A successful retry resets the incident. A player-specific problem must not disable the task or block unrelated eligible players.

If a required capability is unavailable for every upload, keep the recovery schedule enabled and perform one due capability check instead of repeatedly generating unusable work. Limit the unsent preserved-image backlog to three; then perform recovery-only runs until delivery works. Explain that production is waiting for recovery, not continuing successfully. Explicit user cancellation and actual access restrictions remain binding. Do not continually retry a security denial; notify and wait for the required authorization change.

## Live completion and accurate reporting

Completion requires the existing verifier's exact original-file match, decoded dimensions, correct player mapping and Chromium/WebKit desktop/mobile checks. Inspect the selected player's actual screenshots. Preserve the compact page design and all separate HTML statistics.

Count distinct newly updated player pages, not retries, failed attempts, stale-record reconciliation of work published before the reporting window, or repeat checks of previously completed players. Deduplicate by player ID and approved asset hash. The 2026-09-17 status check found seven genuinely new verified pages since the previous blocker exchange: Kelsey Mitchell, Aaliyah Edwards, Azura Stevens, Betnijah Laney-Hamilton, Aicha Coulibaly, Alysha Clark and Alyssa Thomas. A'ja and Sabrina were only reconfirmed and must not inflate that count.

Keep the existing ten-page milestone baseline. The on-demand seven-page status report is not a new ten-page milestone and does not reset the counter. At the next ten-page milestone, include all ten player names and their direct public page links here in ChatGPT; also link any smaller final completion batch.

Report a newly detected incident once in the detecting run, saying whether it recovered, whether the live page changed, and whether help is needed. Send a follow-up for recovery or a material change, not every identical retry. Ask the owner only for a truly necessary action unavailable through authorized tools. No routine approval, posting or manual file upload requests. Push/email delivery must not be claimed without evidence.
