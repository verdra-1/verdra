# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Replacement profiles: store, validation, conflicts, snapshot compile, undo and redo.

Spec S-20. Each profile is one `verdra.profile` v1 file, `profiles/<name>.json` (plan 9.2, 9.3),
written atomically with `.bak` (plan 9.7). `ProfileStore` keeps the profiles in their order
(the setting `replacements.profile_order`), records every edit for undo and redo, and compiles
the enabled replacements into the `roots.rules.GraftSnapshot` the proxy reads (spec S-21):
a profile higher in the list wins for the same original, and within one profile the later
replacement wins (rule 1).
"""

from __future__ import annotations

import copy
import logging
import re
import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Annotated
from urllib.parse import urlsplit

import msgspec
from msgspec import Meta, Struct, field
from PySide6.QtCore import QCoreApplication

from verdra.roots import rules
from verdra.soil import atomic, terrain

log = logging.getLogger(__name__)

FORMAT = terrain.FORMAT_PROFILE
VERSION = 1
#: Rule 3.
MAX_REPLACEMENTS = 10_000
#: Undo and redo cover the last 50 edits of the session.
UNDO_LIMIT = 50
#: Rule 2: the longest profile name.
MAX_NAME = 100

AssetId = Annotated[int, Meta(ge=1)]
UtcTimestamp = Annotated[datetime, Meta(tz=True)]


class Original(Struct, kw_only=True):
    """The asset a replacement replaces, and the TexturePack map it names (or None)."""

    asset_id: AssetId
    slot: rules.Slot | None = None


class Target(Struct, kw_only=True):
    """What the client receives instead (plan 9.3: `asset_id`, `file`, `url`, `remove`)."""

    kind: rules.TargetKind
    value: str = ""


class Replacement(Struct, kw_only=True):
    """One replacement in a profile."""

    id: str
    enabled: bool = True
    original: Original
    target: Target
    asset_type: str = ""
    note: str = ""


class Profile(Struct, kw_only=True):
    """A `verdra.profile` v1 file."""

    format: str = FORMAT
    version: int = VERSION
    id: str
    name: str
    enabled: bool = True
    created: UtcTimestamp
    modified: UtcTimestamp
    replacements: list[Replacement] = field(default_factory=list)


class ProfileError(ValueError):
    """A profile can't be saved as it is; the message is the sentence the user sees."""


class ProfileUnreadableError(RuntimeError):
    """A profile file and its `.bak` both failed to load; the file was moved aside."""

    def __init__(self, path: Path, moved: Path) -> None:
        super().__init__(f"{path} can't be read; moved to {moved.name}")
        self.path = path
        self.moved = moved


# --- Names (rule 2) -------------------------------------------------------------------------------

_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{n}" for p in ("COM", "LPT") for n in range(10)}


def name_problem(name: str) -> str | None:
    """Return why `name` can't be a profile name on Windows and Linux, or None if it can."""
    if not name.strip():
        return QCoreApplication.translate("M-PROF-04", "Enter a name for the profile.")
    if _FORBIDDEN.search(name):
        return QCoreApplication.translate(
            "M-PROF-04", "A profile name can't contain < > : \" / \\ | ? or *."
        )
    if name.endswith((".", " ")) or name.split(".", 1)[0].upper().strip() in _RESERVED:
        return QCoreApplication.translate("M-PROF-04", "This name can't be used for a file.")
    if len(name) > MAX_NAME:
        return QCoreApplication.translate(
            "M-PROF-04", "A profile name can be at most {n} characters."
        ).format(n=MAX_NAME)
    return None


# --- Replacements (rule 5) ------------------------------------------------------------------------


def replacement_problem(replacement: Replacement) -> str | None:
    """Return why a replacement can't be used (left out of the snapshot), or None."""
    target = replacement.target
    if target.kind == "asset_id" and not (target.value.isdigit() and int(target.value) > 0):
        return QCoreApplication.translate("M-EDIT-01", "No asset with ID {id} was found.").format(
            id=target.value
        )
    if target.kind == "url" and urlsplit(target.value).scheme != "https":
        return QCoreApplication.translate("M-EDIT-03", "Only HTTPS links are allowed.")
    if target.kind == "file" and not target.value:
        return QCoreApplication.translate(
            "M-GRAFT-02", "The file for this replacement is missing: {path}."
        ).format(path="")
    return None


