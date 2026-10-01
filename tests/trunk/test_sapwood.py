# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""App lifetime: command line, startup order and shutdown (Master plan 8.4)."""

import logging
from pathlib import Path

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from verdra.soil import terrain
from verdra.trunk.sapwood import cli, shutdown, startup


def test_command_line() -> None:
    assert cli.parse([]) == cli.Arguments()
    parsed = cli.parse(["--minimised", "-platform", "offscreen", "roblox-player:1+launchmode:play"])
    assert parsed.minimised
    assert parsed.link == "roblox-player:1+launchmode:play"
    assert cli.parse(["--minimized"]).minimised
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

    def show_window(self, *, minimised: bool) -> None:
        self.calls.append(f"window minimised={minimised}")
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
    built: list[FakeInterface] = []

    def build(services: startup.Services) -> FakeInterface:
        built.append(FakeInterface(services))
        return built[-1]

    link = "roblox-player:1+launchmode:play"
    with caplog.at_level(logging.INFO, logger="verdra"):
        assert startup.run(["verdra", "--minimised", link], build) == 0
    interface = built[0]
    assert interface.calls == ["splash", "window minimised=True", f"activate {link}"]
    services = interface.services
    assert services.shut_down
    assert services.tendrils.running() == []
    log = (tmp_path / "logs" / "verdra.log").read_text(encoding="utf-8")
    steps = ["settings and logging ready", "splash shown", "window shown"]
    positions = [log.index(f"Startup: {step}") for step in steps]
    assert positions == sorted(positions)
    assert "Shutdown finished" in log
    shutdown.run(services)  # a second call does nothing


def _unique_channel(
    self: startup.SingleInstance, name: str | None = None, parent: object = None
) -> None:
    from PySide6.QtCore import QObject

    QObject.__init__(self, parent)  # type: ignore[arg-type]
    self.name = f"verdra-test-startup-{id(self)}"
    self._server = None
    self._pending = []
