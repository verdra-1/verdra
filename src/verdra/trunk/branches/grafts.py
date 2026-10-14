# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Replacement profiles: store, validation, conflicts, snapshot compile, undo and redo.

Spec S-20. Each profile is one `verdra.profile` file, `profiles/<name>.json` (plan 9.2, 9.3),
written atomically with `.bak` (plan 9.7). Version 2 (spec S-26) keeps, per replacement, the
version last applied next to the saved one, and per profile its applied switch; a version 1 file
is migrated when it is loaded (applied = saved, the old file kept as `<name>.json.v1`), and a
file from a newer Verdra is left untouched and unused. `ProfileStore` keeps the profiles in
their order (the setting `replacements.profile_order`), records every edit for undo and redo,
and compiles the enabled replacements into the `roots.rules.GraftSnapshot` the proxy reads (spec
S-21): a profile higher in the list wins for the same original, and within one profile the later
replacement wins (rule 1).
"""

from __future__ import annotations

import copy
import hashlib
import logging
import re
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PureWindowsPath
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
VERSION = 2
#: Spec S-26 rule 7: all copies of applied files together.
MAX_APPLIED_BYTES = 2 * 1024**3
#: Spec S-26: the room phases B and C have inside a replacement, as its JSON.
MAX_VIEW_BYTES = 4096
#: The suffix the version 1 file is kept under after migrating (plan 9.7).
V1_SUFFIX = ".v1"
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


class Applied(Struct, kw_only=True):
    """The version of a replacement the game gets now (spec S-26), set by applying it."""

    original: Original
    target: Target
    enabled: bool = True
    asset_type: str = ""
    #: The SHA-256 of a file target's bytes, whose copy is in the Applied folder (rule 4).
    sha256: str | None = None
    at: UtcTimestamp


class Replacement(Struct, kw_only=True):
    """One replacement in a profile: its saved version, and the applied one (or None)."""

    id: str
    enabled: bool = True
    original: Original
    target: Target
    asset_type: str = ""
    note: str = ""
    #: The original's asset name, for display only (S-26).
    name: str = ""
    #: Deleted after it was applied: it stays until the deletion is applied (S-25, question N1).
    deleted: bool = False
    applied: Applied | None = None
    #: Reserved for Editor 2.0 phases B and C; kept as it is (S-26).
    view: dict[str, Any] = field(default_factory=dict[str, Any])


class Profile(Struct, kw_only=True):
    """A `verdra.profile` v2 file."""

    format: str = FORMAT
    version: int = VERSION
    id: str
    name: str
    enabled: bool = True
    #: The switch as last applied, or None if the profile was never applied (S-26 rule 3).
    applied_enabled: bool | None = None
    created: UtcTimestamp
    modified: UtcTimestamp
    replacements: list[Replacement] = field(default_factory=list)


class ProfileError(ValueError):
    """A profile can't be saved as it is; the message is the sentence the user sees."""


class ProfileNewerError(RuntimeError):
    """A profile file comes from a newer Verdra: it is left untouched and not used (S-20 rule 4)."""

    def __init__(self, path: Path, version: int) -> None:
        super().__init__(f"{path} is a {FORMAT} v{version} file; this Verdra reads v{VERSION}")
        self.path = path
        self.version = version


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


class _Header(Struct):
    """The two fields every version has, read before the rest."""

    format: str = ""
    version: int = 0


def file_version(data: bytes) -> int:
    """Return the `verdra.profile` version of a file; raises `msgspec.DecodeError` and
    `msgspec.ValidationError` for anything that isn't a profile."""
    header = msgspec.json.decode(data, type=_Header)
    if header.format != FORMAT or header.version < 1:
        msg = f"not a {FORMAT} file"
        raise msgspec.ValidationError(msg)
    return header.version


def encode_v1(profile: Profile) -> bytes:
    """A version 1 profile's bytes, as a version 1 Verdra writes them (the `.v1` copy kept when
    migrating, readable by that Verdra again)."""
    fields = ("id", "enabled", "original", "target", "asset_type", "note")
    data = {
        "format": FORMAT,
        "version": 1,
        "id": profile.id,
        "name": profile.name,
        "enabled": profile.enabled,
        "created": profile.created,
        "modified": profile.modified,
        "replacements": [
            {key: getattr(replacement, key) for key in fields}
            for replacement in profile.replacements
        ],
    }
    return msgspec.json.format(msgspec.json.encode(data), indent=2) + b"\n"


