# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Tests for `verdra.soil.humus`: one Platform per OS package, macOS deferred (decision 0014)."""

import ast
import importlib
import pkgutil
import re
import sys
from pathlib import Path

import pytest

from verdra.soil import humus, meadow, orchard, tundra

SRC = Path(__file__).resolve().parents[2] / "src" / "verdra"


def test_each_os_package_implements_the_platform() -> None:
    platforms: dict[humus.System, humus.Platform] = {
        "windows": meadow.PLATFORM,
        "macos": orchard.PLATFORM,
        "linux": tundra.PLATFORM,
    }
    for system, platform in platforms.items():
        assert humus.platform_for(system) is platform
        assert platform.system == system
    assert [p.name for p in platforms.values()] == ["Windows", "macOS", "Linux"]


def test_windows_and_linux_are_supported() -> None:
    assert meadow.PLATFORM.support() is None
    assert tundra.PLATFORM.support() is None


def test_the_running_system_is_supported() -> None:
    # CI runs on Windows and Linux only (decision record 0014).
    assert humus.current().support() is None
    assert humus.system_name() in {"Windows", "Linux"}


def test_the_macos_adapter_reports_unsupported() -> None:
    expected = humus.Unsupported(system="macos", reason="deferred")
    assert orchard.PLATFORM.support() == expected
    assert orchard.PLATFORM.prefers_reduced_motion() is None
    modules = [info.name for info in pkgutil.iter_modules(orchard.__path__)]
    assert sorted(modules) == sorted(
        [
            "autostart",
            "files",
            "hotkeys",
            "instances",
            "keeper",
            "keeper_client",
            "launcher",
            "watchdog",
        ]
    )
    for name in modules:
        module = importlib.import_module(f"verdra.soil.orchard.{name}")
        assert module.support() == expected, name


def test_macos_resolves_to_the_deferred_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    assert humus.current() is orchard.PLATFORM
    assert humus.prefers_reduced_motion() is None


def test_linux_reads_gnome_animations(monkeypatch: pytest.MonkeyPatch) -> None:
    for output, reduce in (("false", True), ("true", False), (None, None)):
        monkeypatch.setattr(humus, "read_command", lambda _command, out=output: out)
        assert tundra.PLATFORM.prefers_reduced_motion() is reduce


def test_a_failing_os_read_counts_as_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail() -> bool | None:
        raise OSError

    monkeypatch.setattr(humus.current(), "prefers_reduced_motion", fail)
    assert humus.prefers_reduced_motion() is None


#: Ways code could check the operating system itself instead of asking the Platform.
OS_CHECK = re.compile(
    r"sys\.platform|platform\.system\(|os\.name\b|os\.uname\(|QSysInfo|\bdarwin\b|\bmacos\b|"
    r"\bwin32\b|\bwindll\b",
    re.IGNORECASE,
)


def _code_without_docstrings(path: Path) -> str:
    """Return a module's code with docstrings and comments left out."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body:
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                body[0] = ast.Pass()
    return ast.unparse(tree)


def test_nothing_outside_soil_checks_the_operating_system() -> None:
    """Master plan 16.2: only soil knows the OS; everything else asks the Platform."""
    found = []
    for path in sorted(SRC.rglob("*.py")):
        if (SRC / "soil") in path.parents:
            continue
        for line in _code_without_docstrings(path).splitlines():
            if OS_CHECK.search(line):
                found.append(f"{path.relative_to(SRC)}: {line.strip()}")
    assert found == []


def test_the_os_check_scan_catches_checks() -> None:
    probes = [
        'if sys.platform == "darwin": pass',
        "import platform\nif platform.system() == 'Windows': pass",
        "if os.name == 'nt': pass",
        "kind = QSysInfo.productType()",
    ]
    for probe in probes:
        assert OS_CHECK.search(ast.unparse(ast.parse(probe))), probe


def test_the_proxy_environment_replaces_every_spelling_and_keeps_the_rest() -> None:
    environment = {"Path": "x", "https_proxy": "http://a:1", "Http_Proxy": "http://b:2", "NO": "1"}
    assert humus.proxy_environment(environment, 5000) == {
        "Path": "x",
        "NO": "1",
        "HTTPS_PROXY": "http://127.0.0.1:5000",
        "HTTP_PROXY": "http://127.0.0.1:5000",
    }
    assert environment["https_proxy"] == "http://a:1"  # the user's own copy is untouched


def test_macos_answers_every_s12_job_with_deferred(tmp_path: Path) -> None:
    expected = humus.Unsupported(system="macos", reason="deferred")
    assert orchard.PLATFORM.roblox_clients() == expected
    assert orchard.PLATFORM.link_handler() == expected
    assert orchard.PLATFORM.trust_files_in(tmp_path) == []
