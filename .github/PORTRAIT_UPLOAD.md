# Approved portrait: whole-file upload

Owner workflow stays: generate one image, owner approves, upload original to its player folder, verify live. Do not generate another face merely because transport fails. Do not reduce resolution, manually copy base64 chunks, or create a new workflow per player.

## Proven route

The reusable `.github/workflows/portrait-upload.yml` receives `.github/portrait-upload.json`, downloads the WHOLE PNG, checks its exact SHA-256/byte count/player identity, commits it as `images/players/<slug>/portrait.png`, then dispatches the EXISTING fcb-wnba publisher. The existing folder mapper creates the image record automatically. The publisher verifies actual public pixels/files at desktop/mobile widths. No user API key or Dropbox connection is needed for this route.

Aja proof: upload run 35150035606, image commit b6c0afed62de7f1a4c9129d61b2363b4a38ef7b0, publication/live verification run 35150053814. Original PNG SHA-256 925c2dbc0c01e26b8ccbff0fea9090c608c6be35c84dde4b9a40ad08a1363554, 1,583,575 bytes, 1244x1264. Final Git blob 4ec072d05ae1fc4700a0d7f091e8f28b3834384c. Live output is byte-identical to the approved local source.

## Supplying a whole-file handoff from chat

1. Verify local approved source bytes and player ID/slug. Preserve the master in connected Drive under a unique player-ID/slug/checksum filename.
2. The ordinary Drive fetch `download_url` at `*.oaiusercontent.com` returned HTTP 403 in GitHub runners. Do not repeatedly retry that URL or call it a GitHub permission failure.
3. Proven supported handoff: create a TEMPORARY native Google Doc; call `batch_update_document` with `insertInlineImage`, `uri` set to the local source placeholder, and `image_uris` containing that same real local path. This uses runtime's whole-image upload handling, not base64.
4. Read the Doc with `fields="documentId,tabs(tabProperties,documentTab(inlineObjects))"`. The inserted inline image's `imageProperties.sourceUri` is the temporary direct original-file storage URL. Use that EXACT returned URL, not `contentUri` (a Google-rendered image) and not a guessed URL. Do not mix legacy inlineObjects and tabs in the field mask.
5. Read the current `.github/portrait-upload.json` SHA and replace it via GitHub update_file with a fresh request ID, exact player_id/player_name/slug, approved=true, the original SHA-256, byte count, dimensions, approval/generation context, master Drive file ID, and the sourceUri as download_url. Commit promptly: the signed source URL is short-lived. Never reuse an expired one or publish unrelated private data. Only the already-approved public illustration is transferred.
6. Wait for the uploader and its dispatched fcb-wnba run. The uploader scrubs the URL from the current request after transfer; its receipt is pending until live checks finish. Download `portrait-live-verification`, compare the original hash and actual dimensions, and inspect the actual screenshots before reporting completion. Mark the receipt/review status verified only after success.
7. Delete only the temporary Doc created for the handoff after the file has reached GitHub. Keep the private master and the original in the repository.

This is one reusable transport path. The temporary Doc is not part of the website and is not the published image. No resampling, screenshot extraction or recompression occurs; exact original-byte equality is mandatory. The upload does not generate any additional player images. Bulk generation remains paused under the latest one-player approval process.