def decode(data: bytes) -> Profile:
    """Parse and validate a profile of this version or version 1 (read as version 2, nothing
    applied yet: `migrate` sets that); raises `msgspec.DecodeError` or
    `msgspec.ValidationError`."""
    version = file_version(data)
    if version > VERSION:
        msg = f"a {FORMAT} v{version} file"
        raise msgspec.ValidationError(msg)
    profile = msgspec.json.decode(data, type=Profile)
    profile.version = VERSION
    if len(profile.replacements) > MAX_REPLACEMENTS:
        msg = f"more than {MAX_REPLACEMENTS} replacements"
        raise msgspec.ValidationError(msg)
    for replacement in profile.replacements:
        if len(msgspec.json.encode(replacement.view)) > MAX_VIEW_BYTES:
            log.debug("A replacement's view settings were too large and were dropped.")
            replacement.view = {}
    return profile


def read_profile(path: Path, now: Callable[[], datetime] | None = None) -> Profile:
    """Read a profile, falling back to its `.bak`; if both fail, move the file aside (rule 4).

    Raises:
        ProfileNewerError: The file comes from a newer Verdra; it is left as it is.
        ProfileUnreadableError: Neither the file nor its `.bak` could be read.
    """
    return read_profile_version(path, now)[0]


def read_profile_version(
    path: Path, now: Callable[[], datetime] | None = None
) -> tuple[Profile, int]:
    """`read_profile`, and the version of the file it was read from (the file or its `.bak`).

    Raises:
        ProfileNewerError: The file comes from a newer Verdra; it is left as it is.
        ProfileUnreadableError: Neither the file nor its `.bak` could be read.
    """
    for candidate in (path, atomic.backup_path(path)):
        try:
            data = atomic.read_bytes(candidate)
            version = file_version(data)
        except (OSError, msgspec.DecodeError, msgspec.ValidationError) as error:
            log.debug("Couldn't read the profile %s: %s", candidate.name, error)
            continue
        if version > VERSION:
            raise ProfileNewerError(path, version)
        try:
            return decode(data), version
        except (msgspec.DecodeError, msgspec.ValidationError) as error:
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


# --- Applied versions (spec S-26) ---------------------------------------------------------------


class AppliedCopies:
    """Copies of the files behind applied replacements, named by their SHA-256 (S-26 rule 4).

    A copy is written once and shared by every replacement whose file has the same bytes, so the
    game keeps an applied version when the user's file changes or disappears. It keeps the
    file's suffix in lower case (`<sha256>.obj`), because an OBJ is told by its suffix (`sniff`).
    `prune` deletes the copies no applied version names any more.
    """

    def __init__(self, folder: Path, limit: int = MAX_APPLIED_BYTES) -> None:
        self.folder = folder
        self.limit = limit

    def path(self, sha256: str) -> Path | None:
        """Return the copy with this SHA-256, or None if there is none."""
        if not self.folder.is_dir():
            return None
        return next((p for p in sorted(self.folder.glob(f"{sha256}*")) if p.stem == sha256), None)

    def has(self, sha256: str) -> bool:
        """Return whether the copy with this SHA-256 exists."""
        return self.path(sha256) is not None

    def size(self) -> int:
        """Return the bytes all copies use."""
        if not self.folder.is_dir():
            return 0
        return sum(path.stat().st_size for path in self.folder.iterdir() if path.is_file())

    def keep(self, path: Path) -> str:
        """Copy a file in (unless its bytes are there already) and return its SHA-256.

        Raises:
            OSError: The file can't be read, or the copy can't be written.
            ProfileError: The copies would use more than the limit (M-EDIT-23).
        """
        data = atomic.read_bytes(path)
        sha256 = hashlib.sha256(data).hexdigest()
        if self.has(sha256):
            return sha256
        if self.size() + len(data) > self.limit:
            raise ProfileError(
                QCoreApplication.translate(
                    "M-EDIT-23",
                    "Applied copies of your files would use more than 2 GB. Delete replacements "
                    "you don't need, then apply again.",
                )
            )
        self.folder.mkdir(parents=True, exist_ok=True)
        atomic.write_atomic(self.folder / f"{sha256}{path.suffix.lower()}", data)
        return sha256

    def prune(self, named: Iterable[str]) -> int:
        """Delete every copy whose SHA-256 isn't in `named`; return how many went."""
        if not self.folder.is_dir():
            return 0
        keep = set(named)
        gone = 0
        for path in self.folder.iterdir():
            if path.is_file() and path.stem not in keep:
                path.unlink(missing_ok=True)
                gone += 1
        return gone


def applied_hashes(profiles: Iterable[Profile]) -> set[str]:
    """Return the SHA-256 of every file an applied version names (what `prune` keeps)."""
    return {
        replacement.applied.sha256
        for profile in profiles
        for replacement in profile.replacements
        if replacement.applied is not None and replacement.applied.sha256
    }


