# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Guard: no test reaches the real computer's Verdra folders or secret store.

Enabled for every test in tests/conftest. Reset everything (S-16) deletes the CA key from the
secret store and undoes the ledger's changes, and startup reads and writes the config, data and
cache folders; a test that reached them would change the machine it runs on. So every test gets:

- `VERDRA_HOME` pointing at a fresh temporary folder, so `soil/terrain`'s folders are inside it
  (a test may point it elsewhere, or remove it to test the real paths' names, which it then must
  not write to);
- a fresh in-memory secret store as keyring's backend, so `bark/husk` never reaches Windows
  Credential Manager or the Secret Service. Tests of other backends pass theirs explicitly.

It also fails a test that leaves the `verdra` logger changed (its level, propagation or
handlers): a level left behind decides which records the next test sees, so a test that counts
records would pass or fail depending on what ran before it.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError

from verdra.soil import terrain


class MemoryKeyring(KeyringBackend):
    """A secret store that keeps everything in memory."""

    priority = 1  # pyright: ignore[reportAssignmentType] - keyring declares it as a property

    def __init__(self) -> None:
        super().__init__()
        self.items: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.items.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.items[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        if (service, username) not in self.items:
            raise PasswordDeleteError(username)
        del self.items[(service, username)]


@pytest.fixture(autouse=True)
def isolated_system(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[MemoryKeyring]:
    """Give the test its own Verdra home folder and an in-memory secret store."""
    monkeypatch.setenv(terrain.HOME_OVERRIDE_VARIABLE, str(tmp_path_factory.mktemp("home")))
    store = MemoryKeyring()
    keyring.set_keyring(store)
    before = logger_state()
    yield store
    after = logger_state()
    if after != before:
        logger = logging.getLogger("verdra")
        logger.setLevel(before[0])
        logger.propagate = before[1]
        for handler in set(logger.handlers) - set(before[2]):
            logger.removeHandler(handler)
        pytest.fail(
            f"The test changed the verdra logger: {before[:2]} -> {after[:2]}, "
            f"{len(after[2])} handler(s) where there were {len(before[2])}. Stop what started "
            "logging (Rings.stop) before the test ends.",
            pytrace=False,
        )


def logger_state() -> tuple[int, bool, tuple[logging.Handler, ...]]:
    """Return the `verdra` logger's level, propagation and handlers (pytest's own left out)."""
    logger = logging.getLogger("verdra")
    ours = tuple(h for h in logger.handlers if not type(h).__module__.startswith("_pytest"))
    return logger.level, logger.propagate, ours
