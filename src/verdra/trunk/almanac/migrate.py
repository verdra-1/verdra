# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""One function per schema step; newer files open read-only.

A migration is a pure function from a document at version N to the same document at version
N + 1 (Master plan 9.7). Steps are chained to reach the current version, and each step has a
fixture file and a test. The same helpers serve every versioned format (settings, ledger,
profiles and so on); each format passes its own steps.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

Document = dict[str, Any]
Step = Callable[[Document], Document]

#: Settings migrations: SETTINGS_STEPS[n] turns a version-n settings document into version n + 1.
#: Version 1 is the first released version, so there are no steps yet.
SETTINGS_STEPS: Mapping[int, Step] = {}


class MigrationError(ValueError):
    """A document can't be brought to the current version."""


def is_newer(version: int, current: int) -> bool:
    """Return whether a document comes from a newer Verdra than this one."""
    return version > current


def migrate(document: Document, steps: Mapping[int, Step], current: int) -> Document:
    """Return `document` brought from its own version up to `current`.

    Args:
        document: A parsed document with an integer "version" key no greater than `current`.
        steps: The format's migration steps, keyed by the version they start from.
        current: The version this Verdra writes.

    Raises:
        MigrationError: If a step in the chain is missing or the version is invalid.
    """
    version = document.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise MigrationError(f"invalid version {version!r}")
    if is_newer(version, current):
        raise MigrationError(f"version {version} is newer than {current}")
    result = dict(document)
    for start in range(version, current):
        step = steps.get(start)
        if step is None:
            raise MigrationError(f"no migration from version {start}")
        result = step(dict(result))
        result["version"] = start + 1
    return result
