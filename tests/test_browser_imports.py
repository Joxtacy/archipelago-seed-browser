"""Guard the kvui-before-kivy import order inside ``_run_app``.

Importing ``kivy.core.window`` before ``kvui`` hangs the app on Linux
(SDL audio init after window creation deadlocks). kvui's own assert is
stripped in frozen AP builds, so this static check is the only guard.
"""

from __future__ import annotations

import ast
import inspect

from seed_browser import browser


def _imported_modules(fn: object) -> list[str]:
    tree = ast.parse(inspect.getsource(fn))
    mods: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            mods.append(node.module)
        elif isinstance(node, ast.Import):
            mods.extend(alias.name for alias in node.names)
    return mods


def test_run_app_imports_kvui_before_any_kivy_module() -> None:
    mods = _imported_modules(browser._run_app)
    assert "kvui" in mods
    first_kivy = next(i for i, m in enumerate(mods) if m.split(".")[0] in ("kivy", "kivymd"))
    assert mods.index("kvui") < first_kivy
