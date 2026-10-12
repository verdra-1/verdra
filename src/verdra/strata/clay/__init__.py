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

Versions 6.00 and 7.00 (chunked, with Draco-compressed geometry) are read through DracoPy, and
`write_filemesh7` writes 7.00 in the layout Roblox's CDN sends (decision record 0023). Every
count is checked against the data before anything is allocated (plan 10.7: at most 64 MB a
mesh); anything unreadable raises `ClayError`, and random bytes never raise anything else.

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
    """Read a FileMesh (versions 1.00 to 7.00) into a `Mesh`."""
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
        if version in ("6.00", "7.00"):
            return _read_chunked(body)
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


# --- FileMesh 7.00 (what Roblox's CDN sends; captured 12 October 2026) -----------------------
#
# docs/platforms/evidence/windows/mip-packs-2026-10-12.txt and decision record 0023: the line
# "version 7.00", then chunks of an 8-byte name, a u32 chunk version and a u32 size: COREMESH
# (version 2: a u32 length, then the geometry as a Draco bitstream) and LODS (version 1: u16 LOD
# type, u8 count of high-quality levels, u32 count of face offsets, the u32 offsets).
#
# The Draco bitstream (public Draco format, version 2.2) is Verdra's own minimal writer: a
# sequential mesh with uncompressed indices and five attributes in the captured order, ids and
# types (position, normal as a generic float attribute, texture coordinate, a 4-byte generic
# attribute, color). Each attribute is stored raw (Draco's generic attribute coding), where
# Roblox's file compresses the normal, the generic attribute and the color; any Draco decoder
# reads both the same way.

#: Draco's names for what the captured attributes are (public Draco format).
_DRACO_POSITION, _DRACO_COLOR, _DRACO_TEX_COORD, _DRACO_GENERIC = 0, 2, 3, 4
_DRACO_UINT8, _DRACO_FLOAT32 = 2, 9
#: (Draco type, data type, components, unique id) of the captured attributes, in their order.
_DRACO_ATTRIBUTES: Final = (
    (_DRACO_POSITION, _DRACO_FLOAT32, 3, 0),
    (_DRACO_GENERIC, _DRACO_FLOAT32, 3, 1),  # the normal (unit vectors in the capture)
    (_DRACO_TEX_COORD, _DRACO_FLOAT32, 2, 2),
    (_DRACO_GENERIC, _DRACO_UINT8, 4, 3),  # observed all 0; meaning unknown
    (_DRACO_COLOR, _DRACO_UINT8, 4, 4),  # observed all 255 (white, opaque)
)
#: LODS: observed values whose meaning isn't known (the capture: type 4, 2 high-quality levels).
_LOD_TYPE: Final = 4
#: The most triangles Verdra writes into one mesh (Roblox's own import limit is far lower).
MAX_FACES: Final = 1_000_000


def write_filemesh7(mesh: Mesh) -> bytes:
    """Write `mesh` the way Roblox's CDN sends meshes: FileMesh 7.00 (decision record 0023).

    One level of detail. An empty mesh (Remove) becomes one triangle with no area at the
    origin, so the file still holds valid geometry and nothing is drawn.
    """
    if len(mesh.faces) > MAX_FACES:
        msg = f"it has {len(mesh.faces):,} triangles; a mesh can have at most {MAX_FACES:,}"
        raise ClayError(msg)
    if not mesh.faces:
        point = Vertex((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0))
        mesh = Mesh((point, point, point), ((0, 1, 2),))
    draco = draco_mesh(with_normals(mesh))
    core = struct.pack("<I", len(draco)) + draco
    lods = struct.pack("<HBI", _LOD_TYPE, 1, 2) + struct.pack("<2I", 0, len(mesh.faces))
    data = b"version 7.00\n" + _chunk(b"COREMESH", 2, core) + _chunk(b"LODS", 1, lods)
    if len(data) > MAX_MESH_BYTES:
        msg = "the mesh would be larger than 64 MB"
        raise ClayError(msg)
    return data


def with_normals(mesh: Mesh) -> Mesh:
    """`mesh` with a normal for every vertex that has none (an OBJ without `vn` lines).

    The missing ones become the normalized sum of the normals of the triangles around the
    vertex, each weighted by its area (the cross product's length), so flat parts stay flat.
    """
    if all(vertex.normal != (0.0, 0.0, 0.0) for vertex in mesh.vertices):
        return mesh
    sums = [[0.0, 0.0, 0.0] for _ in mesh.vertices]
    for face in mesh.faces:
        a, b, c = (mesh.vertices[index].position for index in face)
        u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        cross = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        for index in face:
            for axis in range(3):
                sums[index][axis] += cross[axis]
    vertices = []
    for vertex, total in zip(mesh.vertices, sums, strict=True):
        length = math.sqrt(sum(c * c for c in total))
        if vertex.normal != (0.0, 0.0, 0.0) or length == 0:
            vertices.append(vertex)
        else:
            normal = (total[0] / length, total[1] / length, total[2] / length)
            vertices.append(Vertex(vertex.position, normal, vertex.uv))
    return Mesh(tuple(vertices), mesh.faces)