def migrate(profile: Profile, folder: Path, copies: AppliedCopies, at: datetime) -> Profile:
    """Turn a version 1 profile into version 2: everything saved counts as applied (S-26).

    Under version 1 Verdra published every saved replacement at its next start, so the game had
    exactly the saved set: each replacement's applied version is its saved one, and the
    profile's applied switch is its switch. A file target's bytes are copied into the Applied
    folder; a file that is missing gets no copy (the row then shows Problem, as it would have
    failed to prepare).
    """
    migrated = copy.deepcopy(profile)
    migrated.applied_enabled = migrated.enabled
    for replacement in migrated.replacements:
        sha256 = None
        if replacement.target.kind == "file" and replacement.target.value:
            try:
                sha256 = copies.keep(resolve(replacement.target.value, folder))
            except (OSError, ProfileError) as error:
                log.debug(  # the row shows Problem (S-25, M-ROW-14), which says it in plain words
                    "The file of a replacement of asset %d couldn't be kept: %s",
                    replacement.original.asset_id,
                    error,
                )
        replacement.applied = Applied(
            original=copy.deepcopy(replacement.original),
            target=copy.deepcopy(replacement.target),
            enabled=replacement.enabled,
            asset_type=replacement.asset_type,
            sha256=sha256,
            at=at,
        )
    return migrated


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


def _target_text(target: Target) -> str:
    """A target in plain words for the log: a file by its name, a link by its host."""
    if target.kind == "file":
        name = PureWindowsPath(target.value).name or target.value
        return QCoreApplication.translate("M-GRAFT-13", "file {name}").format(name=name)
    if target.kind == "url":
        host = urlsplit(target.value).hostname or "?"
        return QCoreApplication.translate("M-GRAFT-13", "link on {host}").format(host=host)
    if target.kind == "remove":
        return QCoreApplication.translate("M-GRAFT-13", "Remove")
    return QCoreApplication.translate("M-GRAFT-13", "asset {asset}").format(asset=target.value)


def _soon() -> str:
    return QCoreApplication.translate(
        "M-SOON-01", "This part of Verdra isn't built yet. It will arrive in a later version."
    )


