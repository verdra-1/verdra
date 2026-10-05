# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Meshes: FileMesh reader and writer (every documented version), Draco through DracoPy, OBJ
import and export.

Spec S-33 (strata/clay), written from the public descriptions of Roblox's FileMesh format. Pure
functions over bytes:

- `read_mesh` reads FileMesh versions 1.00 to 5.00 into a `Mesh` (the highest-detail level of
  detail only; bones, skinning and facial animation data are skipped, not kept);
- `write_filemesh` writes version 2.00, the lowest version that holds positions, normals and
  texture coordinates, which is all a static replacement mesh needs;
- `read_obj` and `write_obj` convert to and from Wavefront OBJ.

Versions 6.00 and 7.00 (chunked, with Draco-compressed geometry) are refused with a plain reason
until their layout is confirmed. Every count is checked against the data before anything is
allocated (plan 10.7: at most 64 MB a mesh); anything unreadable raises `ClayError`, and random
bytes never raise anything else.

Texture coordinates: FileMesh stores V with 0 at the top of the image, OBJ with 0 at the bottom,
so V is flipped between the two.
"""

from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass, field
from typing import Final

#: Plan 10.7.
MAX_MESH_BYTES: Final = 64 * 1024 * 1024
MAX_ELEMENTS: Final = 4_000_000

_VERSION = re.compile(rb"\Aversion (\d\.\d\d)\r?\n")


class ClayError(ValueError):
    """A mesh can't be read or written; the message is the plain reason (M-FMT-01)."""


@dataclass(frozen=True, slots=True)
class Vertex:
    """One vertex: position, normal and texture coordinate (U, V with V = 0 at the top)."""

    position: tuple[float, float, float]
    normal: tuple[float, float, float]
    uv: tuple[float, float]


@dataclass(frozen=True, slots=True)
class Mesh:
    """Triangles over shared vertices."""

    vertices: tuple[Vertex, ...]
    faces: tuple[tuple[int, int, int], ...]

    def __post_init__(self) -> None:
        count = len(self.vertices)
        for face in self.faces:
            if any(not 0 <= index < count for index in face):
                msg = f"a triangle uses vertex {max(face)}, but there are only {count}"
                raise ClayError(msg)


def mesh_version(data: bytes) -> str:
    """Return the FileMesh version ("2.00"), or raise `ClayError` if it isn't a FileMesh."""
    match = _VERSION.match(data[:32])
    if match is None:
        msg = "it isn't a Roblox mesh file"
        raise ClayError(msg)
    return match.group(1).decode()


# --- Reading ---------------------------------------------------------------------------------


def read_mesh(data: bytes) -> Mesh:
    """Read a FileMesh (versions 1.00 to 5.00) into a `Mesh`."""
    if len(data) > MAX_MESH_BYTES:
        msg = f"it is {len(data):,} bytes; meshes can be at most 64 MB"
        raise ClayError(msg)
    version = mesh_version(data)
    body = data[_VERSION.match(data).end() :]  # type: ignore[union-attr]
    try:
        if version in ("1.00", "1.01"):
            return _read_v1(body, scale=0.5 if version == "1.00" else 1.0)
        if version == "2.00":
            return _read_v2(body)
        if version in ("3.00", "3.01"):
            return _read_v3(body)
        if version in ("4.00", "4.01", "5.00"):
            return _read_v4(body, v5=version == "5.00")
    except struct.error as error:
        msg = "the mesh data ends early"
        raise ClayError(msg) from error
    msg = f"mesh version {version} isn't supported yet"
    raise ClayError(msg)


_NUMBER = r"\s*([-+0-9.eE]+|nan|inf|-inf)\s*"
_TRIPLE = re.compile(rf"\[{_NUMBER},{_NUMBER},{_NUMBER}\]".encode())


