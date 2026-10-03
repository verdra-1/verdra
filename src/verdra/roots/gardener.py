# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Routing lifecycle and status (Idle, Routing, Degraded, Error); CA in Roblox trust files;
coexistence check.

This part: the CA block in Roblox trust files (spec S-10). Each change is recorded in the
ledger before it is made (`ca_roblox_bundle`, plan 9.4) with the file's SHA-256, its original
mode (read-only flag included) and the exact bytes inserted, so removing the block gives back
the file byte for byte. Files are written only through soil/atomic. Which files to change comes
from the confirmed platform facts (plan 16.4), not from here.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import stat
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from cryptography import x509

from verdra.bark import husk, resin, scar
from verdra.soil import atomic, terrain


def _newline(data: bytes) -> bytes:
    return b"\r\n" if b"\r\n" in data else b"\n"


def _write_keeping_mode(path: Path, data: bytes, mode: int) -> None:
    """Write `path` atomically, then give it back `mode` (its read-only flag included)."""
    with contextlib.suppress(FileNotFoundError):
        os.chmod(path, mode | stat.S_IWUSR)  # a read-only target can't be replaced on Windows
    try:
        atomic.write_atomic(path, data)
    finally:
        os.chmod(path, mode)


def add_ca(path: Path, certificate: x509.Certificate, ledger: scar.Ledger) -> bool:
    """Add the CA block to a trust file; return False if the file already has exactly it.

    A Verdra block the ledger doesn't know about (an older CA) is removed first, so the file
    never holds two.
    """
    data = atomic.read_bytes(path)
    newline = _newline(data)
    block = resin.trust_block(certificate).replace("\n", newline.decode("ascii")).encode("ascii")
    if data.count(terrain.CA_BEGIN_MARKER.encode("ascii")) == 1 and block in data:
        return False
    data = resin.strip_blocks(data)
    inserted = (newline if data and not data.endswith(b"\n") else b"") + block
    mode = stat.S_IMODE(path.stat().st_mode)
    entry = ledger.begin(
        "ca_roblox_bundle",
        str(path),
        {
            "sha256_before": hashlib.sha256(data).hexdigest(),
            "mode": mode,
            "inserted": inserted.decode("ascii"),
        },
    )
    try:
        _write_keeping_mode(path, data + inserted, mode)
    except OSError as error:
        ledger.mark(entry.id, "failed", error=str(error))
        raise
    ledger.mark(entry.id, "done")
    return True


def remove_ca(entry: scar.Entry, ledger: scar.Ledger) -> None:
    """Undo a `ca_roblox_bundle` entry: take the block out and restore the file's mode.

    Works for entries a crash left `pending`: if the block never reached the file, there is
    nothing to take out.
    """
    path = Path(entry.target)
    if not path.exists():
        ledger.mark(entry.id, "removed")
        return
    data = atomic.read_bytes(path)
    inserted = str(entry.details["inserted"]).encode("ascii")
    restored = data.replace(inserted, b"", 1) if inserted in data else resin.strip_blocks(data)
    mode = int(entry.details["mode"])
    if restored != data:
        _write_keeping_mode(path, restored, mode)
    else:
        os.chmod(path, mode)
    ledger.mark(entry.id, "removed")


def certificate_path() -> Path:
    """Return `trust/ca.crt` in the config folder (plan 9.1)."""
    return terrain.config_dir() / terrain.TRUST_FOLDER / terrain.CA_CERTIFICATE_FILE


def _load(vault: husk.Husk, cert_file: Path) -> resin.Authority | None:
    """Return the stored CA, or None if the certificate or its key is missing or doesn't match."""
    text = vault.load_ca_key()
    if text is None or not cert_file.exists():
        return None
    try:
        certificate = x509.load_pem_x509_certificate(atomic.read_bytes(cert_file))
        key = resin.key_from_secret(text)
    except ValueError:
        return None
    return resin.Authority(certificate, key) if resin.matches(certificate, key) else None


def ensure_ca(
    vault: husk.Husk,
    ledger: scar.Ledger,
    trust_files: Iterable[Path],
    now: datetime,
    cert_file: Path | None = None,
) -> resin.Authority:
    """Return a valid CA, in every trust file; create or rotate it first if needed (S-10).

    Rotation (30 days before expiry) follows the spec's order: a new CA is created, the old
    block is removed from every trust file, the new block is added, and only then is the old
    key replaced in the secret store. No file ever holds two blocks.
    """
    cert_file = cert_file if cert_file is not None else certificate_path()
    files = list(trust_files)
    current = _load(vault, cert_file)
    if current is not None and not resin.needs_rotation(current.certificate, now):
        for path in files:
            add_ca(path, current.certificate, ledger)
        return current
    fresh = resin.create_authority(now)
    for entry in list(ledger.open_entries()):
        if entry.kind == "ca_roblox_bundle":
            remove_ca(entry, ledger)
    for path in files:
        add_ca(path, fresh.certificate, ledger)
    vault.save_ca_key(resin.key_to_secret(fresh.key))
    atomic.write_atomic(cert_file, resin.certificate_pem(fresh.certificate))
    return fresh
