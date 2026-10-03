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
"""

from __future__ import annotations

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
    yield store
