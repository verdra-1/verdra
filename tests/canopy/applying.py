# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""What the tests of applying share: a stand-in for trunk's Sprout, and the toasts shown."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from verdra.canopy.crown.dew import Toast
from verdra.canopy.crown.window import Shell
from verdra.trunk.branches import sprout


class StubSprout(QObject):
    """Records what Apply now asks of trunk's Sprout."""

    refused = Signal(str)
    other_tool = Signal(str)
    backups_changed = Signal()
    others_changed = Signal(bool)
    held_back = Signal(str)
    handed_off = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []
        #: A Player this Verdra started is running.
        self.running = False
        #: Players Verdra didn't start, and Studios, that are running.
        self.others: tuple[int, ...] = ()
        self.studio: tuple[int, ...] = ()
        self.routing = True
        self.cache: sprout.CacheMove | None = sprout.CacheMove(
            ("rbx-storage.db", "rbx-storage"), Path("C:/Verdra/Roblox cache backup/1")
        )

    def roblox_running(self) -> bool:
        return self.running

    def roblox_processes(self) -> sprout.RunningRoblox:
        players = frozenset(((7,) if self.running else ()) + self.others)
        return sprout.RunningRoblox(players, bool(self.studio))

    def players_started_here(self) -> set[int]:
        return {7} if self.running else set()

    def refresh_others(self) -> frozenset[int]:
        self.others_changed.emit(bool(self.others))
        return frozenset(self.others)

    def close_roblox(self) -> None:
        self.calls.append("close")

    def clear_cache(self) -> sprout.CacheMove | None:
        self.calls.append("clear")
        return self.cache

    def launch(self, link: str | None = None) -> None:
        self.calls.append("launch")

    def start_routing(self) -> None:
        self.calls.append("start")


def toasts(shell: Shell) -> list[str]:
    return [t.text for t in shell.window.findChildren(Toast)]
