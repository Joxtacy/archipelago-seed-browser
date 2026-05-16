# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An Archipelago Launcher add-on, shipped as a single `seed_browser.apworld`
that users drop into AP's `custom_worlds/` directory. It registers a
`Type.TOOL` tile in the launcher and opens a standalone Kivy window that
lists local multiworld seed zips with per-seed actions (host, open
spoiler, reveal, delete, extract patch).

Target AP version: **0.6.7**. Python: `>=3.11,<3.14` (AP's `ModuleUpdate`
hard-blocks 3.14+). Project uses `uv` for env + dependency management.

## Common commands

```sh
uv sync --all-extras --dev            # install deps into .venv
uv run ruff check                     # lint
uv run pytest                         # run unit tests
uv run pytest tests/test_scanner.py   # single test file
uv run pytest -k _format_size         # single test by name
./scripts/build_apworld.sh            # build dist/seed_browser.apworld
python scripts/build_icon.py          # regenerate seed_browser/icon.png
```

Multidata-decoding tests require AP on the import path. Enable with
`ARCHIPELAGO_SRC=/path/to/Archipelago uv run pytest` — `tests/conftest.py`
prepends it to `sys.path` and otherwise the AP-dependent tests skip.

Releases are tag-driven (`v*` → `.github/workflows/release.yml`). See
`RELEASING.md` — keep `pyproject.toml` `version` and (on stable tags only)
`seed_browser/archipelago.json` `world_version` in sync with the tag.

## Architecture

### Module layout
- `seed_browser/__init__.py` — apworld entry point. Imports of
  `worlds.LauncherComponents` / `worlds.AutoWorld` are guarded so the
  package can be imported in tests without AP on `sys.path`. Registers a
  `Component(Type.TOOL, func=_launch)` and a hidden `World` stub
  (`_seed_browser`) that exists only to satisfy the apworld loader.
- `seed_browser/browser.py` — the Kivy app. **All Kivy/KivyMD imports
  happen inside `_run_app`** so importing this module from the launcher
  costs nothing. Pure helpers (`filter_seeds`, `sort_seeds`,
  `_format_seed_row`, `_format_seed_footer_lines`, `_format_slot_progress`,
  `_format_size`) are at module scope so they can be unit-tested without
  Kivy.
- `seed_browser/scanner.py` — seed-zip introspection. Returns `Seed`
  dataclasses from `scan_seed` / `scan_directory`.
- `seed_browser/actions.py` — every filesystem/process side effect (host,
  open spoiler, reveal, delete, extract patch). UI layer stays
  declarative; actions either succeed silently or raise.
- `seed_browser/games.py` — patch-suffix → game-name map sourced from
  `worlds.Files.AutoPatchRegister`. Unused by v1 but kept as a thin shim.
- `seed_browser/ui/` — empty placeholder package, reserved for future
  widget extraction. Do not invent files here unless splitting `browser.py`.

### apworld packaging
`scripts/build_apworld.sh` zips the `seed_browser/` directory (excluding
`__pycache__`/`*.pyc`) into `dist/seed_browser.apworld`. The apworld
loader treats this zip as a Python package — every runtime file must live
under `seed_browser/`. `seed_browser/archipelago.json` is AP's
metadata file (compatible_version, world_version).

### Seed data flow
For each `AP_<id>.zip` under AP's resolved `output_path()`:
1. **Namelist scan** (cheap): spoiler presence, multidata presence,
   per-slot patch suffixes via `AP_<id>_P<slot>_<player>.<suffix>` regex.
2. **Multidata decode** (authoritative): `.archipelago` entry is
   `[format_byte][zlib(pickle)]` decoded via AP's `Utils.restricted_loads`
   (sandboxed unpickler). Yields `slot_info` (slot→name/game/type),
   generator version, min server version, and `locations` (slot→total
   check count).
3. **Sibling `.apsave` decode** (when present): zlib-compressed pickle
   written by `MultiServer._save`. Yields per-slot checked counts and
   completion (`ClientStatus.CLIENT_GOAL == 30`). Only team 0 is read —
   multi-team is intentionally out of scope.

Multidata is authoritative for slot listing because patch filenames only
cover ROM-based slots; server-only games (Jigsaw, ChecksFinder) have no
entry in the zip namelist.

Seed mtime is taken from the `.archipelago` zip entry's `date_time`
(survives file copies/syncs that clobber filesystem mtime) and falls back
to `path.stat().st_mtime` if the multidata is unreadable.

### UI shape
`browser.py` builds a single-window MD layout: header (output path +
Refresh), search field, sort bar (Date/Size/Slots/Last hosted/Game),
scrolling `MDList` of `MDCard` rows, status footer. Rows are collapsed
by default; clicking `+` expands a per-slot detail panel.
`self._expanded: set[Path]` survives `_refresh()` so toggle state is
preserved across rescans. `self._seeds_cache` holds the last scan;
sort/filter/expand-toggle re-render from it without touching disk.

`watchdog` is soft-imported. When present, `_start_watcher` debounces
filesystem events via `Clock.schedule_once(..., 0.5)` and re-scans on the
main thread. When absent, the Refresh button is the only refresh path.

### Action quirks worth knowing
- **Host (macOS)**: `Launcher.launch` uses `open -a Terminal.app <argv>`,
  which makes `open` interpret argv as files-to-open rather than a
  command. `actions._macos_terminal_command` bypasses with an
  `osascript` `do script` so MultiServer actually receives the seed
  path. Keep the single-`tell` block — splitting into two top-level
  `tell` directives launches Terminal twice and leaves a stray empty
  window.
- **Delete**: prefers `send2trash` (soft-imported); falls back to
  `Path.unlink`. Always requires `confirmed=True` — the UI drives the
  confirmation dialog.
- **Extract patch**: pins on `_P<slot>_` so it can't grab another slot's
  patch with the same suffix; writes flat next to the seed zip,
  stripping any zip-internal path.

### Errors are surfaced, never crashed
The launcher does not wrap `Component.func` in try/except
(`Launcher.py:412-423`), so a raise propagates and kills the launcher
process. The entry point in `seed_browser/__init__._launch` and the app's
per-action `_do_action` both catch broad `Exception`, log, and (for
actions) write the message into the status label. Preserve this — never
let UI handlers raise.

## Conventions

- Ruff is configured with `line-length = 100`, `target-version = "py311"`,
  selects `E,F,I,B,UP`. Before committing, run both
  `uv run ruff format` (to apply formatting) and `uv run ruff check`
  (to catch lint). `check` alone won't reformat code.
- `from __future__ import annotations` is used throughout — keep it on
  new modules.
- Dataclasses use `slots=True`.
- Soft-imports (`watchdog`, `send2trash`, AP modules) live behind
  `try/except ImportError`. Don't make any of them hard requirements —
  the package must import without AP for tests, and the apworld must run
  on AP installs that don't have `watchdog`/`send2trash`.
- Tests for pure helpers go in `tests/test_*.py` with no Kivy import;
  AP-dependent tests check `ap_available` (fixture in `conftest.py`)
  and skip when AP isn't importable.

## Version control

This repo is colocated `jj` + `git`. Per global preference, use `jj`
commands by default (`jj describe`, `jj new`, `jj log`, `jj diff`,
`jj bookmark set`, `jj git push`). Tags currently still require
`git push origin <tag>` since `jj git push` doesn't push tags — see
`RELEASING.md`.
