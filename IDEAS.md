# Post-v1 ideas

Things explicitly deferred from v1 (PLAN.md §2) plus anything else
worth thinking about after the foundation ships. Roughly ordered by
gut-feel value, not commitment.

## Per-slot detail (next natural step)

`Seed.slots` already has `(slot_num, slot_name, game_name)` per slot —
the v1 UI just collapses it. A row-expansion would surface that for
free, and is a stepping stone for everything below.

**Multidata investigation (2026-05-15).** Decoded a real 2-slot seed via
`Utils.restricted_loads`. Findings drive the items below:

- The `slot_info` entries are `NetworkSlot(name, game, type, group_members)`.
  We extract `name` and `game`; `type` (a `SlotType` enum: 0=spectator,
  1=player, 2=group) and `group_members` are dropped on the floor today.
- `payload["version"]` is the AP version that *generated* the seed
  (e.g. `(0, 6, 7)`).
- `payload["minimum_versions"]` carries `{'server': (M, m, p), 'clients':
  {slot_num: (M, m, p), ...}}` — the AP versions required to host / play
  this seed.
- `payload["datapackage"]` is keyed by game name. Each value has a
  `checksum` (SHA-1 fingerprint of the world's item/location tables) —
  this is **not** a semver apworld version, it's a content hash. Useful
  for a "the installed apworld matches the one used at generation"
  compatibility check, less useful for human display on its own.
- APWorld semver versions are **not** in the multidata. The closest
  proxy is the datapackage checksum.
- `payload["seed_name"]` equals the `AP_<digits>` filename id — nothing
  new to surface there.

Concrete features unlocked:

- **Expandable rows.** Click a row to reveal per-slot detail. Each slot
  line shows slot number, slot name, game, slot type (player / group /
  spectator), and whether a patch file is present in the zip.
- **Generator version label.** Show `payload["version"]` in the row or
  the expanded view: `AP 0.6.7`. Cheap, broadly useful.
- **Minimum-version hint.** When `minimum_versions["server"]` exceeds
  the locally installed AP's version, flag it on the row ("requires AP
  ≥ 0.5.0"). Avoid the user clicking Host on a seed their AP can't
  actually run.
- **Datapackage-checksum compatibility check.** Compare each game's
  checksum against the locally loaded datapackage; flag mismatches in
  the expanded slot row ("Jigsaw apworld differs from generation"). Hide
  the raw SHA from the UI by default — it's only useful for
  troubleshooting.

## Save-file awareness (high value, low complexity)

When AP's Host process runs a seed, `MultiServer` writes a sibling
`<seed_id>.apsave` next to the zip in the same output folder
(`MultiServer.py:613`). The file is a zlib-compressed pickled dict of
the server's running state; its presence is the definitive signal that
the seed has been hosted at least once. Decoded structure observed
2026-05-15 against a real save:

```
client_activity_timers     # tuple[(team, slot) → unix-ts]
client_connection_timers   # tuple[(team, slot) → unix-ts]
client_game_state          # dict[(team, slot) → ClientStatus int]
connect_names              # dict[player-name → (team, slot)]
hints / hints_used         # hint state
location_checks            # dict[(team, slot) → set[location_id]]
received_items             # dict[(team, slot) → list[item]]
group_collected / stored_data / name_aliases / random_state
game_options               # baked-in server-side options
version                    # save schema version (currently 2)
```

Each tier below stacks on the previous. All four reuse the scanner's
sibling-file pattern.

- **Hosted / unhosted marker.** Add `has_save: bool` to `Seed` —
  populated by `seed.path.with_suffix(".apsave").exists()`. Show a
  small "played" badge on the row or filter "unplayed only".
- **Last-hosted timestamp.** `apsave.stat().st_mtime` reflects the last
  save (= most recent host shutdown). Render "last hosted 3 days ago"
  next to the generation time, or as a secondary column. Becomes a
  fourth sort key.
- **Per-slot progress** from `location_checks`: total checks per slot
  comes from the multidata's `locations` map (already in `payload`);
  completed checks come from `len(location_checks[(team, slot)])`.
  Display `12 / 87` per slot in the expanded row. Decoding is `zlib +
  pickle.loads` and is gated on `save_version` to stay safe across
  schema bumps.
- **Completion state** from `client_game_state`. `ClientStatus.CLIENT_GOAL`
  (30) means the slot is finished. Show a ✓ on completed slots; tag a
  row as "complete" when all player slots are at goal. Drives a
  "completed seeds" filter, and a candidate for auto-archive
  workflows.

Note: this supersedes the standalone "Recently-hosted history" idea —
AP already maintains the history we'd otherwise track in a sidecar.

## Quick wins

- **Search / filter.** Text box that filters rows by filename, game
  name, or slot name. Becomes essential as the list passes ~20 seeds.
- **Sort by game name.** Alphabetical, in addition to date / size / slots.
- **Copy seed ID to clipboard** from the row (small icon button).
- **"Host on archipelago.gg" → open browser.** New row button that
  calls `webbrowser.open("https://archipelago.gg/uploads")`. User still
  picks the file manually on the upload page, but it cuts the
  "remember-the-URL, open-a-tab" friction. Zero protocol risk; no
  authentication required from us. Stretch shape lives under "Bigger"
  below.
- **Empty-spoiler edge case.** Some seeds have a `_Spoiler.txt` entry
  that's just the header (race mode partial). Detect and reflect in the
  Spoiler button state (e.g. show as "empty spoiler" rather than just
  enabled).
- **Persist sort preference** across sessions. Today every launch
  defaults to "date (desc)". One-line JSON sidecar in
  `~/Library/Application Support/Archipelago/seed_browser/state.json`.

## Bigger

- **Tags / favourites / user notes.** Sidecar storage next to each zip
  (e.g. `AP_<id>.seedbrowser.json`). Tag freeform strings, mark
  favourites, attach a short note ("Aug stream", "for retry"). Drives
  search/filter and ordering.
- **Per-slot patch extraction.** Right-click a slot row → save its patch
  (`.aplttp`, `.apmc`, etc.) to disk for sending to a player.
- **Batch operations.** Multi-select rows + bulk delete / reveal. Less
  obvious bulk operations (e.g. bulk host) probably aren't useful.
- **Multi-folder support.** Scan more than just AP's `output_path` —
  e.g. an `~/Documents/AP-seeds/` archive of finished games. Set via
  Seed Browser settings, not `host.yaml`.
- **Re-generate seed** by invoking AP's Generate component on the
  original YAMLs (if discoverable from the multidata). Speculative —
  may not be feasible without manual YAML pointers.
- **Deeper archipelago.gg integration.** The Quick-Wins "open browser"
  button is the safe baseline. A scripted upload exists as a stretch:
  POST to `/uploads` (the form route, no documented API) returns a
  redirect to `/seed/<uuid>`; a follow-up GET on `/new_room/<uuid>`
  redirects to `/host_room/<room_uuid>` — the URL players connect to.
  Investigation 2026-05-15 (`WebHostLib/upload.py:171`,
  `WebHostLib/misc.py:172`). Caveats: relies on a Flask session cookie
  (anonymous uploads work but room ownership is ephemeral); the site
  has upload size + rate limits set in their nginx/gunicorn config; no
  endorsed API contract, so this is fragile across webhost changes.
  Authenticated uploads tied to the user's archipelago.gg account
  (GitHub OAuth / passwordless email) are high-effort and likely
  brittle — defer indefinitely unless someone really wants it.

## Operational nice-to-haves

- **Cross-machine seed sync.** Out of scope for v1 (PLAN §2). Could be
  as simple as a "watched folder" pointed at iCloud/Dropbox.
- **Notification when a new seed lands** in the output folder.
  Watchdog plumbing is already in place; this is a UI affordance on
  top of it (e.g. a toast / snackbar) rather than just a silent refresh.
- **Drag-drop seed onto another app** — e.g. drag a row into Discord to
  share the zip. Kivy supports drag sources; viability depends on the
  target app.

## Explicit no

- **Telemetry.** No.
- **Auto-update apworlds on AP version bump.** Out of scope; AP's own
  apworld manager handles installs.
- **Anything that requires writing to AP's source tree.** Stay
  side-by-side; never touch core files.