# --- Files ----------------------------------------------------------------------------------------


def encode(profile: Profile) -> bytes:
    """Return the file's bytes: UTF-8, two-space indented, a newline at the end (plan 9.3)."""
    return msgspec.json.format(msgspec.json.encode(profile), indent=2) + b"\n"


def decode(data: bytes) -> Profile:
    """Parse and validate a profile; raises `msgspec.DecodeError` or `msgspec.ValidationError`."""
    profile = msgspec.json.decode(data, type=Profile)
    if profile.format != FORMAT or profile.version != VERSION:
        msg = f"not a {FORMAT} v{VERSION} file"
        raise msgspec.ValidationError(msg)
    if len(profile.replacements) > MAX_REPLACEMENTS:
        msg = f"more than {MAX_REPLACEMENTS} replacements"
        raise msgspec.ValidationError(msg)
    return profile


def read_profile(path: Path, now: Callable[[], datetime] | None = None) -> Profile:
    """Read a profile, falling back to its `.bak`; if both fail, move the file aside (rule 4).

    Raises:
        ProfileUnreadableError: Neither the file nor its `.bak` could be read.
    """
    for candidate in (path, atomic.backup_path(path)):
        try:
            return decode(atomic.read_bytes(candidate))
        except (OSError, msgspec.DecodeError, msgspec.ValidationError) as error:
            log.debug("Couldn't read the profile %s: %s", candidate.name, error)
    stamp = (now or (lambda: datetime.now(UTC)))().strftime("%Y%m%d-%H%M%S")
    moved = atomic.move_aside(path, f"broken-{stamp}")
    raise ProfileUnreadableError(path, moved)


def write_profile(path: Path, profile: Profile) -> None:
    """Write a profile atomically, keeping the previous version as `.bak`."""
    if len(profile.replacements) > MAX_REPLACEMENTS:
        raise ProfileError(
            QCoreApplication.translate(
                "M-PROF-05", "A profile can hold at most {n} replacements."
            ).format(n=f"{MAX_REPLACEMENTS:,}")
        )
    atomic.write_atomic(path, encode(profile), keep_backup=True)


# --- Snapshot (spec S-21, S-23) ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Compiled:
    """A snapshot, and the replacements left out of it with their reasons."""

    snapshot: rules.GraftSnapshot
    left_out: tuple[tuple[str, str], ...]


def compile_snapshot(profiles: Sequence[Profile]) -> Compiled:
    """Compile the enabled replacements of the enabled profiles, `profiles` highest first."""
    grafts: dict[rules.Original, rules.Graft] = {}
    overridden: dict[rules.Original, list[rules.Graft]] = {}
    left_out: list[tuple[str, str]] = []
    # Lowest profile first, each replacement in order: whatever comes later wins (rule 1).
    for profile in reversed(profiles):
        if not profile.enabled:
            continue
        for replacement in profile.replacements:
            if not replacement.enabled:
                continue
            problem = replacement_problem(replacement)
            if problem is not None:
                left_out.append((replacement.id, problem))
                continue
            key = (replacement.original.asset_id, replacement.original.slot)
            graft = rules.Graft(
                original=replacement.original.asset_id,
                slot=replacement.original.slot,
                kind=replacement.target.kind,
                value=replacement.target.value,
                profile=profile.name,
                replacement=replacement.id,
            )
            if key in grafts:
                overridden.setdefault(key, []).insert(0, grafts[key])
            grafts[key] = graft
    snapshot = rules.GraftSnapshot(
        MappingProxyType(grafts),
        MappingProxyType({key: tuple(value) for key, value in overridden.items()}),
    )
    return Compiled(snapshot, tuple(left_out))


# --- The store (S-20) ---------------------------------------------------------------------------


@dataclass(slots=True)
class _State:
    profiles: list[Profile]


