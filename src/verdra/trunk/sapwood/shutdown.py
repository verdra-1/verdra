# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Shutdown order: stop routing, clear hosts entries, flush logs and settings.

Master plan 8.4. Routing and hosts entries arrive with M1 and M6; until then shutdown cancels
background jobs (3 s grace, spec S-04), writes pending settings and window state, releases the
single-instance channel and flushes the log last, so every earlier step is recorded.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from verdra.trunk.sapwood.startup import Services

log = logging.getLogger(__name__)


def run(services: Services) -> None:
    """Stop everything in order. Safe to call more than once."""
    if services.shut_down:
        return
    services.shut_down = True
    log.info("Verdra is quitting.")
    # 1-2. Stop accepting proxy connections, stop routing (M1, M6).
    # 3. Optional actions from Settings, such as closing Roblox (M1).
    services.tendrils.shutdown()
    services.settings.flush()
    services.state.save()
    services.single.release()
    log.info("Shutdown finished after %d ms of running.", services.elapsed_ms())
    services.rings.stop()