def prepare_content(
    graft: rules.Graft, folder: Path, fetched: Fetched | None = None
) -> rules.Content | str:
    """Read and convert a content replacement's target ahead of time; or say why it can't be used.

    S-21 rule 2: the proxy only picks prepared bytes. A Local file or a link's image is decoded
    once (strata/ochre, plan 10.7 limits) and written as PNG and as KTX2 in the CDN's own texture
    layout (decision record 0022), the formats the CDN sends images in; Remove is a transparent
    picture in both. A mesh is written as FileMesh 7.00 (decision record 0023); sounds and other
    types follow with their own steps (M-SOON-01 until then). A link's bytes come from `fetched`
    (bark/rain's cache).
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
        packs = ochre.roblox_packs(_CLEAR)  # the smallest BC3 texture, all transparent
        return rules.Content(
            ochre.to_png(_CLEAR),
            packs[2],
            "remove",
            clay.write_filemesh7(clay.Mesh((), ())),  # an empty mesh: nothing drawn
            packs,
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
    packs = ochre.roblox_packs(pixels)
    return rules.Content(ochre.to_png(pixels), packs[2], source, ktx2_packs=packs)


def _mesh(data: bytes, kind: str, source: str) -> rules.Content | str:
    try:
        mesh = clay.read_obj(data) if kind == "obj" else clay.read_mesh(data)
        return rules.Content(b"", b"", source, clay.write_filemesh7(mesh))
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
        applied_order: Iterable[str] = (),
        on_applied_order: Callable[[list[str]], None] | None = None,
    ) -> None:
        self.folder = folder
        self.on_order = on_order
        self.on_applied_order = on_applied_order
        self.now = now or (lambda: datetime.now(UTC))
        self.unreadable: list[ProfileUnreadableError] = []
        #: Files from a newer Verdra, left untouched and not used (S-20 rule 4, M-PROF-11).
        self.newer: list[ProfileNewerError] = []
        #: Copies of the files behind applied replacements (S-26 rule 4).
        self.copies = AppliedCopies(folder.parent / terrain.APPLIED_FOLDER)
        self._undo: list[_State] = []
        self._redo: list[_State] = []
        self.profiles = self._load(list(order))
        #: The profile order as last applied (S-26 rule 3); the current order until then.
        self.applied_order = list(applied_order) or [p.id for p in self.profiles]
        #: Replacement ID -> why the last `promote` couldn't apply its saved version.
        self.skipped: dict[str, str] = {}

    # Reading

    def _load(self, order: list[str]) -> list[Profile]:
        loaded: list[Profile] = []
        if self.folder.is_dir():
            for path in sorted(self.folder.glob("*.json")):
                try:
                    loaded.append(self._read(path))
                except ProfileNewerError as error:
                    self.newer.append(error)
                    log.warning(
                        "%s",
                        QCoreApplication.translate(
                            "M-PROF-11",
                            "The profile file {file} was saved by a newer version of Verdra, so "
                            "this version leaves it as it is and doesn't use it.",
                        ).format(file=path.name),
                    )
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

    def _read(self, path: Path) -> Profile:
        """Read one profile file, migrating a version 1 file to version 2 on disk (S-26)."""
        profile, version = read_profile_version(path, self.now)
        if version == 1:
            kept = path.with_name(path.name + V1_SUFFIX)
            if not kept.exists():
                atomic.write_atomic(kept, encode_v1(profile))
            profile = migrate(profile, self.folder / profile.name, self.copies, self.now())
            write_profile(path, profile)
            log.debug("Updated the profile file %s to version %d.", path.name, VERSION)
        return profile

    def get(self, profile_id: str) -> Profile:
        """Return a copy of the profile with this ID (edits go through the store)."""
        return copy.deepcopy(_find(self.profiles, profile_id))

    def compile(self, fetched: Fetched | None = None) -> Compiled:
        """Compile the saved profiles into a snapshot (S-21), content prepared: what the next
        apply publishes (Preview changes, S-23)."""
        saved = copy.deepcopy(self.profiles)
        for profile in saved:
            profile.replacements = [r for r in profile.replacements if not r.deleted]
        return compile_snapshot(saved, folder=self.folder, fetched=fetched)

    def compile_applied(self, fetched: Fetched | None = None) -> Compiled:
        """Compile the applied versions into the snapshot the game gets (S-26 rule 1)."""
        return compile_snapshot(self.applied_profiles(), folder=self.folder, fetched=fetched)

    def applied_profiles(self) -> list[Profile]:
        """The profiles as last applied, in the applied order: each profile's applied switch,
        each replacement's applied version, a file target pointing at its applied copy (S-26).

        A profile never applied, and a replacement never applied, are left out. A file whose
        copy is missing keeps its path, so preparing it fails with the reason (Problem, S-25).
        """
        rank = {profile_id: index for index, profile_id in enumerate(self.applied_order)}
        ordered = sorted(
            self.profiles, key=lambda p: (rank.get(p.id, len(rank)), p.name.casefold())
        )
        result = []
        for profile in ordered:
            if profile.applied_enabled is None:
                continue
            view = Profile(
                id=profile.id,
                name=profile.name,
                enabled=profile.applied_enabled,
                applied_enabled=profile.applied_enabled,
                created=profile.created,
                modified=profile.modified,
            )
            for replacement in profile.replacements:
                applied = replacement.applied
                if applied is None:
                    continue
                target = copy.deepcopy(applied.target)
                kept = self.copies.path(applied.sha256) if applied.sha256 else None
                if target.kind == "file" and kept is not None:
                    target.value = str(kept)
                view.replacements.append(
                    Replacement(
                        id=replacement.id,
                        enabled=applied.enabled,
                        original=copy.deepcopy(applied.original),
                        target=target,
                        asset_type=applied.asset_type,
                    )
                )
            result.append(view)
        return result

    def promote(self) -> None:
        """Apply every saved change: saved versions become the applied ones (S-26).

        Deleted replacements go; a file target's bytes are copied into the Applied folder. A
        file that can't be read keeps its previous applied version (the game keeps what it had;
        the row shows Problem). Applying isn't an edit: undo and redo never change applied
        versions.

        Raises:
            ProfileError: The applied copies would use more than 2 GB (M-EDIT-23); nothing
                changed.
        """
        stamp = self.now()
        skipped: dict[str, str] = {}
        promoted = copy.deepcopy(self.profiles)
        for profile in promoted:
            profile.applied_enabled = profile.enabled
            kept: list[Replacement] = []
            for replacement in profile.replacements:
                if replacement.deleted:
                    continue
                sha256 = None
                if replacement.target.kind == "file" and replacement.target.value:
                    path = resolve(replacement.target.value, self.folder / profile.name)
                    try:
                        sha256 = self.copies.keep(path)
                    except OSError:
                        skipped[replacement.id] = QCoreApplication.translate(
                            "M-GRAFT-02", "The file for this replacement is missing: {path}."
                        ).format(path=path)
                        kept.append(replacement)  # its previous applied version stays
                        continue
                replacement.applied = Applied(
                    original=copy.deepcopy(replacement.original),
                    target=copy.deepcopy(replacement.target),
                    enabled=replacement.enabled,
                    asset_type=replacement.asset_type,
                    sha256=sha256,
                    at=stamp,
                )
                kept.append(replacement)
            profile.replacements = kept
        self._apply(self.profiles, promoted)
        self.skipped = skipped
        self._undo = [_State(self._keep_applied(state.profiles)) for state in self._undo]
        self._redo = [_State(self._keep_applied(state.profiles)) for state in self._redo]
        self.applied_order = [p.id for p in self.profiles]
        if self.on_applied_order is not None:
            self.on_applied_order(self.applied_order)
        self.copies.prune(applied_hashes(self.profiles))

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
        """Remove one replacement from a profile; one that was applied stays, marked deleted,
        until the deletion is applied (S-25 Deleted, S-26)."""

        def change(profiles: list[Profile]) -> None:
            items = _find(profiles, profile_id).replacements
            for replacement in items:
                if replacement.id == replacement_id and replacement.applied is not None:
                    replacement.deleted = True
            items[:] = [r for r in items if r.id != replacement_id or r.deleted]

        self._edit(change)

    def remove_replacements(self, profile_id: str, replacement_ids: Iterable[str]) -> None:
        """Remove several replacements in one edit (one undo step); applied ones stay, marked
        deleted, until the deletion is applied (S-26)."""
        gone = set(replacement_ids)

        def change(profiles: list[Profile]) -> None:
            items = _find(profiles, profile_id).replacements
            for replacement in items:
                if replacement.id in gone and replacement.applied is not None:
                    replacement.deleted = True
            items[:] = [r for r in items if r.id not in gone or r.deleted]

        self._edit(change)

    def set_replacements_enabled(
        self,
        profile_id: str,
        replacement_ids: Iterable[str],
        enabled: bool,  # noqa: FBT001 - mirrors the switch
    ) -> None:
        """Switch several replacements on or off in one edit (S-26)."""
        chosen = set(replacement_ids)

        def change(profiles: list[Profile]) -> None:
            for replacement in _find(profiles, profile_id).replacements:
                if replacement.id in chosen:
                    replacement.enabled = enabled

        self._edit(change)

    def duplicate_replacement(self, profile_id: str, replacement_id: str) -> Replacement:
        """Copy a replacement right below it, switched off, noted "Copy of <note>" (S-26, N7).

        Off, because two replacements of one original are a conflict (S-20 rule 1).
        """
        source = next(r for r in self.get(profile_id).replacements if r.id == replacement_id)
        note = (
            QCoreApplication.translate("M-EDIT-21", "Copy of {note}").format(note=source.note)
            if source.note
            else QCoreApplication.translate("M-EDIT-21", "Copy")
        )
        copied = Replacement(
            id=str(uuid.uuid4()),
            enabled=False,
            original=copy.deepcopy(source.original),
            target=copy.deepcopy(source.target),
            asset_type=source.asset_type,
            note=note,
            name=source.name,
            view=copy.deepcopy(source.view),
        )

        def change(profiles: list[Profile]) -> None:
            items = _find(profiles, profile_id).replacements
            if len(items) >= MAX_REPLACEMENTS:
                raise ProfileError(
                    QCoreApplication.translate(
                        "M-PROF-05", "A profile can hold at most {n} replacements."
                    ).format(n=f"{MAX_REPLACEMENTS:,}")
                )
            index = next(i for i, r in enumerate(items) if r.id == replacement_id)
            items.insert(index + 1, copy.deepcopy(copied))

        self._edit(change)
        return copied

    def move_replacements(
        self, profile_id: str, replacement_ids: Iterable[str], to_profile_id: str
    ) -> int:
        """Move replacements to another profile, at its end; return how many moved (S-26).

        A replacement the game has stays where it is, marked deleted, until applied; the moved
        copy is new in the other profile (N5: the game changes only when applied).
        """
        chosen = [r for r in self.get(profile_id).replacements if r.id in set(replacement_ids)]
        moved = [
            Replacement(
                id=str(uuid.uuid4()) if r.applied is not None else r.id,
                enabled=r.enabled,
                original=copy.deepcopy(r.original),
                target=copy.deepcopy(r.target),
                asset_type=r.asset_type,
                note=r.note,
                name=r.name,
                view=copy.deepcopy(r.view),
            )
            for r in chosen
            if not r.deleted
        ]

        def change(profiles: list[Profile]) -> None:
            source = _find(profiles, profile_id).replacements
            target = _find(profiles, to_profile_id).replacements
            if len(target) + len(moved) > MAX_REPLACEMENTS:
                raise ProfileError(
                    QCoreApplication.translate(
                        "M-PROF-05", "A profile can hold at most {n} replacements."
                    ).format(n=f"{MAX_REPLACEMENTS:,}")
                )
            ids = {r.id for r in chosen}
            for replacement in source:
                if replacement.id in ids and replacement.applied is not None:
                    replacement.deleted = True
            source[:] = [r for r in source if r.id not in ids or r.deleted]
            target.extend(copy.deepcopy(moved))

        self._edit(change)
        return len(moved)

    def revert(self, profile_id: str, replacement_ids: Iterable[str]) -> None:
        """Revert to live version: the saved version becomes the applied one again (S-26)."""
        chosen = set(replacement_ids)

        def change(profiles: list[Profile]) -> None:
            for replacement in _find(profiles, profile_id).replacements:
                applied = replacement.applied
                if replacement.id not in chosen or applied is None:
                    continue
                replacement.deleted = False
                replacement.original = copy.deepcopy(applied.original)
                replacement.target = copy.deepcopy(applied.target)
                replacement.enabled = applied.enabled
                replacement.asset_type = applied.asset_type

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
        self._apply(self.profiles, self._keep_applied(state.profiles))

    def _keep_applied(self, profiles: list[Profile]) -> list[Profile]:
        """`profiles` (an undo or redo state) with today's applied versions: undo and redo
        change saved versions only (S-26). A replacement deleted and since applied away, and so
        never applied now, isn't brought back as deleted."""
        current = {p.id: p.applied_enabled for p in self.profiles}
        applied = {r.id: r.applied for p in self.profiles for r in p.replacements}
        result = copy.deepcopy(profiles)
        for profile in result:
            profile.applied_enabled = current.get(profile.id)
            for replacement in profile.replacements:
                replacement.applied = copy.deepcopy(applied.get(replacement.id))
            profile.replacements = [
                r for r in profile.replacements if not (r.deleted and r.applied is None)
            ]
        return result

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


