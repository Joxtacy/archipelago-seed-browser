"""Unit tests for :mod:`seed_browser.actions`.

Covers the pure-logic bits per PLAN.md §7 Phase 3 — UI invocation and
the actual host/spoiler/reveal commands are exercised manually against
a real AP install.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest

from seed_browser.actions import (
    _macos_terminal_command,
    _reveal_command,
    delete_seed,
    extract_slot_patch,
    open_in_browser_upload,
    open_spoiler,
)
from seed_browser.scanner import Seed


def _seed(path: Path, *, has_spoiler: bool = False) -> Seed:
    return Seed(path=path, mtime=0.0, size_bytes=0, has_spoiler=has_spoiler)


def test_reveal_command_macos(tmp_path: Path) -> None:
    p = tmp_path / "AP_1.zip"
    assert _reveal_command(p, "darwin") == ["open", "-R", str(p)]


def test_reveal_command_windows(tmp_path: Path) -> None:
    p = tmp_path / "AP_1.zip"
    assert _reveal_command(p, "win32") == ["explorer", f"/select,{p}"]


def test_reveal_command_linux_falls_back_to_parent(tmp_path: Path) -> None:
    p = tmp_path / "AP_1.zip"
    # xdg-open has no portable "select" flag; we open the parent dir instead.
    assert _reveal_command(p, "linux") == ["xdg-open", str(p.parent)]


def test_delete_seed_refuses_without_confirmation(tmp_path: Path) -> None:
    p = tmp_path / "AP_1.zip"
    p.write_bytes(b"x")
    with pytest.raises(ValueError, match="confirmed=True"):
        delete_seed(_seed(p), confirmed=False)
    assert p.exists(), "file must not be touched without explicit confirmation"


def test_delete_seed_hard_unlink_when_send2trash_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Setting ``sys.modules['send2trash'] = None`` makes ``import
    send2trash`` raise ImportError — verifies the fallback path."""
    p = tmp_path / "AP_1.zip"
    p.write_bytes(b"x")
    monkeypatch.setitem(sys.modules, "send2trash", None)
    delete_seed(_seed(p), confirmed=True)
    assert not p.exists()


def test_delete_seed_uses_send2trash_when_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "AP_1.zip"
    p.write_bytes(b"x")
    calls: list[str] = []

    class _FakeSend2Trash:
        @staticmethod
        def send2trash(path: str) -> None:
            calls.append(path)
            Path(path).unlink()

    monkeypatch.setitem(sys.modules, "send2trash", _FakeSend2Trash)
    delete_seed(_seed(p), confirmed=True)
    assert calls == [str(p)]
    assert not p.exists()


def test_macos_terminal_command_quotes_paths_with_spaces() -> None:
    """Spaces in paths must round-trip through shell quoting *and*
    AppleScript string escaping unscathed."""
    cmd = _macos_terminal_command(["/usr/bin/python3", "/Apps/MultiServer.py", "/seeds/AP 1.zip"])
    assert cmd[:2] == ["osascript", "-e"]
    script = cmd[2]
    # AppleScript "do script" gets the shell command as a literal string.
    # The shell-level quoting (single quotes around the path with a space)
    # must survive intact inside the AppleScript double-quoted literal.
    assert "'/seeds/AP 1.zip'" in script
    assert "do script" in script
    assert "activate" in script


def test_macos_terminal_command_escapes_embedded_quotes() -> None:
    """A double-quote in an argv element would break the AppleScript
    literal unless escaped to ``\\\"``."""
    cmd = _macos_terminal_command(["echo", 'he said "hi"'])
    script = cmd[2]
    # Literal `\"` in the AppleScript means the source string contains a
    # backslash followed by a double-quote.
    assert '\\"' in script


def test_open_in_browser_upload_targets_archipelago_gg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The website-host button must point at archipelago.gg's upload
    page, not anywhere else — and never accidentally upload the file
    itself (that would be the deeper integration we deferred)."""
    calls: list[str] = []
    monkeypatch.setattr("seed_browser.actions.webbrowser.open", calls.append)
    open_in_browser_upload(_seed(Path("/tmp/AP_1.zip")))
    assert calls == ["https://archipelago.gg/uploads"]


def test_extract_slot_patch_writes_file_alongside_seed(tmp_path: Path) -> None:
    """Extract the slot's patch entry to the same directory as the
    seed zip and return the resulting path."""
    seed_path = tmp_path / "AP_12345.zip"
    with zipfile.ZipFile(seed_path, "w") as zf:
        zf.writestr("AP_12345_P1_Jox.apmc", b"patch-bytes")
        zf.writestr("AP_12345_P2_Bob.aplttp", b"other-slot-bytes")

    seed = Seed(
        path=seed_path,
        mtime=0.0,
        size_bytes=0,
        slot_patches={1: ".apmc", 2: ".aplttp"},
    )
    out = extract_slot_patch(seed, 1)
    assert out == tmp_path / "AP_12345_P1_Jox.apmc"
    assert out.read_bytes() == b"patch-bytes"


def test_extract_slot_patch_refuses_server_only_slot(tmp_path: Path) -> None:
    """Slots without a patch entry (Jigsaw, ChecksFinder, ...) must
    raise rather than silently produce an empty file."""
    seed = Seed(path=tmp_path / "AP_1.zip", mtime=0.0, size_bytes=0)
    with pytest.raises(ValueError, match="no patch file"):
        extract_slot_patch(seed, 1)


def test_extract_slot_patch_does_not_grab_wrong_slot(tmp_path: Path) -> None:
    """The ``_P<slot>_`` guard prevents the regex from matching a
    different slot that happens to share the same patch suffix."""
    seed_path = tmp_path / "AP_99.zip"
    with zipfile.ZipFile(seed_path, "w") as zf:
        zf.writestr("AP_99_P1_Alice.apmc", b"slot1")
        zf.writestr("AP_99_P2_Bob.apmc", b"slot2")
    seed = Seed(
        path=seed_path,
        mtime=0.0,
        size_bytes=0,
        slot_patches={1: ".apmc", 2: ".apmc"},
    )
    assert extract_slot_patch(seed, 2).read_bytes() == b"slot2"


def test_open_spoiler_rejects_seed_without_spoiler(tmp_path: Path) -> None:
    p = tmp_path / "AP_1.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("AP_1.archipelago", b"\x00")
    with pytest.raises(ValueError, match="no spoiler"):
        open_spoiler(_seed(p, has_spoiler=False))
