"""Standalone Kivy app for the Seed Browser.

Launched as a subprocess by :func:`worlds.LauncherComponents.launch`. All
Kivy / KivyMD imports happen inside :func:`_run_app` so that importing
this module from the launcher costs nothing.
"""

from __future__ import annotations

import datetime
import logging
import threading
from pathlib import Path
from typing import Literal

from . import actions
from .scanner import Seed, scan_directory

logger = logging.getLogger(__name__)

SortKey = Literal["date", "size", "slots", "hosted", "game"]
_SORT_LABELS: dict[SortKey, str] = {
    "date": "Date",
    "size": "Size",
    "slots": "Slots",
    "hosted": "Last hosted",
    "game": "Game",
}

SeedState = Literal["untouched", "in_progress", "complete"]
StateFilter = Literal["all", "untouched", "in_progress", "complete"]
_STATE_LABELS: dict[StateFilter, str] = {
    "all": "All",
    "untouched": "Untouched",
    "in_progress": "In progress",
    "complete": "Complete",
}


def run(*args: str) -> None:
    """Entry point invoked by the launcher subprocess."""
    try:
        _run_app(args)
    except Exception:
        logging.exception("Seed Browser crashed")
        raise


def _resolve_output_dir() -> Path:
    """Use AP's own output_path resolver — reads host.yaml's
    ``general_options.output_path`` and falls back to AP defaults."""
    from Utils import output_path

    return Path(output_path())


def _format_seed_row(seed: Seed) -> str:
    """Compact collapsed-row label. Spoiler presence is already shown
    by the row's Spoiler button (enabled/disabled); the hosted
    timestamp + file size move to the expanded footer."""
    if seed.error:
        return f"{seed.path.name}  —  error: {seed.error}"
    ts = datetime.datetime.fromtimestamp(seed.mtime).strftime("%Y-%m-%d %H:%M")
    nslots = len(seed.slots)
    games_str = ", ".join(f"{count}×{game}" if count > 1 else game for game, count in seed.games)
    parts = [ts, f"{nslots} slots", games_str]
    if seed.has_save:
        parts.append("hosted")
    return "  ·  ".join(parts)


def _format_version(version: tuple[int, int, int] | None) -> str | None:
    if version is None:
        return None
    return ".".join(str(p) for p in version)


def _format_seed_footer_lines(seed: Seed) -> list[str]:
    """Build the multi-line footer for the expanded panel.

    Split across rows so the footer stays readable at narrower window
    widths:
        line 1: filename · size
        line 2: AP version metadata (when known)
        line 3: last hosted timestamp (when applicable)

    Spoiler presence is intentionally omitted — the row's Spoiler
    button already signals it.
    """
    lines: list[str] = [f"{seed.path.name}  ·  {_format_size(seed.size_bytes)}"]

    version_parts: list[str] = []
    gen = _format_version(seed.generator_version)
    if gen:
        version_parts.append(f"AP {gen}")
    minsrv = _format_version(seed.min_server_version)
    if minsrv:
        version_parts.append(f"requires server ≥ AP {minsrv}")
    if version_parts:
        lines.append("  ·  ".join(version_parts))

    if seed.has_save and seed.last_hosted is not None:
        hosted_ts = datetime.datetime.fromtimestamp(seed.last_hosted).strftime("%Y-%m-%d %H:%M")
        lines.append(f"last hosted {hosted_ts}")

    return lines


def _format_slot_progress(seed: Seed, slot_num: int) -> str:
    """Render the ' · N/M checks · done' suffix for a per-slot row.

    Returns an empty string if we have nothing to say (no save, no
    totals). Pure helper — extracted for testing.

    Once ``has_save`` is True we surface ``0/N`` even for slots whose
    client never connected — otherwise the row asymmetrically omits the
    unplayed slots and reads as if we're missing data.
    """
    parts: list[str] = []
    checked = seed.slot_checked.get(slot_num)
    total = seed.slot_totals.get(slot_num)
    if total is not None and seed.has_save:
        parts.append(f"{checked or 0}/{total} checks")
    elif checked is not None and total is not None:
        parts.append(f"{checked}/{total} checks")
    elif checked is not None:
        parts.append(f"{checked} checks")
    if seed.slot_complete.get(slot_num):
        parts.append("done")
    if not parts:
        return ""
    return "  ·  " + "  ·  ".join(parts)