# --- Row status (spec S-25) ----------------------------------------------------------------------


class Status(StrEnum):
    """A replacement's status (S-25); "Draft" belongs to the editor, not to a saved row."""

    PROBLEM = "problem"
    DELETED = "deleted"
    EDITED = "edited"
    NEW = "new"
    OFF = "off"
    SEEN = "seen"
    LIVE = "live"


#: S-25: what wins when more than one status applies.
PRECEDENCE: Final = (
    Status.PROBLEM,
    Status.DELETED,
    Status.EDITED,
    Status.NEW,
    Status.OFF,
    Status.SEEN,
    Status.LIVE,
)


@dataclass(frozen=True, slots=True)
class RowState:
    """One row's status, and what its pill and tooltip need (S-25)."""

    status: Status
    #: Loads since Roblox started, and the time of the last one (Live · seen).
    loads: int = 0
    last: float | None = None
    #: The problem's full reason (Problem), or a detail line (another row wins, the file changed).
    detail: str = ""
    #: The saved version differs from the applied one in a way the game sees (S-26 rule 5).
    waiting: bool = False


def _seen_by_game(replacement: Replacement) -> tuple[object, ...]:
    return (
        replacement.original.asset_id,
        replacement.original.slot,
        replacement.target.kind,
        replacement.target.value,
        replacement.enabled,
    )


