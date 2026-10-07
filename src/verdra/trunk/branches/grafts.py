# SPDX-FileCopyrightText: 2026 q0f7
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
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Any, Final
from urllib.parse import urlsplit

import msgspec
from msgspec import Meta, Struct, field
from PySide6.QtCore import QCoreApplication, QObject, Signal

import verdra
from verdra.bark import pollinator, rain
from verdra.roots import rules
from verdra.soil import atomic, terrain
from verdra.strata import clay, ochre

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
#: For the interface, which can't import `roots`.
TargetKind = rules.TargetKind
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
    """Return why `name` can't be a profile name on Windows, or None if it can."""
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
    if target.kind == "url" and (problem := url_problem(target.value)) is not None:
        return problem
    if target.kind == "file" and not target.value:
        return QCoreApplication.translate(
            "M-GRAFT-02", "The file for this replacement is missing: {path}."
        ).format(path="")
    return None


# --- Target files and links (spec S-22) ----------------------------------------------------------

#: The formats a Local file target can have, and the asset family each one replaces.
FAMILIES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "png": "Image",
        "jpeg": "Image",
        "ktx2": "Image",
        "dds": "Image",
        "mesh": "Mesh",
        "obj": "Mesh",
        "ogg": "Audio",
        "mp3": "Audio",
    }
)
#: Plan 10.7 limits by family, checked on the file size before anything reads it. Images are
#: limited by pixels (strata/ochre); 64 MB bounds the file itself.
SIZE_LIMITS: Final[Mapping[str, int]] = MappingProxyType(
    {
        "Image": 64 * 1024 * 1024,
        "Mesh": 64 * 1024 * 1024,
        "Audio": 50 * 1024 * 1024,
    }
)
#: Every target kind, and the ones the grafter serves today: the others stay out of the
#: snapshot (`compile_snapshot`) until it serves content (S-21 deviation, docs/m2/notes.md).
ALL_KINDS: Final = frozenset({"asset_id", "file", "url", "remove"})
SERVED: Final = frozenset({"asset_id", "file", "url", "remove"})
_HEAD = 64
_MAGIC: Final = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xabKTX 20\xbb\r\n\x1a\n", "ktx2"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"DDS ", "dds"),
    (b"OggS", "ogg"),
    (b"ID3", "mp3"),
)
_MESH = re.compile(rb"version [1-9]\.\d\d")
_OBJ_LINE = re.compile(rb"\s*(#|v |vt |vn |f |o |g |s |mtllib |usemtl |$)")


def sniff(head: bytes, name: str = "") -> str | None:
    """Return the format of a file from its first bytes (and, for OBJ, its name), or None.

    Formats are told apart by content, never by name alone; OBJ has no signature, so it needs
    both the `.obj` suffix and a first line that is OBJ.
    """
    for magic, kind in _MAGIC:
        if head.startswith(magic):
            return kind
    if _MESH.match(head):
        return "mesh"
    if _is_mp3_frame(head):
        return "mp3"
    if name.lower().endswith(".obj") and b"\0" not in head:
        first = head.split(b"\n", 1)[0]
        if _OBJ_LINE.match(first):
            return "obj"
    return None


def _is_mp3_frame(head: bytes) -> bool:
    """Return whether `head` starts with an MPEG audio frame header (no ID3 tag)."""
    if len(head) < 4 or head[0] != 0xFF or head[1] & 0xE0 != 0xE0:
        return False
    version, layer = (head[1] >> 3) & 3, (head[1] >> 1) & 3
    bitrate, rate = head[2] >> 4, (head[2] >> 2) & 3
    return version != 1 and layer != 0 and bitrate not in {0, 15} and rate != 3


def resolve(value: str, folder: Path) -> Path:
    """Return the file a Local file target names: `./` paths are inside the profile's folder."""
    if value.startswith("./"):
        return folder / value[2:]
    return Path(value)


def stored_path(path: Path, folder: Path) -> str:
    """Return how a Local file is stored: `./…` inside the profile's folder, else absolute."""
    path = path.absolute()
    try:
        inside = path.relative_to(folder.absolute())
    except ValueError:
        return str(path)
    return f"./{inside.as_posix()}"


