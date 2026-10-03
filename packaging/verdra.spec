# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: F821 - PyInstaller defines SPECPATH, workpath, Analysis, PYZ, EXE and COLLECT.
"""PyInstaller build of Verdra (Master plan 13.6).

One folder, no UPX, no single-file mode, so the Qt libraries stay separate, replaceable files
(decision record 0002). Every Qt binding outside the allowed modules (plan 8.1, `[tool.verdra.qt]`
in pyproject.toml) is excluded; `tools/check_build.py` then checks the built folder.

Usage: uv run pyinstaller packaging/verdra.spec --noconfirm
"""

import sys
from pathlib import Path, PurePath

from PyInstaller.utils.hooks import copy_metadata

ROOT = Path(SPECPATH).parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))
import check_build  # noqa: E402 - found through the path added above

from verdra.soil import terrain  # noqa: E402 - found through the path added above

CONFIG = check_build.load_config(ROOT)
ALLOWED = check_build.permitted(CONFIG)
OTHERS = check_build.installed_modules() - ALLOWED
EXCLUDED = sorted(f"PySide6.Qt{name}" for name in OTHERS)

# The short Git commit the About dialog and the support bundle show (plan 13.4).
BUILD_STAMP = Path(workpath) / "build.txt"
BUILD_STAMP.parent.mkdir(parents=True, exist_ok=True)
BUILD_STAMP.write_text(check_build.build_id(ROOT) + "\n", encoding="utf-8")

analysis = Analysis(
    [str(ROOT / "src" / "verdra" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    datas=[
        (str(ROOT / "src" / "verdra" / "assets"), "verdra/assets"),
        # The legal texts exist once, at the repository root (decision record 0010).
        *((str(ROOT / name), "verdra/assets/legal") for name in check_build.LEGAL_TEXTS),
        (str(BUILD_STAMP), "verdra/assets"),
        *copy_metadata("verdra"),
    ],
    # roots/litmus is diagnostic interception from source only (spec S-11, decision record 0015).
    excludes=[*EXCLUDED, "tkinter", check_build.DIAGNOSTIC_MODULE],
    noarchive=False,
)

# Qt plugins can pull in libraries of modules the app never imports (the input-method plugin
# brings Qt Virtual Keyboard and Qt Quick, for example). Leave out every file the build gate
# would reject; Qt skips a plugin it can't load.
def keep(entry: tuple[str, str, str]) -> bool:
    return check_build.rejected(PurePath(entry[0]), ALLOWED, OTHERS) is None


analysis.binaries = [entry for entry in analysis.binaries if keep(entry)]
analysis.datas = [entry for entry in analysis.datas if keep(entry)]
pyz = PYZ(analysis.pure)
executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name=terrain.EXECUTABLE,  # "verdra" / "verdra.exe" (Reference R3); never changes
    console=False,
    upx=False,
)
COLLECT(executable, analysis.binaries, analysis.datas, upx=False, name="Verdra")
