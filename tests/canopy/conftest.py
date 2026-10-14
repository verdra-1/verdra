# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Fixtures for interface tests: a full shell over temporary folders."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from tests.canopy.applying import StubSprout
from verdra.canopy.crown.window import Shell
from verdra.soil import terrain
from verdra.trunk import rings, tendrils
from verdra.trunk.almanac.store import SettingsStore, StateStore
from verdra.trunk.branches import grafts
from verdra.trunk.sapwood import cli
from verdra.trunk.sapwood.single import SingleInstance
from verdra.trunk.sapwood.startup import Services


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(terrain.HOME_OVERRIDE_VARIABLE, str(tmp_path))
    return tmp_path


@pytest.fixture
def services(home: Path, qapp: QApplication) -> Iterator[Services]:
    settings = SettingsStore()
    settings.load()
    state = StateStore()
    state.load()
    logs = rings.Rings()
    logs.start()
    made = Services(
        app=qapp,
        arguments=cli.Arguments(),
        settings=settings,
        state=state,
        rings=logs,
        tendrils=tendrils.Tendrils(workers=2),
        single=SingleInstance(f"verdra-test-{home.name}"),
    )
    yield made
    # What shutdown does (trunk/sapwood/shutdown): a pending save is written now, so its timer
    # can't fire in a later test (tests/support/qt_lifetimes, guard 4).
    made.tendrils.shutdown(grace=0.5)
    settings.flush(final=True)
    logs.stop()


@pytest.fixture
def shell(services: Services, qtbot: QtBot) -> Iterator[object]:
    from verdra.canopy.crown.window import Shell

    made = Shell(services)
    made.build()
    qtbot.addWidget(made.window)
    yield made
    made.window.allow_close = True
    made.window.close()


@pytest.fixture
def made(services: Services, qtbot: QtBot) -> Iterator[tuple[Shell, StubSprout]]:
    services.grafts = grafts.Grafts(terrain.config_dir() / "profiles", services.settings)
    stub = StubSprout()
    services.sprout = stub  # type: ignore[assignment]
    shell = Shell(services)
    shell.build()
    qtbot.addWidget(shell.window)
    yield shell, stub
    shell.window.allow_close = True
    shell.window.close()
    services.sprout = None
    stub.deleteLater()
    services.grafts.deleteLater()
