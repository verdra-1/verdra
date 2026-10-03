# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""OS secret store through keyring; Linux fallback file (0600) for the CA key only.

Secrets live in the OS secret store under service `io.github.verdra-1.verdra` (Master plan
10.6, Reference R3): Windows Credential Manager, or the Secret Service on Linux. When a Linux
desktop has no Secret Service, the CA key alone goes to `trust/ca.key` in the config folder,
readable only by the user (mode 0600), and the app shows M-CA-03 (plan 16.2, risk R-10).
Reset everything deletes it. Nothing here logs or returns a secret except to its caller.
"""

from __future__ import annotations

import contextlib
import os
import stat
from enum import StrEnum
from pathlib import Path

import keyring
import keyring.backend
import keyring.errors
from keyring.backends import fail, null

from verdra.soil import atomic, humus, terrain


class NoSecretStoreError(RuntimeError):
    """The system has no secret store, and this system may not use the key file instead."""


class Where(StrEnum):
    """Where the CA key was saved."""

    STORE = "store"
    FILE = "file"


def secure_storage_available(backend: keyring.backend.KeyringBackend) -> bool:
    """Return whether `backend` is a real secret store (not keyring's fail or null backend)."""
    return not isinstance(backend, (fail.Keyring, null.Keyring)) and backend.priority > 0


def fallback_path() -> Path:
    """Return the Linux fallback file for the CA key."""
    return terrain.config_dir() / terrain.TRUST_FOLDER / terrain.CA_KEY_FALLBACK_FILE


class Husk:
    """The CA key's place in the secret store, with the documented Linux fallback file."""

    def __init__(
        self,
        backend: keyring.backend.KeyringBackend | None = None,
        *,
        file_fallback: bool | None = None,
        key_file: Path | None = None,
    ) -> None:
        self.backend = backend if backend is not None else keyring.get_keyring()
        self.file_fallback = (
            humus.current().key_file_fallback if file_fallback is None else file_fallback
        )
        self.key_file = key_file if key_file is not None else fallback_path()

    @property
    def secure(self) -> bool:
        """Whether a real secret store is available."""
        return secure_storage_available(self.backend)

    def uses_file(self) -> bool:
        """Return whether the CA key lives in the fallback file (show M-CA-03)."""
        return not self.secure and self.key_file.exists()

    def save_ca_key(self, text: str) -> Where:
        """Save the CA key and return where it went.

        Raises:
            NoSecretStoreError: No secret store, and this system may not use the key file.
        """
        if self.secure:
            self.backend.set_password(terrain.SECRET_SERVICE, terrain.SECRET_ITEM_CA_KEY, text)
            self._remove_file()
            return Where.STORE
        if not self.file_fallback:
            msg = "no secret store on this system"
            raise NoSecretStoreError(msg)
        # mkstemp creates the temporary file with mode 0600, and the rename keeps it.
        atomic.write_atomic(self.key_file, text.encode("ascii"))
        os.chmod(self.key_file, stat.S_IRUSR | stat.S_IWUSR)
        return Where.FILE

    def load_ca_key(self) -> str | None:
        """Return the CA key's text, or None if Verdra has none yet."""
        if self.secure:
            text = self.backend.get_password(terrain.SECRET_SERVICE, terrain.SECRET_ITEM_CA_KEY)
            if text is not None:
                return text
        if self.file_fallback and self.key_file.exists():
            return atomic.read_bytes(self.key_file).decode("ascii")
        return None

    def delete_ca_key(self) -> None:
        """Delete the CA key from the secret store and the fallback file (Reset everything)."""
        if self.secure:
            with contextlib.suppress(keyring.errors.PasswordDeleteError):
                self.backend.delete_password(terrain.SECRET_SERVICE, terrain.SECRET_ITEM_CA_KEY)
        self._remove_file()

    def _remove_file(self) -> None:
        with contextlib.suppress(FileNotFoundError):
            self.key_file.unlink()
