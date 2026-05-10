"""Archipelago Launcher add-on: lists locally generated multiworld seed zips.

Registers a tile in the launcher (`Type.TOOL`) that opens a standalone Kivy
window. The Kivy app itself lives in :mod:`seed_browser.browser` and is
lazy-imported so the launcher pays no Kivy cost at startup.
"""

from __future__ import annotations

import logging

from worlds.AutoWorld import World
from worlds.LauncherComponents import (
    Component,
    Type,
    components,
)
from worlds.LauncherComponents import (
    launch as launch_component,
)


def _launch(*args: str) -> None:
    """Tile-click entry point. Forwarded args (if any) come from drag-drop
    or CLI; a plain tile click hands us no args.

    Exceptions are caught so a broken Seed Browser cannot crash the
    launcher process (`Launcher.py:412-423` does not wrap `func` in a
    try/except).
    """
    try:
        from .browser import run

        launch_component(run, name="Seed Browser", args=args)
    except Exception:
        logging.exception("Seed Browser failed to launch")


components.append(
    Component(
        "Seed Browser",
        func=_launch,
        component_type=Type.TOOL,
        description="Browse generated multiworld seed zips.",
    )
)


class _SeedBrowserStub(World):
    """Apworld-loader validation stub. Never used for generation.

    The `hidden` flag (`worlds/AutoWorld.py:313`) keeps this out of yaml
    templates and the game picker; the metaclass still requires
    `game`, `item_name_to_id`, and `location_name_to_id` to be present.
    """

    game = "_seed_browser"
    hidden = True
    topology_present = False
    item_name_to_id: dict[str, int] = {}
    location_name_to_id: dict[str, int] = {}
