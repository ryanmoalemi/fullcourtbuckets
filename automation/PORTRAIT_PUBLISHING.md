# Player portrait approval and publication

The owner's latest instruction overrides earlier unattended approval: show ONE intended player's image, obtain approval, publish that exact version, verify the public result, then show the next image. The previous bulk-generation task remains paused. Do not change the approved compact design.

## Durable identity and source storage

Immediately save each full-resolution master under a unique name containing the permanent player ID, player slug and source checksum. Never reuse `confident_basketball_athlete_portrait.png` for multiple people. Record the generation/attachment reference and preserve the actual master bytes, not only a temporary sandbox path. Use the original approved master for every export. A missing master is a blocker, not permission to substitute a new face or enlarge a thumbnail.

Map each approved export by exact provider ID, slug, name, immutable player-specific asset path, decoded width/height and `asset_sha256`. Record source dimensions, source checksum, export settings and approval context. Normally export transparent 640x650 WebP, quality 95, method 6, exact=true, from a master at least 1024px on each side. No upscaling or embedded text. All names and statistics remain HTML.

## Required gate before deployment

`automation/verify_portraits.py --create-plan` verifies each approved mapping against the actual player JSON, requires a checksum, decodes the real image bytes with Pillow, checks real dimensions and alpha, enforces resolution/provenance, and rejects duplicate image bytes assigned to different people. A legacy resolution exception never bypasses decoding. The existing page build is then checked in Chromium at 1365x850, 390x844 and 320x568. A failure prevents this workflow's deployment.

## Required gate after deployment

The same frozen publish plan is downloaded from that run's artifact, not reconstructed from potentially changed main. Chromium and WebKit visit the actual public player URL at all three viewports. Each check must pass:

- Correct primary name, canonical player URL and provider ID.
- Exactly one expected image, successful browser `image.decode()`, and actual natural dimensions matching the approved export.
- Correct `currentSrc` path, image HTTP response, and SHA-256 of public bytes equal to the approved export.
- Side-by-side name/portrait, no page overflow, no square number card or image caption, and stats immediately below the hero. Fold position is recorded, not guessed.
- Statistics remain present. Quarantined pages are checked for zero image elements rather than treated as completed portraits.

Screenshots and reports are uploaded as `portrait-local-verification` and `portrait-live-verification`. The deployment job fails if any live check fails. Do not mark an image verified or tell the owner it is live based on a commit, HTTP 200, successful deployment step, or filename alone. Provide the page and screenshot evidence, review the intended artwork visually, then proceed to the next approval. Hash matching verifies file identity; it cannot independently establish a person's likeness.

The separate statistics schedule is preserved. Do not resume autonomous image generation under the old blanket approval.
