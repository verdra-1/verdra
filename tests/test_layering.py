# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""The layering rules of Master plan 8.2 and Reference R1 can't be bypassed (finding M8).

import-linter checks the import graph (`lint-imports`). The first tests prove that it really
breaks on a forbidden import, by adding one to a copy of the package. It can't see two other
ways around the rules, so the later tests check those directly:

- a lower layer reached through a name that trunk re-exports (`from verdra.trunk.rings import
  veil`): every name canopy uses from Verdra's own packages must come from canopy, trunk or
  soil/terrain;
- file and OS calls in canopy that need no import (`Path.read_text`): canopy is widgets only,
  and only theme.py and splash.py read Verdra's own bundled assets (R1: theme.py turns
  tokens.json into a palette).

Dynamic imports, which no static check sees, are banned in src/ by ruff (TID251).
"""

from __future__ import annotations

import ast
import functools
import importlib
import inspect
import os
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src" / "verdra"
CANOPY = SOURCE / "canopy"
#: Where canopy may take names from (Reference R1: trunk is the only layer the UI talks to; soil's
#: shared constants are allowed).
CANOPY_MAY_USE = ("verdra.canopy", "verdra.trunk", "verdra.soil.terrain")
#: The only canopy modules that read files: Verdra's own bundled assets.
ASSET_READERS = {"crown/theme.py", "crown/splash.py"}
#: pathlib's file-system methods (str.replace and QDialog.open are not file calls, so `open`
#: counts only as the built-in function).
PATH_CALLS = {
    "read_text",
    "read_bytes",
    "write_text",
    "write_bytes",
    "mkdir",
    "unlink",
    "rmdir",
    "rename",
    "touch",
    "iterdir",
    "glob",
    "rglob",
    "exists",
    "is_file",
    "is_dir",
    "stat",
    "chmod",
}
ASSET_CALLS = {"read_text", "read_bytes", "exists"}
#: Qt classes that start processes or touch the file system or the network.
QT_OS_CLASSES = {
    "QProcess",
    "QDesktopServices",
    "QFileSystemWatcher",
    "QSettings",
    "QFile",
    "QSaveFile",
    "QTemporaryFile",
    "QLockFile",
    "QDir",
    "QFileInfo",
    "QStandardPaths",
    "QLocalSocket",
    "QLocalServer",
    "QNetworkAccessManager",
    "QTcpSocket",
    "QUdpSocket",
    "QSslSocket",
    "QtNetwork",
}


# --- import-linter really breaks ------------------------------------------------------------


def lint_copy(tmp_path: Path, module: str, line: str) -> subprocess.CompletedProcess[str]:
    """Run lint-imports on a copy of the package with `line` added to `module`."""
    copy = tmp_path / "src" / "verdra"
    shutil.copytree(SOURCE, copy, ignore=shutil.ignore_patterns("__pycache__", "assets"))
    target = copy / module
    target.write_text(target.read_text(encoding="utf-8") + f"\n{line}\n", encoding="utf-8")
    shutil.copyfile(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    lint = shutil.which("lint-imports")
    assert lint is not None
    env = os.environ | {"PYTHONPATH": str(tmp_path / "src")}
    return subprocess.run(  # noqa: S603 - the project's own tool on a temporary copy
        [lint, "--config", str(tmp_path / "pyproject.toml"), "--no-cache"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.mark.parametrize(
    ("module", "line", "contract"),
    [
        ("canopy/leaves/badge.py", "from verdra.bark import veil", "The UI talks only to trunk"),
        ("trunk/rings.py", "from verdra.canopy.leaves import badge", "Layers (Master plan 8.2)"),
        (
            "canopy/leaves/badge.py",
            "import subprocess",
            "The UI makes no OS, disk or network calls of its own",
        ),
        (
            "canopy/leaves/badge.py",
            "from verdra.soil import humus",
            "The UI makes no OS, disk or network calls of its own",
        ),
    ],
)
def test_import_linter_breaks_on_a_forbidden_import(
    tmp_path: Path, module: str, line: str, contract: str
) -> None:
    done = lint_copy(tmp_path, module, line)
    assert done.returncode != 0, done.stdout
    assert f"{contract} BROKEN" in done.stdout


def test_import_linter_keeps_the_real_package(tmp_path: Path) -> None:
    done = lint_copy(tmp_path, "canopy/leaves/badge.py", "")
    assert done.returncode == 0, done.stdout


# --- re-exports through trunk -----------------------------------------------------------------


def _origin(value: object) -> str | None:
    """Return the module a Verdra object comes from, or None for plain data."""
    # A partial or a bound method comes from wherever its function does (finding F7).
    while isinstance(value, functools.partial) or inspect.ismethod(value):
        value = value.func if isinstance(value, functools.partial) else value.__func__
    if isinstance(value, types.ModuleType):
        return value.__name__
    if inspect.isclass(value) or inspect.isfunction(value) or inspect.isbuiltin(value):
        return getattr(value, "__module__", None)
    return None


def _allowed(origin: str | None) -> bool:
    if origin is None or origin == "verdra" or not origin.startswith("verdra."):
        return True
    return any(origin == prefix or origin.startswith(prefix + ".") for prefix in CANOPY_MAY_USE)


def _bindings(tree: ast.AST, where: str) -> tuple[dict[str, object], list[str]]:
    """Return the Verdra names a module imports, and the imports that reach a lower layer."""
    bound: dict[str, object] = {}
    problems: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("verdra"):
            parent = importlib.import_module(node.module)
            for alias in node.names:
                value = getattr(parent, alias.name, None)
                if value is None:
                    try:
                        value = importlib.import_module(f"{node.module}.{alias.name}")
                    except ModuleNotFoundError:
                        continue  # not a module: an undefined name, which pyright reports
                bound[alias.asname or alias.name] = value
                if not _allowed(_origin(value)):
                    problems.append(f"{where}:{node.lineno}: {node.module}.{alias.name}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("verdra"):
                    target = alias.name if alias.asname else alias.name.split(".")[0]
                    bound[alias.asname or target] = importlib.import_module(target)
    return bound, problems


def _attribute_problem(node: ast.Attribute, bound: dict[str, object], where: str) -> str | None:
    """Return a problem if an attribute chain on an imported module reaches a lower layer."""
    chain: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        chain.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name) or current.id not in bound:
        return None
    value = bound[current.id]
    for attr in reversed(chain):
        if not isinstance(value, types.ModuleType):
            return None
        value = getattr(value, attr, None)
        if not _allowed(_origin(value)):
            return f"{where}:{node.lineno}: {'.'.join([current.id, *reversed(chain)])}"
    return None


def reexport_problems(source: str, where: str) -> list[str]:
    """Return every name in `source` that reaches a lower layer through a Verdra module."""
    tree = ast.parse(source)
    bound, problems = _bindings(tree, where)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and (problem := _attribute_problem(node, bound, where)):
            problems.append(problem)
        # getattr(module, "name") is the same attribute written another way.
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            spelled = ast.Attribute(value=node.args[0], attr=node.args[1].value, ctx=ast.Load())
            ast.copy_location(spelled, node)
            if problem := _attribute_problem(spelled, bound, where):
                problems.append(problem)
    return sorted(set(problems))


def canopy_files() -> list[Path]:
    return sorted(CANOPY.rglob("*.py"))


def test_canopy_uses_no_lower_layer_through_trunk() -> None:
    problems: list[str] = []
    for path in canopy_files():
        where = path.relative_to(SOURCE).as_posix()
        problems += reexport_problems(path.read_text(encoding="utf-8"), where)
    assert problems == []


@pytest.fixture
def reexporting_trunk(monkeypatch: pytest.MonkeyPatch) -> None:
    """A trunk module that re-exports lower layers, as `from verdra.bark import veil` does."""
    import verdra.trunk

    probe = types.ModuleType("verdra.trunk.probe")
    probe.veil = importlib.import_module("verdra.bark.veil")  # type: ignore[attr-defined]
    probe.atomic = importlib.import_module("verdra.soil.atomic")  # type: ignore[attr-defined]

    def write() -> None:
        """Stands in for a soil function that trunk wraps in a partial."""

    write.__module__ = "verdra.soil.atomic"
    probe.write = functools.partial(write)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "verdra.trunk.probe", probe)
    monkeypatch.setattr(verdra.trunk, "probe", probe, raising=False)


@pytest.mark.usefixtures("reexporting_trunk")
@pytest.mark.parametrize(
    "line",
    [
        "from verdra.trunk.probe import veil",
        "from verdra.trunk import probe\nprobe.veil.__name__",
        "import verdra.trunk.probe as p\np.atomic.write_atomic",
        "from verdra.trunk.probe import atomic",
        "from verdra.trunk.probe import write",
        "from verdra.trunk import probe\nprobe.write",
        "from verdra.trunk import probe\ngetattr(probe, 'veil')",
        "import verdra.trunk.probe as p\ngetattr(p, 'atomic')",
    ],
)
def test_a_reexport_through_trunk_is_caught(line: str) -> None:
    assert reexport_problems(line, "x.py") != []


def test_names_from_trunk_itself_pass() -> None:
    source = "from verdra.trunk import rings\nrings.__name__\nfrom verdra.soil import terrain\n"
    assert reexport_problems(source, "x.py") == []


# --- file and OS calls in canopy --------------------------------------------------------------


def _constructed(value: ast.expr) -> bool:
    """Whether `value` builds an object (`Path(x)`, `QImage()`) or names a file module."""
    if isinstance(value, ast.Call):
        return True
    return isinstance(value, ast.Name) and value.id in {"io", "Path", "codecs", "gzip"}


def _call_problem(call: ast.Call, *, reads_assets: bool) -> str | None:
    function = call.func
    if isinstance(function, ast.Name) and function.id == "open":
        return "open()"
    if not isinstance(function, ast.Attribute):
        return None
    name = function.attr
    if name in PATH_CALLS and not (reads_assets and name in ASSET_CALLS):
        return f"{name}()"
    # save(target) writes a file (QImage, QPixmap); QPainter.save() with no target only pushes
    # painter state. open() and load() on a freshly built object (Path(...).open,
    # QPixmap().load(path)) read one. Tokens.load() is theme.py's own read.
    writes = name == "save" and bool(call.args or call.keywords)
    if writes or (name in {"open", "load"} and _constructed(function.value)):
        return f"{name}()"
    if (
        isinstance(function.value, ast.Name)
        and function.value.id == "terrain"
        and name[:1].islower()
    ):
        return f"terrain.{name}()"
    return None


def file_call_problems(source: str, where: str, *, reads_assets: bool) -> list[str]:
    """Return every file or OS call in one canopy module."""
    problems: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            problem = _call_problem(node, reads_assets=reads_assets)
            if problem is not None:
                problems.append(f"{where}:{node.lineno}: {problem}")
        if isinstance(node, ast.Name) and node.id in QT_OS_CLASSES:
            problems.append(f"{where}:{node.lineno}: {node.id}")
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("PySide6"):
            names = {alias.name for alias in node.names} | {(node.module or "").split(".")[-1]}
            problems += [f"{where}:{node.lineno}: {n}" for n in sorted(names & QT_OS_CLASSES)]
    return problems


def test_canopy_makes_no_file_or_os_calls() -> None:
    problems: list[str] = []
    for path in canopy_files():
        where = path.relative_to(CANOPY).as_posix()
        problems += file_call_problems(
            path.read_text(encoding="utf-8"), where, reads_assets=where in ASSET_READERS
        )
    assert problems == []


@pytest.mark.parametrize(
    "line",
    [
        "Path('x').read_text()",
        "open('x')",
        "terrain.config_dir()",
        "QDesktopServices.openUrl(url)",
        "path.write_bytes(b'')",
        "Path(t).open('w')",
        "io.open('x')",
        "QImage().save('x.png')",
        "QPixmap(16, 16).save('x.png')",
        "QStandardPaths.writableLocation(location)",
        "QDir.home().entryList()",
        "QSaveFile('x')",
        "from PySide6.QtNetwork import QNetworkAccessManager",
        "from PySide6 import QtNetwork",
    ],
)
def test_a_file_or_os_call_in_canopy_is_caught(line: str) -> None:
    assert file_call_problems(line, "x.py", reads_assets=False) != []


def test_painter_state_saves_are_not_file_calls() -> None:
    assert file_call_problems("painter.save()", "x.py", reads_assets=False) == []


# --- dynamic imports --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "import importlib\nimportlib.import_module('PySide6.QtQuick3D')",
        "from importlib import import_module\nimport_module('verdra.bark.veil')",
        "import importlib\nimportlib.reload(module)",
        "import importlib.util\nimportlib.util.find_spec('PySide6.QtQuick')",
        "from importlib.machinery import SourceFileLoader\nSourceFileLoader('m', 'm.py')",
        "import pkgutil\npkgutil.resolve_name('PySide6.QtQuick:QQuickView')",
        "import runpy\nrunpy.run_module('verdra.bark.veil')",
        "import builtins\nbuiltins.__import__('PySide6.QtQuick')",
    ],
)
def test_ruff_bans_dynamic_imports_in_the_app(line: str) -> None:
    ruff = shutil.which("ruff")
    assert ruff is not None
    done = subprocess.run(  # noqa: S603 - the project's own linter, source on stdin
        [
            ruff,
            "check",
            "--stdin-filename",
            "src/verdra/canopy/probe.py",
            "--select",
            "TID251",
            "-",
        ],
        input=line + "\n",
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode != 0
    assert "TID251" in done.stdout


# Names that reach the import machinery or run code without a static import. ruff bans the
# direct forms; this also catches indirect ones such as getattr(builtins, "__import__").
DYNAMIC_NAMES = frozenset({"__import__", "__builtins__", "builtins", "exec", "eval", "compile"})


def dynamic_import_problems(source: str, where: str) -> list[str]:
    """Return every route to a dynamic import or dynamic code in one module."""
    problems: list[str] = []
    for node in ast.walk(ast.parse(source)):
        # A bare name only: dialog.exec() and re.compile() are methods, not built-ins.
        if isinstance(node, ast.Name) and node.id in DYNAMIC_NAMES:
            problems.append(f"{where}:{node.lineno}: {node.id}")
        if isinstance(node, ast.Attribute) and node.attr in {"__import__", "__builtins__"}:
            problems.append(f"{where}:{node.lineno}: {node.attr}")
        if isinstance(node, ast.Constant) and node.value in {"__import__", "__builtins__"}:
            problems.append(f"{where}:{node.lineno}: {node.value!r}")
        if isinstance(node, ast.Import) and any(a.name == "builtins" for a in node.names):
            problems.append(f"{where}:{node.lineno}: import builtins")
        if isinstance(node, ast.ImportFrom) and node.module == "builtins":
            problems.append(f"{where}:{node.lineno}: from builtins import")
    return problems


def test_the_app_never_reaches_the_import_machinery_dynamically() -> None:
    """ruff can't ban a built-in, so this checks the built-ins and indirect routes directly."""
    problems: list[str] = []
    for path in sorted(SOURCE.rglob("*.py")):
        where = path.relative_to(SOURCE).as_posix()
        problems += dynamic_import_problems(path.read_text(encoding="utf-8"), where)
    assert problems == []


@pytest.mark.parametrize(
    "line",
    [
        "__import__('PySide6.QtQuick')",
        "import builtins\ngetattr(builtins, name)('PySide6.QtQuick')",
        "from builtins import __import__ as load",
        "getattr(__builtins__, '__import__')('PySide6.QtQuick')",
        "vars(sys.modules['builtins'])['__import__']('x')",
        "exec('import PySide6.QtQuick')",
        "eval(text)",
        "compile(text, 'x', 'exec')",
    ],
)
def test_a_dynamic_import_route_is_caught(line: str) -> None:
    assert dynamic_import_problems(line, "x.py") != []


def test_qt_exec_and_regex_compile_are_not_dynamic_code() -> None:
    assert dynamic_import_problems("dialog.exec()\nre.compile('a')", "x.py") == []


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__]))
