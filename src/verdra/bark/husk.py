# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""OS secret store through keyring.

Secrets live in the OS secret store under service `io.github.verdra-1.verdra` (Master plan
10.6, Reference R3): Windows Credential Manager. Without a secret store, saving the CA key is
refused; there is no key file (the Linux fallback file of risk R-10 left with Linux, decision
record 0018). Nothing here logs or returns a secret except to its caller.
"""

from __future__ import annotations

import contextlib
from enum import StrEnum

import keyring
import keyring.backend
import keyring.errors
from keyring.backends import fail, null

from verdra.soil import terrain


class NoSecretStoreError(RuntimeError):
    """The system has no secret store."""


class Where(StrEnum):
    """Where the CA key was saved."""

    STORE = "store"


def secure_storage_available(backend: keyring.backend.KeyringBackend) -> bool:
    """Return whether `backend` is a real secret store (not keyring's fail or null backend)."""
    return not isinstance(backend, (fail.Keyring, null.Keyring)) and backend.priority > 0


class Husk:
    """The CA key's place in the secret store."""

    def __init__(self, backend: keyring.backend.KeyringBackend | None = None) -> None:
        self.backend = backend if backend is not None else keyring.get_keyring()

    @property
    def secure(self) -> bool:
        """Whether a real secret store is available."""
        return secure_storage_available(self.backend)

    def save_ca_key(self, text: str) -> Where:
        """Save the CA key and return where it went.

        Raises:
            NoSecretStoreError: The system has no secret store.
        """
        if not self.secure:
            msg = "no secret store on this system"
            raise NoSecretStoreError(msg)
        self.backend.set_password(terrain.SECRET_SERVICE, terrain.SECRET_ITEM_CA_KEY, text)
        return Where.STORE

    def load_ca_key(self) -> str | None:
        """Return the CA key's text, or None if Verdra has none yet."""
        if not self.secure:
            return None
        return self.backend.get_password(terrain.SECRET_SERVICE, terrain.SECRET_ITEM_CA_KEY)

    def delete_ca_key(self) -> None:
        """Delete the CA key from the secret store (Reset everything)."""
        if self.secure:
            with contextlib.suppress(keyring.errors.PasswordDeleteError):
                self.backend.delete_password(terrain.SECRET_SERVICE, terrain.SECRET_ITEM_CA_KEY)
