# Approved portrait: whole-file upload

Owner workflow stays: generate one image, owner approves, upload original to its player folder, verify live. Do not generate another face merely because transport fails. Do not reduce resolution, manually copy base64 chunks, or create a new workflow per player.

## Proven route

The reusable `.github/workflows/portrait-upload.yml` receives `.github/portrait-upload.json`, obtains the WHOLE PNG, checks its exact SHA-256/byte count/player identity, commits it as `images/players/<slug>/portrait.png`, then dispatches the EXISTING fcb-wnba publisher. The existing folder mapper creates the image record automatically. The publisher verifies actual public pixels/files at desktop/mobile widths. No user API key or Dropbox connection is needed for this route.

Aja proof: upload run 35150035606, image commit b6c0afed62de7f1a4c9129d61b2363b4a38ef7b0, publication/live verification run 35150053814. Original PNG SHA-256 925c2dbc0c01e26b8ccbff0fea9090c608c6be35c84dde4b9a40ad08a1363554, 1,583,575 bytes, 1244x1264. Final Git blob 4ec072d05ae1fc4700a0d7f091e8f28b3834384c. Live output is byte-identical to the approved local source.

Ashlon Jackson proof that the Google Doc `sourceUri` path can still work: upload run 35473176718, publication run 35473185147, SHA-256 23db58ae84a633670083527a4061ade363932f6dca5d1adc4e5dc3417fd4473d. That success does **not** mean BLOCKED_FILE_REFERENCE is fixed. Ashten Prechtel and Awa Fam later failed with the same error after using the exact runtime `file_...` form.

## Two supported ways to supply the original

The uploader accepts **exactly one** original-file source:

1. `download_url` — the existing short-lived Docs `imageProperties.sourceUri` (OAI/Azure hosts only).
2. `repository_path` — a Google-independent file already in the same git commit at `portrait-handoff/<player_id>-<slug>-<sha256>.png`.

Both paths validate the same way and store identical bytes at `images/players/<slug>/portrait.png` and `portrait-masters/<player_id>-<slug>-<sha256>.png`. Live Chromium/WebKit checks remain mandatory. Upload or a green Actions run is not completion.

Do not send both fields. Do not add new URL hosts to evade a blocked connector call. Do not use `contentUri`, guessed URLs, screenshots, recompression, or base64 chunking.

## Google-independent GitHub handoff

GitHub itself can store a binary blob. This repository now consumes that blob through the existing uploader. That is **not** a claim that the ChatGPT GitHub connector can currently bind a generated PNG.

### Discover the live ChatGPT GitHub connector first

Do not invent a tool schema. In the same ChatGPT run:

1. List the connected GitHub actions. Look for `create_blob`, `create_tree`, `create_commit`, `update_ref`, and any `create_or_update_file` / `update_file`.
2. Read the actual `create_blob` parameter schema, including `content`, `encoding`, size limits, and whether a `file_uri` / file-reference field exists.
3. Run this distinguishing test on the **same already-accepted original** (no regeneration):
   - If the schema takes `content` plus `encoding=base64` and does **not** require a connector file reference: pass **one** whole-file Base64 of the original PNG. This is Git's native blob encoding, not the forbidden "Base64 chunking" workaround of splitting the file into many text pieces.
   - If the schema requires `file_uri` / a runtime `file_...` reference: try that exact reference **once**. If the result is `BLOCKED_FILE_REFERENCE`, stop. Do not retry the same reference on a timer. Do not evade through Drive, Docs, a renamed file, or a rewritten URL.
   - Record the documented size limit. Typical portraits are ~1.5–2.2 MB (larger as Base64). If the tool cannot carry that payload, ChatGPT cannot complete this handoff automatically.
4. Capture a redacted envelope (action name, argument **types**/keys, error code, HTTP status, correlation id, whether the provider was contacted). Never log tokens or signed URLs.
5. If the blob is created, add it on current `main` as `portrait-handoff/<player_id>-<slug>-<sha256>.png` with `create_tree` / `create_commit` / `update_ref` (no force-push). Then write `.github/portrait-upload.json` with `repository_path` and omit `download_url`.

Example request after the PNG is in git:

