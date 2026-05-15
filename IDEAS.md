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

## Quick wins

- **Search / filter.** Text box that filters rows by filename, game
  name, or slot name. Becomes essential as the list passes ~20 seeds.
- **Sort by game name.** Alphabetical, in addition to date / size / slots.
- **Copy seed ID to clipboard** from the row (small icon button).
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
- **Recently-hosted history.** Track which seeds were hosted and when
  via Seed Browser, surface a "recently hosted" filter or column. State
  lives in the same sidecar JSON used by tags.
- **Multi-folder support.** Scan more than just AP's `output_path` —
  e.g. an `~/Documents/AP-seeds/` archive of finished games. Set via
  Seed Browser settings, not `host.yaml`.
- **Re-generate seed** by invoking AP's Generate component on the
  original YAMLs (if discoverable from the multidata). Speculative —
  may not be feasible without manual YAML pointers.

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
