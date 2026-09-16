# Full Court Buckets: approved player-page rollout

The compact Caitlin Clark layout is the visual reference for every player page.
Run `rollout_player_design.py` after the existing page builder and portrait applier.
All names, numbers, team information and statistics remain HTML. Existing
statistics must not be changed by this design step.

## Approved visual specification

- Keep the existing purple gradient, circular outlines and faint outline number.
- No square number card behind a portrait.
- Name and portrait share the compact desktop and mobile row.
- Head and shoulders, not a long torso; straight bottom crop at the stats divider.
- Portrait reaches the right edge. No visible caption below the image.
- Use native transparency; preserve the exact approved Caitlin illustration.
- No player labels, numbers, logo, typography or decorative background baked into art.
- A longer name may use the provided smaller typography. Never abbreviate a name to fit.

## Production status

The rollout status and exact player worklist are generated from the live player
index, not a manually maintained count:

- `data/wnba/illustration-rollout.json`
- `data/wnba/illustration-queue.json`

A pending entry is not an illustration. An image belongs to one intended player
ID and slug. A copied Caitlin portrait, a generic face or a name-only placeholder
must never be counted as a finished player portrait. Repeated names with distinct
IDs are not silently merged. Verify each individual likeness and source context.

The existing `content/player-illustrations.json` remains the publication manifest.
An entry is published only after an actual local image exists, the player ID and
name agree, and the image has been reviewed. A generated draft is not automatically
approved. Artwork is not regenerated during the daily statistics refresh.

## Bulk production is not running

This change does not purchase a service, call an image generation API, schedule
image generation, or spend credits. It prepares the full worklist. Separate image
production is still required for profiles without approved artwork. The
BALLDONTLIE key is for statistics, not image generation, and must never be sent to
an image service.

For an unattended bulk producer, obtain the user's budget approval and a separately
funded image API credential. Put that credential in a dedicated repository secret,
not in chat, source code, client JavaScript or a public file. Native in-chat image
generation remains an alternative for individually produced batches. No API
credential is required merely to apply the layout or keep current statistics fresh.

Before a paid rollout, test the style on a small batch. Account for text/image
inputs and rework, not only the advertised output-image price. Do not promise a
hard billing cap without enforcing it in the actual producer. Do not silently
retry an ambiguous, possibly charged generation request. Keep a resumable ledger
and stop for budget exhaustion, uncertain identity or unsuccessful review.

## Verification

`python -m unittest discover -s automation -p 'test_*.py' -v`

The shared design reuses `apply_portraits.CSS`. The approved Caitlin page was
pixel-identical before and after the shared-layout pass at widths 320, 390, 430
and 1365 in the local browser test. External fonts were unavailable in that test;
it does not certify identical font loading on every browser or that every possible
phone height displays every long name above the fold.