def _applied_by_game(applied: Applied) -> tuple[object, ...]:
    return (
        applied.original.asset_id,
        applied.original.slot,
        applied.target.kind,
        applied.target.value,
        applied.enabled,
    )


class FileChecks:
    """Whether the file behind a row is the applied one (S-26 rule 6), hashed only when its size
    or modified time changed since the last look."""

    def __init__(self) -> None:
        self._known: dict[Path, tuple[int, int, str]] = {}

    def known(self, path: Path) -> tuple[bool, str | None]:
        """(True, SHA-256) if the file is as last hashed; (True, None) if it is gone or
        unreadable; (False, None) if it must be hashed again (`sha256`, on a worker)."""
        try:
            info = path.stat()
        except OSError:
            return True, None
        found = self._known.get(path)
        if found is not None and found[:2] == (info.st_size, info.st_mtime_ns):
            return True, found[2] or None  # "": couldn't be read, like gone
        return False, None

    def sha256(self, path: Path) -> str | None:
        """Return the file's SHA-256, or None if it can't be read."""
        try:
            info = path.stat()
        except OSError:
            return None
        known = self._known.get(path)
        if known is not None and known[:2] == (info.st_size, info.st_mtime_ns):
            return known[2]
        try:
            digest = hashlib.sha256(atomic.read_bytes(path)).hexdigest()
        except OSError:
            digest = ""  # remembered, so an unreadable file isn't hashed again and again
        self._known[path] = (info.st_size, info.st_mtime_ns, digest)
        return digest or None


