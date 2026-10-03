# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""App lifetime: command line, startup order and shutdown (Master plan 8.4)."""

import ast
import json
import logging
import os
import subprocess
import sys
import time
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import psutil
import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from verdra.soil import humus, terrain
from verdra.trunk.sapwood import cli, shutdown, startup

#: M-SET-16, as the store reports an unknown key.
UNKNOWN_KEY = (
    "The setting {key} isn't known to this version of Verdra. It's kept in the file but not used."
)

ROOT = Path(__file__).resolve().parents[2]


def test_command_line() -> None:
    assert cli.parse([]) == cli.Arguments()
    parsed = cli.parse(["--minimized", "-platform", "offscreen", "roblox-player:1+launchmode:play"])
    assert parsed.minimized
    assert parsed.link == "roblox-player:1+launchmode:play"
    assert cli.parse(["--minimized"]).minimized
    reset = cli.parse(["--reset-everything", "--quiet"])
    assert (reset.reset_everything, reset.quiet) == (True, True)
    assert cli.parse(["https://example.com"]).link is None


def test_reset_everything_says_it_does_nothing_yet(capsys: pytest.CaptureFixture[str]) -> None:
    assert startup.run(["verdra", "--reset-everything"], lambda _services: None) == 0  # type: ignore[arg-type, return-value]
    assert "Nothing was changed" in capsys.readouterr().out
    assert startup.run(["verdra", "--reset-everything", "--quiet"], lambda _s: None) == 0  # type: ignore[arg-type, return-value]
    assert capsys.readouterr().out == ""


class FakeInterface:
    def __init__(self, services: startup.Services) -> None:
        self.services = services
        self.calls: list[str] = []

    def show_splash(self) -> None:
        self.calls.append("splash")

    def build(self) -> None:
        self.calls.append("build")

    def show_window(self, *, minimized: bool) -> None:
        self.calls.append(f"window minimized={minimized}")
        QTimer.singleShot(50, QApplication.quit)

    def activate(self, link: str) -> None:
        self.calls.append(f"activate {link}")


def test_startup_order_and_shutdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv(terrain.HOME_OVERRIDE_VARIABLE, str(tmp_path))
    monkeypatch.setattr(startup.SingleInstance, "__init__", _unique_channel)
    # The startup steps are technical detail, logged at Debug level (plan 16.2, F13).
    settings = tmp_path / "config" / terrain.SETTINGS_FILE
    settings.parent.mkdir(parents=True)
    since = datetime.now(UTC).isoformat()
    advanced = {"detailed_logging": True, "detailed_logging_since": since}
    settings.write_text(
        json.dumps({"format": "verdra.settings", "version": 1, "advanced": advanced}),
        encoding="utf-8",
    )
    built: list[FakeInterface] = []

    def build(services: startup.Services) -> FakeInterface:
        built.append(FakeInterface(services))
        return built[-1]

    link = "roblox-player:1+launchmode:play"
    with caplog.at_level(logging.INFO, logger="verdra"):
        assert startup.run(["verdra", "--minimized", link], build) == 0
    interface = built[0]
    assert interface.calls == ["splash", "build", "window minimized=True", f"activate {link}"]
    services = interface.services
    assert services.shut_down
    assert services.tendrils.running() == []
    log = (tmp_path / "logs" / "verdra.log").read_text(encoding="utf-8")
    steps = ["settings and logging ready", "splash shown", "window shown"]
    positions = [log.index(f"Startup: {step}") for step in steps]
    assert positions == sorted(positions)
    # M-SHELL-05 names the system as people read it, from the Platform (plan 16.2).
    assert f"started on {humus.system_name()}." in log
    assert "Shutdown finished" in log
    shutdown.run(services)  # a second call does nothing


ORDER_PROBE = """
import os, sys
from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtWidgets import QApplication
from verdra.trunk import rings, tendrils
from verdra.trunk.almanac.store import SettingsStore
from verdra.trunk.sapwood import startup
from verdra.trunk.sapwood.single import SingleInstance

events = []

def record(name, original):
    def wrapper(*args, **kwargs):
        events.append((name, QCoreApplication.instance() is not None))
        return original(*args, **kwargs)
    return wrapper

def load(store):
    original_load(store)
    if os.environ.get("PROBE_START_IN_TRAY") == "off":
        store.set("general.start_minimized", False)

original_load = record("load settings", SettingsStore.load)
SingleInstance.hand_over = record("check single instance", SingleInstance.hand_over)
SettingsStore.load = load
rings.Rings.start = record("start logging", rings.Rings.start)
SingleInstance.claim = record("claim channel", SingleInstance.claim)
startup.install_translator = record("install translator", startup.install_translator)
tendrils.Tendrils.start = record("start services", tendrils.Tendrils.start)

class Interface:
    def show_splash(self):
        events.append(("show splash", QCoreApplication.instance() is not None))
    def build(self):
        events.append(("build window", True))
    def show_window(self, **kwargs):
        (in_tray,) = kwargs.values()  # one keyword; its name follows startup's spelling
        events.append(("show window", in_tray))
        QTimer.singleShot(0, QApplication.quit)
    def activate(self, link):
        pass

startup.run(["verdra", *sys.argv[1:], "-platform", "offscreen"], lambda services: Interface())
print(events)
"""


