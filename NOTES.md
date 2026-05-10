# Phase 0 — Reference notes

Produced before Phase 1 per PLAN §5. Captures the AP API surface this project
depends on, the prerequisite/decision status from §3/§4, and the places where
PLAN.md's stated assumptions need to be revised before code is written.

All citations are against the local Archipelago tree at
`/Users/joxtacy/PrivateProjects/Archipelago`, tag **`0.6.7`**, rev
**`debe4cf0`**. Filesystem snapshots (`output/`, `host.yaml`) are from
`~/Library/Application Support/Archipelago/` on this machine.

---

## 1. Prerequisites (PLAN §3)

| Item | Status | Notes |
| --- | --- | --- |
| AP source available | ✅ | `/Users/joxtacy/PrivateProjects/Archipelago` @ `0.6.7` |
| AP user install available | ✅ | `~/Library/Application Support/Archipelago/` with `host.yaml`, `output/`, `custom_worlds/` |
| Python pinned to AP-supported version | ⚠️ **Mismatch** | AP `ModuleUpdate.py:8` enforces `3.11.0 ≤ version < 3.14.0`. Local default is **3.14.3**. Phase 1 must run/test under a 3.13.x interpreter (e.g. `pyenv install 3.13.7 && pyenv local 3.13.7`). Do not pin 3.14 in `pyproject.toml`. |
| Real seeds available | ⚠️ Marginal | 2 seed zips in `output/`. PLAN recommends "at least 2–3". Generate one more multi-game seed before Phase 2 visual testing. Current inventory: `AP_05108149285254774479.zip` (3 entries incl. `.apmc` patch) and `AP_60686799217853776124.zip` (multidata + spoiler only, no patch files). |

## 2. Decisions taken (PLAN §4)

User is in auto mode; defaults locked unless they course-correct.

1. **UI library**: **Kivy via `kvui.ThemedApp`**. Reasoning: AP ships Kivy 2.3.1 as a hard runtime dep (`requirements.txt`), `ThemedApp` (`kvui.py:116`) is subclassable as a standalone app, and theme parity with the launcher is free. Tk would re-introduce a stdlib dep that doesn't exist on the macOS frozen build.
2. **Repo name**: `archipelago-seed-browser` (the GitHub slug). The local working directory is currently `ap-games-manager`; we'll keep that as the working folder but use `archipelago-seed-browser` for the public repo name and the README install link.
3. **License**: **MIT**, matching `Archipelago/LICENSE`.
4. **Module name**: `seed_browser` (the folder that gets zipped into `SeedBrowser.apworld`).
5. **Output path discovery**: Use AP's own resolver. `Utils.output_path()` (`Utils.py:222`) already reads `general_options.output_path` from `host.yaml` via `settings.get_settings()` (`settings.py:881`) and falls back to creating one. **Call `Utils.output_path()` with no args to get the resolved directory.** No tool-specific override.

## 3. Reference API surface (PLAN §5)

### 3.1 Launcher integration — `worlds/LauncherComponents.py`

- `Component` constructor (`LauncherComponents.py:60-82`):

  ```python
  Component(display_name, script_name=None, frozen_name=None, cli=False,
            icon='icon', component_type=None, func=None,
            file_identifier=None, game_name=None, supports_uri=False,
            description="")
  ```
- `Type` enum (`LauncherComponents.py:11-17`) — values: `TOOL`, `MISC`,
  `CLIENT`, `ADJUSTER`, `FUNC` (deprecated), `HIDDEN`. **`Type.TOOL`
  exists in 0.6.7.**
- The launcher renders a single flat grid filtered by
  `(CLIENT, TOOL, ADJUSTER, MISC)` (`Launcher.py:287, 339, 348`). There is
  **no dedicated "Tools" section** — PLAN's wording is slightly off; tiles
  share one grid but `Type.TOOL` distinguishes them in the filter.
- Apworlds register by appending to the module-level list:
  `from worlds.LauncherComponents import Component, Type, components, launch as launch_component`
  then `components.append(Component(...))` (canonical example:
  `worlds/factorio/__init__.py:10, 25-30`).
- Icon resolution: `icon_paths[component.icon]` (`Launcher.py:320`).
  Apworld-local icons use the `"ap:<module>/<relative_path>.png"` format
  (`LauncherComponents.py:255`).

### 3.2 Tile invocation — `Launcher.py:412-423, 462-470`

- When the user clicks a tile, the launcher calls **`component.func()`
  with NO arguments** on the main thread (`Launcher.py:414`). Args are
  only forwarded when a Component is dispatched via file drag-drop /
  CLI / `file_identifier`.
  → **Phase 1 entry point should be `def run(*args)` defaulting to `()`**;
    do not assume `args` is populated.
- Exceptions from `func` are **not caught** and will crash the launcher
  process. Wrap our entry in try/except and log.
