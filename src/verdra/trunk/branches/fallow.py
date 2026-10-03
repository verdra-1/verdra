# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Reset everything: undo every ledger entry in reverse order.

Spec S-16. `system_changes` lists what Settings › System changes shows: every ledger entry
(`bark/scar`, plan 9.4) that isn't `removed`, newest first, which is the order `reset` undoes
them in. The interface gets plain values and never the ledger itself.

`reset` runs one undo action per entry kind with the details stored in the entry. Each action
first checks whether the change is there, so entries a crash left `pending` are undone the same
way. An entry whose undo fails, or whose kind this version can't undo, is marked `failed` with
its reason and stays listed; the others still run (S-16 rules 1 and 2). Then the CA key leaves
the secret store and `trust/ca.crt` is deleted: they are in Verdra's own places, not ledger
entries. `command_line` is `verdra --reset-everything [--quiet]`.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject

from verdra.bark import husk, scar
from verdra.roots import gardener

#: Undoes one ledger entry and marks it `removed`; raises if it can't.
Undo = Callable[[scar.Entry, scar.Ledger], None]


class LedgerUnreadableError(RuntimeError):
    """Neither the ledger nor its backup can be read (M-RESET-05)."""

    def __init__(self, path: Path) -> None:
        super().__init__(str(path))
        self.path = path


@dataclass(frozen=True, slots=True)
class Change:
    """One system change, as Settings › System changes shows it."""

    id: str
    #: The ledger entry kind (plan 9.4), for example `ca_roblox_bundle`.
    kind: str
    #: What was changed: a file path, a handler name, a task name.
    target: str
    created: datetime
    #: "pending", "done" or "failed".
    state: str
    #: Why a failed change couldn't be made or undone; None otherwise.
    reason: str | None


def kind_names() -> dict[str, str]:
    """Return the plain name of each system change kind (plan 9.4; spec S-16)."""
    return {
        "ca_roblox_bundle": QCoreApplication.translate(
            "Settings", "Verdra's certificate in Roblox"
        ),
        "hosts_entries": QCoreApplication.translate("Settings", "Hosts file entries"),
        "keeper_install": QCoreApplication.translate("Settings", "Verdra Keeper helper"),
        "scheduled_task": QCoreApplication.translate("Settings", "Scheduled task"),
        "launch_agent": QCoreApplication.translate("Settings", "Launch agent"),
        "launch_daemon": QCoreApplication.translate("Settings", "Launch daemon"),
        "polkit_policy": QCoreApplication.translate("Settings", "Permission policy"),
        "systemd_unit": QCoreApplication.translate("Settings", "System service"),
        "autostart": QCoreApplication.translate("Settings", "Start with the system"),
        "launcher_entry": QCoreApplication.translate("Settings", "Launcher entry"),
        "uri_handler": QCoreApplication.translate("Settings", "Roblox link handler"),
        "file_tweak": QCoreApplication.translate("Settings", "File tweak"),
        "client_settings_file": QCoreApplication.translate("Settings", "Client settings file"),
        "frame_rate_setting": QCoreApplication.translate("Settings", "Frame-rate cap"),
    }


def system_changes(path: Path | None = None) -> list[Change]:
    """Return every change Verdra may have in place, newest first.

    Raises:
        LedgerUnreadableError: The ledger and its backup are both damaged.
    """
    return [_change(entry) for entry in _open(path).open_entries()]


def _open(path: Path | None) -> scar.Ledger:
    try:
        return scar.Ledger(path)
    except scar.LedgerError as error:
        raise LedgerUnreadableError(path or scar.ledger_path()) from error


def _change(entry: scar.Entry) -> Change:
    return Change(
        id=entry.id,
        kind=entry.kind,
        target=entry.target,
        created=entry.created,
        state=entry.state,
        reason=_reason(entry),
    )


def _reason(entry: scar.Entry) -> str | None:
    if entry.state != "failed":
        return None
    error = entry.details.get("error")
    return str(error) if error is not None else None


def undo_actions() -> dict[str, Undo]:
    """Return the undo action of each kind this version can make (S-16 "Undo per kind").

    `uri_handler` joins with the link handling it undoes (S-12); until then no such entry can
    exist, and one that did would be reported as failed rather than skipped.
    """
    return {"ca_roblox_bundle": gardener.remove_ca}


