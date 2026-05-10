"""Standalone Kivy app for the Seed Browser.

Launched as a subprocess by :func:`worlds.LauncherComponents.launch`. All
Kivy / KivyMD imports happen inside :func:`_run_app` so that importing
this module from the launcher costs nothing.
"""

from __future__ import annotations

import datetime
import logging
from pathlib import Path

from .scanner import Seed, scan_directory


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
    spoiler = "  (spoiler)" if seed.has_spoiler else ""
    return f"{ts}  ·  {nslots} slots  ·  {games_str}  ·  {size_str}{spoiler}"


def _format_size(n: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    size = float(n)
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} {units[-1]}"


def _run_app(args: tuple[str, ...]) -> None:
    from kivy.metrics import dp
    from kivymd.uix.boxlayout import MDBoxLayout
    from kivymd.uix.button import MDButton, MDButtonText
    from kivymd.uix.label import MDLabel
    from kivymd.uix.list import MDList, MDListItem, MDListItemHeadlineText
    from kivymd.uix.scrollview import MDScrollView
    from kvui import ThemedApp

    output_dir = _resolve_output_dir()

    class SeedBrowserApp(ThemedApp):
        title = "Seed Browser"

        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)
            self.set_colors()
            self._list_widget: MDList | None = None
            self._status_label: MDLabel | None = None

        def build(self) -> MDBoxLayout:
            root = MDBoxLayout(
                orientation="vertical",
                padding=dp(16),
                spacing=dp(12),
            )

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
            root.add_widget(header)

            scroll = MDScrollView()
            self._list_widget = MDList()
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
            return root

        def _refresh(self) -> None:
            assert self._list_widget is not None
            assert self._status_label is not None
            self._list_widget.clear_widgets()
            seeds = scan_directory(output_dir)
            if not seeds:
                self._list_widget.add_widget(
                    MDListItem(
                        MDListItemHeadlineText(
                            text=f"No AP_*.zip seeds found in {output_dir}",
                        )
                    )
                )
                self._status_label.text = "0 seeds"
                return
            for seed in seeds:
                self._list_widget.add_widget(
                    MDListItem(MDListItemHeadlineText(text=_format_seed_row(seed)))
                )
            self._status_label.text = f"{len(seeds)} seeds"

    SeedBrowserApp().run()