def _format_size(n: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    size = float(n)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} {units[-1]}"


def seed_state(seed: Seed) -> SeedState:
    """Bucket a seed into one of three mutually-exclusive UX states.

    - ``"untouched"`` — no ``.apsave`` exists, so MultiServer has never
      flushed state for this seed.
    - ``"complete"`` — every player-type slot has reported
      ``ClientStatus.CLIENT_GOAL``. Group / spectator slots are ignored
      because they don't have a goal to reach.
    - ``"in_progress"`` — everything else with a save: started, stalled,
      or hosted-but-never-played. A seed with no player slots stays
      here forever once hosted, which is honest — we have no goal
      signal for spectator-only / group-only seeds.
    """
    if not seed.has_save:
        return "untouched"
    players = [n for n, t in seed.slot_types.items() if t == "player"]
    if players and all(seed.slot_complete.get(n, False) for n in players):
        return "complete"
    return "in_progress"


def filter_by_state(seeds: list[Seed], state: StateFilter) -> list[Seed]:
    """Narrow *seeds* to those matching the chip selection. ``"all"``
    returns a fresh copy so callers can chain mutations safely."""
    if state == "all":
        return list(seeds)
    return [s for s in seeds if seed_state(s) == state]


def filter_seeds(seeds: list[Seed], query: str) -> list[Seed]:
    """Filter *seeds* by case-insensitive substring match against the
    filename, decoded game names, and decoded slot/player names.

    Empty / whitespace-only *query* returns the full list. Pure helper
    — exposed at module scope so it can be unit-tested without Kivy.
    """
    needle = query.strip().lower()
    if not needle:
        return list(seeds)
    out: list[Seed] = []
    for s in seeds:
        hay = [s.path.name.lower()]
        hay.extend(g.lower() for g, _ in s.games)
        hay.extend(name.lower() for _, name, _ in s.slots)
        if any(needle in h for h in hay):
            out.append(s)
    return out


def sort_seeds(seeds: list[Seed], *, key: SortKey, desc: bool) -> list[Seed]:
    """Return *seeds* sorted by *key*. Pure helper — extracted for testing.

    For ``key="hosted"`` unhosted seeds (no ``.apsave``) always trail
    the hosted ones regardless of direction; among themselves they keep
    descending-mtime order so the most recently *generated* unhosted
    seed sits at the top of the unhosted block.
    """
    if key == "hosted":
        hosted = sorted(
            (s for s in seeds if s.has_save),
            key=lambda s: s.last_hosted or 0.0,
            reverse=desc,
        )
        unhosted = sorted(
            (s for s in seeds if not s.has_save),
            key=lambda s: s.mtime,
            reverse=True,
        )
        return hosted + unhosted

    if key == "game":
        # Sort by the headlining (first-seen) game name, case-insensitive
        # so 'Jigsaw' and 'jigsaw' group together. Seeds with no decoded
        # games fall to the end regardless of direction — there's nothing
        # meaningful to sort them by.
        with_game = sorted(
            (s for s in seeds if s.games),
            key=lambda s: s.games[0][0].lower(),
            reverse=desc,
        )
        without_game = sorted(
            (s for s in seeds if not s.games),
            key=lambda s: s.mtime,
            reverse=True,
        )
        return with_game + without_game

    keyfns = {
        "date": lambda s: s.mtime,
        "size": lambda s: s.size_bytes,
        "slots": lambda s: len(s.slots),
    }
    return sorted(seeds, key=keyfns[key], reverse=desc)


def _start_watcher(output_dir: Path, on_change: object) -> object | None:
    """Soft-import ``watchdog`` and start a debounced observer for
    *output_dir*. Returns the started ``Observer`` (so caller can stop
    it) or ``None`` if watchdog is unavailable.

    *on_change* is invoked from a watchdog thread, so callers must
    marshal back to the UI thread themselves (Kivy's ``Clock`` is the
    standard tool for this).
    """
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        logger.info("watchdog not installed — auto-refresh disabled")
        return None

    class _Handler(FileSystemEventHandler):
        def on_any_event(self, event: object) -> None:  # noqa: ARG002
            on_change()

    observer = Observer()
    observer.schedule(_Handler(), str(output_dir), recursive=False)
    observer.daemon = True
    observer.start()
    return observer


