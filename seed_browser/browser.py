"""Standalone Kivy app for the Seed Browser.

Launched as a subprocess by :func:`worlds.LauncherComponents.launch`. All
Kivy / KivyMD imports happen inside :func:`_run_app` so that importing
this module from the launcher costs nothing.
"""

from __future__ import annotations

import logging


def run(*args: str) -> None:
    """Entry point invoked by the launcher subprocess.

    Phase 1 opens an empty window with a Close button. Real content is
    added in Phase 2.
    """
    try:
        _run_app(args)
    except Exception:
        logging.exception("Seed Browser crashed")
        raise


def _run_app(args: tuple[str, ...]) -> None:
    from kivy.metrics import dp
    from kivymd.uix.boxlayout import MDBoxLayout
    from kivymd.uix.button import MDButton, MDButtonText
    from kivymd.uix.label import MDLabel
    from kvui import ThemedApp

    class SeedBrowserApp(ThemedApp):
        title = "Seed Browser"

        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)
            self.set_colors()

        def build(self) -> MDBoxLayout:
            root = MDBoxLayout(
                orientation="vertical",
                padding=dp(24),
                spacing=dp(16),
            )
            root.add_widget(
                MDLabel(
                    text="Seed Browser — no seeds shown yet. (Phase 1: empty window.)",
                    halign="center",
                )
            )
            close_btn = MDButton(
                MDButtonText(text="Close"),
                style="filled",
                size_hint=(None, None),
                size=(dp(160), dp(48)),
                pos_hint={"center_x": 0.5},
            )
            close_btn.bind(on_release=lambda _btn: self.stop())
            root.add_widget(close_btn)
            return root

    SeedBrowserApp().run()
