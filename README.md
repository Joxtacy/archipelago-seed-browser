# Archipelago Seed Browser

A launcher add-on for [Archipelago](https://archipelago.gg) that lists the
multiworld seed zips in your local output folder and exposes per-seed actions:

- **Host** the seed in a Terminal/console window via AP's existing Host
  component (`MultiServer`).
- **Open spoiler** — extracts the spoiler log to a temp file and opens it in
  your default text editor.
- **Reveal in file manager** — Finder on macOS, Explorer on Windows,
  `xdg-open` on Linux.
- **Delete** with confirmation — sends to OS trash if `send2trash` is
  available, hard-unlinks otherwise.

The list shows timestamp, slot count, games (with duplicate counts like
`2×Minecraft`), file size, and a `(spoiler)` marker when a spoiler log is
present. Sort by date, size, or slot count; toggle ascending/descending by
clicking the active sort header. If `watchdog` is installed in AP's runtime
the list auto-refreshes when the output folder changes; otherwise use the
**Refresh** button.

Ships as a single `seed_browser.apworld` you drop into your Archipelago
`custom_worlds/` (or `worlds/`) directory.

## Install

1. Download `seed_browser.apworld` from the Releases page.
2. Drop it into your Archipelago `custom_worlds/` directory. On macOS that's
   usually `~/Library/Application Support/Archipelago/worlds/`; on
   Windows / Linux check your AP install's path.
3. Restart the Archipelago Launcher. The **Seed Browser** tile appears under
   the Tools row.

Tested against Archipelago **0.6.7**.

## Build from source

```sh
git clone https://github.com/Joxtacy/archipelago-seed-browser.git
cd archipelago-seed-browser
./scripts/build_apworld.sh    # writes dist/seed_browser.apworld
```

To regenerate the icon:

```sh
python scripts/build_icon.py
```

To run the unit tests:

```sh
uv run pytest
```

Multidata-decoding tests require Archipelago on the import path; set
`ARCHIPELAGO_SRC=/path/to/Archipelago` to enable them.

## Project layout

- [`PLAN.md`](PLAN.md) — phased implementation plan and the working spec.
- [`NOTES.md`](NOTES.md) — reference notes against the AP 0.6.7 source.
- [`IDEAS.md`](IDEAS.md) — post-v1 ideas (search/filter, favourites,
  batch ops, etc.).
- [`RELEASING.md`](RELEASING.md) — runbook for cutting a release.

## License

MIT — same as Archipelago. See [`LICENSE`](LICENSE).
