# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Leaf certificates load into TLS without touching the disk (plan 10.3, spec S-10 test 6)."""

import asyncio
import os
import ssl
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization

from verdra.bark import resin
from verdra.soil import humus, orchard

NOW = datetime.now(UTC)
HOST = "assetdelivery.roblox.com"


def leaf_pems(authority: resin.Authority) -> tuple[bytes, bytes, resin.Leaf]:
    leaf = resin.issue_leaf(authority, HOST, NOW)
    key = leaf.key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return resin.certificate_pem(leaf.certificate), key, leaf


def files_under(root: Path) -> set[Path]:
    return {path for path in root.rglob("*") if path.is_file()}


@pytest.mark.spec("S-10", 6)
def test_a_leaf_loaded_from_memory_serves_tls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    authority = resin.create_authority(NOW)
    certificate, key, leaf = leaf_pems(authority)
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    before = files_under(tmp_path)
    humus.current().load_cert_chain(server, certificate, key)
    assert files_under(tmp_path) == before  # nothing written, not even a temporary file

    async def handshake() -> bytes:
        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            writer.write(b"hello")
            await writer.drain()
            writer.close()

        listener = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=server)
        port = listener.sockets[0].getsockname()[1]
        client = ssl.create_default_context(
            cadata=resin.certificate_pem(authority.certificate).decode()
        )
        reader, writer = await asyncio.open_connection(
            "127.0.0.1", port, ssl=client, server_hostname=HOST
        )
        peer = writer.get_extra_info("peercert")
        data = await reader.read()
        writer.close()
        listener.close()
        assert peer is not None
        return data

    assert asyncio.run(asyncio.wait_for(handshake(), timeout=30)) == b"hello"
    assert leaf.certificate.subject.rfc4514_string() == f"CN={HOST}"


def test_loading_twice_in_a_row_works() -> None:
    authority = resin.create_authority(NOW)
    for _ in range(3):
        certificate, key, _leaf = leaf_pems(authority)
        humus.current().load_cert_chain(ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER), certificate, key)


def test_a_bad_key_raises_and_releases_everything() -> None:
    authority = resin.create_authority(NOW)
    certificate, _key, _leaf = leaf_pems(authority)
    # OpenSSL refuses the key; Python reports ssl.SSLError on Linux and, after reading a pipe on
    # Windows, a plain OSError (errno 22). SSLError is an OSError, so both are caught here.
    with pytest.raises(OSError):
        humus.current().load_cert_chain(
            ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER), certificate, b"not a key"
        )
    # Nothing is left half open: the next load works.
    certificate, key, _leaf = leaf_pems(authority)
    humus.current().load_cert_chain(ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER), certificate, key)


def test_macos_refuses() -> None:
    with pytest.raises(NotImplementedError):
        orchard.PLATFORM.load_cert_chain(ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER), b"", b"")


@pytest.mark.skipif(not hasattr(os, "memfd_create"), reason="Linux only")
def test_linux_closes_its_memory_files() -> None:
    authority = resin.create_authority(NOW)
    certificate, key, _leaf = leaf_pems(authority)
    open_before = set(os.listdir("/proc/self/fd"))
    humus.platform_for("linux").load_cert_chain(
        ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER), certificate, key
    )
    assert set(os.listdir("/proc/self/fd")) <= open_before | set()
