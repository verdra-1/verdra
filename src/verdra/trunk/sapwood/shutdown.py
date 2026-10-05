# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Shutdown order: stop routing, clear hosts entries, flush logs and settings.

Master plan 8.4. Shutdown closes the Roblox Verdra launched when `routing.close_roblox_on_quit`
is on and stops routing (S-12; hosts entries arrive with M6), cancels background jobs (3 s
grace, spec S-04), writes pending settings and window state, releases the single-instance
channel and flushes the log last, so every earlier step is recorded.
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication

from verdra.trunk.branches import fallow

if TYPE_CHECKING:
    from verdra.trunk.sapwood.startup import Services

log = logging.getLogger(__name__)


def run(services: Services) -> None:
    """Stop everything in order. Safe to call more than once."""
    if services.shut_down:
        return
    services.shut_down = True
    log.info("%s", QCoreApplication.translate("M-SHELL-08", "Verdra is quitting."))
    # 1-3. Close the Roblox Verdra launched if Settings say so, then stop routing (S-12). The
    # hosts entries of Hosts-file routing join here at M6.
    if services.sprout is not None:
        services.sprout.quit()
    services.tendrils.shutdown()
    if not services.erase_own_data:
        services.settings.flush(final=True)
        services.state.save()
    services.single.release()
    log.debug("Shutdown finished after %d ms of running.", services.elapsed_ms())
    if services.errors is not None:
        services.errors.uninstall()
    services.rings.stop()
    if services.erase_own_data:
        # Last, with logging stopped: the log folder goes at the end of the run (spec S-16).
        left = fallow.erase_own_folders()
        if left:
            print(  # noqa: T201 - logging has stopped; the folders are named for the user
                QCoreApplication.translate(
                    "M-RESET-11", "Verdra couldn't delete everything in {folders}."
                ).format(folders=", ".join(str(folder) for folder in left)),
                file=sys.stderr,
            )