def _run_order_probe(tmp_path: Path, *flags: str, start_in_tray: str = "on") -> list[object]:
    env = os.environ | {
        terrain.HOME_OVERRIDE_VARIABLE: str(tmp_path),
        "QT_QPA_PLATFORM": "offscreen",
        "PROBE_START_IN_TRAY": start_in_tray,
    }
    done = subprocess.run(  # noqa: S603
        [sys.executable, "-c", ORDER_PROBE, *flags],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return ast.literal_eval(done.stdout.strip().splitlines()[-1])


def test_startup_follows_plan_8_4(tmp_path: Path) -> None:
    """Plan 8.4 steps 1 to 7 run in order: the Qt application comes only at step 4 (M12), and
    the services start after the splash and before the window is built."""
    assert _run_order_probe(tmp_path) == [
        ("check single instance", False),
        ("load settings", False),
        ("start logging", False),
        ("claim channel", True),
        ("install translator", True),
        ("show splash", True),
        ("start services", True),
        ("build window", True),
        ("show window", False),
    ]


@pytest.mark.parametrize(
    ("flags", "setting", "in_tray"),
    [
        ((), "on", False),
        (("--minimized",), "on", True),
        (("--minimized",), "off", False),
    ],
)
def test_start_in_the_tray_needs_the_flag_and_the_setting(
    tmp_path: Path, flags: tuple[str, ...], setting: str, in_tray: bool
) -> None:
    # Reference R2: "Start in the tray" is only used when started with the system, and the
    # system starts Verdra with --minimized (R3 autostart).
    events = _run_order_probe(tmp_path, *flags, start_in_tray=setting)
    assert events[-1] == ("show window", in_tray)


def _unique_channel(
    self: startup.SingleInstance, name: str | None = None, parent: object = None
) -> None:
    from PySide6.QtCore import QObject

    QObject.__init__(self, parent)  # type: ignore[arg-type]
    self.name = f"verdra-test-startup-{id(self)}"
    self._server = None
    self._pending = []


def test_startup_is_timed_from_process_creation() -> None:
    # Plan 12.4 measures "after launch": the interpreter and the imports that ran before
    # startup.run must count, so the clock starts when the process was created.
    created = psutil.Process().create_time()
    launched = startup.launched_at()
    age = time.monotonic() - launched
    assert age >= time.time() - created - 0.05
    assert launched <= time.monotonic()


GUARD_PROBE = """
import importlib, sys
from verdra.trunk.sapwood import startup
startup.install_qt_guard()
startup.install_qt_guard()
assert sum(isinstance(f, startup.QtGuard) for f in sys.meta_path) == 1
import PySide6.QtSvg  # allowed
for name in ("PySide6.QtCharts", "PySide6.QtQuick3D", "PySide6.QtDataVisualization"):
    try:
        importlib.import_module(name)
    except ImportError as error:
        print("blocked", name, error)
    else:
        print("LOADED", name)
"""


def test_qt_modules_outside_plan_8_1_are_blocked_at_import() -> None:
    """16.2: GPL-only Qt modules are blocked at import, also dynamic ones (finding M8)."""
    done = subprocess.run(  # noqa: S603
        [sys.executable, "-c", GUARD_PROBE],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    lines = done.stdout.splitlines()
    assert [line.split()[:2] for line in lines] == [
        ["blocked", "PySide6.QtCharts"],
        ["blocked", "PySide6.QtQuick3D"],
        ["blocked", "PySide6.QtDataVisualization"],
    ]


def test_the_guard_matches_the_configured_qt_modules() -> None:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        configured = tomllib.load(handle)["tool"]["verdra"]["qt"]["allowed-modules"]
    assert set(configured) == startup.QT_MODULES


def test_the_app_installs_the_guard_before_the_ui_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    import verdra.__main__ as entry

    seen: list[bool] = []

    def fake_run(argv: list[str], build: object) -> int:
        seen.append(any(isinstance(f, startup.QtGuard) for f in sys.meta_path))
        return 0

    monkeypatch.setattr(startup, "run", fake_run)
    monkeypatch.setattr(sys, "meta_path", list(sys.meta_path))
    assert entry.main() == 0
    assert seen == [True]


def test_what_settings_report_on_loading_reaches_the_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qapp: QApplication
) -> None:
    """Settings load before logging starts (8.4); their reports still reach Activity (F1)."""
    monkeypatch.setenv(terrain.HOME_OVERRIDE_VARIABLE, str(tmp_path))
    monkeypatch.setattr(startup.SingleInstance, "__init__", _unique_channel)
    settings_file = terrain.config_dir() / terrain.SETTINGS_FILE
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(
        '{"format": "verdra.settings", "version": 1, "future_key": 1}', encoding="utf-8"
    )
    built: list[FakeInterface] = []

    def build(services: startup.Services) -> FakeInterface:
        built.append(FakeInterface(services))
        return built[-1]

    assert startup.run(["verdra"], build) == 0
    log = (tmp_path / "logs" / "verdra.log").read_text(encoding="utf-8")
    assert UNKNOWN_KEY.format(key="future_key") in log
    activity = [record.message for record in built[0].services.rings.ring.snapshot()]
    assert UNKNOWN_KEY.format(key="future_key") in activity
