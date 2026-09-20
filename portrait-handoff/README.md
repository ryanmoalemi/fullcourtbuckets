# Portrait handoff tray

Temporary inbound originals for the existing `portrait-upload.yml` uploader. This directory is not a website publishing folder and is not a substitute for `images/players/<slug>/portrait.png`.

Place exactly one accepted PNG here, named:

`<player_id>-<exact-slug>-<sha256>.png`

Then set `.github/portrait-upload.json` with that `repository_path` and **no** `download_url`. The uploader copies the identical bytes into the player folder and `portrait-masters/`, then deletes this handoff file.

Do not put drafts, screenshots, resized exports, or a second format here. Do not use this directory to bypass a connector security denial by renaming or re-encoding a blocked file.
