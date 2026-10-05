# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Running the tests on a non-Windows development machine (decision record 0018).

Verdra runs on Windows only; CI runs every test on Windows, where the real platform loads TLS
certificates from memory (`soil/meadow`, spec S-10 test 6). A contributor's or an automated
session's machine may still be Linux, where `soil/tundra` now refuses every job. So that the
proxy's own logic (hyphae, mycelium, the grafter, the benchmark) stays testable there, this
plugin gives the paused platform a test-only certificate loader: the PEM files go into a private
temporary folder that is removed at once. It never runs on Windows, never ships (tests only), and
the in-memory loading tests themselves are Windows-only.
"""

from __future__ import annotations

import shutil
import ssl
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from verdra.soil import humus


def load_through_private_files(context: ssl.SSLContext, certificate: bytes, key: bytes) -> None:
    """Load a PEM certificate and key through files in a private folder, then remove them."""
    folder = Path(tempfile.mkdtemp(prefix="verdra-test-tls-"))  # mode 0700
    try:
        (folder / "c.pem").write_bytes(certificate)
        (folder / "k.pem").write_bytes(key)
        context.load_cert_chain(folder / "c.pem", folder / "k.pem")
    finally:
        shutil.rmtree(folder, ignore_errors=True)


@pytest.fixture(autouse=True)
def certificates_on_a_dev_machine(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """On a non-Windows machine, let the paused platform load test certificates.

    A test marked `real_platform` sees the platform as it ships.
    """
    if humus.system() != "windows" and request.node.get_closest_marker("real_platform") is None:
        monkeypatch.setattr(
            type(humus.current()), "load_cert_chain", staticmethod(load_through_private_files)
        )
    yield
