# Post-v1 ideas

Things explicitly deferred from v1 (PLAN.md §2) plus anything else
worth thinking about after the foundation ships. Roughly ordered by
gut-feel value, not commitment.

## Per-slot detail (next natural step)

`Seed.slots` already has `(slot_num, slot_name, game_name)` per slot —
the v1 UI just collapses it. A row-expansion would surface that for
free, and is a stepping stone for everything below.

- **Expandable rows.** Click a row to reveal per-slot detail. Each slot
  line shows slot number, slot name, game, and whether a patch file is
  present in the zip (we already track this implicitly).
- **Datapackage / world versions.** Investigate what `payload` in
  `_decode_slot_info` actually contains beyond `slot_info` — AP's
  multidata has a `datapackage` dict with per-game `version` or
  `checksum`. If those match the apworld's own version (varies per
  world), surface them in the expanded row. Spike against a real
  multi-game seed before committing to a UI.
- **Seed name vs filename.** AP's multidata carries an internal
  `seed_name` distinct from the `AP_<digits>.zip` filename. Show it
  somewhere — at least in the expanded view.

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
