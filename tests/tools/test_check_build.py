# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""The build gate: only allowed Qt modules in the built folder."""

import sys
from pathlib import Path, PurePath

import pytest

from tools import check_build
from verdra.soil import terrain

CONFIG = {
    "allowed-modules": ["QtCore", "QtGui", "QtWidgets", "QtSvg", "QtMultimedia"],
    "build-support": {"DBus": "Qt Base", "XcbQpa": "Qt Base"},
}
MODULES = {
    "Core", "Gui", "Widgets", "Svg", "SvgWidgets", "Multimedia", "MultimediaWidgets", "DBus",
    "Charts", "VirtualKeyboard", "Quick", "Quick3D", "Pdf",
}  # fmt: skip


@pytest.mark.parametrize(
    ("name", "module"),
    [
        ("libQt6Core.so.6", "Core"),
        ("Qt6Widgets.dll", "Widgets"),
        ("libQt6Gui.6.dylib", "Gui"),
        ("PySide6/Qt/lib/QtSvg.framework/Versions/A/QtSvg", "Svg"),
        ("PySide6/QtMultimedia.abi3.so", "Multimedia"),
        ("PySide6/QtCharts.pyd", "Charts"),
        ("PySide6/QtCore.cpython-314-darwin.so", "Core"),
        ("libQt63DCore.so.6", "3DCore"),
        ("libpython3.14.so.1.0", None),
        ("PySide6/Qt/plugins/platforms/libqxcb.so", None),
    ],
)
def test_names_map_to_their_qt_module(name: str, module: str | None) -> None:
    assert check_build.qt_module(PurePath(name)) == module


def build(root: Path, names: list[str]) -> Path:
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
    return root


ALLOWED = [
    "verdra",
    "_internal/libQt6Core.so.6",
    "_internal/libQt6DBus.so.6",
    "_internal/PySide6/QtWidgets.abi3.so",
    "_internal/PySide6/Qt/plugins/imageformats/libqsvg.so",
    "_internal/PySide6/Qt/plugins/platforms/libqxcb.so",
    "_internal/PySide6/Qt/lib/QtGui.framework/Versions/A/QtGui",
    "_internal/numpy/testing/__init__.py",
]


def test_allowed_build_passes(tmp_path: Path) -> None:
    assert check_build.check(build(tmp_path, ALLOWED), CONFIG, MODULES) == []


@pytest.mark.parametrize(
    "name",
    [
        "_internal/libQt6VirtualKeyboard.so.6",
        "_internal/Qt6Charts.dll",
        "_internal/PySide6/Qt/lib/QtQuick3D.framework/Versions/A/QtQuick3D",
        "_internal/PySide6/QtSvgWidgets.pyd",
        "_internal/PySide6/Qt/plugins/platforminputcontexts/libqtvirtualkeyboardplugin.so",
        "_internal/PySide6/Qt/plugins/imageformats/qpdf.dll",
        "_internal/PySide6/Qt/plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll",
        "_internal/PySide6/Qt/qml/QtQuick/qmldir",
        "_internal/PySide6/Qt/lib/libQt6WaylandCompositor.so.6",
        "_internal/PySide6/Qt/lib/libQt6WaylandEglCompositorHwIntegration.so.6",
        "_internal/PySide6/Qt/plugins/wayland-graphics-integration-server/libqt-wayland-x.so",
    ],
)
def test_other_qt_modules_fail(tmp_path: Path, name: str) -> None:
    problems = check_build.check(build(tmp_path, [*ALLOWED, name]), CONFIG, MODULES)
    assert len(problems) == 1
    assert problems[0].startswith(name)


def test_support_libraries_come_from_the_config() -> None:
    assert check_build.permitted(CONFIG) == {
        "Core", "Gui", "Widgets", "Svg", "Multimedia", "DBus", "XcbQpa",
    }  # fmt: skip


