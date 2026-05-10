# Archipelago Seed Browser — Implementation Plan

A launcher add-on (distributed as an `.apworld`) that lists locally generated
multiworld seeds, surfaces what games and players are in each, and exposes
common per-seed actions (host, view spoiler, reveal in file manager, delete).

This document is the working spec. It is written to be read by Claude Code as
project context **and** by Jesper as a checklist. Phases are sequential;
do not skip ahead. Each phase has explicit verification — run it before
declaring the phase done.

---

## 1. Goals (v1)

- Registers as a tile in the Archipelago Launcher under the Tools section.
- Opens a window listing every `AP_*.zip` in the user's output directory.
- Each row shows: timestamp, games (with counts when duplicated), slot names,
  number of slots, file size, whether a spoiler log is present.
- Per-row actions: **Host this seed**, **Open spoiler**, **Reveal in file
  manager**, **Delete** (with confirmation).
- Refreshes when the output folder changes, or via an explicit refresh button.
- Game-name detection works dynamically by inspecting the patch suffixes
  declared by registered worlds — no hardcoded extension table.
- Ships as a single `.apworld` artifact installable by drop-in.

## 2. Out of scope for v1

These are explicitly deferred. Do not build them in v1, even if they look
small. They go in `IDEAS.md` for later.

- Tags / favourites / user notes (sidecar storage).
- Search and filtering UI.
- Batch operations across multiple seeds.
- Per-slot patch extraction.
- Cross-machine seed sync.
- Telemetry of any kind.

## 3. Prerequisites

Before starting Phase 1, confirm:

- A working Archipelago install is available locally for testing. Either a
  cloned `ArchipelagoMW/Archipelago` repo (preferred — easier to read source)
  or a normal user install with a writable `custom_worlds/` directory.
- Python version matches what the target AP install uses. Check the AP repo's
  `setup.py` / `requirements.txt`. Pin the dev environment to that.
- At least 2–3 real generated seed zips exist in the AP output folder, ideally
  covering more than one game, for visual testing.

If any of these are missing, **stop and ask the user** — do not invent test
fixtures or guess versions.

## 4. Decisions to confirm before Phase 1

Claude Code: present these to the user and wait for answers before writing
code. Do not assume defaults.

1. **UI library.** Recommendation: **Kivy via AP's `kvui.py`** — fits the
   launcher's look, no extra dependencies for end users. Alternative: Tk
   (faster to prototype, visually inconsistent). Pick one and commit.
2. **Repo name.** Default suggestion: `archipelago-seed-browser`. Confirm.
3. **License.** Match Archipelago's (MIT) unless told otherwise.
4. **Module / apworld name.** Internal package name, e.g. `seed_browser`.
   This becomes the folder inside the `.apworld` zip.
5. **Output path discovery.** Read from `host.yaml`
   (`general_options.output_path`) via AP's own `Utils` module, falling back
   to AP's default. Confirm that's the desired behavior vs. a tool-specific
   override.

## 5. Reference reading (do this first, in this order)

Before any implementation, Claude Code should read the following from the
local AP source and write a short `NOTES.md` summarizing the actual API
surface — names, signatures, and any version differences observed.

1. `worlds/LauncherComponents.py` — `Component` class, `components` list,
   `Type` enum, `launch_subprocess`, `icon_paths`.
2. `Launcher.py` — how components are discovered, rendered, and dispatched.
3. `kvui.py` — base widgets, theming, app class, any list/recycleview
   helpers.
4. `Utils.py` — `user_path`, `local_path`, `home_path`, config loading.
5. `worlds/AutoWorld.py` — `AutoWorldRegister`, how to enumerate registered
   worlds and their patch suffixes / display names.
6. `MultiServer.py` (skim only) — to understand what a `.archipelago` file
   is and how Host launches it; we will shell out to the existing Host
   component, not reimplement.
7. One existing community apworld that registers a launcher component
   (e.g. APWorld Manager if accessible) — confirm the registration pattern
   actually works as documented.

The output of this step is `NOTES.md`. **Do not proceed to Phase 1 until
`NOTES.md` exists and has been reviewed.** If anything in that file
contradicts assumptions in this plan, stop and flag it.

