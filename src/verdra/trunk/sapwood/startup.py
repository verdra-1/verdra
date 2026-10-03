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

import importlib.abc
import importlib.machinery
import logging
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Protocol

import psutil
from PySide6.QtCore import QCoreApplication, QLocale, QTranslator
from PySide6.QtWidgets import QApplication

import verdra
from verdra.soil import humus, terrain
from verdra.trunk import rings, tendrils
from verdra.trunk.almanac.store import SettingsStore, StateStore
from verdra.trunk.sapwood import cli, shutdown
from verdra.trunk.sapwood.single import SingleInstance

log = logging.getLogger(__name__)


class Interface(Protocol):
    """What startup needs from the interface (implemented in canopy/crown/window.py)."""

    def show_splash(self) -> None:
        """Show the splash screen."""

    def build(self) -> None:
        """Build the main window, tray and shortcuts, once the services have started."""

    def show_window(self, *, minimized: bool) -> None:
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
    #: The OS's reduced-motion preference (plan 6.6), asked once at startup; None if unknown.
    os_reduce_motion: bool | None = None

    def elapsed_ms(self) -> int:
        """Return milliseconds since launch."""
        return round((time.monotonic() - self.started) * 1000)

    def step(self, name: str) -> None:
        """Log a startup step with its timestamp (technical detail, so Debug level)."""
        log.debug("Startup: %s after %d ms.", name, self.elapsed_ms())


#: The Qt modules Verdra may load (Master plan 8.1). pyproject's [tool.verdra.qt] list must match;
#: a test checks it.
QT_MODULES: Final = frozenset(
    {
        "QtCore",
        "QtGui",
        "QtWidgets",
        "QtNetwork",
        "QtOpenGL",
        "QtOpenGLWidgets",
        "QtSvg",
        "QtMultimedia",
    }
)


class QtGuard(importlib.abc.MetaPathFinder):
    """Refuses to import any PySide6 Qt module outside plan 8.1's list.

    The PySide6 Addons wheel also installs GPL-only modules (Qt Charts, Qt Quick 3D, …). Static
    checks keep them out of the code; this guard also stops a dynamic import at run time.
    """

    def find_spec(
        self, fullname: str, path: object = None, target: object = None
    ) -> importlib.machinery.ModuleSpec | None:
        """Raise ImportError for a disallowed Qt module; leave every other import alone."""
        package, _, module = fullname.partition(".")
        if package == "PySide6" and module.startswith("Qt"):
            name = module.split(".", 1)[0]
            if name not in QT_MODULES:
                raise ImportError(f"PySide6.{name} isn't one of the Qt modules Verdra may use")
        return None


def install_qt_guard() -> None:
    """Put `QtGuard` first in the import system (once); the app does it before the UI loads."""
    if not any(isinstance(finder, QtGuard) for finder in sys.meta_path):
        sys.meta_path.insert(0, QtGuard())


def install_translator(app: QCoreApplication, language: str) -> QTranslator | None:
    """Load the compiled message catalogue for `language` ("system" or a tag) into `app`.

    Plan 8.4 step 4. Only English exists so far; it also supplies the plural forms (R5,
    M-STATUS-02), so it is loaded whenever no catalogue for the chosen language exists.
    """
    folder = Path(verdra.__file__).resolve().parent / "assets" / "i18n"
    locale = QLocale.system() if language == "system" else QLocale(language)
    translator = QTranslator(app)
    if not (
        translator.load(locale, "verdra", "_", str(folder))
        or translator.load(str(folder / "verdra_en.qm"))
    ):
        log.warning(
            "%s",
            QCoreApplication.translate(
                "M-SHELL-04", "Verdra's translations couldn't be loaded, so it shows English text."
            ),
        )
        log.debug("No message catalogue in %s.", folder)
        return None
    app.installTranslator(translator)
    return translator


def legal_text(name: str) -> str | None:
    """Return a legal text for the About dialog (LICENSE, NOTICE, PRIVACY.md, …), or None.

    The texts exist once, at the repository root; a build carries copies (decision record
    0010). None means this build doesn't carry that text.
    """
    try:
        return (terrain.legal_dir() / name).read_text(encoding="utf-8")
    except OSError:
        return None