def row_state(
    replacement: Replacement,
    profile: Profile,
    folder: Path,
    *,
    problems: Mapping[str, str],
    loads: rules.Loads,
    winners: Mapping[tuple[int, rules.Slot | None], tuple[str, str]],
    digest_of: Callable[[Path, str | None], str | None],
) -> RowState:
    """The status of one replacement (S-25), from its saved and applied versions.

    `problems`: replacement ID -> why it can't be used (as saved or as applied); `winners`:
    original -> (replacement ID, profile name) of the replacement the game gets for it;
    `digest_of(path, applied)`: the file's SHA-256, `applied` while it isn't hashed yet, or
    None if it is gone (S-26 rule 6).
    """
    applied = replacement.applied
    path = (
        resolve(replacement.target.value, folder / profile.name)
        if replacement.target.kind == "file" and replacement.target.value
        else None
    )
    digest = digest_of(path, applied.sha256 if applied is not None else None) if path else None
    file_changed = (
        applied is not None
        and applied.sha256 is not None
        and digest is not None
        and digest != applied.sha256
    )
    waiting = (
        replacement.deleted
        or (applied is None and replacement.enabled)
        or (applied is not None and _seen_by_game(replacement) != _applied_by_game(applied))
        or file_changed
    )
    found = _problem(replacement, path, digest, problems, waiting=waiting)
    if found is not None:
        return found
    if replacement.deleted or applied is None or waiting:
        return _pending(replacement, applied, file_changed=file_changed, waiting=waiting)
    return _live(replacement, profile, applied, loads, winners)


def _problem(
    replacement: Replacement,
    path: Path | None,
    digest: str | None,
    problems: Mapping[str, str],
    *,
    waiting: bool,
) -> RowState | None:
    """Problem (S-25): the row can't be used, or its file is gone; else None.

    A file gone from under an applied row says that the game keeps the applied version
    (M-ROW-14), which is more than the plain reason preparing it gives."""
    if replacement.id in problems and not (
        path is not None and digest is None and replacement.applied is not None
    ):
        return RowState(Status.PROBLEM, detail=problems[replacement.id], waiting=waiting)
    if path is not None and digest is None:
        missing = QCoreApplication.translate(
            "M-ROW-14",
            "The file for this replacement is missing: {name}. The game keeps the applied "
            "version until you apply.",
        ).format(name=path.name)
        return RowState(Status.PROBLEM, detail=missing, waiting=waiting)
    return None


def _pending(
    replacement: Replacement, applied: Applied | None, *, file_changed: bool, waiting: bool
) -> RowState:
    """A row with a change waiting for the next apply, or never applied (S-25)."""
    if replacement.deleted:
        return RowState(Status.DELETED, waiting=True)
    if applied is None:
        return RowState(Status.NEW if replacement.enabled else Status.OFF, waiting=waiting)
    if replacement.enabled and not applied.enabled:
        return RowState(Status.NEW, waiting=True)  # switched on since it was applied off
    detail = (
        QCoreApplication.translate("M-ROW-15", "The file changed after it was applied.")
        if file_changed
        else ""
    )
    return RowState(Status.EDITED, detail=detail, waiting=True)