def _chunk(name: bytes, version: int, data: bytes) -> bytes:
    return name.ljust(8, b"\x00") + struct.pack("<II", version, len(data)) + data


def draco_mesh(mesh: Mesh) -> bytes:
    """`mesh` as a Draco 2.2 bitstream: sequential, uncompressed indices, raw attributes."""
    points, faces = len(mesh.vertices), len(mesh.faces)
    out = bytearray(b"DRACO" + bytes([2, 2, 1, 0]) + b"\x00\x00")  # mesh, sequential, no flags
    out += _varint(faces) + _varint(points) + b"\x01"  # uncompressed indices
    indices = [index for face in mesh.faces for index in face]
    if points < 1 << 8:  # noqa: PLR2004
        out += bytes(indices)
    elif points < 1 << 16:  # noqa: PLR2004
        out += struct.pack(f"<{len(indices)}H", *indices)
    elif points < 1 << 21:  # noqa: PLR2004
        out += b"".join(_varint(index) for index in indices)
    else:
        out += struct.pack(f"<{len(indices)}I", *indices)
    out += b"\x01" + _varint(len(_DRACO_ATTRIBUTES))  # one attributes decoder
    for kind, data_type, components, unique_id in _DRACO_ATTRIBUTES:
        out += bytes([kind, data_type, components, 0]) + _varint(unique_id)
    out += bytes(len(_DRACO_ATTRIBUTES))  # every attribute: the generic (raw) coding
    vertices = mesh.vertices
    out += struct.pack(f"<{3 * points}f", *(c for v in vertices for c in v.position))
    out += struct.pack(f"<{3 * points}f", *(c for v in vertices for c in v.normal))
    out += struct.pack(f"<{2 * points}f", *(c for v in vertices for c in v.uv))
    out += bytes(4 * points)
    out += b"\xff" * (4 * points)
    return bytes(out)


_DRACO_TYPE_NAMES: Final = {
    0: "position",
    1: "normal",
    2: "color",
    3: "texture coordinate",
    4: "generic",
}
_DRACO_DATA_NAMES: Final = {
    1: "int8",
    2: "uint8",
    3: "int16",
    4: "uint16",
    5: "int32",
    6: "uint32",
    9: "float32",
}


def draco_summary(data: bytes) -> list[str]:
    """What a Draco bitstream's header and attribute list say, without decoding the geometry.

    The attribute list is read only after uncompressed indices (the layout Roblox's meshes and
    Verdra's use); for other layouts the summary stops at the counts.
    """
    if not data.startswith(b"DRACO") or len(data) < 11:  # noqa: PLR2004
        return ["not a Draco bitstream"]
    major, minor, kind, method = data[5:9]
    (flags,) = struct.unpack_from("<H", data, 9)
    lines = [f"Draco {major}.{minor}, encoder type {kind}, method {method}, flags {flags}"]
    try:
        faces, position = _read_varint(data, 11)
        points, position = _read_varint(data, position)
        connectivity = data[position]
        position += 1
        lines.append(f"faces {faces}, points {points}, connectivity method {connectivity}")
        if method != 0 or connectivity != 1:
            return lines
        if points < 1 << 8:  # noqa: PLR2004
            position += 3 * faces
        elif points < 1 << 16:  # noqa: PLR2004
            position += 6 * faces
        elif points < 1 << 21:  # noqa: PLR2004
            for _ in range(3 * faces):
                _value, position = _read_varint(data, position)
        else:
            position += 12 * faces
        decoders = data[position]
        count, position = _read_varint(data, position + 1)
        declared = []
        for _ in range(count):
            kind, data_type, components, _normalized = data[position : position + 4]
            unique_id, position = _read_varint(data, position + 4)
            declared.append(
                f"id {unique_id}: {_DRACO_TYPE_NAMES.get(kind, kind)} "
                f"{_DRACO_DATA_NAMES.get(data_type, data_type)} x {components}"
            )
        codings = list(data[position : position + count])
        lines.append(f"attribute decoders {decoders}, attributes {count}:")
        lines += [
            f"  {text}, coding {coding}" for text, coding in zip(declared, codings, strict=False)
        ]
    except IndexError, ValueError:
        lines.append("(ends early)")
    return lines


