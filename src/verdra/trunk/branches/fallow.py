# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Reset everything: undo every ledger entry in reverse order.

Spec S-16. This part lists the system changes for Settings › System changes: every ledger entry
(`bark/scar`, plan 9.4) that isn't `removed`, newest first, which is the order Reset everything
undoes them in. The interface gets plain values and never the ledger itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from verdra.bark import scar


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


def system_changes(path: Path | None = None) -> list[Change]:
    """Return every change Verdra may have in place, newest first.

    Raises:
        LedgerUnreadableError: The ledger and its backup are both damaged.
    """
    try:
        ledger = scar.Ledger(path)
    except scar.LedgerError as error:
        raise LedgerUnreadableError(path or scar.ledger_path()) from error
    return [
        Change(
            id=entry.id,
            kind=entry.kind,
            target=entry.target,
            created=entry.created,
            state=entry.state,
            reason=_reason(entry),
        )
        for entry in reversed(ledger.entries())
        if entry.state in scar.OPEN_STATES
    ]


def _reason(entry: scar.Entry) -> str | None:
    if entry.state != "failed":
        return None
    error = entry.details.get("error")
    return str(error) if error is not None else None