def test_the_real_config_allows_only_plan_modules() -> None:
    config = check_build.load_config()
    assert config["allowed-modules"] == [
        "QtCore", "QtGui", "QtWidgets", "QtNetwork", "QtOpenGL", "QtOpenGLWidgets", "QtSvg",
        "QtMultimedia",
    ]  # fmt: skip
    assert all(reason for reason in config["build-support"].values())


def test_launch_reports_a_missing_app(tmp_path: Path) -> None:
    assert "is missing" in (check_build.launch(tmp_path, timeout=1).problem or "")


def test_cli_fails_on_a_bad_build(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    build(tmp_path, ["_internal/Qt6Charts.dll"])
    assert check_build.main([str(tmp_path)]) == 1
    assert "Qt6Charts.dll" in capsys.readouterr().err
    assert check_build.main([str(tmp_path / "missing")]) == 2


@pytest.mark.parametrize(
    "name",
    [
        "_internal/libQt6WaylandCompositor.so.6",
        "_internal/Qt6WaylandCompositor.dll",
        "_internal/PySide6/Qt/lib/QtWaylandCompositor.framework/Versions/A/QtWaylandCompositor",
        "_internal/PySide6/Qt/plugins/wayland-graphics-integration-server/libqt-wayland-x.so",
    ],
)
def test_wayland_compositor_fails_even_when_allowed(tmp_path: Path, name: str) -> None:
    # GPL-only (decision record 0010): not even an allowlist entry lets it through.
    config = CONFIG | {"build-support": {"WaylandCompositor": "wrongly allowed"}}
    problems = check_build.check(build(tmp_path, [name]), config, MODULES)
    assert problems == [f"{name}: Qt Wayland Compositor is GPL-only and must never ship"]


def test_legal_texts_must_match_the_repository(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    for name in check_build.LEGAL_TEXTS:
        (root / name).write_text(name, encoding="utf-8")
    legal = tmp_path / "dist" / "_internal" / "verdra" / "assets" / "legal"
    legal.mkdir(parents=True)
    (legal / "LICENSE").write_text("LICENSE", encoding="utf-8")
    (legal / "NOTICE").write_text("changed", encoding="utf-8")
    assert check_build.check_legal_texts(tmp_path / "dist", root) == [
        "assets/legal/NOTICE: differs from the repository's NOTICE",
        "assets/legal/PRIVACY.md: missing from the build",
    ]


def test_window_time_is_reported_against_the_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    check_build.report_window_time(1200)
    check_build.report_window_time(1800)
    out = capsys.readouterr().out
    assert "1200 ms after launch (within the 1500 ms budget" in out
    assert "1800 ms after launch (OVER the 1500 ms budget" in out
    assert summary.read_text(encoding="utf-8").count("Window visible") == 2


def test_modules_without_a_python_binding_are_known() -> None:
    # Qt Virtual Keyboard (GPL-only) ships a plugin and a library but no binding; the real
    # wheel's module list must still contain it, so its plugin is rejected (review finding C1).
    modules = check_build.installed_modules()
    assert "VirtualKeyboard" in modules
    allowed = check_build.permitted(check_build.load_config())
    plugin = PurePath(
        "_internal/PySide6/Qt/plugins/platforminputcontexts/libqtvirtualkeyboardplugin.so"
    )
    assert check_build.rejected(plugin, allowed, modules - allowed) is not None


def test_the_executable_has_its_r3_name() -> None:
    # Reference R3: the command-line executable is "verdra" ("verdra.exe"); finding H8.
    spec = (Path(__file__).resolve().parents[2] / "packaging" / "verdra.spec").read_text("utf-8")
    assert "name=terrain.EXECUTABLE" in spec
    assert terrain.EXECUTABLE == "verdra"


def test_the_build_records_its_commit(tmp_path: Path) -> None:
    # Review finding M11: About must show the short Git commit (plan 13.4), not "dev".
    assert check_build.check_build_stamp(tmp_path) == [
        "assets/build.txt: missing, so About would show build 'dev'"
    ]
    stamp = tmp_path / "_internal" / "verdra" / "assets" / "build.txt"
    stamp.parent.mkdir(parents=True)
    stamp.write_text("dev\n", encoding="utf-8")
    assert check_build.check_build_stamp(tmp_path) == ["assets/build.txt: not a Git commit"]
    stamp.write_text(check_build.build_id() + "\n", encoding="utf-8")
    assert check_build.check_build_stamp(tmp_path) == []


def test_the_launch_turns_on_detailed_logging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The startup steps are Debug lines (F13), so the launch check needs detailed logging."""
    from verdra.trunk.almanac.store import SettingsStore  # noqa: PLC0415 - Qt only here
    from verdra.trunk.rings import detailed_logging_expired  # noqa: PLC0415

    check_build.detailed_logging(tmp_path)
    monkeypatch.setenv(terrain.HOME_OVERRIDE_VARIABLE, str(tmp_path))
    store = SettingsStore()
    store.load()
    assert store.notices == []
    assert store.value("advanced.detailed_logging") is True
    assert not detailed_logging_expired(store.value("advanced.detailed_logging_since"))


MARKER = b"diagnostic marker for the test"


@pytest.mark.spec("S-11", 10)
def test_the_marker_is_the_one_litmus_carries() -> None:
    from verdra.roots import litmus

    assert check_build.diagnostic_marker() == litmus.MARKER.encode()
    source = Path(litmus.__file__).read_text(encoding="utf-8")
    assert litmus.MARKER in source


@pytest.mark.spec("S-11", 10)
def test_a_build_holding_the_diagnostic_code_fails(tmp_path: Path) -> None:
    (tmp_path / "_internal").mkdir()
    (tmp_path / "_internal" / "clean.so").write_bytes(b"nothing here")
    assert check_build.check_no_diagnostics(tmp_path, MARKER, [("verdra.roots.hyphae", b"")]) == []
    (tmp_path / "_internal" / "leak.pyc").write_bytes(b"xx" + MARKER + b"yy")
    archived = [
        ("verdra.roots.litmus", b""),
        ("verdra.other", b"code " + MARKER),
        ("verdra.fine", b"code"),
    ]
    problems = check_build.check_no_diagnostics(tmp_path, MARKER, archived)
    assert [problem.split(" ")[0:4] for problem in problems] == [
        ["_internal/leak.pyc", "holds", "the", "diagnostic"],
        ["the", "archived", "module", "verdra.roots.litmus"],
        ["the", "archived", "module", "verdra.other"],
    ]


def test_a_folder_without_the_executable_has_no_archived_modules(tmp_path: Path) -> None:
    assert list(check_build.archived_modules(tmp_path)) == []


def stand_in(folder: Path, script: str) -> None:
    executable = folder / terrain.EXECUTABLE
    executable.write_text("#!/bin/sh\n" + script + "\n", encoding="utf-8")
    executable.chmod(0o755)


@pytest.mark.spec("S-11", 10)
@pytest.mark.skipif(sys.platform == "win32", reason="the stand-in app is a POSIX shell script")
def test_the_launch_check_requires_the_flag_refused(tmp_path: Path) -> None:
    stand_in(tmp_path, "exit 2")
    assert check_build.refuses_diagnosis(tmp_path) is None
    stand_in(tmp_path, "exit 0")
    assert check_build.refuses_diagnosis(tmp_path) == (
        "the built app exited with code 0 for --diagnose-interception"
    )
    stand_in(
        tmp_path,
        f'mkdir -p "$VERDRA_HOME/logs" && touch "$VERDRA_HOME/logs/{terrain.LOG_FILE}"; exit 2',
    )
    assert "started logging" in (check_build.refuses_diagnosis(tmp_path) or "")
    stand_in(tmp_path, "sleep 5")
    assert "didn't refuse" in (check_build.refuses_diagnosis(tmp_path, timeout=0.5) or "")