```json
{
  "request_id": "<player_id>-<sha12>-upload-<utc>",
  "player_id": 67076,
  "player_name": "Awa Fam",
  "slug": "awa-fam",
  "approved": true,
  "sha256": "<64 hex>",
  "bytes": 1976438,
  "dimensions": [1185, 1327],
  "repository_path": "portrait-handoff/67076-awa-fam-<64 hex>.png"
}
```

The uploader copies those exact bytes, writes the GitHub master, deletes the handoff file, scrubs the request, and dispatches `fcb-wnba.yml`. Inspect `portrait-live-verification` before calling the page complete.

### Smallest owner action if ChatGPT cannot carry the bytes

Manual download/upload is a fallback, not the autonomous path. Use it only when the generating ChatGPT conversation still has the original PNG and connector binding cannot deliver it:

1. In that conversation, download the generated original PNG (not a screenshot or thumbnail).
2. On GitHub, Upload files into `portrait-handoff/<player_id>-<exact-slug>-<sha256>.png` on `main`. Do not resize or re-export.
3. An authorized agent then submits the `repository_path` request above and waits for live verification.

Do not ask the owner to run the publisher, edit player HTML, or post code.

## Supplying a whole-file handoff from chat (Google Docs path)

Keep using this path when the connector actually accepts the runtime file reference. It remains intermittent.

1. Verify local approved source bytes and player ID/slug. Prefer preserving the master in connected Drive under a unique player-ID/slug/checksum filename. If Drive rejects the exact runtime `file_...` reference once, do not treat that as a GitHub permission failure. Continue with either the temporary-Doc handoff below **or** the Google-independent GitHub handoff above. The uploader preserves the same exact PNG in GitHub under `portrait-masters/<player_id>-<slug>-<sha256>.png`.
2. The ordinary Drive fetch `download_url` at `*.oaiusercontent.com` returned HTTP 403 in GitHub runners. Do not repeatedly retry that URL or call it a GitHub permission failure.
3. Previously successful Docs handoff: create a TEMPORARY native Google Doc; call `batch_update_document` with `insertInlineImage`, setting the request `uri` placeholder and `image_uris` to the exact runtime-generated `file_...` reference. Mounted `/mnt/data/...` paths have returned `BLOCKED_FILE_REFERENCE`. The runtime-reference form has both succeeded and later failed; do not declare it fixed after one success.
4. Read the Doc with `fields="documentId,tabs(tabProperties,documentTab(inlineObjects))"`. The inserted inline image's `imageProperties.sourceUri` is the temporary direct original-file storage URL. Use that EXACT returned URL, not `contentUri` (a Google-rendered image) and not a guessed URL. Do not mix legacy inlineObjects and tabs in the field mask.
5. Read the current `.github/portrait-upload.json` SHA and replace it via GitHub `update_file` with a fresh request ID, exact player_id/player_name/slug, approved=true, the original SHA-256, byte count, dimensions, approval/generation context, optional master Drive file ID, and the sourceUri as `download_url`. Commit promptly: the signed source URL is short-lived. Never reuse an expired one or publish unrelated private data. Only the already-approved public illustration is transferred.
6. Wait for the uploader and its dispatched fcb-wnba run. The uploader scrubs the URL from the current request after transfer; its receipt is pending until live checks finish. Download `portrait-live-verification`, compare the original hash and actual dimensions, and inspect the actual screenshots before reporting completion. Mark the receipt/review status verified only after success.
7. Delete only the temporary Doc created for the handoff after the file has reached GitHub. Keep any Drive master that exists. The uploader also keeps the exact original in the repository under `portrait-masters/`; this GitHub master is authoritative when Drive preservation was unavailable.

This is one reusable transport path. The temporary Doc is not part of the website and is not the published image. No resampling, screenshot extraction or recompression occurs; exact original-byte equality is mandatory. The upload does not generate any additional player images.

## What BLOCKED_FILE_REFERENCE is not

- Not a missing `images/players/<slug>/` folder. The uploader creates that folder.
- Not proof that GitHub write permission is missing when other GitHub writes in the same run succeed.
- Not automatically a stale `/mnt/data` path. Distinguish schema mismatch from a later binding denial.
- Not fixed because Antonia Delaere or Ashlon Jackson later published.
- Not a preserved original. A generation ID, runtime `file_...` string, and SHA-256 are identifiers. If Drive and GitHub never received the bytes, the original is not recoverable from those strings in a later session.
