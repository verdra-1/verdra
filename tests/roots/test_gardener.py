# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Spec S-10: the CA block in Roblox trust files (rules 2 to 4, tests 2 and 7)."""

import logging
import os
import stat
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PySide6.QtCore import QTimer
from pytestqt.qtbot import QtBot

from tests.support.isolation import MemoryKeyring
from verdra.bark import husk, resin, scar
from verdra.roots import gardener
from verdra.soil import terrain

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def authority() -> resin.Authority:
    return resin.create_authority(NOW)


def bundle(newline: str = "\n", trailing: bool = True) -> bytes:
    """A trust-file stand-in: two other CAs' PEM blocks, as cacert.pem files hold them."""
    other = resin.create_authority(NOW).certificate
    another = resin.create_authority(NOW).certificate
    text = (
        "## Bundle of CA Root Certificates\n\nOther CA\n"
        + resin.certificate_pem(other).decode()
        + "\nAnother CA\n"
        + resin.certificate_pem(another).decode()
    )
    if not trailing:
        text = text.rstrip("\n")
    return text.replace("\n", newline).encode()


#: Until the trust files are recorded on real machines (plan 16.4), these stand in for them.
FIXTURES = {
    "lf": bundle(),
    "crlf": bundle("\r\n"),
    "no final newline": bundle(trailing=False),
    "empty": b"",
}


def blocks(data: bytes) -> int:
    return data.count(terrain.CA_BEGIN_MARKER.encode())


@pytest.mark.spec("S-10", 2)
@pytest.mark.parametrize("name", list(FIXTURES))
@pytest.mark.parametrize("read_only", [False, True], ids=["writable", "read-only"])
def test_the_block_goes_in_once_and_comes_out_byte_identical(
    tmp_path: Path, authority: resin.Authority, name: str, read_only: bool
) -> None:
    original = FIXTURES[name]
    path = tmp_path / "cacert.pem"
    path.write_bytes(original)
    if read_only:
        os.chmod(path, stat.S_IREAD)
    mode = stat.S_IMODE(path.stat().st_mode)
    book = scar.Ledger(tmp_path / "changes.json")
    assert gardener.add_ca(path, authority.certificate, book)
    assert not gardener.add_ca(path, authority.certificate, book)  # adding twice: still one
    changed = path.read_bytes()
    assert blocks(changed) == 1
    assert changed.startswith(original.rstrip(b"\r\n"))
    assert stat.S_IMODE(path.stat().st_mode) == mode
    (entry,) = book.entries()
    assert entry.kind == "ca_roblox_bundle"
    assert entry.state == "done"
    assert entry.target == str(path)
    for opened in list(book.open_entries()):
        gardener.remove_ca(opened, book)
    assert path.read_bytes() == original
    assert stat.S_IMODE(path.stat().st_mode) == mode
    assert [e.state for e in book.entries()] == ["removed"]
    os.chmod(path, stat.S_IREAD | stat.S_IWRITE)


@pytest.mark.spec("S-10", 2)
def test_a_block_the_ledger_doesnt_know_is_replaced_not_doubled(
    tmp_path: Path, authority: resin.Authority
) -> None:
    path = tmp_path / "cacert.pem"
    old = resin.create_authority(NOW).certificate
    path.write_bytes(FIXTURES["lf"] + resin.trust_block(old).encode())
    book = scar.Ledger(tmp_path / "changes.json")
    assert gardener.add_ca(path, authority.certificate, book)
    data = path.read_bytes()
    assert blocks(data) == 1
    assert resin.trust_block(authority.certificate).encode() in data
    assert resin.trust_block(old).encode() not in data