- For UI tools that own their own Kivy app, the canonical pattern is to
  **spawn a subprocess** via `launch_component(run_app, name="...", args=(...))`
  (`LauncherComponents.py:100-105`). This is what `OptionsCreator.py` does
  and what AP's adjusters do. **No secondary-window API exists** —
  `MDApp.run()` takes the main thread.

### 3.3 `Utils.py` helpers (paths + open)

| Helper | Line | Returns on macOS user install |
| --- | --- | --- |
| `local_path(*p)` | 131 | AP source / frozen bundle root |
| `home_path(*p)` | 160 | `~/Library/Application Support/Archipelago` (via `platformdirs`) |
| `user_path(*p)` | 185 | The writable of the two (caches the choice) |
| `cache_path(*p)` | 211 | `~/Library/Caches/Archipelago` |
| `output_path(*p)` | 222 | `user_path/<general_options.output_path>` |
| `open_file(path)` | 231 | `subprocess.call(["open", path])` — fire-and-forget |
| `is_frozen()` | 127 | True under cx_Freeze |
| `__version__` | 55 | `"0.6.7"` (pinned for compatibility note in README) |

Settings access: `from settings import get_settings; get_settings()["general_options"]["output_path"]`.

There is **no built-in "reveal in file manager" helper**. We must implement
it in `seed_browser/actions.py`:

- macOS: `subprocess.call(["open", "-R", str(path)])`
- Windows: `subprocess.run(["explorer", f"/select,{path}"])` (note: no
  shell quoting; `/select,` is a single arg with comma)
- Linux: `subprocess.call(["xdg-open", str(path.parent)])` as fallback —
  most file managers don't have a portable "select" flag.

### 3.4 World registry + patch suffixes — **PLAN deviation**

PLAN §7 Phase 2 task 1 says to "walk `AutoWorldRegister.world_types`,
pull each world's patch suffix". This is **wrong** for 0.6.7:

- `World.patch_suffix` does not exist. `worlds/AutoWorld.py:272-355` has
  `game`, `hidden`, `zip_path`, etc. but no patch-suffix attribute.
- Patch suffixes live on **patch container classes** (subclasses of
  `APPlayerContainer` / `APPatch` / `APDeltaPatch`), e.g.
  `worlds/alttp/Rom.py:3006`: `LttPDeltaPatch.patch_file_ending = ".aplttp"`.
- The canonical registry is **`worlds.Files.AutoPatchRegister.file_endings`**
  (`worlds/Files.py:30`): a `dict[str, AutoPatchRegister]` populated at
  import time, mapping each unique `patch_file_ending` to its handler
  class. Each handler class carries a `game` attribute pointing back at
  the AP world.

**Revised `build_extension_map()` design** (replace PLAN §7 Phase 2 task 1):

```python
from worlds.Files import AutoPatchRegister
def build_extension_map() -> dict[str, str]:
    return {
        ending: handler.game
        for ending, handler in AutoPatchRegister.file_endings.items()
        if handler.game  # defensive; APContainer base has game=None
    }
```

Worlds without a patch container (e.g. ChecksFinder) are absent from this
map and correctly fall through. SNES- and BizHawk-specific client
registries (`AutoSNIClientRegister.game_handlers` at
`worlds/AutoSNIClient.py:47`; `AutoBizHawkClientRegister.game_handlers`
at `worlds/_bizhawk/client.py:28`) also expose `patch_suffix` but the
patch-container registry is the authoritative single source — those
client registries exist for SNI / BizHawk routing, not for our display
mapping.

To **hide our own non-functional World stub** from yaml templates,
PLAN's "hidden = True" is literal: `worlds/AutoWorld.py:313` declares
`hidden: ClassVar[bool] = False` on the `World` base. Set it to `True`
on our stub.

### 3.5 Seed zip format — confirmed against real files

Confirmed by `zipfile.ZipFile(...).namelist()` on the two real seeds:

```
AP_05108149285254774479.zip ->
    AP_05108149285254774479.archipelago
    AP_05108149285254774479_Spoiler.txt
    AP_05108149285254774479_P1_Jox.apmc
AP_60686799217853776124.zip ->
    AP_60686799217853776124.archipelago
    AP_60686799217853776124_Spoiler.txt
```

Filename grammar (flat, no subdirs):

- `AP_<seed_id>.archipelago` — gzipped msgpack multidata. Always present.
- `AP_<seed_id>_Spoiler.txt` — optional. Presence determined by
  `race_mode == 0` at generation time. PLAN's `has_spoiler` flag = does
  `AP_<seed_id>_Spoiler.txt` appear in the namelist.
- `AP_<seed_id>_P<slot>_<player_safe>.<patch_suffix>` — per-slot patch.
  Player name has spaces → underscores; everything after the last `.` is
  the suffix. Server-only slots do **not** produce a patch entry.

