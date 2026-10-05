# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Spec S-10: the CA key in the secret store (plan 10.6), and no key file without one."""

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
    vault = husk.Husk(store)
    authority = resin.create_authority(NOW)
    assert vault.save_ca_key(resin.key_to_secret(authority.key)) is husk.Where.STORE
    assert store.items[(terrain.SECRET_SERVICE, terrain.SECRET_ITEM_CA_KEY)].startswith(
        "-----BEGIN PRIVATE KEY-----"
    )
    text = vault.load_ca_key()
    assert text is not None
    assert resin.matches(authority.certificate, resin.key_from_secret(text))
    # Config, cache, log and temp folders all live under the test home here.
    assert files_holding(home, key_material(authority)) == []
    vault.delete_ca_key()
    assert vault.load_ca_key() is None
    vault.delete_ca_key()  # deleting twice is harmless


@pytest.mark.spec("S-10", 5)
def test_without_a_store_saving_is_refused_and_nothing_is_written(home: Path) -> None:
    vault = husk.Husk(fail.Keyring())
    with pytest.raises(husk.NoSecretStoreError):
        vault.save_ca_key("secret")
    assert files_holding(home, [b"secret"]) == []
    assert vault.load_ca_key() is None