def file_family(path: Path) -> tuple[str | None, str | None]:
    """Check a Local file target: return (its family, None), or (None, the reason it can't be used).

    Reads only the first bytes, so it is quick enough for live validation.
    """
    try:
        size = path.stat().st_size
        with path.open("rb") as file:
            head = file.read(_HEAD)
    except OSError:
        return None, QCoreApplication.translate(
            "M-GRAFT-02", "The file for this replacement is missing: {path}."
        ).format(path=path)
    kind = sniff(head, path.name)
    if kind is None:
        return None, QCoreApplication.translate(
            "M-EDIT-08",
            "This file type isn't supported. Use PNG, JPEG, KTX2, OBJ, MESH, OGG or MP3.",
        )
    family = FAMILIES[kind]
    if size > SIZE_LIMITS[family]:
        return None, QCoreApplication.translate(
            "M-EDIT-09", "This file is too big. The limit is {size} MB."
        ).format(size=SIZE_LIMITS[family] // (1024 * 1024))
    return family, None


def url_problem(value: str) -> str | None:
    """Return M-EDIT-03 unless `value` is an HTTPS link with a host, else None."""
    parts = urlsplit(value)
    if parts.scheme.lower() != "https" or not parts.hostname:
        return QCoreApplication.translate("M-EDIT-03", "Only HTTPS links are allowed.")
    return None


# --- The asset type check (spec S-22; S-21 rule 3) -------------------------------------------


def type_name(asset_type: str) -> str:
    """The noun an asset type is called in messages ("picture", "mesh", "decal"…)."""
    names = {name.lower(): name for name in pollinator.NAMES.values()}
    by_family = {"image": "picture", "mesh": "mesh", "audio": "sound"}
    key = asset_type.strip().lower()
    return by_family.get(key) or names.get(key) or "different kind of item"


def original_type(kind: pollinator.AssetKind) -> str:
    """What is saved as a replacement's asset type once Roblox has said what the original is."""
    return kind.family or pollinator.NAMES.get(kind.type_id, "other").capitalize()


def type_problem(original: str, target: str) -> str | None:
    """M-EDIT-02 when a `target` type can't stand in for an `original` type, else None.

    Both are asset types as saved ("Image", "Mesh", "Audio", "Decal"…), "" when unknown; an
    unknown one is never refused here (the CDN's answer is checked again when served, M-GRAFT-12).
    """
    if not original or not target or original.lower() == target.lower():
        return None
    return QCoreApplication.translate("M-EDIT-02", "A {target} can't replace a {original}.").format(
        target=type_name(target), original=type_name(original)
    )


def target_problem(kind: str, value: str, folder: Path) -> str | None:
    """Return why a Local file, URL or Remove target can't be saved, or None (S-22 rule 1)."""
    if kind == "file":
        if not value:
            return QCoreApplication.translate("M-EDIT-12", "Choose a file to use instead.")
        return file_family(resolve(value, folder))[1]
    if kind == "url":
        return url_problem(value)
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


#: Remove (S-21): a fully transparent picture, served in whichever format the CDN answers with.
_CLEAR: Final = ochre.Pixels(1, 1, b"\0\0\0\0")

#: For a link: its downloaded bytes, or why there are none yet (still downloading, or failed).
Fetched = Callable[[str], bytes | str]


def _soon() -> str:
    return QCoreApplication.translate(
        "M-SOON-01", "This part of Verdra isn't built yet. It will arrive in a later version."
    )


def prepare_content(
    graft: rules.Graft, folder: Path, fetched: Fetched | None = None
) -> rules.Content | str:
    """Read and convert a content replacement's target ahead of time; or say why it can't be used.

    S-21 rule 2: the proxy only picks prepared bytes. A Local file or a link's image is decoded
    once (strata/ochre, plan 10.7 limits) and written as PNG and as KTX2, the formats the CDN
    sends images in; Remove is a transparent picture in both. Meshes and sounds follow with their
    own steps (M-SOON-01 until then). A link's bytes come from `fetched` (bark/rain's cache).
    """
    if graft.slot is not None:
        return _soon()
    prepared = _prepare(graft, folder, fetched)
    if isinstance(prepared, rules.Content) and graft.kind != "remove":
        served = "Mesh" if prepared.mesh else "Image"
        problem = type_problem(graft.asset_type, served)
        if problem is not None:  # S-21 rule 3: an unsupported combination is never sent
            return problem
    return prepared


def _prepare(graft: rules.Graft, folder: Path, fetched: Fetched | None) -> rules.Content | str:
    if graft.kind == "remove":
        return rules.Content(
            ochre.to_png(_CLEAR),
            ochre.write_ktx2(_CLEAR),
            "remove",
            clay.write_filemesh(clay.Mesh((), ())),  # an empty mesh: nothing drawn
        )
    if graft.kind == "url":
        data = fetched(graft.value) if fetched is not None else _soon()
        if isinstance(data, str):
            return data
        return _picture(data, "url", graft.value)
    if graft.kind != "file":
        return _soon()
    return _file_content(resolve(graft.value, folder))


def _file_content(path: Path) -> rules.Content | str:
    family, problem = file_family(path)
    if problem is not None:
        return problem
    if family not in {"Image", "Mesh"}:
        return _soon()
    try:
        data = atomic.read_bytes(path)
    except OSError:
        return QCoreApplication.translate(
            "M-GRAFT-02", "The file for this replacement is missing: {path}."
        ).format(path=path)
    return _picture(data, "file", str(path))


def _picture(data: bytes, source: str, where: str) -> rules.Content | str:
    """Decode a picture or mesh once and write what the CDN serves, or say why it can't be used.

    A picture becomes PNG and KTX2; a FileMesh (any version clay reads) or an OBJ becomes a
    FileMesh 2.00 (strata/clay, plan 10.7 limits). Sounds follow later (M-SOON-01).
    """
    kind = sniff(data[:_HEAD], where)
    if kind is None:
        return QCoreApplication.translate(
            "M-EDIT-08",
            "This file type isn't supported. Use PNG, JPEG, KTX2, OBJ, MESH, OGG or MP3.",
        )
    if FAMILIES[kind] == "Mesh":
        return _mesh(data, kind, source)
    if FAMILIES[kind] != "Image":
        return _soon()
    try:
        pixels = ochre.read_image(data)
    except ochre.OchreError as error:
        return QCoreApplication.translate(
            "M-GRAFT-06", "This file couldn't be used: {reason}."
        ).format(reason=error)
    return rules.Content(ochre.to_png(pixels), ochre.write_ktx2(pixels), source)


def _mesh(data: bytes, kind: str, source: str) -> rules.Content | str:
    try:
        mesh = clay.read_obj(data) if kind == "obj" else clay.read_mesh(data)
        return rules.Content(b"", b"", source, clay.write_filemesh(mesh))
    except clay.ClayError as error:
        return QCoreApplication.translate(
            "M-GRAFT-06", "This file couldn't be used: {reason}."
        ).format(reason=error)


def compile_snapshot(
    profiles: Sequence[Profile],
    served: frozenset[str] = SERVED,
    folder: Path | None = None,
    fetched: Fetched | None = None,
) -> Compiled:
    """Compile the enabled replacements of the enabled profiles, `profiles` highest first.

    Replacements whose target kind isn't in `served` are left out with M-SOON-01. With `folder`
    (the profiles' folder), content replacements are prepared (`prepare_content`); one that
    can't be is left out with its reason.
    """
    grafts: dict[rules.Original, rules.Graft] = {}
    content: dict[int, rules.Content] = {}
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
            if problem is None and replacement.target.kind not in served:
                # Until the grafter serves content, these stay out of the snapshot, so routing
                # decrypts no more than it does for Asset ID swaps.
                problem = QCoreApplication.translate(
                    "M-SOON-01",
                    "This part of Verdra isn't built yet. It will arrive in a later version.",
                )
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
                asset_type=replacement.asset_type,
            )
            if graft.kind != "asset_id" and folder is not None:
                prepared = prepare_content(graft, folder / profile.name, fetched)
                if isinstance(prepared, str):
                    left_out.append((replacement.id, prepared))
                    continue
                content[graft.original] = prepared
            elif graft.original in content and graft.slot is None:
                del content[graft.original]  # a later Asset ID replacement wins
            if key in grafts:
                overridden.setdefault(key, []).insert(0, grafts[key])
            grafts[key] = graft
    snapshot = rules.GraftSnapshot(
        MappingProxyType(grafts),
        MappingProxyType({key: tuple(value) for key, value in overridden.items()}),
        MappingProxyType(content),
    )
    return Compiled(snapshot, tuple(left_out))


