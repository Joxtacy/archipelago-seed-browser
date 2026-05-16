"""Per-row actions: host a seed, open its spoiler, reveal in the file
manager, delete it.

All filesystem-touching operations live here so the UI layer in
:mod:`seed_browser.browser` can stay declarative. Each public function
takes a :class:`~seed_browser.scanner.Seed` and either succeeds silently
or raises — UI is responsible for surfacing errors.

Why we shell out to Host:
    The launcher's Host ``Component`` is registered with ``script_name``
    only (no ``func``) — there is no callable to invoke directly. The
    canonical dispatch is ``Launcher.launch(Launcher.get_exe(host),
    in_terminal=host.cli)``: Host has ``cli=True``, so on macOS/Linux it
    must run inside a terminal window or MultiServer sits silently
    blocked on stdin. We import those helpers from ``Launcher.py`` —
    its module-level imports do not pull Kivy, so the cost is bounded.
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
import sys
import tempfile
import webbrowser
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .scanner import Seed

logger = logging.getLogger(__name__)


def host_seed(seed: Seed) -> None:
    """Spawn AP's Host component on *seed*'s zip via the launcher's own
    dispatcher so the terminal-window handling for ``cli=True``
    components is preserved.

    macOS special case: ``Launcher.launch`` uses ``open -a Terminal.app
    <argv...>``, which makes ``open`` treat the trailing tokens as files
    to open in Terminal rather than as a command to run. We bypass it
    here with an AppleScript ``do script`` so MultiServer actually starts
    with the seed argument.
    """
    import Launcher
    from worlds.LauncherComponents import components

    host = next((c for c in components if c.display_name == "Host"), None)
    if host is None:
        raise RuntimeError("Host component not registered in this Archipelago install")
    exe = Launcher.get_exe(host)
    if exe is None:
        raise RuntimeError("Cannot resolve Host executable from component metadata")
    argv = [*exe, str(seed.path)]
    if sys.platform == "darwin" and host.cli:
        subprocess.Popen(_macos_terminal_command(argv))
    else:
        Launcher.launch(argv, in_terminal=host.cli)


def open_spoiler(seed: Seed) -> None:
    """Extract the ``*_Spoiler.txt`` entry to a temp file and open it."""
    if not seed.has_spoiler:
        raise ValueError("seed has no spoiler log")
    from Utils import open_file

    with zipfile.ZipFile(seed.path) as zf:
        entry = next((n for n in zf.namelist() if n.endswith("_Spoiler.txt")), None)
        if entry is None:
            raise ValueError("spoiler entry missing from zip namelist")
        content = zf.read(entry)

    fd, tmp_path = tempfile.mkstemp(suffix=".txt", prefix="ap_spoiler_")
    with os.fdopen(fd, "wb") as f:
        f.write(content)
    open_file(tmp_path)


_UPLOADS_URL = "https://archipelago.gg/uploads"


def open_in_browser_upload(_seed: Seed) -> None:
    """Open archipelago.gg's upload page in the default browser.

    Doesn't push the zip directly — the user picks it on the upload
    page. This is the safe convenience-only path; a scripted upload
    against the form route is documented in IDEAS.md as a stretch.
    """
    webbrowser.open(_UPLOADS_URL)


def extract_slot_patch(seed: Seed, slot_num: int) -> Path:
    """Pull slot *slot_num*'s patch entry out of *seed*'s zip and write
    it next to the zip in the same directory. Returns the path of the
    extracted file.

    Refuses (``ValueError``) when the slot has no patch in the scanner's
    ``slot_patches`` map — server-only slots (Jigsaw, ChecksFinder, …)
    have no patch container; nothing to extract.
    """
    if slot_num not in seed.slot_patches:
        raise ValueError(f"slot {slot_num} has no patch file")
    suffix = seed.slot_patches[slot_num]
    with zipfile.ZipFile(seed.path) as zf:
        # Patch entries follow ``AP_<id>_P<slot>_<player>.<suffix>``. We
        # already know the suffix; the slot guard pins ``_P<N>_`` so we
        # don't grab another slot's patch with the same suffix.
        slot_marker = f"_P{slot_num}_"
        entry = next(
            (n for n in zf.namelist() if slot_marker in n and n.endswith(suffix)),
            None,
        )
        if entry is None:
            raise FileNotFoundError(
                f"no patch entry for slot {slot_num} in {seed.path.name}"
            )
        # Strip any zip-internal path so we always write a flat file
        # alongside the seed zip, not into a subdir.
        destination = seed.path.parent / Path(entry).name
        with zf.open(entry) as src, open(destination, "wb") as dst:
            dst.write(src.read())
    return destination


def reveal_in_file_manager(seed: Seed) -> None:
    """Open the OS file manager focused on *seed*'s zip."""
    cmd = _reveal_command(seed.path, sys.platform)
    subprocess.Popen(cmd)


def delete_seed(seed: Seed, *, confirmed: bool) -> None:
    """Delete *seed*'s zip. Sends to OS trash if ``send2trash`` is
    available, falls back to a hard ``unlink`` otherwise.

    Refuses unless *confirmed* is ``True`` — the UI must drive the
    confirmation dialog.
    """
    if not confirmed:
        raise ValueError("delete_seed requires confirmed=True")
    try:
        import send2trash
    except ImportError:
        seed.path.unlink()
        logger.info("hard-deleted %s (send2trash unavailable)", seed.path)
    else:
        send2trash.send2trash(str(seed.path))


def _macos_terminal_command(argv: list[str]) -> list[str]:
    """Return the ``osascript`` argv that opens a new Terminal.app
    window and runs *argv* inside it.

    Extracted as a pure function so the AppleScript composition can be
    unit-tested without spawning a process.
    """
    shell_cmd = shlex.join(argv)
    # AppleScript string literal: escape backslashes first, then quotes.
    escaped = shell_cmd.replace("\\", "\\\\").replace('"', '\\"')
    # Single tell block: `do script` opens a new window with the command,
    # then `activate` fronts Terminal. Two separate top-level `-e tell`s
    # would launch Terminal twice when it wasn't already running,
    # producing a stray empty window.
    script = f'tell application "Terminal"\n    do script "{escaped}"\n    activate\nend tell'
    return ["osascript", "-e", script]


def _reveal_command(path: Path, platform: str) -> list[str]:
    """Pure helper — return the argv that opens a file manager on *path*.

    Extracted from :func:`reveal_in_file_manager` so it can be unit-tested
    without monkey-patching :mod:`subprocess`.
    """
    if platform == "darwin":
        return ["open", "-R", str(path)]
    if platform.startswith("win"):
        return ["explorer", f"/select,{path}"]
    return ["xdg-open", str(path.parent)]