def _read_v1(body: bytes, *, scale: float) -> Mesh:
    first, _, rest = body.partition(b"\n")
    try:
        count = int(first.strip())
    except ValueError as error:
        msg = "the mesh's triangle count isn't a number"
        raise ClayError(msg) from error
    _check_count(count, len(rest) // 21)  # "[0,0,0]" at least 7 bytes, 3 per corner
    triples = [tuple(_finite(float(x)) for x in m.groups()) for m in _TRIPLE.finditer(rest)]
    if len(triples) < count * 9:
        msg = f"the mesh says {count} triangles but holds fewer"
        raise ClayError(msg)
    vertices = []
    for corner in range(count * 3):
        position, normal, uv = triples[corner * 3 : corner * 3 + 3]
        vertices.append(
            Vertex(
                (position[0] * scale, position[1] * scale, position[2] * scale),
                (normal[0], normal[1], normal[2]),
                (uv[0], 1.0 - uv[1]),  # version 1 stores V with 0 at the bottom
            )
        )
    faces = tuple((i * 3, i * 3 + 1, i * 3 + 2) for i in range(count))
    return Mesh(tuple(vertices), faces)


def _read_vertices(body: bytes, offset: int, count: int, size: int) -> tuple[Vertex, ...]:
    if size not in (36, 40):
        msg = f"vertices of {size} bytes aren't a known layout"
        raise ClayError(msg)
    _check_count(count, (len(body) - offset) // size)
    vertices = []
    for index in range(count):
        values = struct.unpack_from("<8f", body, offset + index * size)
        _finite(*values)
        vertices.append(Vertex(values[0:3], values[3:6], (values[6], values[7])))  # type: ignore[arg-type]
    return tuple(vertices)


def _read_faces(body: bytes, offset: int, count: int) -> list[tuple[int, int, int]]:
    _check_count(count, (len(body) - offset) // 12)
    return [struct.unpack_from("<3I", body, offset + i * 12) for i in range(count)]


def _read_v2(body: bytes) -> Mesh:
    header_size, vertex_size, face_size, vertices, faces = struct.unpack_from("<HBBII", body, 0)
    if header_size != 12 or face_size != 12:
        msg = "the version 2 header doesn't have the expected sizes"
        raise ClayError(msg)
    read = _read_vertices(body, header_size, vertices, vertex_size)
    triangles = _read_faces(body, header_size + vertices * vertex_size, faces)
    return Mesh(read, tuple(triangles))


def _read_v3(body: bytes) -> Mesh:
    header_size, vertex_size, face_size, lod_size, lods, vertices, faces = struct.unpack_from(
        "<HBBHHII", body, 0
    )
    if header_size != 16 or face_size != 12 or lod_size != 4:
        msg = "the version 3 header doesn't have the expected sizes"
        raise ClayError(msg)
    read = _read_vertices(body, header_size, vertices, vertex_size)
    faces_at = header_size + vertices * vertex_size
    triangles = _read_faces(body, faces_at, faces)
    offsets = _read_lods(body, faces_at + faces * 12, lods)
    return Mesh(read, tuple(_first_lod(triangles, offsets)))


def _read_v4(body: bytes, *, v5: bool) -> Mesh:
    header_size = struct.unpack_from("<H", body, 0)[0]
    if header_size != (32 if v5 else 24):
        msg = f"the version {'5' if v5 else '4'} header doesn't have the expected size"
        raise ClayError(msg)
    (_lod_type, vertices, faces, lods, bones, _names, _subsets, _high, _unused) = (
        struct.unpack_from("<HIIHHIHBB", body, 2)
    )
    read = _read_vertices(body, header_size, vertices, 40)
    offset = header_size + vertices * 40
    if bones:
        offset += vertices * 8  # skinning: four bone indices and four weights a vertex
    triangles = _read_faces(body, offset, faces)
    offsets = _read_lods(body, offset + faces * 12, lods)
    return Mesh(read, tuple(_first_lod(triangles, offsets)))


def _read_lods(body: bytes, offset: int, count: int) -> list[int]:
    _check_count(count, (len(body) - offset) // 4)
    return list(struct.unpack_from(f"<{count}I", body, offset)) if count else []


def _first_lod(
    triangles: list[tuple[int, int, int]], offsets: list[int]
) -> list[tuple[int, int, int]]:
    """The highest-detail level: faces from the first offset to the second."""
    if len(offsets) >= 2 and 0 <= offsets[0] <= offsets[1] <= len(triangles):
        return triangles[offsets[0] : offsets[1]]
    return triangles


def _check_count(count: int, available: int) -> None:
    if count < 0 or count > MAX_ELEMENTS or count > available:
        msg = f"the mesh claims {count:,} elements but the data holds at most {available:,}"
        raise ClayError(msg)


def _finite(*values: float) -> float:
    if not all(math.isfinite(v) for v in values):
        msg = "the mesh holds a number that isn't finite"
        raise ClayError(msg)
    return values[0]


# --- Writing ---------------------------------------------------------------------------------


def write_filemesh(mesh: Mesh) -> bytes:
    """Write `mesh` as FileMesh version 2.00 (36-byte vertices, no colors)."""
    _check_count(len(mesh.vertices), MAX_ELEMENTS)
    _check_count(len(mesh.faces), MAX_ELEMENTS)
    parts = [
        b"version 2.00\n",
        struct.pack("<HBBII", 12, 36, 12, len(mesh.vertices), len(mesh.faces)),
    ]
    for vertex in mesh.vertices:
        parts.append(struct.pack("<9f", *vertex.position, *vertex.normal, *vertex.uv, 0.0))
    for face in mesh.faces:
        parts.append(struct.pack("<3I", *face))
    data = b"".join(parts)
    if len(data) > MAX_MESH_BYTES:
        msg = "the mesh would be larger than 64 MB"
        raise ClayError(msg)
    return data


# --- OBJ -------------------------------------------------------------------------------------


def read_obj(data: bytes) -> Mesh:
    """Import a Wavefront OBJ (positions, texture coordinates, normals, polygons as fans)."""
    if len(data) > MAX_MESH_BYTES:
        msg = f"it is {len(data):,} bytes; meshes can be at most 64 MB"
        raise ClayError(msg)
    text = data.decode("utf-8", errors="replace")
    obj = _Obj()
    positions, uvs, normals, vertices = obj.positions, obj.uvs, obj.normals, obj.vertices
    faces: list[tuple[int, int, int]] = []
    for number, line in enumerate(text.splitlines(), 1):
        fields = line.split("#", 1)[0].split()
        if not fields:
            continue
        try:
            if fields[0] == "v":
                positions.append((float(fields[1]), float(fields[2]), float(fields[3])))
                _finite(*positions[-1])
            elif fields[0] == "vt":
                uvs.append((float(fields[1]), float(fields[2]) if len(fields) > 2 else 0.0))
                _finite(*uvs[-1])
            elif fields[0] == "vn":
                normals.append((float(fields[1]), float(fields[2]), float(fields[3])))
                _finite(*normals[-1])
            elif fields[0] == "f":
                corners = [_corner(field, obj) for field in fields[1:]]
                if len(corners) < 3:
                    msg = "a face has fewer than three corners"
                    raise ClayError(msg)
                faces.extend(
                    (corners[0], corners[i], corners[i + 1]) for i in range(1, len(corners) - 1)
                )
        except ClayError as error:
            msg = f"line {number} of the OBJ file: {error}"
            raise ClayError(msg) from error
        except (IndexError, ValueError) as error:
            msg = f"line {number} of the OBJ file can't be read"
            raise ClayError(msg) from error
        if len(vertices) > MAX_ELEMENTS or len(faces) > MAX_ELEMENTS:
            msg = "the OBJ file has too many vertices or faces"
            raise ClayError(msg)
    if not faces:
        msg = "the OBJ file has no faces"
        raise ClayError(msg)
    return Mesh(tuple(vertices), tuple(faces))


@dataclass(slots=True)
class _Obj:
    """What an OBJ file has declared so far."""

    positions: list[tuple[float, float, float]] = field(default_factory=list)
    uvs: list[tuple[float, float]] = field(default_factory=list)
    normals: list[tuple[float, float, float]] = field(default_factory=list)
    vertices: list[Vertex] = field(default_factory=list)
    seen: dict[tuple[int, int, int], int] = field(default_factory=dict)


def _corner(text: str, obj: _Obj) -> int:
    parts = (text.split("/") + ["", ""])[:3]
    positions, uvs, normals, vertices, seen = (
        obj.positions,
        obj.uvs,
        obj.normals,
        obj.vertices,
        obj.seen,
    )

    def index(number: str, count: int) -> int:
        if not number:
            return -1
        value = int(number)
        resolved = value - 1 if value > 0 else count + value
        if not 0 <= resolved < count:
            msg = f"a face refers to element {value}, which doesn't exist"
            raise ClayError(msg)
        return resolved

    key = (
        index(parts[0], len(positions)),
        index(parts[1], len(uvs)),
        index(parts[2], len(normals)),
    )
    if key[0] < 0:
        msg = "a face corner has no position"
        raise ClayError(msg)
    if key not in seen:
        u, v = uvs[key[1]] if key[1] >= 0 else (0.0, 0.0)
        normal = normals[key[2]] if key[2] >= 0 else (0.0, 0.0, 0.0)
        seen[key] = len(vertices)
        vertices.append(Vertex(positions[key[0]], normal, (u, 1.0 - v)))
    return seen[key]


def write_obj(mesh: Mesh) -> bytes:
    """Export a mesh as Wavefront OBJ (one position, coordinate and normal a vertex)."""
    lines = ["# Exported by Verdra"]
    lines += [f"v {x:.6g} {y:.6g} {z:.6g}" for x, y, z in (v.position for v in mesh.vertices)]
    lines += [f"vt {u:.6g} {1.0 - v:.6g}" for u, v in (v.uv for v in mesh.vertices)]
    lines += [f"vn {x:.6g} {y:.6g} {z:.6g}" for x, y, z in (v.normal for v in mesh.vertices)]
    lines += ["f " + " ".join(f"{i + 1}/{i + 1}/{i + 1}" for i in face) for face in mesh.faces]
    return ("\n".join(lines) + "\n").encode()
