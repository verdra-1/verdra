# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Spec S-16: Reset everything undoes the ledger (trunk/branches/fallow), command line included.

Every test runs with its own Verdra home folder and an in-memory secret store
(tests/support/isolation), so the default ledger, `trust/ca.crt` and the CA key are the test's.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from tests.roots.test_gardener import FIXTURES
from tests.support.isolation import MemoryKeyring
from verdra.bark import husk, resin, scar
from verdra.roots import gardener
from verdra.soil import terrain
from verdra.trunk.branches import fallow
from verdra.trunk.sapwood import startup

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def catalog(qapp: QApplication) -> Iterator[None]:
    """The English catalogue, which gives M-RESET-01 and M-RESET-02 their plural forms."""
    translator = startup.install_translator(qapp, "en")
    assert translator is not None
    yield
    qapp.removeTranslator(translator)
    translator.deleteLater()


def trust_files(root: Path) -> list[Path]:
    """Copies of the trust-file fixtures, as two Roblox versions would hold them."""
    files = []
    for number, data in enumerate(FIXTURES.values()):
        path = root / f"version-{number}" / "ssl" / "cacert.pem"
        path.parent.mkdir(parents=True)
        path.write_bytes(data)
        files.append(path)
    return files


def snapshot(files: list[Path], store: MemoryKeyring) -> dict[str, object]:
    return {
        "files": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        "secrets": dict(store.items),
        "certificate": gardener.certificate_path().exists(),
        "open entries": [e.id for e in scar.Ledger().open_entries()],
    }


@pytest.mark.spec("S-16", 1)
def test_reset_puts_back_everything_routing_changed(
    tmp_path: Path, isolated_system: MemoryKeyring
) -> None:
    """At M1 routing changes the trust files and the secret store; the link handler joins with
    S-12."""
    files = trust_files(tmp_path)
    before = snapshot(files, isolated_system)
    gardener.ensure_ca(husk.Husk(), scar.Ledger(), files, NOW)
    assert snapshot(files, isolated_system) != before
    summary = fallow.reset()
    assert summary.removed == len(files) and summary.failed == []
    assert snapshot(files, isolated_system) == before


@pytest.mark.spec("S-16", 2)
@pytest.mark.parametrize("crash", ["before the change", "before done"])
def test_reset_completes_what_a_crash_left_half_done(tmp_path: Path, crash: str) -> None:
    path = trust_files(tmp_path)[0]
    original = path.read_bytes()
    ledger = scar.Ledger()
    authority = resin.create_authority(NOW)
    block = resin.trust_block(authority.certificate).encode()
    ledger.begin(
        "ca_roblox_bundle",
        str(path),
        {"sha256_before": "", "mode": 0o644, "inserted": block.decode()},
    )
    if crash == "before done":
        path.write_bytes(original + block)  # the change was made; "done" was never written
    summary = fallow.reset()
    assert summary.removed == 1
    assert path.read_bytes() == original
    assert [e.state for e in scar.Ledger().entries()] == ["removed"]


@pytest.mark.spec("S-16", 3)
def test_a_second_reset_finds_nothing_to_remove_and_changes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = trust_files(tmp_path)
    gardener.ensure_ca(husk.Husk(), scar.Ledger(), files, NOW)
    assert fallow.command_line(quiet=False) == 0
    capsys.readouterr()
    ledger_bytes = scar.ledger_path().read_bytes()
    contents = [p.read_bytes() for p in files]
    assert fallow.command_line(quiet=False) == 0
    assert capsys.readouterr().out == "Removed 0 changes. Verdra left nothing behind.\n"
    assert scar.ledger_path().read_bytes() == ledger_bytes
    assert [p.read_bytes() for p in files] == contents