@pytest.mark.spec("S-10", 7)
def test_the_ledger_entry_is_written_before_the_file_changes(
    tmp_path: Path, authority: resin.Authority, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "cacert.pem"
    path.write_bytes(FIXTURES["lf"])
    ledger_file = tmp_path / "changes.json"
    book = scar.Ledger(ledger_file)
    seen: list[str] = []

    def crash(target: Path, data: bytes, mode: int) -> None:
        # The process dies right here: the entry must already be on disk, the file untouched.
        seen.extend(e.state for e in scar.Ledger(ledger_file).entries())
        raise SystemExit

    monkeypatch.setattr(gardener, "_write_keeping_mode", crash)
    with pytest.raises(SystemExit):
        gardener.add_ca(path, authority.certificate, book)
    monkeypatch.undo()
    assert seen == ["pending"]
    assert path.read_bytes() == FIXTURES["lf"]
    # After the "restart", Reset everything finds the pending entry and undoes it cleanly.
    after = scar.Ledger(ledger_file)
    (entry,) = after.open_entries()
    assert entry.state == "pending"
    gardener.remove_ca(entry, after)
    assert path.read_bytes() == FIXTURES["lf"]
    assert [e.state for e in after.entries()] == ["removed"]


def test_a_failed_write_marks_the_entry_failed(
    tmp_path: Path, authority: resin.Authority, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "cacert.pem"
    path.write_bytes(FIXTURES["lf"])
    book = scar.Ledger(tmp_path / "changes.json")

    def full(target: Path, data: bytes, mode: int) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(gardener, "_write_keeping_mode", full)
    with pytest.raises(OSError, match="No space"):
        gardener.add_ca(path, authority.certificate, book)
    (entry,) = book.entries()
    assert entry.state == "failed"
    assert "No space" in entry.details["error"]


def test_removing_from_a_file_that_is_gone_or_was_replaced(
    tmp_path: Path, authority: resin.Authority
) -> None:
    path = tmp_path / "cacert.pem"
    path.write_bytes(FIXTURES["lf"])
    book = scar.Ledger(tmp_path / "changes.json")
    gardener.add_ca(path, authority.certificate, book)
    (entry,) = book.open_entries()
    path.write_bytes(FIXTURES["crlf"])  # Roblox replaced the file: nothing of ours left
    gardener.remove_ca(entry, book)
    assert path.read_bytes() == FIXTURES["crlf"]
    gardener.add_ca(path, authority.certificate, book)
    (second,) = book.open_entries()
    path.unlink()
    gardener.remove_ca(second, book)
    assert [e.state for e in book.entries()] == ["removed", "removed"]


# --- Creation and rotation (spec S-10, test 4) -------------------------------------------------


@pytest.fixture
def setup(tmp_path: Path) -> tuple[husk.Husk, scar.Ledger, list[Path], Path]:
    vault = husk.Husk(MemoryKeyring())
    book = scar.Ledger(tmp_path / "changes.json")
    files = []
    for name, data in (("one", FIXTURES["lf"]), ("two", FIXTURES["crlf"])):
        path = tmp_path / name / "cacert.pem"
        path.parent.mkdir()
        path.write_bytes(data)
        files.append(path)
    return vault, book, files, tmp_path / "trust" / "ca.crt"


def test_the_first_start_creates_the_ca_and_adds_it(
    setup: tuple[husk.Husk, scar.Ledger, list[Path], Path],
) -> None:
    vault, book, files, cert_file = setup
    authority = gardener.ensure_ca(vault, book, files, NOW, cert_file)
    stored = vault.load_ca_key()
    assert stored is not None
    assert resin.matches(authority.certificate, resin.key_from_secret(stored))
    assert cert_file.read_bytes() == resin.certificate_pem(authority.certificate)
    for path in files:
        assert blocks(path.read_bytes()) == 1
    # The next start finds the same CA and changes nothing.
    again = gardener.ensure_ca(vault, book, files, NOW + timedelta(days=1), cert_file)
    assert again.certificate == authority.certificate
    assert len(book.entries()) == 2


@pytest.mark.spec("S-10", 4)
def test_rotation_leaves_one_block_signed_by_the_new_ca(
    setup: tuple[husk.Husk, scar.Ledger, list[Path], Path],
) -> None:
    vault, book, files, cert_file = setup
    old = gardener.ensure_ca(vault, book, files, NOW, cert_file)
    old_key_text = vault.load_ca_key()
    rotate_at = old.certificate.not_valid_after_utc - timedelta(days=30)
    new = gardener.ensure_ca(vault, book, files, rotate_at, cert_file)
    assert new.certificate != old.certificate
    assert not resin.needs_rotation(new.certificate, rotate_at)
    for path in files:
        data = path.read_bytes()
        assert blocks(data) == 1
        newline = "\r\n" if b"\r\n" in data else "\n"
        assert resin.trust_block(new.certificate).replace("\n", newline).encode() in data
    stored = vault.load_ca_key()
    assert stored is not None and stored != old_key_text  # the old key is gone from the store
    assert resin.matches(new.certificate, resin.key_from_secret(stored))
    assert cert_file.read_bytes() == resin.certificate_pem(new.certificate)
    assert [e.state for e in book.entries()] == ["removed", "removed", "done", "done"]
    # Reset everything afterwards leaves the files as they were before Verdra.
    for entry in list(book.open_entries()):
        gardener.remove_ca(entry, book)
    assert [p.read_bytes() for p in files] == [FIXTURES["lf"], FIXTURES["crlf"]]


def test_a_certificate_without_its_key_means_a_new_ca(
    setup: tuple[husk.Husk, scar.Ledger, list[Path], Path],
) -> None:
    vault, book, files, cert_file = setup
    first = gardener.ensure_ca(vault, book, files, NOW, cert_file)
    vault.delete_ca_key()
    second = gardener.ensure_ca(vault, book, files, NOW, cert_file)
    assert second.certificate != first.certificate
    for path in files:
        assert blocks(path.read_bytes()) == 1
    cert_file.write_bytes(b"not a certificate")
    third = gardener.ensure_ca(vault, book, files, NOW, cert_file)
    assert third.certificate != second.certificate


# --- New Roblox versions (spec S-10, test 3) ---------------------------------------------------


#: Stand-in for the recorded layout: the trust file inside a version folder (plan 16.4).
def trust_files_in(version: Path) -> list[Path]:
    return [version / "ssl" / "cacert.pem"]


@pytest.mark.spec("S-10", 3)
def test_a_new_version_folder_gets_the_block_within_10_s(
    tmp_path: Path,
    authority: resin.Authority,
    qtbot: QtBot,
    caplog: pytest.LogCaptureFixture,
) -> None:
    install = tmp_path / "Versions"
    (install / "version-old" / "ssl").mkdir(parents=True)
    book = scar.Ledger(tmp_path / "changes.json")
    watch = gardener.VersionWatch([install], trust_files_in, authority.certificate, book)
    started = time.monotonic()
    with (
        caplog.at_level(logging.INFO, logger="verdra"),
        qtbot.waitSignal(watch.updated, timeout=10_000) as signal,
    ):
        # The installer makes the folder first and writes its files a moment later.
        version = install / "version-new"
        (version / "ssl").mkdir(parents=True)
        QTimer.singleShot(
            1500, lambda: (version / "ssl" / "cacert.pem").write_bytes(FIXTURES["lf"])
        )
    assert time.monotonic() - started < 10
    assert signal.args == [str(version)]
    data = (version / "ssl" / "cacert.pem").read_bytes()
    assert blocks(data) == 1
    assert [e.target for e in book.entries()] == [str(version / "ssl" / "cacert.pem")]
    activity = [r.getMessage() for r in caplog.records if r.name.startswith("verdra")]
    assert activity == ["Roblox updated. Verdra added its certificate to the new version."]
    assert not watch.pending
    assert not watch.timer.isActive()


def test_a_version_folder_that_never_gets_a_trust_file_is_given_up(
    tmp_path: Path, authority: resin.Authority, qtbot: QtBot
) -> None:
    install = tmp_path / "Versions"
    install.mkdir()
    book = scar.Ledger(tmp_path / "changes.json")
    watch = gardener.VersionWatch([install], trust_files_in, authority.certificate, book)
    watch.PATIENCE_SECONDS = 0.5
    (install / "version-empty").mkdir()
    qtbot.waitUntil(lambda: not watch.pending and not watch.timer.isActive(), timeout=10_000)
    assert book.entries() == []


def test_a_version_whose_trust_file_cant_take_the_block_is_missing_until_repaired(
    tmp_path: Path, authority: resin.Authority, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S-14 Degraded (c): reported after the patience runs out, cleared by `repair`."""
    install = tmp_path / "Versions"
    install.mkdir()
    book = scar.Ledger(tmp_path / "changes.json")
    watch = gardener.VersionWatch([install], trust_files_in, authority.certificate, book)
    watch.PATIENCE_SECONDS = 0.5

    def locked(*_args: object) -> None:
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr(gardener, "add_ca", locked)
    version = install / "version-locked"
    with qtbot.waitSignal(watch.missing, timeout=10_000) as signal:
        (version / "ssl").mkdir(parents=True)
        (version / "ssl" / "cacert.pem").write_bytes(FIXTURES["lf"])
    assert signal.args == [str(version)]
    assert watch.lacking == {version}
    assert not watch.repair()  # still locked
    monkeypatch.undo()
    with qtbot.waitSignal(watch.updated, timeout=1_000):
        assert watch.repair()
    assert watch.lacking == set()
    assert blocks((version / "ssl" / "cacert.pem").read_bytes()) == 1
