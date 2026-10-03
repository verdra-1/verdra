# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Spec S-10: the CA key in the secret store, with the Linux fallback file (plan 10.6, 16.2)."""

import os
import stat
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from keyring.backends import fail, null

from tests.support.isolation import MemoryKeyring
from verdra.bark import husk, resin
from verdra.soil import terrain

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(terrain.HOME_OVERRIDE_VARIABLE, str(tmp_path / "home"))
    temp = tmp_path / "temp"
    temp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp))
    return tmp_path


def key_material(authority: resin.Authority) -> list[bytes]:
    """Every form the CA key could take on disk: PEM, DER and the raw scalar."""
    key = authority.key
    pem = resin.key_to_secret(key).encode()
    der = key.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    scalar = key.private_numbers().private_value.to_bytes(32, "big")
    body = b"".join(line for line in pem.splitlines() if not line.startswith(b"-----"))
    return [pem, der, scalar, body]


def files_holding(root: Path, secrets: list[bytes]) -> list[Path]:
    return [
        path
        for path in root.rglob("*")
        if path.is_file() and any(secret in path.read_bytes() for secret in secrets)
    ]


def test_only_real_stores_count_as_secure() -> None:
    assert husk.secure_storage_available(MemoryKeyring())
    assert not husk.secure_storage_available(fail.Keyring())
    assert not husk.secure_storage_available(null.Keyring())


@pytest.mark.spec("S-10", 5)
def test_the_key_goes_to_the_secret_store_and_nowhere_on_disk(home: Path) -> None:
    store = MemoryKeyring()
    vault = husk.Husk(store, file_fallback=True)
    authority = resin.create_authority(NOW)
    assert vault.save_ca_key(resin.key_to_secret(authority.key)) is husk.Where.STORE
    assert store.items[(terrain.SECRET_SERVICE, terrain.SECRET_ITEM_CA_KEY)].startswith(
        "-----BEGIN PRIVATE KEY-----"
    )
    assert not vault.uses_file()
    text = vault.load_ca_key()
    assert text is not None
    assert resin.matches(authority.certificate, resin.key_from_secret(text))
    # Config, cache, log and temp folders all live under the test home here.
    assert files_holding(home, key_material(authority)) == []
    vault.delete_ca_key()
    assert vault.load_ca_key() is None
    vault.delete_ca_key()  # deleting twice is harmless


@pytest.mark.spec("S-10", 5)
@pytest.mark.skipif(sys.platform == "win32", reason="file modes are POSIX; Windows has a store")
def test_without_a_store_linux_keeps_one_user_only_file(home: Path) -> None:
    vault = husk.Husk(fail.Keyring(), file_fallback=True)
    authority = resin.create_authority(NOW)
    assert vault.save_ca_key(resin.key_to_secret(authority.key)) is husk.Where.FILE
    assert vault.uses_file()  # the app shows M-CA-03
    key_file = home / "home" / "config" / terrain.TRUST_FOLDER / terrain.CA_KEY_FALLBACK_FILE
    assert vault.key_file == key_file
    assert files_holding(home, key_material(authority)) == [key_file]
    info = key_file.stat()
    assert stat.S_IMODE(info.st_mode) == 0o600
    assert info.st_uid == os.getuid()
    text = vault.load_ca_key()
    assert text is not None
    assert resin.matches(authority.certificate, resin.key_from_secret(text))
    vault.delete_ca_key()  # Reset everything
    assert not key_file.exists()
    assert files_holding(home, key_material(authority)) == []
    assert not vault.uses_file()


def test_without_a_store_other_systems_refuse(home: Path) -> None:
    vault = husk.Husk(fail.Keyring(), file_fallback=False)
    with pytest.raises(husk.NoSecretStoreError):
        vault.save_ca_key("secret")
    assert files_holding(home, [b"secret"]) == []
    assert vault.load_ca_key() is None


def test_a_store_that_appears_later_takes_over_the_file(home: Path) -> None:
    authority = resin.create_authority(NOW)
    text = resin.key_to_secret(authority.key)
    husk.Husk(fail.Keyring(), file_fallback=True).save_ca_key(text)
    store = MemoryKeyring()
    vault = husk.Husk(store, file_fallback=True)
    assert vault.load_ca_key() == text  # still readable from the file
    assert vault.save_ca_key(text) is husk.Where.STORE
    assert not vault.key_file.exists()
    assert files_holding(home, key_material(authority)) == []


def test_only_linux_may_use_the_key_file() -> None:
    from verdra.soil import meadow, orchard, tundra

    assert tundra.PLATFORM.key_file_fallback
    assert not meadow.PLATFORM.key_file_fallback
    assert not orchard.PLATFORM.key_file_fallback