def launched_at() -> float:
    """Return when this process was started, on the `time.monotonic()` clock.

    Plan 12.4 budgets the time until the window is visible "after launch", so startup steps are
    timed from the moment the operating system created the process: interpreter start-up and
    the Qt imports count too.
    """
    try:
        age = time.time() - psutil.Process().create_time()
    except psutil.Error:
        age = 0.0
    return time.monotonic() - max(0.0, age)


def run(argv: list[str], build_interface: Callable[[Services], Interface]) -> int:
    """Start Verdra and return its exit code."""
    started = launched_at()
    arguments = cli.parse(argv[1:])
    if arguments.reset_everything:
        if not arguments.quiet:
            message = QCoreApplication.translate(
                "M-RESET-04",
                "Reset everything isn't available in this version yet. Nothing was changed.",
            )
            print(message)  # noqa: T201 - the command line's answer
        return 0

    # 8.4 step 1: a second launch hands its link to the running Verdra and exits. This needs no
    # Qt application, so nothing else is set up for a launch that only forwards a link.
    single = SingleInstance()
    if single.hand_over(arguments.link):
        return 0

    # Steps 2 and 3: settings (with their .bak fallback and migration), then logging. What the
    # settings report on loading waits in the log queue until logging starts.
    logging_ = rings.Rings()
    logging_.hold()
    state = StateStore()
    state.load()
    settings = SettingsStore(state=state)
    settings.load()
    logging_.start(detailed=bool(settings.value("advanced.detailed_logging")))

    # Step 4: the Qt application. Listening on the single-instance channel needs its event
    # loop, so the channel is claimed now; a launch that started in between wins the race and
    # this one hands over to it.
    app = QApplication.instance() or QApplication(argv)
    assert isinstance(app, QApplication)  # noqa: S101 - created just above
    app.setApplicationName(terrain.PRODUCT_NAME)
    app.setApplicationVersion(verdra.__version__)
    app.setOrganizationName(terrain.PRODUCT_NAME)
    app.setDesktopFileName(terrain.LINUX_DESKTOP_ENTRY.removesuffix(".desktop"))
    if not single.claim(arguments.link):
        logging_.stop()
        return 0
    install_translator(app, str(settings.value("general.language")))

    # The theme follows the OS's reduced-motion preference; the UI makes no OS calls itself.
    os_reduce_motion = humus.prefers_reduced_motion()

    services = Services(
        os_reduce_motion=os_reduce_motion,
        app=app,
        arguments=arguments,
        settings=settings,
        state=state,
        rings=logging_,
        # The workers start at step 5; what is submitted before then waits in the queue.
        tendrils=tendrils.Tendrils(
            workers=int(settings.value("advanced.worker_threads")), start=False
        ),
        single=single,
        started=started,
    )
    settings.save_in_background(services.tendrils.submit)
    services.detailed_logging = rings.DetailedLogging(logging_, settings, app)
    log.info(
        "%s",
        QCoreApplication.translate("M-SHELL-05", "Verdra {version} started on {system}.").format(
            version=verdra.__version__, system=humus.system_name()
        ),
    )
    services.step("settings and logging ready")

    interface = build_interface(services)
    interface.show_splash()
    services.step("splash shown")

    # Step 5: the services. Routing, the library and updates join here as their specs are
    # built (M1 onward).
    services.tendrils.start()
    services.step("services started")

    # Step 7: the window, or the tray when Verdra started with the system (--minimized) and
    # "Start in the tray" is on (Reference R2: the setting is only used then).
    interface.build()
    start_in_tray = arguments.minimized and bool(settings.value("general.start_minimized"))
    interface.show_window(minimized=start_in_tray)
    services.step("window shown")
    single.activated.connect(interface.activate)
    if arguments.link:
        interface.activate(arguments.link)

    app.aboutToQuit.connect(lambda: shutdown.run(services))
    return app.exec()