def _run_app(args: tuple[str, ...]) -> None:
    from kivy.clock import Clock
    from kivy.core.window import Window
    from kivy.metrics import dp
    from kivymd.uix.boxlayout import MDBoxLayout
    from kivymd.uix.button import MDButton, MDButtonText
    from kivymd.uix.card import MDCard
    from kivymd.uix.label import MDLabel
    from kivymd.uix.list import MDList
    from kivymd.uix.scrollview import MDScrollView
    from kivymd.uix.textfield import MDTextField, MDTextFieldHintText
    from kvui import ButtonsPrompt, ThemedApp

    # Seed rows + 5-button action strip + sort bar are horizontally
    # demanding. Modest bump over Kivy's 800x600 default so multi-game
    # rows don't wrap awkwardly on first launch. Plain pixel values
    # (not dp) — Window.size doesn't scale through density.
    Window.size = (1000, 700)

    output_dir = _resolve_output_dir()

    class SeedBrowserApp(ThemedApp):
        title = "Seed Browser"

        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)
            self.set_colors()
            self._list_widget: MDList | None = None
            self._status_label: MDLabel | None = None
            self._sort_buttons: dict[SortKey, MDButton] = {}
            self._sort_key: SortKey = "date"
            self._sort_desc: bool = True
            self._state_buttons: dict[StateFilter, MDButton] = {}
            self._state_filter: StateFilter = "all"
            self._observer: object | None = None
            self._refresh_pending: bool = False
            self._expanded: set[Path] = set()
            """Paths of seeds whose detail panel is currently expanded.
            Survives ``_refresh()`` so toggle state isn't lost on
            re-scan."""
            self._seeds_cache: list[Seed] = []
            """Last successful scan result — sort/filter/expand toggles
            re-render from this without hitting the filesystem again."""
            self._filter_text: str = ""
            self._scan_gen: int = 0
            """Monotonic counter bumped on every ``_refresh`` dispatch.
            Worker threads attach the value they saw to their result and
            it's discarded on the UI thread if another scan has started
            in the meantime."""
            self._row_widgets: dict[Path, tuple[Seed, object]] = {}
            """``{seed.path: (seed, card_widget)}`` for every seed in the
            current cache (visible or filtered out). The Seed identity is
            tracked so that re-scans which replace the Seed object also
            invalidate the cached card. Lets ``_render_seeds`` reuse
            widgets across filter / sort changes — building a card is
            far more expensive than re-parenting one."""

        def build(self) -> MDBoxLayout:
            # Match the AP launcher's deep-navy backdrop. The default
            # MDBoxLayout has no bg and reads as pure black against the
            # window; using ``theme_cls.backgroundColor`` (the same hook
            # the launcher's top_screen uses at Launcher.py:385) keeps
            # us visually consistent with the rest of AP.
            root = MDBoxLayout(
                orientation="vertical",
                padding=dp(16),
                spacing=dp(8),
                md_bg_color=self.theme_cls.backgroundColor,
            )

            root.add_widget(self._build_header())
            root.add_widget(self._build_search_bar())
            root.add_widget(self._build_state_bar())
            root.add_widget(self._build_sort_bar())

            scroll = MDScrollView()
            # Add inner spacing so seed-row cards visually separate from
            # each other without needing dividers.
            self._list_widget = MDList(spacing=dp(8), padding=(0, dp(4)))
            scroll.add_widget(self._list_widget)
            root.add_widget(scroll)

            self._status_label = MDLabel(
                text="",
                halign="left",
                size_hint_y=None,
                height=dp(24),
            )
            root.add_widget(self._status_label)

            self._refresh()
            self._observer = _start_watcher(output_dir, self._on_watcher_event)
            return root

        def _build_header(self) -> MDBoxLayout:
            header = MDBoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(48),
                spacing=dp(12),
            )
            header.add_widget(
                MDLabel(
                    text=f"Output: {output_dir}",
                    halign="left",
                    valign="center",
                )
            )
            refresh_btn = MDButton(
                MDButtonText(text="Refresh"),
                style="filled",
                size_hint=(None, None),
                size=(dp(120), dp(40)),
                pos_hint={"center_y": 0.5},
            )
            refresh_btn.bind(on_release=lambda _btn: self._refresh())
            header.add_widget(refresh_btn)
            return header

        def _build_search_bar(self) -> MDBoxLayout:
            bar = MDBoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(56),
                spacing=dp(8),
            )
            field = MDTextField(
                MDTextFieldHintText(text="Search by filename, game, or player name"),
                size_hint_x=1,
            )
            field.bind(text=lambda _w, value: self._on_filter_change(value))
            bar.add_widget(field)
            return bar

        def _on_filter_change(self, text: str) -> None:
            self._filter_text = text
            self._render_seeds()

        def _build_state_bar(self) -> MDBoxLayout:
            bar = MDBoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(40),
                spacing=dp(8),
            )
            bar.add_widget(
                MDLabel(
                    text="Show",
                    halign="left",
                    valign="center",
                    size_hint_x=None,
                    width=dp(64),
                )
            )
            for key in ("all", "untouched", "in_progress", "complete"):
                btn = MDButton(
                    MDButtonText(text=_STATE_LABELS[key]),
                    style="tonal",
                    size_hint=(None, None),
                    size=(dp(144), dp(40)),
                )
                btn.bind(on_release=lambda _btn, k=key: self._set_state_filter(k))
                self._state_buttons[key] = btn
                bar.add_widget(btn)
            bar.add_widget(MDLabel())  # spacer
            self._update_state_button_styles()
            return bar

        def _set_state_filter(self, state: StateFilter) -> None:
            self._state_filter = state
            self._update_state_button_styles()
            self._render_seeds()

        def _update_state_button_styles(self) -> None:
            for key, btn in self._state_buttons.items():
                btn.style = "filled" if key == self._state_filter else "tonal"

        def _build_sort_bar(self) -> MDBoxLayout:
            bar = MDBoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(40),
                spacing=dp(8),
            )
            bar.add_widget(
                MDLabel(
                    text="Sort by",
                    halign="left",
                    valign="center",
                    size_hint_x=None,
                    width=dp(64),
                )
            )
            for key in ("date", "size", "slots", "hosted", "game"):
                btn = MDButton(
                    MDButtonText(text=_SORT_LABELS[key]),
                    style="tonal",
                    size_hint=(None, None),
                    size=(dp(176), dp(40)),
                )
                btn.bind(on_release=lambda _btn, k=key: self._set_sort(k))
                self._sort_buttons[key] = btn
                bar.add_widget(btn)
            bar.add_widget(MDLabel())  # spacer
            self._update_sort_button_labels()
            return bar

        def _set_sort(self, key: SortKey) -> None:
            if key == self._sort_key:
                self._sort_desc = not self._sort_desc
            else:
                self._sort_key = key
                self._sort_desc = True
            self._update_sort_button_labels()
            self._render_seeds()

        def _update_sort_button_labels(self) -> None:
            suffix = " (desc)" if self._sort_desc else " (asc)"
            for key, btn in self._sort_buttons.items():
                label = _SORT_LABELS[key]
                if key == self._sort_key:
                    label = f"{label}{suffix}"
                    btn.style = "filled"
                else:
                    btn.style = "tonal"
                btn.children[0].text = label

        def _refresh(self) -> None:
            """Dispatch a background rescan and return immediately. Use
            ``_render_seeds`` for sort/filter/expand-toggle updates that
            don't need fresh filesystem state.

            The actual scan runs on a worker thread so the first scan
            (or any scan that misses the cache) doesn't freeze the UI.
            Existing rows stay on screen until the new result lands —
            cache hits make this near-instantaneous on follow-up scans.
            """
            assert self._list_widget is not None
            assert self._status_label is not None

            if not output_dir.exists():
                self._scan_gen += 1
                self._seeds_cache = []
                self._list_widget.clear_widgets()
                self._show_message(
                    f"Output folder does not exist:\n{output_dir}",
                    status="folder missing",
                )
                return
            if not output_dir.is_dir():
                self._scan_gen += 1
                self._seeds_cache = []
                self._list_widget.clear_widgets()
                self._show_message(
                    f"Output path is not a directory:\n{output_dir}",
                    status="not a directory",
                )
                return

            self._scan_gen += 1
            gen = self._scan_gen
            prior = {s.path: s for s in self._seeds_cache}
            self._status_label.text = "scanning…"
            threading.Thread(
                target=self._scan_worker,
                args=(gen, prior),
                daemon=True,
            ).start()

        def _scan_worker(self, gen: int, prior: dict[Path, Seed]) -> None:
            """Runs on a background thread. Must not touch Kivy widgets
            directly — results go through ``Clock.schedule_once`` so the
            UI update lands on the main thread."""
            seeds: list[Seed] = []
            err: Exception | None = None
            try:
                # 4 workers is enough to overlap I/O across a typical
                # output folder without paying meaningful pool overhead.
                # Per-seed cost is mostly zipfile reads + zlib, both of
                # which release the GIL.
                seeds = scan_directory(output_dir, cache=prior, workers=4)
            except OSError as e:
                err = e
            except Exception as e:  # noqa: BLE001  # never crash the launcher
                logger.exception("seed scan failed")
                err = e
            Clock.schedule_once(
                lambda _dt: self._on_scan_complete(gen, seeds, err), 0
            )

        def _on_scan_complete(
            self, gen: int, seeds: list[Seed], err: Exception | None
        ) -> None:
            if gen != self._scan_gen:
                return  # a newer scan has already started; drop this result
            assert self._list_widget is not None
            if err is not None:
                self._seeds_cache = []
                self._list_widget.clear_widgets()
                self._show_message(
                    f"Cannot read {output_dir}:\n{err}",
                    status="folder unreadable",
                )
                return
            self._seeds_cache = seeds
            self._render_seeds()

        def _render_seeds(self) -> None:
            """Render the cached seed list applying the current filter
            and sort. Cheap — no disk access, and existing card widgets
            are reused so filter / sort changes don't pay the per-card
            construction cost."""
            assert self._list_widget is not None
            assert self._status_label is not None

            # Drop cards whose seed disappeared from the cache or whose
            # Seed object got replaced by a re-scan — those are stale
            # and need to be rebuilt before being shown again.
            current_by_path = {s.path: s for s in self._seeds_cache}
            for path in list(self._row_widgets):
                cached_seed, _card = self._row_widgets[path]
                if current_by_path.get(path) is not cached_seed:
                    del self._row_widgets[path]

            if not self._seeds_cache:
                self._list_widget.clear_widgets()
                self._show_message(
                    f"No AP_*.zip seeds found in\n{output_dir}",
                    status="0 seeds",
                )
                return

            # State chip narrows the universe first; text search then
            # refines within that subset. Matches the visual order in
            # the UI (chip row above search) and the user's mental
            # model: "show me hosted seeds called minecraft".
            visible = filter_by_state(self._seeds_cache, self._state_filter)
            visible = filter_seeds(visible, self._filter_text)
            sorted_visible = sort_seeds(
                visible, key=self._sort_key, desc=self._sort_desc
            )
            total = len(self._seeds_cache)

            if not sorted_visible:
                self._list_widget.clear_widgets()
                self._show_message(
                    self._no_match_message(),
                    status=f"0 of {total} match",
                )
                return

            cards_in_order: list[object] = []
            for seed in sorted_visible:
                cached = self._row_widgets.get(seed.path)
                if cached is None:
                    card = self._build_seed_row(seed)
                    self._row_widgets[seed.path] = (seed, card)
                else:
                    card = cached[1]
                cards_in_order.append(card)

            # Reparent in the new order. clear_widgets + add_widget on
            # already-built widgets is cheap (just list mutation +
            # layout invalidation); the expensive work — building the
            # MDCard tree — only happens for genuinely-new seeds above.
            self._list_widget.clear_widgets()
            for card in cards_in_order:
                self._list_widget.add_widget(card)

            if self._filter_text.strip() or self._state_filter != "all":
                self._status_label.text = f"{len(sorted_visible)} of {total} match"
            else:
                self._status_label.text = f"{total} seeds"

        def _no_match_message(self) -> str:
            """Tailor the empty-state message to whichever filter (or
            both) is currently active so the user knows what to relax."""
            text = self._filter_text.strip()
            state = self._state_filter
            if text and state != "all":
                return (
                    f"No {_STATE_LABELS[state].lower()} seeds match '{text}'"
                )
            if text:
                return f"No seeds match '{text}'"
            if state != "all":
                return f"No seeds are {_STATE_LABELS[state].lower()}"
            return "No seeds"

        def _show_message(self, text: str, *, status: str) -> None:
            assert self._list_widget is not None
            assert self._status_label is not None
            row = MDBoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(96),
                padding=(dp(16), dp(8)),
            )
            row.add_widget(MDLabel(text=text, halign="left", valign="center"))
            self._list_widget.add_widget(row)
            self._status_label.text = status

        def _on_watcher_event(self) -> None:
            """Watchdog thread → debounce → main thread refresh."""
            if self._refresh_pending:
                return
            self._refresh_pending = True
            Clock.schedule_once(lambda _dt: self._coalesced_refresh(), 0.5)

        def _coalesced_refresh(self) -> None:
            self._refresh_pending = False
            self._refresh()

        def _build_seed_row(self, seed: Seed) -> MDCard:
            has_details = bool(seed.slots) or seed.generator_version is not None
            expanded = has_details and seed.path in self._expanded

            # Card sits on top of the navy bg using the next surface
            # tone up — same trick the launcher tiles use. Flat
            # (elevation 0) so it reads as a row strip, not a chunky
            # raised tile.
            card = MDCard(
                orientation="vertical",
                size_hint_y=None,
                height=dp(64),  # adjusted below if expanded
                md_bg_color=self.theme_cls.surfaceContainerColor,
                radius=[dp(8)],
                elevation=0,
                ripple_behavior=False,
            )

            header = MDBoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(64),
                padding=(dp(16), 0),
                spacing=dp(8),
            )
            if has_details:
                header.add_widget(self._expand_button(seed, expanded))
            header.add_widget(
                MDLabel(
                    text=_format_seed_row(seed),
                    halign="left",
                    valign="center",
                )
            )
            header.add_widget(self._build_action_buttons(seed))
            card.add_widget(header)

            if expanded:
                details = self._build_details_panel(seed)
                card.add_widget(details)
                card.height = dp(64) + details.height + dp(8)

            return card

        def _expand_button(self, seed: Seed, expanded: bool) -> MDButton:
            btn = MDButton(
                MDButtonText(
                    text="-" if expanded else "+",
                    font_style="Title",
                    role="large",
                ),
                style="tonal",
                size_hint=(None, None),
                size=(dp(56), dp(48)),
                pos_hint={"center_y": 0.5},
            )
            btn.bind(on_release=lambda _btn, s=seed: self._toggle_expanded(s))
            return btn

        def _toggle_expanded(self, seed: Seed) -> None:
            if seed.path in self._expanded:
                self._expanded.discard(seed.path)
            else:
                self._expanded.add(seed.path)
            self._swap_row(seed)

        def _swap_row(self, seed: Seed) -> None:
            """Rebuild just *seed*'s card in place. Avoids the full
            list re-render that toggling expansion used to trigger —
            with many seeds the per-card widget churn was visible as
            input lag on every '+' click."""
            assert self._list_widget is not None
            cached = self._row_widgets.get(seed.path)
            if cached is None or cached[1].parent is None:
                # Lost track of the widget (e.g. cache was cleared
                # between renders). Fall back to a full re-render so
                # state reconciles cleanly.
                self._render_seeds()
                return
            old = cached[1]
            idx = self._list_widget.children.index(old)
            self._list_widget.remove_widget(old)
            new = self._build_seed_row(seed)
            self._list_widget.add_widget(new, index=idx)
            self._row_widgets[seed.path] = (seed, new)

        def _build_details_panel(self, seed: Seed) -> MDBoxLayout:
            slot_line_h = dp(36)
            footer_line_h = dp(24)
            footer_lines = _format_seed_footer_lines(seed)
            n_slots = len(seed.slots)
            panel_height = (
                n_slots * slot_line_h
                + len(footer_lines) * footer_line_h
                + dp(8)
            )

            panel = MDBoxLayout(
                orientation="vertical",
                size_hint_y=None,
                height=panel_height,
                padding=(dp(72), dp(4), dp(16), dp(8)),
                spacing=dp(2),
            )
            for slot_num, slot_name, game in seed.slots:
                panel.add_widget(self._build_slot_row(seed, slot_num, slot_name, game))
            for line in footer_lines:
                panel.add_widget(
                    MDLabel(
                        text=line,
                        halign="left",
                        valign="middle",
                        size_hint_y=None,
                        height=footer_line_h,
                    )
                )
            return panel

        def _build_slot_row(
            self, seed: Seed, slot_num: int, slot_name: str, game: str
        ) -> MDBoxLayout:
            slot_type = seed.slot_types.get(slot_num, "player")
            patch = seed.slot_patches.get(slot_num)
            patch_marker = f"  [{patch}]" if patch else ""
            progress_marker = _format_slot_progress(seed, slot_num)

            row = MDBoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(36),
                spacing=dp(8),
            )
            row.add_widget(
                MDLabel(
                    text=(
                        f"Slot {slot_num} — {slot_name}  "
                        f"({game}, {slot_type}){patch_marker}{progress_marker}"
                    ),
                    halign="left",
                    valign="middle",
                )
            )
            if patch:
                btn = MDButton(
                    MDButtonText(text=f"Extract {patch}"),
                    style="tonal",
                    size_hint=(None, None),
                    size=(dp(148), dp(32)),
                    pos_hint={"center_y": 0.5},
                )
                btn.bind(
                    on_release=lambda _btn, s=seed, n=slot_num: self._extract_patch(s, n)
                )
                row.add_widget(btn)
            return row

        def _extract_patch(self, seed: Seed, slot_num: int) -> None:
            assert self._status_label is not None
            try:
                dest = actions.extract_slot_patch(seed, slot_num)
            except Exception as e:  # noqa: BLE001  # surface, never crash
                logger.exception(
                    "extract patch failed for slot %s in %s", slot_num, seed.path
                )
                self._status_label.text = f"extract failed: {e}"
                return
            self._status_label.text = f"extracted slot {slot_num} to {dest}"

        def _build_action_buttons(self, seed: Seed) -> MDBoxLayout:
            box = MDBoxLayout(
                orientation="horizontal",
                size_hint=(None, None),
                width=dp(440),
                height=dp(40),
                spacing=dp(4),
                pos_hint={"center_y": 0.5},
            )
            corrupt = seed.error is not None
            box.add_widget(
                self._action_button(
                    "Host",
                    lambda _btn, s=seed: self._do_action(actions.host_seed, s, "host"),
                    disabled=corrupt or not seed.has_archipelago_file,
                )
            )
            box.add_widget(
                self._action_button(
                    "AP.gg",
                    lambda _btn, s=seed: self._do_action(
                        actions.open_in_browser_upload, s, "open archipelago.gg"
                    ),
                )
            )
            box.add_widget(
                self._action_button(
                    "Spoiler",
                    lambda _btn, s=seed: self._do_action(actions.open_spoiler, s, "open spoiler"),
                    disabled=not seed.has_spoiler,
                )
            )
            box.add_widget(
                self._action_button(
                    "Reveal",
                    lambda _btn, s=seed: self._do_action(
                        actions.reveal_in_file_manager, s, "reveal"
                    ),
                )
            )
            box.add_widget(
                self._action_button(
                    "Delete",
                    lambda _btn, s=seed: self._confirm_delete(s),
                )
            )
            return box

        def _action_button(
            self, label: str, on_release: object, *, disabled: bool = False
        ) -> MDButton:
            btn = MDButton(
                MDButtonText(text=label),
                style="tonal",
                size_hint=(None, None),
                size=(dp(84), dp(40)),
            )
            btn.disabled = disabled
            btn.bind(on_release=on_release)
            return btn

        def _do_action(self, fn, seed: Seed, label: str) -> None:
            try:
                fn(seed)
            except Exception as e:  # noqa: BLE001  # surface errors, never crash app
                logger.exception("%s failed for %s", label, seed.path)
                assert self._status_label is not None
                self._status_label.text = f"{label} failed: {e}"

        def _confirm_delete(self, seed: Seed) -> None:
            games = ", ".join(f"{c}×{g}" if c > 1 else g for g, c in seed.games) or "(unknown)"
            dialog: ButtonsPrompt | None = None

            def _response(label: str) -> None:
                assert dialog is not None
                dialog.dismiss()
                if label != "Delete":
                    return
                try:
                    actions.delete_seed(seed, confirmed=True)
                except Exception as e:  # noqa: BLE001
                    logger.exception("delete failed for %s", seed.path)
                    assert self._status_label is not None
                    self._status_label.text = f"delete failed: {e}"
                    return
                self._refresh()

            dialog = ButtonsPrompt(
                "Delete seed?",
                f"{seed.path.name}\nGames: {games}",
                _response,
                "Cancel",
                "Delete",
            )
            dialog.open()

    SeedBrowserApp().run()