def _live(
    replacement: Replacement,
    profile: Profile,
    applied: Applied,
    loads: rules.Loads,
    winners: Mapping[tuple[int, rules.Slot | None], tuple[str, str]],
) -> RowState:
    """An applied row with nothing waiting: Off, Live, or Live · seen (S-25)."""
    if not applied.enabled or not profile.applied_enabled:
        return RowState(Status.OFF)
    winner = winners.get((applied.original.asset_id, applied.original.slot))
    if winner is not None and winner[0] != replacement.id:
        wins = QCoreApplication.translate(
            "M-ROW-13", "Another replacement for this asset wins (profile {name})."
        ).format(name=winner[1])
        return RowState(Status.LIVE, detail=wins)
    count = loads.counts.get(applied.original.asset_id, 0)
    if count:
        return RowState(Status.SEEN, loads=count, last=loads.last.get(applied.original.asset_id))
    return RowState(Status.LIVE)


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

    Apply now waits for links still downloading (`downloading`), and `settled` says when the
    last one has finished or failed, so it can go on without a second click.

    Signals:
        changed(): The profiles changed (an edit, undo or redo), or a link finished downloading.
        settled(): No link is downloading any more (the last one finished or failed).
    """

    changed = Signal()
    settled = Signal()
    #: An original asset Roblox loaded or asked a further pack of (S-25), from the proxy's
    #: thread (queued); `object` because asset IDs outgrow a Qt int.
    loaded = Signal(object)

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
        #: Loads since Roblox started (S-25), counted by the grafter; shared with sprout.
        self.loads = rules.Loads(notify=self.loaded.emit)
        self.files = FileChecks()
        #: Files being hashed on a worker (S-26 rule 6).
        self._hashing: set[Path] = set()
        self.store = ProfileStore(
            folder,
            settings.value("replacements.profile_order"),
            on_order=lambda order: settings.set("replacements.profile_order", order),
            applied_order=settings.value("replacements.applied_order"),
            on_applied_order=lambda order: settings.set("replacements.applied_order", order),
        )
        #: Replacement ID -> why it was left out of the last published snapshot.
        self.warnings: dict[str, str] = {}

    @property
    def profiles(self) -> list[Profile]:
        """The profiles, highest first (read only: edit through the methods)."""
        return self.store.profiles

    @property
    def downloading(self) -> int:
        """How many links are downloading now."""
        return sum(1 for reason in self._links.values() if not reason)

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

    def states(self, profile: Profile) -> dict[str, RowState]:
        """Each replacement's status in `profile` (S-25), by replacement ID."""
        saved = self.store.compile(self._cached_link)
        problems = {**dict(saved.left_out), **self.warnings}
        winners = {
            key: (graft.replacement, graft.profile)
            for key, graft in self.holder.current.grafts.items()
        }
        return {
            replacement.id: row_state(
                replacement,
                profile,
                self.store.folder,
                problems=problems,
                loads=self.loads,
                winners=winners,
                digest_of=self._digest,
            )
            for replacement in profile.replacements
        }

    def _digest(self, path: Path, applied: str | None) -> str | None:
        """A file's SHA-256 for its row's status (S-26 rule 6): known, or hashed on a worker
        (the status is "unchanged" until then, and `changed` redraws it), or None if gone."""
        known, digest = self.files.known(path)
        if known:
            return digest
        if path not in self._hashing:
            self._hashing.add(path)
            if self.pool is None:
                self.files.sha256(path)
                self._hashing.discard(path)
                return self.files.known(path)[1]
            job = self.pool.submit(
                QCoreApplication.translate("M-EDIT-25", "Checking replacement files"),
                lambda _handle: self.files.sha256(path),
            )
            job.succeeded.connect(lambda _digest: self._hashed(path))
            job.failed.connect(lambda _reason: self._hashed(path))
        return applied if applied is not None else ""

    def _hashed(self, path: Path) -> None:
        self._hashing.discard(path)
        self.changed.emit()

    def waiting(self) -> int:
        """How many changes wait for the next apply (S-25 banner and button, S-27 rule 1):
        rows whose saved version differs, profiles switched, and a changed order (one)."""
        count = 0
        for profile in self.store.profiles:
            if profile.applied_enabled is not None and profile.enabled != profile.applied_enabled:
                count += 1
            count += sum(1 for state in self.states(profile).values() if state.waiting)
        order = [p.id for p in self.store.profiles]
        applied = [p for p in self.store.applied_order if p in order]
        if applied and applied != [p for p in order if p in applied]:
            count += 1
        return count

    def preview(self) -> Preview:
        """Preview changes (S-23): what the next Apply now publishes (no download starts)."""
        return preview(self.store.compile(self._cached_link).snapshot)

    def publish(self, *, retry: bool = True) -> int:
        """Apply now: every saved change becomes applied (S-26), then the applied snapshot is
        published; return how many originals it replaces.

        Apply now tries a link whose download failed again (`retry`); when it goes on after
        waiting for downloads, it doesn't, so a link that keeps failing can't keep it waiting.

        Raises:
            ProfileError: The applied copies would use more than 2 GB (M-EDIT-23).
        """
        if retry:
            for link in [link for link, reason in self._links.items() if reason]:
                del self._links[link]
        self.store.promote()
        self.changed.emit()
        count = self._publish()
        self._log_left_out()
        return count

    def publish_applied(self) -> int:
        """Publish what was last applied, nothing saved since (startup; S-26 rule 1)."""
        count = self._publish()
        self._log_left_out()
        return count

    def _log_left_out(self) -> None:
        """M-GRAFT-13: each replacement Apply now left out, which one and why, in plain words.

        A link still downloading isn't a problem (M-APPLY-04 says so); a file is named by its
        name only and a link by its host (S-21 rule 6: never a full link in the log).
        """
        rows = {
            replacement.id: (profile.name, replacement)
            for profile in self.store.profiles
            for replacement in profile.replacements
        }
        for replacement_id, reason in self.warnings.items():
            if reason == self._downloading() or replacement_id not in rows:
                continue
            profile, replacement = rows[replacement_id]
            log.warning(
                "%s",
                QCoreApplication.translate(
                    "M-GRAFT-13",
                    "The replacement of asset {asset} in profile {profile} ({target}) wasn't "
                    "applied: {reason}",
                ).format(
                    asset=replacement.original.asset_id,
                    profile=profile,
                    target=_target_text(replacement.target),
                    reason=reason,
                ),
            )

    def _publish(self) -> int:
        """Publish the applied versions (S-26 rule 1: never what is only saved)."""
        compiled = self.store.compile_applied(self._link)
        self.holder.publish(compiled.snapshot)
        # A saved change that couldn't be applied is never silent (S-21, S-25 Problem).
        self.warnings = {**dict(compiled.left_out), **self.store.skipped}
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
        if not self.downloading:
            self.settled.emit()

    def _download_failed(self, url: str, reason: str) -> None:
        self._links[url] = reason or "?"
        log.warning("%s", self._failed(url, self._links[url]))
        self._publish()  # the table shows why; the next Apply now tries again
        self.changed.emit()
        if not self.downloading:
            self.settled.emit()

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
