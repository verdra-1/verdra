# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Build gate: the built folder holds Qt libraries of the allowed modules only.

Master plan 8.1, 12.3 and risk R-07, decision record 0002. Installing PySide6 also installs the
PySide6 Addons wheel, which contains Qt modules that are available under the GPL only. Imports
are checked by `tools/licenses.py`; this script checks what PyInstaller actually put in the
built folder, because Qt plugins can pull in libraries of modules the app never imports.

The check is an allowlist, so it needs no list of GPL-only modules: every Qt library, framework
and binding in the folder must belong to a module in `[tool.verdra.qt] allowed-modules` or to a
support library named in `[tool.verdra.qt.build-support]`. Plugins and QML files that belong to
any other Qt module fail too. Anything from Qt Wayland Compositor (GPL-only) fails by name, even
if it were added to the allowlist. `packaging/verdra.spec` uses the same rules to leave those files
out of the build.

It also checks that the build carries LICENSE, NOTICE and PRIVACY.md exactly as they are at the
repository root.

It also checks that the diagnostic interception of spec S-11 (roots/litmus, source only) isn't
in the build: no loose file and no module in the executable's archive may carry its marker, and
no archived module may have its name (test 10, decision record 0015).

With `--launch`, the built app is also started once without a screen (Qt's offscreen platform,
a throwaway data folder) and must report its main window ready within 60 seconds. It is then
started with `--diagnose-interception` and must refuse it: exit code 2, before it writes a log.

Usage: uv run python tools/check_build.py dist/Verdra [--launch]
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import pkgutil
import re
import subprocess
import sys
import tempfile
import time
import tomllib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePath
from typing import Any

from verdra.soil import terrain

ROOT = Path(__file__).resolve().parent.parent
# Qt Wayland Compositor is available under the GPL only (decision record 0010). Its libraries,
# QML plugins and server-side graphics plugins fail the check by name, before the allowlist is
# consulted, so no configuration can let them through.
COMPOSITOR = "compositor"
COMPOSITOR_PLUGINS = "wayland-graphics-integration-server"
READY = "main window ready"
WINDOW_SHOWN = re.compile(r"Startup: window shown after (\d+) ms")
#: Plan 12.4: window visible after launch within 1.5 s (mid-range laptop, warm disk).
WINDOW_BUDGET_MS = 1500
#: The legal texts the About dialog shows; the build copies them from the repository root.
LEGAL_TEXTS = ("LICENSE", "NOTICE", "PRIVACY.md")
LAUNCH_TIMEOUT_S = 60
#: Spec S-11 test 10: the source-only diagnostic module and the flag a build must refuse.
DIAGNOSTIC_MODULE = "verdra.roots.litmus"
DIAGNOSE_FLAG = "--diagnose-interception"

# libQt6Core.so.6, Qt6Core.dll, libQt6Core.6.dylib
LIBRARY = re.compile(r"^(?:lib)?Qt6([A-Za-z0-9]+?)(?:\.\d+)*\.(?:dll|so|dylib)(?:\.\d+)*$")
# QtCore.framework (macOS)
FRAMEWORK = re.compile(r"^Qt([A-Za-z0-9]+)\.framework$")
# PySide6 bindings: QtCore.abi3.so, QtCore.pyd, QtCore.cpython-314-darwin.so
BINDING = re.compile(r"^Qt([A-Za-z0-9]+)\.(?:abi3\.so|pyd|cpython-[^.]+\.so)$")