@dataclass(frozen=True, slots=True)
class Outcome:
    """What happened to one change."""

    change: Change
    #: Why it couldn't be removed; None if it was.
    reason: str | None = None

    @property
    def removed(self) -> bool:
        return self.reason is None


@dataclass(frozen=True, slots=True)
class Summary:
    """Every change reset tried to remove, in the order it tried them."""

    outcomes: tuple[Outcome, ...]

    @property
    def removed(self) -> int:
        return sum(outcome.removed for outcome in self.outcomes)

    @property
    def failed(self) -> list[Outcome]:
        return [outcome for outcome in self.outcomes if not outcome.removed]


def reset(
    path: Path | None = None,
    *,
    vault: husk.Husk | None = None,
    cert_file: Path | None = None,
    actions: dict[str, Undo] | None = None,
    on_item: Callable[[Outcome], None] | None = None,
) -> Summary:
    """Undo every change still in the ledger, newest first, then delete Verdra's CA.

    Raises:
        LedgerUnreadableError: The ledger and its backup are both damaged; nothing was undone.
    """
    ledger = _open(path)
    actions = undo_actions() if actions is None else actions
    outcomes: list[Outcome] = []
    for entry in list(ledger.open_entries()):
        reason: str | None = None
        action = actions.get(entry.kind)
        if action is None:
            reason = QCoreApplication.translate(
                "M-RESET-06", "Verdra can't undo this kind of change in this version."
            )
        else:
            try:
                action(entry, ledger)
            except Exception as error:  # noqa: BLE001 - one failure never stops the others (rule 2)
                reason = str(error) or type(error).__name__
        if reason is not None:
            ledger.mark(entry.id, "failed", error=reason)
        outcome = Outcome(_change(entry), reason)
        outcomes.append(outcome)
        if on_item is not None:
            on_item(outcome)
    (vault if vault is not None else husk.Husk()).delete_ca_key()
    with contextlib.suppress(FileNotFoundError):
        (cert_file if cert_file is not None else gardener.certificate_path()).unlink()
    return Summary(tuple(outcomes))


def item_line(outcome: Outcome) -> str:
    """Return the sentence for one change reset removed or couldn't remove."""
    name = kind_names().get(outcome.change.kind, outcome.change.kind)
    if outcome.removed:
        return QCoreApplication.translate("M-RESET-07", "Removed {change} ({target}).").format(
            change=name, target=outcome.change.target
        )
    return QCoreApplication.translate(
        "M-RESET-08", "Couldn't remove {change} ({target}): {reason}"
    ).format(change=name, target=outcome.change.target, reason=outcome.reason)


class ResetSummary(QObject):
    """The summary sentences. They have plural forms, and lupdate makes plural catalogue entries
    only from `QObject.tr` with the count in a plain name."""

    def removed(self, count: int) -> str:
        return self.tr("Removed %n changes. Verdra left nothing behind.", "M-RESET-01", count)

    def failed(self, count: int) -> str:
        return self.tr(
            "%n changes couldn't be removed. See the list for details.", "M-RESET-02", count
        )


def summary_line(summary: Summary) -> str:
    """Return M-RESET-01 when everything was removed, M-RESET-02 otherwise."""
    counts = ResetSummary()
    if summary.failed:
        return counts.failed(len(summary.failed))
    return counts.removed(summary.removed)


def command_line(*, quiet: bool, write: Callable[[str], None] = print) -> int:
    """Run `verdra --reset-everything [--quiet]` and return its exit code.

    Prints one line per change and the summary, or nothing with `quiet`. Exit code 0: every
    change was removed, or there was nothing to remove; 1: something couldn't be removed or the
    ledger can't be read (S-16, "Command line").
    """
    say = (lambda _line: None) if quiet else write
    try:
        summary = reset(on_item=lambda outcome: say(item_line(outcome)))
    except LedgerUnreadableError as error:
        say(
            QCoreApplication.translate(
                "M-RESET-05", "Verdra can't read its list of system changes in {path}."
            ).format(path=error.path)
        )
        return 1
    say(summary_line(summary))
    return 1 if summary.failed else 0
