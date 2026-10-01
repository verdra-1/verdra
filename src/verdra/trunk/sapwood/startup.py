# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Startup order (8.4) with step timestamps.

`run` follows Master plan 8.4: arguments and the single-instance check, settings, logging, the Qt
application with fonts, theme and splash, services, then the main window. Each step is logged
with the milliseconds since launch, so the 1.5 s budget (plan 12.4) can be read from the log.

The interface itself belongs to `canopy`, which `trunk` must not import. `__main__` passes a
factory that builds it from the services prepared here.
"""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from PySide6.QtWidgets import QApplication

import verdra
from verdra.soil import terrain
from verdra.trunk import rings, tendrils
from verdra.trunk.almanac.store import SettingsStore, StateStore
from verdra.trunk.sapwood import cli, shutdown
from verdra.trunk.sapwood.single import SingleInstance

log = logging.getLogger(__name__)


class Interface(Protocol):
    """What startup needs from the interface (implemented in canopy/crown/window.py)."""

    def show_splash(self) -> None:
        """Show the splash screen."""

    def show_window(self, *, minimised: bool) -> None:
        """Show the main window (or stay in the tray) and close the splash when it's ready."""

    def activate(self, link: str) -> None:
        """Bring the window forward for a second launch, with its link if it had one."""


@dataclass
class Services:
    """Everything the interface talks to."""

    app: QApplication
    arguments: cli.Arguments
    settings: SettingsStore
    state: StateStore
    rings: rings.Rings
    tendrils: tendrils.Tendrils
    single: SingleInstance
    detailed_logging: rings.DetailedLogging | None = None
    shut_down: bool = False
    started: float = field(default_factory=time.monotonic)

    def elapsed_ms(self) -> int:
        """Return milliseconds since launch."""
        return round((time.monotonic() - self.started) * 1000)

    def step(self, name: str) -> None:
        """Log a startup step with its timestamp."""
        log.info("Startup: %s after %d ms.", name, self.elapsed_ms())


def run(argv: list[str], build_interface: Callable[[Services], Interface]) -> int:
    """Start Verdra and return its exit code."""
    started = time.monotonic()
    arguments = cli.parse(argv[1:])
    if arguments.reset_everything:
        if not arguments.quiet:
            print("Reset everything isn't available in this version yet. Nothing was changed.")  # noqa: T201
        return 0

    app = QApplication.instance() or QApplication(argv)
    assert isinstance(app, QApplication)  # noqa: S101 - created just above
    app.setApplicationName(terrain.PRODUCT_NAME)
    app.setApplicationVersion(verdra.__version__)
    app.setOrganizationName(terrain.PRODUCT_NAME)
    app.setDesktopFileName(terrain.LINUX_DESKTOP_ENTRY.removesuffix(".desktop"))

    single = SingleInstance()
    if not single.claim(arguments.link):
        return 0

    settings = SettingsStore()
    settings.load()
    state = StateStore()
    state.load()
    logging_ = rings.Rings()
    logging_.start(detailed=bool(settings.value("advanced.detailed_logging")))
    services = Services(
        app=app,
        arguments=arguments,
        settings=settings,
        state=state,
        rings=logging_,
        tendrils=tendrils.Tendrils(workers=int(settings.value("advanced.worker_threads"))),
        single=single,
        started=started,
    )
    services.detailed_logging = rings.DetailedLogging(logging_, settings, app)
    log.info("Verdra %s starting on %s.", verdra.__version__, sys.platform)
    services.step("settings and logging ready")

    interface = build_interface(services)
    interface.show_splash()
    services.step("splash shown")

    # Services (routing, library, updates) start here as their specs are built (M1 onward).

    interface.show_window(minimised=arguments.minimised)
    services.step("window shown")
    single.activated.connect(interface.activate)
    if arguments.link:
        interface.activate(arguments.link)

    app.aboutToQuit.connect(lambda: shutdown.run(services))
    return app.exec()