## 6. Suggested repo layout

```
archipelago-seed-browser/
├── README.md
├── PLAN.md                    # this file
├── NOTES.md                   # written in reference-reading step
├── IDEAS.md                   # post-v1 ideas land here
├── LICENSE
├── pyproject.toml             # dev deps only; runtime deps come from AP
├── .gitignore
├── seed_browser/              # the apworld package
│   ├── __init__.py            # registers the Component
│   ├── browser.py             # window / app entry point
│   ├── scanner.py             # zip introspection
│   ├── games.py               # patch-suffix → game-name resolution
│   ├── actions.py             # host / spoiler / reveal / delete
│   └── ui/
│       ├── __init__.py
│       ├── main_window.py
│       └── seed_row.py
├── tests/
│   ├── fixtures/              # tiny synthetic AP_*.zip files
│   ├── test_scanner.py
│   ├── test_games.py
│   └── test_actions.py
├── scripts/
│   └── build_apworld.sh       # zips seed_browser/ into SeedBrowser.apworld
└── .github/workflows/
    └── release.yml            # builds the apworld on tag push
```

## 7. Phased plan

### Phase 1 — Foundation: tile appears, opens a window

**Goal.** Installable `.apworld` that puts a tile in the launcher and opens
an empty window when clicked.

**Tasks.**

1. Initialize the repo with the layout above (empty modules, `pyproject.toml`,
   `.gitignore`, MIT `LICENSE`, stub `README.md`).
2. Implement `seed_browser/__init__.py` to register a `Component` with the
   launcher. Use `Type.TOOL`, `func=launch_browser` where `launch_browser`
   imports lazily from `seed_browser.browser` and calls a `run()` entry
   point. Lazy import is mandatory — don't pull Kivy at module import time
   or the launcher slows down.
3. Add a minimal `World` stub with `hidden = True` so the apworld
   loader has something to register but the stub never appears in yaml
   templates or the game picker. `hidden` is the literal attribute name
   on `worlds.AutoWorld.World` in 0.6.7 (`AutoWorld.py:313`). Confirmed
   in `NOTES.md` §3.4.
4. Implement `seed_browser/browser.py` with a `run(args)` function that
   opens a single empty window with the title "Seed Browser" and a close
   button. No data, no list yet.
5. Write `scripts/build_apworld.sh` — zips the `seed_browser/` directory
   into `SeedBrowser.apworld`. One-liner with `zip -r`.

**Verification.**

- Run `scripts/build_apworld.sh`, drop the resulting `.apworld` into the
  test AP install's `custom_worlds/`, launch the launcher, confirm the
  tile appears with the correct label and (placeholder) icon.
- Click the tile, confirm the empty window opens without errors in the
  console.
- Close the window, confirm it doesn't crash the launcher.

**Done when.** All three verification steps pass on the user's machine.
Commit and tag `v0.1.0-foundation`.

---

### Phase 2 — Zip scanning + read-only list

**Goal.** The window shows real data from the user's output folder.

**Tasks.**

1. Implement `seed_browser/games.py`:
   - `build_extension_map() -> dict[str, str]` that walks
     `worlds.Files.AutoPatchRegister.file_endings` and returns a
     `{".aplttp": "A Link to the Past"}` map by reading
     `handler_class.game` for each `(suffix, handler_class)` pair.
     `AutoPatchRegister.file_endings` is the single authoritative
     `{suffix: handler}` registry populated at import time
     (`worlds/Files.py:30`). Server-only games (ChecksFinder etc.)
     have no patch container and are naturally absent. Patch suffix is
     NOT a `World` attribute in 0.6.7 — see `NOTES.md` §3.4.
   - Cache the result; rebuild only on explicit refresh.