def load_config(root: Path = ROOT) -> dict[str, Any]:
    """Return the `[tool.verdra.qt]` table from pyproject.toml."""
    with (root / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["tool"]["verdra"]["qt"]


def permitted(config: dict[str, Any]) -> set[str]:
    """Return the Qt module names (without "Qt") whose libraries may ship."""
    allowed = {name.removeprefix("Qt") for name in config["allowed-modules"]}
    return allowed | set(config.get("build-support", {}))


def installed_modules() -> set[str]:
    """Return every Qt module name (without "Qt") the installed PySide6 carries.

    Python bindings alone are not enough: some Qt modules ship only as libraries and plugins (Qt
    Virtual Keyboard has no binding but installs an input-method plugin). So the list also takes
    every Qt library in the wheel and every module named in the wheel's own manifests.
    """
    import json  # noqa: PLC0415 - only needed when the check runs

    import PySide6  # noqa: PLC0415 - only needed when the check runs

    package = Path(PySide6.__file__).parent
    modules = {
        info.name.removeprefix("Qt")
        for info in pkgutil.iter_modules(PySide6.__path__)
        if info.name.startswith("Qt")
    }
    for path in (package / "Qt").rglob("*"):
        module = qt_module(path.relative_to(package))
        if module is not None:
            modules.add(module)
    for manifest in package.glob("PySide6_*.json"):
        modules.update(json.loads(manifest.read_text(encoding="utf-8")))
    return modules


def qt_module(path: PurePath) -> str | None:
    """Return the Qt module a library, framework or binding belongs to, or None."""
    for part in reversed(path.parts):
        for pattern in (FRAMEWORK, LIBRARY, BINDING):
            match = pattern.match(part)
            if match:
                return match.group(1)
    return None


def rejected(path: PurePath, allowed: set[str], others: Iterable[str]) -> str | None:
    """Return why a file must not ship, or None if it may.

    Args:
        path: The file's path inside the built folder.
        allowed: Module names (without "Qt") that may ship.
        others: Every other Qt module name (without "Qt"); plugins and QML files named after
            one of them are rejected.
    """
    lowered = [part.lower() for part in path.parts]
    if any(COMPOSITOR in part for part in lowered) or COMPOSITOR_PLUGINS in lowered:
        return "Qt Wayland Compositor is GPL-only and must never ship"
    module = qt_module(path)
    if module is not None:
        return None if module in allowed else f"Qt module Qt{module} is not allowed"
    parts = lowered
    if "qml" in parts:
        return "QML files belong to Qt Quick, which is not allowed"
    if "plugins" in parts:
        name = parts[-1]
        allowed_names = [module.lower() for module in allowed]
        for other in sorted(others, key=len, reverse=True):
            word = other.lower()
            # A name that is part of an allowed one ("wayland" in "waylandclient") says nothing.
            if word in name and not any(word in allowed_name for allowed_name in allowed_names):
                return f"plugin of Qt{other}, which is not allowed"
    return None


def check(folder: Path, config: dict[str, Any], modules: set[str]) -> list[str]:
    """Return one problem line per file in `folder` that must not ship."""
    allowed = permitted(config)
    others = modules - allowed
    problems = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(folder)
        reason = rejected(relative, allowed, others)
        if reason is not None:
            problems.append(f"{relative.as_posix()}: {reason}")
    return problems


def build_id(root: Path = ROOT) -> str:
    """Return the short Git commit of the source tree being built (plan 13.4)."""
    result = subprocess.run(  # noqa: S603 - fixed argument list, no shell
        ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
        capture_output=True,
        text=True,
        cwd=root,
        check=False,
    )
    commit = result.stdout.strip()
    if result.returncode != 0 or not re.fullmatch(r"[0-9a-f]{7,40}", commit):
        raise RuntimeError("the build needs a Git checkout to record its commit")
    return commit


def check_build_stamp(folder: Path) -> list[str]:
    """Return a problem if the build doesn't record its commit for the About dialog."""
    stamps = [path for path in folder.rglob("build.txt") if path.parent.name == "assets"]
    if not stamps:
        return ["assets/build.txt: missing, so About would show build 'dev'"]
    if not re.fullmatch(r"[0-9a-f]{7,40}", stamps[0].read_text(encoding="utf-8").strip()):
        return ["assets/build.txt: not a Git commit"]
    return []


def check_legal_texts(folder: Path, root: Path = ROOT) -> list[str]:
    """Return a problem per legal text the build lacks or carries in a different version."""
    found = {path.name: path for path in folder.rglob("*") if path.parent.name == "legal"}
    problems = []
    for name in LEGAL_TEXTS:
        if name not in found:
            problems.append(f"assets/legal/{name}: missing from the build")
        elif found[name].read_bytes() != (root / name).read_bytes():
            problems.append(f"assets/legal/{name}: differs from the repository's {name}")
    return problems


@dataclass
class Launch:
    """The result of starting the built app once."""

    problem: str | None
    window_ms: int | None = None


def detailed_logging(home: Path) -> None:
    """Turn on detailed logging in a throwaway data folder, so the startup steps are logged.

    The steps are technical detail at Debug level (plan 16.2, M0 review round 3).
    """
    settings = home / "config" / terrain.SETTINGS_FILE
    settings.parent.mkdir(parents=True, exist_ok=True)
    since = datetime.now(UTC).isoformat()
    advanced = {"detailed_logging": True, "detailed_logging_since": since}
    document = {"format": "verdra.settings", "version": 1, "advanced": advanced}
    settings.write_text(json.dumps(document), encoding="utf-8")


def launch(folder: Path, timeout: float = LAUNCH_TIMEOUT_S) -> Launch:
    """Start the built app without a screen and report when its window was shown."""
    name = terrain.EXECUTABLE + (".exe" if sys.platform == "win32" else "")
    executable = folder / name
    if not executable.exists():
        return Launch(f"{executable} is missing")
    with tempfile.TemporaryDirectory() as home:
        detailed_logging(Path(home))
        environment = os.environ | {"VERDRA_HOME": home, "QT_QPA_PLATFORM": "offscreen"}
        process = subprocess.Popen([str(executable)], env=environment)  # noqa: S603
        log = Path(home) / "logs" / terrain.LOG_FILE
        deadline = time.monotonic() + timeout
        try:
            while time.monotonic() < deadline:
                text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
                if READY in text:
                    shown = WINDOW_SHOWN.search(text)
                    return Launch(None, int(shown.group(1)) if shown else None)
                if process.poll() is not None:
                    return Launch(
                        f"the app exited with code {process.returncode} before it was ready"
                    )
                time.sleep(0.25)
            return Launch(f"the app wasn't ready after {timeout:.0f} s")
        finally:
            process.kill()
            process.wait()


def diagnostic_marker() -> bytes:
    """Return the marker only roots/litmus carries (read from the source tree)."""
    from verdra.roots import litmus  # noqa: PLC0415 - only the build check needs it

    return litmus.MARKER.encode()


def archived_modules(folder: Path) -> Iterator[tuple[str, bytes]]:
    """Yield (name, decompressed bytes) of every module in the executable's embedded archive."""
    executable = folder / (terrain.EXECUTABLE + (".exe" if sys.platform == "win32" else ""))
    if not executable.is_file():
        return
    # PyInstaller is in the build group only, so it's loaded once a built app is there.
    readers: Any = importlib.import_module("PyInstaller.archive.readers")
    archive = readers.CArchiveReader(str(executable))
    for entry in archive.toc:
        if not entry.endswith(".pyz"):
            continue
        modules = archive.open_embedded_archive(entry)
        for name in modules.toc:
            yield name, modules.extract(name, raw=True) or b""


def check_no_diagnostics(
    folder: Path, marker: bytes, modules: Iterable[tuple[str, bytes]]
) -> list[str]:
    """Return a problem for every file or archived module holding the diagnostic code path."""
    reason = "holds the diagnostic interception code path (spec S-11 test 10)"
    problems = [
        f"{path.relative_to(folder).as_posix()} {reason}"
        for path in sorted(folder.rglob("*"))
        if path.is_file() and marker in path.read_bytes()
    ]
    problems += [
        f"the archived module {name} {reason}"
        for name, data in modules
        if name == DIAGNOSTIC_MODULE or name.startswith(DIAGNOSTIC_MODULE + ".") or marker in data
    ]
    return problems


def refuses_diagnosis(folder: Path, timeout: float = LAUNCH_TIMEOUT_S) -> str | None:
    """Start the built app with the diagnostic flag; return a problem unless it refuses it."""
    name = terrain.EXECUTABLE + (".exe" if sys.platform == "win32" else "")
    with tempfile.TemporaryDirectory() as home:
        environment = os.environ | {"VERDRA_HOME": home, "QT_QPA_PLATFORM": "offscreen"}
        try:
            finished = subprocess.run(  # noqa: S603 - the app just built
                [str(folder / name), DIAGNOSE_FLAG],
                env=environment,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return f"the built app didn't refuse {DIAGNOSE_FLAG} within {timeout:.0f} s"
        if finished.returncode != 2:  # noqa: PLR2004 - argparse's exit code for a usage error
            return f"the built app exited with code {finished.returncode} for {DIAGNOSE_FLAG}"
        if (Path(home) / "logs" / terrain.LOG_FILE).exists():
            return f"the built app started logging before refusing {DIAGNOSE_FLAG}"
    return None


def report_window_time(window_ms: int | None) -> None:
    """Print the window-visible time against the 12.4 budget (and to the CI job summary)."""
    if window_ms is None:
        line = "Window-visible time: not found in the log."
    else:
        verdict = "within" if window_ms <= WINDOW_BUDGET_MS else "OVER"
        line = (
            f"Window visible {window_ms} ms after launch ({verdict} the {WINDOW_BUDGET_MS} ms "
            f"budget of plan 12.4; CI runner, first start of the frozen app)."
        )
    print(line)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as handle:
            handle.write(f"{line}\n")


def main(argv: list[str] | None = None) -> int:
    """Check one built folder; exit 1 if it holds anything outside the allowlist."""
    parser = argparse.ArgumentParser(
        description="Check a PyInstaller build against the Qt allowlist."
    )
    parser.add_argument("folder", type=Path, help="the folder PyInstaller built (dist/Verdra)")
    parser.add_argument("--launch", action="store_true", help="also start the built app once")
    arguments = parser.parse_args(argv)
    if not arguments.folder.is_dir():
        print(f"{arguments.folder} is not a folder", file=sys.stderr)
        return 2
    problems = check(arguments.folder, load_config(), installed_modules())
    problems += check_legal_texts(arguments.folder)
    problems += check_build_stamp(arguments.folder)
    problems += check_no_diagnostics(
        arguments.folder, diagnostic_marker(), archived_modules(arguments.folder)
    )
    started = launch(arguments.folder) if arguments.launch else None
    if started is not None and started.problem is not None:
        problems.append(started.problem)
    refused = refuses_diagnosis(arguments.folder) if arguments.launch else None
    if refused is not None:
        problems.append(refused)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print(f"{len(problems)} problem(s) in the built folder (Master plan 8.1, 13.6).")
        return 1
    print("The built folder holds allowed Qt modules only.")
    if started is not None:
        print("The built app started and reported its main window ready.")
        print(f"The built app refused {DIAGNOSE_FLAG}.")
        report_window_time(started.window_ms)
    return 0


if __name__ == "__main__":
    sys.exit(main())