def _read_varint(data: bytes, position: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        byte = data[position]
        position += 1
        value |= (byte & 0x7F) << shift
        shift += 7
        if byte < 0x80:  # noqa: PLR2004
            return value, position
        if shift > 35:  # noqa: PLR2004
            msg = "a number in the Draco data is too long"
            raise ValueError(msg)


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _read_chunked(body: bytes) -> Mesh:
    """FileMesh 6.00 and 7.00: the COREMESH chunk's Draco geometry, the first level of detail."""
    position, core, lods = 0, None, None
    while position + 16 <= len(body):
        name = body[position : position + 8].rstrip(b"\x00")
        version, size = struct.unpack_from("<II", body, position + 8)
        data = body[position + 16 : position + 16 + size]
        if len(data) < size:
            msg = "the mesh data ends early"
            raise ClayError(msg)
        if name == b"COREMESH":
            core = (version, data)
        elif name == b"LODS":
            lods = (version, data)
        position += 16 + size
    if core is None:
        msg = "the mesh has no geometry (no COREMESH chunk)"
        raise ClayError(msg)
    version, data = core
    if version != 2 or len(data) < 4:  # noqa: PLR2004
        msg = f"geometry stored as COREMESH version {version} isn't supported yet"
        raise ClayError(msg)
    (length,) = struct.unpack_from("<I", data)
    mesh = _from_draco(data[4 : 4 + length])
    first = _first_lod_faces(lods, len(mesh.faces))
    return Mesh(mesh.vertices, mesh.faces[:first])


def _first_lod_faces(lods: tuple[int, bytes] | None, total: int) -> int:
    if lods is None or lods[0] != 1 or len(lods[1]) < 7:  # noqa: PLR2004
        return total
    (count,) = struct.unpack_from("<I", lods[1], 3)
    if count < 2 or len(lods[1]) < 7 + 4 * count:  # noqa: PLR2004
        return total
    end = struct.unpack_from("<I", lods[1], 7 + 4)[0]
    return end if 0 < end <= total else total


def _from_draco(data: bytes) -> Mesh:
    """Decode Draco geometry with DracoPy (Google's Draco library): positions, normals, UVs."""
    import DracoPy  # noqa: PLC0415, N813 - loaded only when a 6.00 or 7.00 mesh is read

    _check_draco_counts(data)
    try:
        decoded = DracoPy.decode(data)
    except Exception as error:  # noqa: BLE001 - DracoPy raises several kinds for bad data
        msg = "the mesh's compressed geometry is damaged"
        raise ClayError(msg) from error
    points = [tuple(float(c) for c in p) for p in decoded.points]
    _check_count(len(points), MAX_ELEMENTS)
    normals = _draco_attribute(decoded, 1, len(points), 3)
    uvs = _draco_attribute(decoded, 2, len(points), 2)
    vertices = tuple(
        Vertex(
            (points[i][0], points[i][1], points[i][2]),
            (normals[i][0], normals[i][1], normals[i][2]),
            (uvs[i][0], uvs[i][1]),
        )
        for i in range(len(points))
    )
    faces = tuple((int(a), int(b), int(c)) for a, b, c in decoded.faces)
    _check_count(len(faces), MAX_ELEMENTS)
    return Mesh(vertices, faces)


def _check_draco_counts(data: bytes) -> None:
    """Refuse counts over plan 10.7's limits before DracoPy allocates for them.

    A sequential Draco mesh (what Roblox and Verdra write) names its face and point counts
    right after the header. Other layouts are left to Draco's own checks against the data size.
    """
    if not data.startswith(b"DRACO") or len(data) < 12 or data[7:9] != b"\x01\x00":  # noqa: PLR2004
        return
    try:
        faces, position = _read_varint(data, 11)
        points, _position = _read_varint(data, position)
    except (IndexError, ValueError) as error:
        msg = "the mesh's compressed geometry is damaged"
        raise ClayError(msg) from error
    _check_count(points, MAX_ELEMENTS)
    _check_count(faces, MAX_ELEMENTS)


def _draco_attribute(decoded: object, unique_id: int, count: int, size: int) -> list[list[float]]:
    """An attribute by its captured id, or zeros when the file has none of that shape."""
    try:
        found = decoded.get_attribute_by_unique_id(unique_id)  # type: ignore[attr-defined]
    except KeyError, IndexError, ValueError:
        found = None
    values = None if found is None else found.get("data")
    if values is None or len(values) != count or len(values[0]) != size:
        return [[0.0] * size for _ in range(count)]
    return [[float(c) for c in row] for row in values]


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