# --- Preview changes (spec S-23) -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PreviewRow:
    """One original that will change: the winner, and what it overrides."""

    winner: rules.Graft
    overridden: tuple[rules.Graft, ...]


@dataclass(frozen=True, slots=True)
class Preview:
    """What Apply now would change, grouped by asset type (S-23)."""

    groups: dict[str, tuple[PreviewRow, ...]]
    changes: int
    conflicts: int


def preview(snapshot: rules.GraftSnapshot) -> Preview:
    """Describe a snapshot for Preview changes: the same snapshot the proxy uses (rule 1).

    A conflict is an original (asset ID and slot) named by more than one enabled replacement;
    the count is of such originals, not of the replacements they override (rule 2).
    """
    groups: dict[str, list[PreviewRow]] = {}
    for key in sorted(snapshot.grafts, key=lambda k: (k[0], k[1] or "")):
        winner = snapshot.grafts[key]
        row = PreviewRow(winner, tuple(snapshot.overridden.get(key, ())))
        groups.setdefault(winner.asset_type or "", []).append(row)
    return Preview(
        {kind: tuple(rows) for kind, rows in sorted(groups.items())},
        changes=len(snapshot.grafts),
        conflicts=sum(1 for key in snapshot.grafts if snapshot.overridden.get(key)),
    )


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

    def compile(self, fetched: Fetched | None = None) -> Compiled:
        """Compile the current profiles into a snapshot (S-21), content prepared."""
        return compile_snapshot(self.profiles, folder=self.folder, fetched=fetched)

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

    def restore_profile(self, profile: Profile, index: int) -> None:
        """Put a deleted profile back where it was, as it was (its "Undo"; an edit itself).

        Raises:
            ProfileError: a profile with its name was made since (M-PROF-01).
        """
        self._check_name(profile.name, ignore=profile.id)
        if any(p.id == profile.id for p in self.profiles):
            return  # already back (Undo was used first)

        def change(profiles: list[Profile]) -> None:
            profiles.insert(min(max(index, 0), len(profiles)), copy.deepcopy(profile))

        self._edit(change)

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