@pytest.mark.spec("S-16", 4)
def test_a_failed_undo_is_kept_with_its_reason_and_retried(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = trust_files(tmp_path)
    gardener.ensure_ca(husk.Husk(), scar.Ledger(), files, NOW)
    blocked = files[0]
    changed = blocked.read_bytes()
    blocked.unlink()
    blocked.mkdir()  # a folder where the file was: no user, administrator or not, can read it
    assert fallow.command_line(quiet=False) == 1
    out = capsys.readouterr().out.splitlines()
    assert len(out) == len(files) + 1
    assert out[-1] == "1 change couldn't be removed. See the list for details."
    failed = [line for line in out if line.startswith("Couldn't remove")]
    assert len(failed) == 1
    assert failed[0].startswith(f"Couldn't remove Verdra's certificate in Roblox ({blocked}): ")
    (left,) = fallow.system_changes()
    assert (left.state, left.target) == ("failed", str(blocked))
    assert left.reason and left.reason in failed[0]
    for path in files[1:]:
        assert path.read_bytes() == FIXTURES[list(FIXTURES)[files.index(path)]]
    # The cause is fixed: the retry removes it.
    blocked.rmdir()
    blocked.write_bytes(changed)
    assert fallow.command_line(quiet=False) == 0
    assert capsys.readouterr().out.splitlines() == [
        f"Removed Verdra's certificate in Roblox ({blocked}).",
        "Removed 1 change. Verdra left nothing behind.",
    ]
    assert blocked.read_bytes() == FIXTURES[list(FIXTURES)[0]]
    assert fallow.system_changes() == []


@pytest.mark.spec("S-16", 6)
def test_the_command_line_prints_one_line_per_item_or_nothing_when_quiet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = trust_files(tmp_path)
    gardener.ensure_ca(husk.Husk(), scar.Ledger(), files, NOW)
    assert startup.run(["verdra", "--reset-everything"], lambda _s: None) == 0  # type: ignore[arg-type, return-value]
    lines = capsys.readouterr().out.splitlines()
    assert lines[:-1] == [f"Removed Verdra's certificate in Roblox ({p})." for p in reversed(files)]
    assert lines[-1] == f"Removed {len(files)} changes. Verdra left nothing behind."
    gardener.ensure_ca(husk.Husk(), scar.Ledger(), files, NOW)
    assert startup.run(["verdra", "--reset-everything", "--quiet"], lambda _s: None) == 0  # type: ignore[arg-type, return-value]
    assert capsys.readouterr().out == ""
    unreadable = tmp_path / "unreadable"
    unreadable.mkdir()  # a folder where a trust file should be: its undo fails
    scar.Ledger().begin("ca_roblox_bundle", str(unreadable), {"mode": 0o644, "inserted": "x"})
    assert startup.run(["verdra", "--reset-everything", "--quiet"], lambda _s: None) == 1  # type: ignore[arg-type, return-value]
    assert capsys.readouterr().out == ""


@pytest.mark.spec("S-16", 7)
def test_another_tools_block_in_the_same_file_stays_byte_for_byte(tmp_path: Path) -> None:
    path = trust_files(tmp_path)[0]
    foreign = b"# BEGIN Other Tool CA\nnot ours\n# END Other Tool CA\n"
    path.write_bytes(FIXTURES["lf"] + foreign)
    gardener.ensure_ca(husk.Husk(), scar.Ledger(), [path], NOW)
    path.write_bytes(path.read_bytes() + foreign)  # the other tool adds a second block after ours
    fallow.reset()
    assert path.read_bytes() == FIXTURES["lf"] + foreign + foreign


def test_reset_deletes_the_ca_key_and_certificate(
    tmp_path: Path, isolated_system: MemoryKeyring
) -> None:
    gardener.ensure_ca(husk.Husk(), scar.Ledger(), trust_files(tmp_path), NOW)
    assert (terrain.SECRET_SERVICE, terrain.SECRET_ITEM_CA_KEY) in isolated_system.items
    assert gardener.certificate_path().exists()
    fallow.reset()
    assert isolated_system.items == {}
    assert not gardener.certificate_path().exists()


def test_a_kind_this_version_cant_undo_is_reported_never_skipped(
    capsys: pytest.CaptureFixture[str],
) -> None:
    scar.Ledger().begin("hosts_entries", "/etc/hosts", {})
    assert fallow.command_line(quiet=False) == 1
    assert capsys.readouterr().out.splitlines() == [
        "Couldn't remove Hosts file entries (/etc/hosts): Verdra can't undo this kind of change "
        "in this version.",
        "1 change couldn't be removed. See the list for details.",
    ]
    (left,) = fallow.system_changes()
    assert left.state == "failed"


def test_reset_reports_each_item_as_it_goes() -> None:
    ledger = scar.Ledger()
    first = ledger.begin("ca_roblox_bundle", "/a", {})
    second = ledger.begin("ca_roblox_bundle", "/b", {})
    seen: list[str] = []

    def undo(entry: scar.Entry, book: scar.Ledger) -> None:
        book.mark(entry.id, "removed")

    summary = fallow.reset(
        actions={"ca_roblox_bundle": undo},
        on_item=lambda outcome: seen.append(outcome.change.id),
    )
    assert seen == [second.id, first.id]  # newest first
    assert summary.removed == 2


def test_an_unreadable_ledger_stops_reset_before_it_changes_anything(
    capsys: pytest.CaptureFixture[str], isolated_system: MemoryKeyring
) -> None:
    isolated_system.items[(terrain.SECRET_SERVICE, terrain.SECRET_ITEM_CA_KEY)] = "key"
    scar.ledger_path().parent.mkdir(parents=True, exist_ok=True)
    scar.ledger_path().write_text("{ damaged", encoding="utf-8")
    assert fallow.command_line(quiet=False) == 1
    assert capsys.readouterr().out == (
        f"Verdra can't read its list of system changes in {scar.ledger_path()}.\n"
    )
    assert isolated_system.items  # the key stays: the trust files may still hold its block


def test_tests_never_reach_the_real_secret_store_or_home_folder(tmp_path: Path) -> None:
    """The isolation guard (tests/support/isolation) every test runs under, without asking."""
    import os

    import keyring

    assert isinstance(keyring.get_keyring(), MemoryKeyring)
    home = Path(os.environ[terrain.HOME_OVERRIDE_VARIABLE])
    assert home.is_relative_to(tmp_path.parent)  # pytest's temporary folder for this run
    assert terrain.config_dir().is_relative_to(home)
