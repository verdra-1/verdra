# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Diagnostic interception (--diagnose-interception): pass-through only, TLS details logged; source
runs only, excluded from builds (decision 0015).

Spec S-11 (tests 9 and 10), plan 16.2. It exists so the M1 gate can check verified TLS and ECDSA
leaf acceptance on real clients before any feature intercepts. The interception it builds
decrypts every host of plan 10.2, runs no symbiont (so every request and response passes
byte for byte), and writes the TLS details of both sides of each connection to Activity
(M-DIAG-02). `trunk/sapwood/cli` offers `--diagnose-interception` only while this module can be
imported from source; `packaging/verdra.spec` leaves it out of every build, and
`tools/check_build.py` fails if `MARKER` turns up anywhere in a built folder (decision record
0015).
"""

from __future__ import annotations

import logging
import ssl
from collections.abc import Callable, Collection, Iterator
from typing import Final, Literal

from PySide6.QtCore import QCoreApplication

from verdra.roots import hyphae, rules

log = logging.getLogger(__name__)

#: Only this module carries this text; a built folder that contains it fails the build check.
MARKER: Final = "verdra/litmus: diagnostic interception, source only"
#: Plan 10.2 (roots/rules), the exact list confirmed by capture at M1.
HOSTS: Final = rules.ROBLOX_HOSTS
#: The leaf key S-10 issues (bark/resin), reported for the client side.
LEAF_KEY: Final = "ECDSA P-256"


class DiagnosticHosts(Collection[str]):
    """The 10.2 hosts, in any letter case and with or without a trailing dot."""

    def __contains__(self, host: object) -> bool:
        return isinstance(host, str) and rules.is_roblox_host(host)

    def __iter__(self) -> Iterator[str]:
        return iter(sorted(HOSTS))

    def __len__(self) -> int:
        return len(HOSTS)


def interception(
    leaves: hyphae.LeafContexts,
    open_upstream: hyphae.Opener,
    *,
    idle_timeout: float = 30.0,
    on_verification_failure: Callable[[str, str], None] | None = None,
) -> hyphae.Interception:
    """Return the diagnostic interception: every 10.2 host, no symbionts, TLS details logged.

    `on_verification_failure` hears of every server certificate that fails (status Degraded).
    """
    hosts = DiagnosticHosts()
    return hyphae.Interception(
        leaves,
        lambda: hosts,
        open_upstream,
        hyphae.Pipeline,
        on_tls=log_tls,
        on_verification_failure=on_verification_failure,
        idle_timeout=idle_timeout,
    )


def log_tls(host: str, side: Literal["client", "upstream"], tls: ssl.SSLObject) -> None:
    """Write one side's TLS details to Activity (M-DIAG-02)."""
    cipher = tls.cipher()
    if side == "client":
        where = QCoreApplication.translate("M-DIAG-02", "Roblox to Verdra")
        detail = QCoreApplication.translate("M-DIAG-02", "Verdra's certificate, key {key}").format(
            key=LEAF_KEY
        )
    else:
        where = QCoreApplication.translate("M-DIAG-02", "Verdra to the server")
        verified = tls.context.verify_mode == ssl.CERT_REQUIRED and tls.context.check_hostname
        detail = (
            QCoreApplication.translate("M-DIAG-02", "the server's certificate verified")
            if verified
            else QCoreApplication.translate("M-DIAG-02", "the server's certificate not verified")
        )
    log.info(
        "%s",
        QCoreApplication.translate(
            "M-DIAG-02", "Diagnostic interception, {host} ({where}): {version}, {cipher}, {detail}."
        ).format(
            host=host,
            where=where,
            version=tls.version() or "?",
            cipher=cipher[0] if cipher else "?",
            detail=detail,
        ),
    )