class ProfileStore:
    """The profiles in `folder`, in order, with undo and redo of the last 50 edits.

    Every edit is saved at once. `order` holds the profile IDs, highest first, as the setting
    `replacements.profile_order` keeps them; `on_order` is told when it changes.
    """

    def __init__(
        self,
        folder: Path,
        order: Iterable[str] = (),
        *,
        on_order: Callable[[list[str]], None] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.folder = folder
        self.on_order = on_order
        self.now = now or (lambda: datetime.now(UTC))
        self.unreadable: list[ProfileUnreadableError] = []
        self._undo: list[_State] = []
        self._redo: list[_State] = []
        self.profiles = self._load(list(order))

    # Reading

    def _load(self, order: list[str]) -> list[Profile]:
        loaded: list[Profile] = []
        if self.folder.is_dir():
            for path in sorted(self.folder.glob("*.json")):
                try:
                    loaded.append(read_profile(path, self.now))
                except ProfileUnreadableError as error:
                    self.unreadable.append(error)
                    log.error(
                        "%s",
                        QCoreApplication.translate(
                            "M-PROF-06",
                            "The profile file {file} couldn't be read, so Verdra set it aside "
                            "as {moved}.",
                        ).format(file=path.name, moved=error.moved.name),
                    )
        rank = {profile_id: index for index, profile_id in enumerate(order)}
        return sorted(loaded, key=lambda p: (rank.get(p.id, len(rank)), p.name.casefold()))

    def get(self, profile_id: str) -> Profile:
        """Return a copy of the profile with this ID (edits go through the store)."""
        return copy.deepcopy(_find(self.profiles, profile_id))

    def compile(self) -> Compiled:
        """Compile the current profiles into a snapshot (S-21)."""
        return compile_snapshot(self.profiles)

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    # Editing

    def create(self, name: str) -> Profile:
        """Add an empty, enabled profile at the top of the list."""
        self._check_name(name)
        stamp = self.now()
        profile = Profile(id=str(uuid.uuid4()), name=name, created=stamp, modified=stamp)
        self._edit(lambda profiles: profiles.insert(0, copy.deepcopy(profile)))
        return profile

    def rename(self, profile_id: str, name: str) -> None:
        """Rename a profile (its file and its folder move with it)."""
        self._check_name(name, ignore=profile_id)

        def change(profiles: list[Profile]) -> None:
            profile = _find(profiles, profile_id)
            profile.name = name

        self._edit(change)

    def duplicate(self, profile_id: str, name: str) -> Profile:
        """Copy a profile under a new name, just below it, disabled."""
        self._check_name(name)
        copied = copy.deepcopy(self.get(profile_id))
        stamp = self.now()
        copied.id, copied.name, copied.enabled = str(uuid.uuid4()), name, False
        copied.created = copied.modified = stamp
        for replacement in copied.replacements:
            replacement.id = str(uuid.uuid4())

        def change(profiles: list[Profile]) -> None:
            index = profiles.index(_find(profiles, profile_id))
            profiles.insert(index + 1, copy.deepcopy(copied))

        self._edit(change)
        return copied

    def delete(self, profile_id: str) -> None:
        """Delete a profile (after M-PROF-02 in the interface)."""
        self._edit(lambda profiles: profiles.remove(_find(profiles, profile_id)))

    def set_enabled(self, profile_id: str, enabled: bool) -> None:  # noqa: FBT001
        """Turn a profile on or off."""

        def change(profiles: list[Profile]) -> None:
            _find(profiles, profile_id).enabled = enabled

        self._edit(change)

    def reorder(self, profile_ids: Sequence[str]) -> None:
        """Put the profiles in this order, highest first."""
        if sorted(profile_ids) != sorted(p.id for p in self.profiles):
            msg = "the new order must name every profile once"
            raise ValueError(msg)

        def change(profiles: list[Profile]) -> None:
            by_id = {p.id: p for p in profiles}
            profiles[:] = [by_id[profile_id] for profile_id in profile_ids]

        self._edit(change)

    def add_replacement(
        self,
        profile_id: str,
        original: Original,
        target: Target,
        asset_type: str = "",
        note: str = "",
    ) -> Replacement:
        """Add a replacement at the end of a profile (so it wins within the profile)."""
        replacement = Replacement(
            id=str(uuid.uuid4()),
            original=original,
            target=target,
            asset_type=asset_type,
            note=note,
        )

        def change(profiles: list[Profile]) -> None:
            profile = _find(profiles, profile_id)
            if len(profile.replacements) >= MAX_REPLACEMENTS:
                raise ProfileError(
                    QCoreApplication.translate(
                        "M-PROF-05", "A profile can hold at most {n} replacements."
                    ).format(n=f"{MAX_REPLACEMENTS:,}")
                )
            profile.replacements.append(copy.deepcopy(replacement))

        self._edit(change)
        return replacement

    def edit_replacement(self, profile_id: str, replacement: Replacement) -> None:
        """Replace the replacement with the same ID."""

        def change(profiles: list[Profile]) -> None:
            items = _find(profiles, profile_id).replacements
            index = next(i for i, r in enumerate(items) if r.id == replacement.id)
            items[index] = copy.deepcopy(replacement)

        self._edit(change)

    def remove_replacement(self, profile_id: str, replacement_id: str) -> None:
        """Remove one replacement from a profile."""

        def change(profiles: list[Profile]) -> None:
            items = _find(profiles, profile_id).replacements
            items[:] = [r for r in items if r.id != replacement_id]

        self._edit(change)

    def undo(self) -> None:
        """Undo the last edit."""
        if self._undo:
            self._redo.append(_State(copy.deepcopy(self.profiles)))
            self._restore(self._undo.pop())

    def redo(self) -> None:
        """Redo the last undone edit."""
        if self._redo:
            self._undo.append(_State(copy.deepcopy(self.profiles)))
            self._restore(self._redo.pop())

    # Internals

    def _check_name(self, name: str, ignore: str | None = None) -> None:
        problem = name_problem(name)
        if problem is None and any(
            p.name.casefold() == name.casefold() and p.id != ignore for p in self.profiles
        ):
            problem = QCoreApplication.translate(
                "M-PROF-01", "A profile named {name} already exists."
            ).format(name=name)
        if problem is not None:
            raise ProfileError(problem)

    def _edit(self, change: Callable[[list[Profile]], None]) -> None:
        before = copy.deepcopy(self.profiles)
        after = copy.deepcopy(self.profiles)
        change(after)
        stamp = self.now()
        old = {p.id: p for p in before}
        for profile in after:
            if profile.id in old and encode(profile) != encode(old[profile.id]):
                profile.modified = stamp
        self._apply(before, after)
        self._undo.append(_State(before))
        del self._undo[:-UNDO_LIMIT]
        self._redo.clear()

    def _restore(self, state: _State) -> None:
        self._apply(self.profiles, state.profiles)

    def _apply(self, before: list[Profile], after: list[Profile]) -> None:
        """Write what changed between `before` and `after`, then make `after` current."""
        self.folder.mkdir(parents=True, exist_ok=True)
        old = {p.id: p for p in before}
        new = {p.id: p for p in after}
        for profile_id, profile in old.items():
            if profile_id not in new or new[profile_id].name != profile.name:
                self._remove_file(profile)
        for profile_id, profile in new.items():
            previous = old.get(profile_id)
            if previous is not None and previous.name != profile.name:
                self._move_folder(previous.name, profile.name)
            if previous is None or encode(previous) != encode(profile):
                write_profile(self.path(profile), profile)
        self.profiles = after
        if [p.id for p in before] != [p.id for p in after] and self.on_order is not None:
            self.on_order([p.id for p in after])

    def path(self, profile: Profile) -> Path:
        """Return the file a profile lives in."""
        return self.folder / f"{profile.name}.json"

    def _remove_file(self, profile: Profile) -> None:
        for path in (self.path(profile), atomic.backup_path(self.path(profile))):
            path.unlink(missing_ok=True)

    def _move_folder(self, old: str, new: str) -> None:
        source = self.folder / old
        if source.is_dir() and not (self.folder / new).exists():
            source.rename(self.folder / new)


def _find(profiles: list[Profile], profile_id: str) -> Profile:
    for profile in profiles:
        if profile.id == profile_id:
            return profile
    raise KeyError(profile_id)