2. Implement `seed_browser/scanner.py`:
   - `Seed` dataclass with fields: `path`, `mtime`, `size_bytes`, `games`
     (list of `(name, count)`), `slots` (list of `(slot_num, slot_name,
     game_name)`), `has_spoiler: bool`, `has_archipelago_file: bool`,
     `error: str | None`.
   - `scan_seed(path: Path) -> Seed` opens the zip via
     `zipfile.ZipFile`, reads the namelist, and parses per-slot patch
     filenames matching the grammar
     `AP_<seed_id>_P<slot>_<player_safe>.<suffix>` to populate
     `slots`. **For server-only slots** (no patch file in the
     namelist) the scanner must additionally open the
     `AP_<seed_id>.archipelago` entry — it is gzip+msgpack — and read
     `slot_info` to reconcile the full slot list. Keep namelist-only
     as the fast path; multidata read is the fallback for server-only
     reconciliation. Confirmed against real seeds in `NOTES.md` §3.5.
   - `scan_directory(path: Path) -> list[Seed]` returns seeds sorted by
     mtime descending. Skip non-`AP_*.zip` files. Tolerate corrupt zips
     (log, return a `Seed` with `error` set; don't crash).
3. Implement output-path discovery in `seed_browser/browser.py` using AP's
   `Utils` helpers per the decision in §4.5.
4. Replace the empty window with a list view. Each row renders:
   `YYYY-MM-DD HH:MM · 4 slots · LTTP, 2×SMW, Keen · 1.2 MB · 📜`
   (the 📜 only when a spoiler is present). Keep it text-only for now —
   no per-row buttons yet.
5. Add a "Refresh" button that re-runs `scan_directory`.

**Verification.**

- Open the tool against a folder with at least 3 real seeds. Confirm rows
  match the actual contents (cross-check by manually unzipping one).
- Confirm a corrupt or partial zip in the folder doesn't crash the app.
- Confirm a freshly generated seed appears after clicking Refresh.
- Unit tests in `tests/test_scanner.py` use synthetic fixture zips with
  hand-crafted namelists; tests pass under `pytest`.

**Done when.** All verification passes; `tests/` has at least 5 scanner
tests including the corrupt-zip path. Commit and tag `v0.2.0-list`.

---

### Phase 3 — Row actions

**Goal.** Each row exposes Host, Open spoiler, Reveal, Delete.

**Tasks.**

1. Implement `seed_browser/actions.py`:
   - `host_seed(seed: Seed)` — invoke the launcher's existing Host
     component. The Host `Component` in 0.6.7
     (`LauncherComponents.py:223-225`) has no `func` — only
     `script_name='MultiServer'` — so direct `func` dispatch is not
     available. Shell out via
     `subprocess.Popen([*get_exe(host.script_name), str(seed.path)])`
     with `host = next(c for c in components if c.display_name ==
     "Host")`. `get_exe` lives in `Launcher.py` and is non-canonical
     to import from an apworld; copy its short body (10 lines) into
     `actions.py`. Use `Popen` (not `run`) so the launcher's main loop
     is not blocked. Confirmed in `NOTES.md` §3.6.
   - `open_spoiler(seed: Seed)` — extract the spoiler txt to a temp file,
     open with `Utils.open_file` (AP already has a cross-platform opener;
     use it rather than rolling your own).
   - `reveal_in_file_manager(seed: Seed)` — cross-platform (`open -R` on
     macOS, `explorer /select,` on Windows, `xdg-open` on parent dir on
     Linux as fallback).
   - `delete_seed(seed: Seed, *, confirmed: bool)` — refuses unless
     `confirmed=True`. Sends to OS trash if `send2trash` is available,
     falls back to `path.unlink()` with a stronger confirmation dialog.
2. Wire each action to a per-row button or context menu in the UI. Use a
   confirmation dialog for Delete that shows the filename and game list.
3. Disable Open spoiler when `has_spoiler` is False (don't hide — disabled
   is more discoverable than missing).
4. After a successful Delete, re-scan and update the list.

**Verification.**

- Manually exercise each action against a real seed.
- Host: confirm a server starts, accepts a connection from a Text Client.
- Spoiler: confirm the file opens in the user's default text app and the
  contents match.
- Reveal: confirm the correct file is highlighted in Finder/Explorer/etc.
- Delete: confirm the file is gone afterwards and the row disappears.
  Confirm cancelling the dialog does nothing.
- `tests/test_actions.py` covers the pure-logic bits (path calculation,
  confirmation gating); UI invocation is tested manually.

**Done when.** All four actions work on the user's primary OS, and at
least one secondary OS via CI or VM if reasonably accessible. Commit and
tag `v0.3.0-actions`.

---

### Phase 4 — Polish

**Goal.** Ship-quality v1.

**Tasks.**

1. Provide a real icon (PNG, the size AP's launcher expects — confirm in
   `NOTES.md`). Place it in `seed_browser/` and reference it in the
   `Component` registration.
2. Sort controls: by date (default, desc), by size, by slot count. Click
   header to toggle.
3. Empty-state UI: when the output folder has no seeds, show a friendly
   message with the resolved folder path so the user can sanity-check it.
4. Error-state UI: if `output_path` doesn't exist or isn't readable, show
   the path and the error rather than a blank list.
5. Filesystem watcher (optional but cheap): if `watchdog` is available,
   auto-refresh on changes; otherwise rely on the manual button. Don't
   add `watchdog` as a hard dep — soft import.
6. README: install instructions, screenshot, brief feature list, link to
   Archipelago, license.

**Verification.**

- Manual UX pass against the user's real output folder.
- Empty and error states triggered manually (point at an empty dir, then
  a non-existent dir).

**Done when.** Jesper has used it for one real solo session and hasn't
hit anything frustrating. Commit and tag `v1.0.0-rc1`.

---

### Phase 5 — Packaging & release

**Goal.** A user can install with one drag-and-drop from a GitHub release.

**Tasks.**

1. `.github/workflows/release.yml`: on tag push matching `v*`, build the
   apworld and upload as a release asset.
2. README install section: link to releases, drop into `custom_worlds/`,
   restart launcher.
3. Open a discussion thread in the AP Discord's tools channel announcing
   v1 (user does this; not Claude Code's job).

**Verification.**

- Push a tag, confirm the workflow produces a downloadable `.apworld`.
- Download from the release URL, install on a clean AP setup, confirm
  the tile appears and basic flow works.

**Done when.** Release published and clean-install tested. Tag `v1.0.0`.

## 8. Testing approach

- **Unit tests** for `scanner.py`, `games.py`, and the pure-logic parts
  of `actions.py`. Use small synthetic zips built in fixtures via
  `zipfile.ZipFile` at test time — do not commit binary zips.
- **Manual integration tests** for everything UI-touching and for any
  action that shells out to AP. Document the manual test checklist in
  `tests/MANUAL.md` and run it at the end of each phase.
- **CI** runs unit tests on every PR, and additionally builds the
  apworld artifact to confirm packaging stays green.

## 9. Conventions

- Format with `ruff format`, lint with `ruff check`. Config in
  `pyproject.toml`. No black/isort/flake8 — ruff covers it.
- Type hints everywhere. `from __future__ import annotations` at the top
  of every module.
- Follow Archipelago's import style where practical: `import worlds.X`,
  not relative imports across the package boundary.
- No new runtime dependencies beyond what Archipelago already ships
  (Kivy, PyYAML, etc.). Optional deps (`watchdog`, `send2trash`) are
  soft-imported and the app degrades gracefully without them.
- Commits: conventional style (`feat:`, `fix:`, `chore:`). One logical
  change per commit. The phase tags above are the only release tags.

## 10. Stop-and-ask checklist

Claude Code should pause and surface the question to the user (not guess)
in any of these situations:

- A reference file in §5 is missing or its API differs materially from
  this plan.
- A decision listed in §4 hasn't been confirmed yet.
- The launcher's component-registration mechanism has changed in the
  installed AP version (e.g. `Type.TOOL` no longer exists).
- A test fails and the fix would require modifying this plan.
- A v1 task turns out to need something from §2 (out of scope) to work
  correctly. Don't silently expand v1 — flag it and ask.

## 11. Definition of done (v1)

- Installs via drop-in `.apworld` on macOS, Linux, and Windows.
- Lists every seed in the user's output folder accurately.
- All four row actions work on the user's primary OS.
- No crashes when fed corrupt zips, missing folders, or permission errors.
- README + screenshot + GitHub release + tagged `v1.0.0`.