def _user_agent() -> str:
    return f"Verdra/{verdra.__version__}"


def _find(profiles: list[Profile], profile_id: str) -> Profile:
    for profile in profiles:
        if profile.id == profile_id:
            return profile
    raise KeyError(profile_id)


# --- The service the interface talks to ----------------------------------------------------------


class Grafts(QObject):
    """Replacement profiles for the interface, and the snapshot the proxy reads (S-20, S-21).

    Every edit is saved at once; `publish` compiles the profiles and swaps the snapshot in, which
    the proxy uses from its next connection (Apply now, S-24).

    A link (URL target) is downloaded on a worker the first time it is published (bark/rain:
    HTTPS only, size limit, cached by SHA-256); until then it is left out with M-GRAFT-09, and
    once it is downloaded the snapshot is published again, so it applies from the next
    connection without another Apply now. A failed download is left out with its reason
    (M-GRAFT-10) and tried again at the next Apply now (S-21).

    Signals:
        changed(): The profiles changed (an edit, undo or redo), or a link finished downloading.
    """

    changed = Signal()

    def __init__(
        self,
        folder: Path,
        settings: Any,
        holder: rules.SnapshotHolder | None = None,
        parent: QObject | None = None,
        *,
        pool: Any = None,
        downloads: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        #: Runs link downloads (trunk/tendrils); without one they run inline (tests).
        self.pool = pool
        self.downloads = downloads if downloads is not None else folder.parent / "Downloads"
        #: Link -> why it has no content yet ("" while it downloads).
        self._links: dict[str, str] = {}
        self.holder = holder or rules.SnapshotHolder()
        self.store = ProfileStore(
            folder,
            settings.value("replacements.profile_order"),
            on_order=lambda order: settings.set("replacements.profile_order", order),
        )
        #: Replacement ID -> why it was left out of the last published snapshot.
        self.warnings: dict[str, str] = {}

    @property
    def profiles(self) -> list[Profile]:
        """The profiles, highest first (read only: edit through the methods)."""
        return self.store.profiles

    def lookup(self, asset_id: int, done: Callable[[str | None, str], None]) -> None:
        """Ask Roblox what asset `asset_id` is (S-22), on a worker; answer on the Qt thread.

        `done(asset_type, problem)`: the asset type to save ("Image", "Decal"…) and "", or None
        and M-EDIT-01 when there is no such asset, or "" and M-EDIT-05 when Roblox can't be
        reached (the replacement can still be saved).
        """

        def answer(kind: pollinator.AssetKind | None) -> None:
            if kind is None:
                done(
                    None,
                    QCoreApplication.translate(
                        "M-EDIT-01", "No asset with ID {id} was found."
                    ).format(id=asset_id),
                )
            else:
                done(original_type(kind), "")

        def unreachable(_reason: str = "") -> None:
            done(
                "",
                QCoreApplication.translate(
                    "M-EDIT-05",
                    "Roblox couldn't be reached to check this ID. You can save it anyway.",
                ),
            )

        if self.pool is None:
            try:
                answer(pollinator.asset_kind(asset_id))
            except pollinator.PollinatorError:
                unreachable()
            return
        job = self.pool.submit(
            QCoreApplication.translate("M-EDIT-13", "Checking an asset ID"),
            lambda _handle: pollinator.asset_kind(asset_id),
        )
        job.succeeded.connect(answer)
        job.failed.connect(unreachable)

    def preview(self) -> Preview:
        """Preview changes (S-23): what the next Apply now publishes (no download starts)."""
        return preview(self.store.compile(self._cached_link).snapshot)

    def publish(self) -> int:
        """Compile and publish the snapshot; return how many originals it replaces.

        Apply now tries a link whose download failed again.
        """
        for link in [link for link, reason in self._links.items() if reason]:
            del self._links[link]
        return self._publish()

    def _publish(self) -> int:
        compiled = self.store.compile(self._link)
        self.holder.publish(compiled.snapshot)
        self.warnings = dict(compiled.left_out)
        return len(compiled.snapshot.grafts)

    def _cached_link(self, url: str) -> bytes | str:
        data = rain.cached(url, self.downloads)
        return data if data is not None else self._downloading()

    def _link(self, url: str) -> bytes | str:
        """A link's content for the snapshot: cached, failed, or downloading (started here)."""
        data = rain.cached(url, self.downloads)
        if data is not None:
            return data
        if url in self._links:
            reason = self._links[url]
            return self._failed(url, reason) if reason else self._downloading()
        self._links[url] = ""
        if self.pool is None:
            try:
                return rain.fetch(url, self.downloads, user_agent=_user_agent())
            except rain.RainError as error:
                self._links[url] = str(error)
                return self._failed(url, str(error))
        job = self.pool.submit(
            QCoreApplication.translate("M-GRAFT-09", "Downloading a replacement"),
            lambda _handle: rain.fetch(url, self.downloads, user_agent=_user_agent()),
        )
        job.succeeded.connect(lambda _data: self._downloaded(url))
        job.failed.connect(lambda reason: self._download_failed(url, reason))
        return self._downloading()

    def _downloaded(self, url: str) -> None:
        self._links.pop(url, None)
        log.info(
            "%s",
            QCoreApplication.translate(
                "M-GRAFT-11", "Downloaded the replacement from {host}. It applies from now on."
            ).format(host=urlsplit(url).hostname),
        )
        self._publish()
        self.changed.emit()

    def _download_failed(self, url: str, reason: str) -> None:
        self._links[url] = reason or "?"
        log.warning("%s", self._failed(url, self._links[url]))
        self._publish()  # the table shows why; the next Apply now tries again
        self.changed.emit()

    @staticmethod
    def _downloading() -> str:
        return QCoreApplication.translate(
            "M-GRAFT-09", "Downloading this replacement. It applies as soon as it's ready."
        )

    @staticmethod
    def _failed(url: str, reason: str) -> str:
        return QCoreApplication.translate(
            "M-GRAFT-10", "The replacement from {host} couldn't be downloaded: {reason}."
        ).format(host=urlsplit(url).hostname, reason=reason)

    def edit(self, method: str, *args: Any) -> Any:
        """Run one `ProfileStore` edit (`create`, `add_replacement`, `undo`…) and say so."""
        result = getattr(self.store, method)(*args)
        self.changed.emit()
        return result
