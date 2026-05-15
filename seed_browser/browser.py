"""Standalone Kivy app for the Seed Browser.

Launched as a subprocess by :func:`worlds.LauncherComponents.launch`. All
Kivy / KivyMD imports happen inside :func:`_run_app` so that importing
this module from the launcher costs nothing.
"""

from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Literal

from . import actions
from .scanner import Seed, scan_directory

logger = logging.getLogger(__name__)

SortKey = Literal["date", "size", "slots", "hosted"]
_SORT_LABELS: dict[SortKey, str] = {
    "date": "Date",
    "size": "Size",
    "slots": "Slots",
    "hosted": "Last hosted",
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
    if seed.error:
        return f"{seed.path.name}  —  error: {seed.error}"
    ts = datetime.datetime.fromtimestamp(seed.mtime).strftime("%Y-%m-%d %H:%M")
    nslots = len(seed.slots)
    games_str = ", ".join(f"{count}×{game}" if count > 1 else game for game, count in seed.games)
    size_str = _format_size(seed.size_bytes)
    parts = [ts, f"{nslots} slots", games_str, size_str]
    if seed.has_spoiler:
        parts.append("(spoiler)")
    if seed.has_save and seed.last_hosted is not None:
        hosted_ts = datetime.datetime.fromtimestamp(seed.last_hosted).strftime("%Y-%m-%d %H:%M")
        parts.append(f"hosted {hosted_ts}")
    return "  ·  ".join(parts)


def _format_version(version: tuple[int, int, int] | None) -> str | None:
    if version is None:
        return None
    return ".".join(str(p) for p in version)


def _format_size(n: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    size = float(n)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} {units[-1]}"


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
    from kivy.metrics import dp
    from kivymd.uix.boxlayout import MDBoxLayout
    from kivymd.uix.button import MDButton, MDButtonText
    from kivymd.uix.card import MDCard
    from kivymd.uix.label import MDLabel
    from kivymd.uix.list import MDList
    from kivymd.uix.scrollview import MDScrollView
    from kvui import ButtonsPrompt, ThemedApp

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
            self._observer: object | None = None
            self._refresh_pending: bool = False
            self._expanded: set[Path] = set()
            """Paths of seeds whose detail panel is currently expanded.
            Survives ``_refresh()`` so toggle state isn't lost on
            re-scan."""

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
            for key in ("date", "size", "slots", "hosted"):
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
            self._refresh()

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
            assert self._list_widget is not None
            assert self._status_label is not None
            self._list_widget.clear_widgets()

            if not output_dir.exists():
                self._show_message(
                    f"Output folder does not exist:\n{output_dir}",
                    status="folder missing",
                )
                return
            if not output_dir.is_dir():
                self._show_message(
                    f"Output path is not a directory:\n{output_dir}",
                    status="not a directory",
                )
                return

            try:
                seeds = scan_directory(output_dir)
            except OSError as e:
                self._show_message(
                    f"Cannot read {output_dir}:\n{e}",
                    status="folder unreadable",
                )
                return

            if not seeds:
                self._show_message(
                    f"No AP_*.zip seeds found in\n{output_dir}",
                    status="0 seeds",
                )
                return

            for seed in sort_seeds(seeds, key=self._sort_key, desc=self._sort_desc):
                self._list_widget.add_widget(self._build_seed_row(seed))
            self._status_label.text = f"{len(seeds)} seeds"

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
            self._refresh()

        def _build_details_panel(self, seed: Seed) -> MDBoxLayout:
            slot_line_h = dp(24)
            footer_h = dp(28)
            has_footer = (
                seed.generator_version is not None or seed.min_server_version is not None
            )
            n_slots = len(seed.slots)
            panel_height = n_slots * slot_line_h + (footer_h if has_footer else 0) + dp(8)

            panel = MDBoxLayout(
                orientation="vertical",
                size_hint_y=None,
                height=panel_height,
                padding=(dp(72), dp(4), dp(16), dp(8)),
                spacing=dp(2),
            )
            for slot_num, slot_name, game in seed.slots:
                slot_type = seed.slot_types.get(slot_num, "player")
                patch = seed.slot_patches.get(slot_num)
                patch_marker = f"  [{patch}]" if patch else ""
                panel.add_widget(
                    MDLabel(
                        text=f"Slot {slot_num} — {slot_name}  ({game}, {slot_type}){patch_marker}",
                        halign="left",
                        valign="middle",
                        size_hint_y=None,
                        height=slot_line_h,
                    )
                )
            if has_footer:
                gen = _format_version(seed.generator_version) or "?"
                minsrv = _format_version(seed.min_server_version) or "?"
                panel.add_widget(
                    MDLabel(
                        text=f"Generated by AP {gen}  ·  Requires server ≥ AP {minsrv}",
                        halign="left",
                        valign="middle",
                        size_hint_y=None,
                        height=footer_h,
                    )
                )
            return panel

        def _build_action_buttons(self, seed: Seed) -> MDBoxLayout:
            box = MDBoxLayout(
                orientation="horizontal",
                size_hint=(None, None),
                width=dp(360),
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
