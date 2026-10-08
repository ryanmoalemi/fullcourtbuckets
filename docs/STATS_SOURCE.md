# Game stats for articles

Use `data/games/<YYYY-MM-DD>-<away>-<home>.json` as the primary stats source. The index is `data/games/index.json`. ESPN is only a cross-check, stored on the same file under `crosscheck`.

On public pages say: Full Court Buckets gathers its own game data and verifies it against official box scores.

Never name or link the data vendor, on the article or on any other public page.

If `crosscheck.mismatches` is not empty, the mismatch is in the JSON and in the workflow summary. Resolve it before review. Do not pick the number that sounds better. If `source` is `espn` and `fallback` is true, the site's own feed did not supply the game.

The short read next to the JSON is the `.md` file. The ESPN box-score link in that file can stay on the article.