Scanner strategy (replaces PLAN §7 Phase 2 task 2 default of "namelist
only"):

1. Parse patch filenames out of the namelist → `(slot_num, player_name, suffix)`.
2. Map `suffix → game_name` via `build_extension_map()` (§3.4).
3. **For server-only slots** the namelist is silent. To populate the
   full `slots: list[(slot_num, slot_name, game_name)]` PLAN wants, we
   must read the `.archipelago` entry: `gzip.decompress` →
   `MultiServer.Multidata.parse` (or directly via `NetUtils` /
   `multidata` deserialiser — confirm in Phase 2 which one is stable).
   This is heavier than namelist-only but unavoidable for correctness.
4. **Counts in the row label** ("LTTP, 2×SMW, Keen") come from collapsing
   the per-slot game list. Trivial.

`mtime` for sort order = file's `os.stat().st_mtime`. Internal zip
entries have matching timestamps but the file's stat is the right signal.

### 3.6 Host this seed — **PLAN deviation**

PLAN §7 Phase 3 task 1 says to "prefer calling its registered `func`
directly". The Host component (`LauncherComponents.py:223-225`) is
registered with **no `func`** — only `script_name='MultiServer'` and
`frozen_name='ArchipelagoServer'`. The launcher dispatches it via
`subprocess.run([*get_exe('MultiServer'), seed_path])`
(`Launcher.py:467-468`).

So:

- "Direct `func` call" is impossible — there is no callable.
- **Phase 3 must shell out** using `get_exe()` (in `Launcher.py`, exposed
  for component dispatch) on a Host `Component` instance fetched from
  `worlds.LauncherComponents.components`. Pattern:
  ```python
  host = next(c for c in components if c.display_name == "Host")
  subprocess.Popen([*get_exe(host.script_name), str(seed.path)])
  ```
- This must run in a detached subprocess (`Popen`, not `run`) so the
  launcher's main loop isn't blocked.

Update PLAN.md Phase 3 task 1 accordingly when revising — leave the
direct-func wording out of the implementation; document it here as
"investigated and not available in 0.6.7".

### 3.7 Confirmation dialogs

`kvui.ButtonsPrompt` (`kvui.py:760-798`) is a ready-made modal for the
Delete confirmation. Signature:

```python
ButtonsPrompt(title, text, response, *button_labels).open()
# response(button_text) is the callback; must call .dismiss() itself.
```

Use this rather than rolling our own `MDDialog`.

### 3.8 Icon size

`Launcher.py:270` sets the launcher window icon from `data/icon.png`.
Card icons are rendered by `ApAsyncImage` at 48×48 (see launcher kv
spec). Provide a **48×48 PNG** for our tile and register it via
`icon_paths['seedbrowser'] = local_path(...)` or with the
`ap:seed_browser/...` lookup.

### 3.9 In-tree example to imitate

No public 0.6.7 apworld registers a Tool-style Component. The closest
pattern lives at `worlds/factorio/__init__.py:25-30` (CLIENT-typed) and
the standalone `OptionsCreator.py` (subprocess-launched standalone
ThemedApp). Use both as references for Phase 1.

## 4. Open questions to confirm before Phase 1 commits

1. **Apworld validation requires a `World` subclass?** PLAN Phase 1 task 3
   assumes so. In 0.6.7 the `.apworld` loader registers anything that
   imports cleanly under `worlds/<name>/`; the `World` stub is not
   strictly required for `LauncherComponents` registration to work, but
   AP's launcher does scan `worlds/*` for `__init__.py`. Plan: ship a
   minimal `class _SeedBrowserStub(World): game = "_seed_browser"; hidden = True; item_name_to_id = {}; location_name_to_id = {}` — and verify it does not show up in the yaml game picker. Drop it if startup works without.
2. **`send2trash` availability.** Not in AP's `requirements.txt`. PLAN
   §7 Phase 3 says soft-import. Keep that — fall back to
   `pathlib.Path.unlink()` with a louder confirmation.
3. **`watchdog` availability.** Same — not in AP. Phase 4 should keep
   the manual Refresh button as the baseline.
4. **`get_exe()` reachability from an apworld.** It's defined in
   `Launcher.py` (not `LauncherComponents.py`), so importing it from an
   apworld is non-canonical. Phase 3 may need to copy its short body
   (10 lines) into `actions.py` rather than reach into `Launcher`.

## 5. PLAN.md amendments to make alongside Phase 1

When opening the Phase 1 PR, update PLAN.md:

- §7 Phase 2 task 1 — replace `AutoWorldRegister` walk with
  `AutoPatchRegister.file_endings` walk (see §3.4 above).
- §7 Phase 2 task 2 — note that fully populating `slots` requires
  reading the `.archipelago` multidata; namelist alone misses server-only
  slots.
- §7 Phase 3 task 1 — direct `func` invocation is not available; spell
  out the `subprocess.Popen([*get_exe('MultiServer'), path])` approach.
- §7 Phase 1 task 3 — `hidden = True` is the correct flag (literal name
  on `World` base class).

---

**Reviewed against AP 0.6.7. Ready to proceed to Phase 1 once the
Python-version pin is set up and PLAN.md is amended per §5 above.**
