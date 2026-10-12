# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Meshes in the layout Roblox's CDN sends: FileMesh 7.00 (strata/clay, decision record 0023).

The layout was captured on the maintainer's PC on 12 October 2026: "version 7.00", a COREMESH
chunk (version 2: a u32 length, then a Draco 2.2 bitstream, sequential, uncompressed indices,
five attributes) and a LODS chunk (version 1). Every mesh here is synthetic; no Roblox content
is used. DracoPy (Google's Draco library) is the independent decoder.
"""

from __future__ import annotations

import math
import struct

import DracoPy
import numpy as np
import pytest

from verdra.roots import litmus
from verdra.strata import clay

#: The captured bitstream's attribute list, byte for byte, right after its indices: one
#: attributes decoder; 5 attributes of (type, data type, components, normalized, unique id).
CAPTURED_ATTRIBUTES = bytes.fromhex(
    "01 05 00 09 03 00 00 04 09 03 00 01 03 09 02 00 02 04 02 04 00 03 02 02 04 00 04"
)
#: The captured bitstream's first bytes: "DRACO", 2.2, mesh, sequential, no flags.
CAPTURED_HEADER = b"DRACO\x02\x02\x01\x00\x00\x00"


def grid(columns: int, rows: int, *, normals: bool = True) -> clay.Mesh:
    """A flat, synthetic grid of `columns` × `rows` squares, two triangles each."""
    vertices = [
        clay.Vertex(
            (float(x), float(y), math.sin(x) * 0.1),
            (0.0, 0.0, 1.0) if normals else (0.0, 0.0, 0.0),
            (x / columns, y / rows),
        )
        for y in range(rows + 1)
        for x in range(columns + 1)
    ]
    faces = []
    for y in range(rows):
        for x in range(columns):
            a = y * (columns + 1) + x
            faces += [(a, a + 1, a + columns + 1), (a + 1, a + columns + 2, a + columns + 1)]
    return clay.Mesh(tuple(vertices), tuple(faces))


def chunks(data: bytes) -> list[tuple[bytes, int, bytes]]:
    body = data[data.index(b"\n") + 1 :]
    found, position = [], 0
    while position < len(body):
        name = body[position : position + 8].rstrip(b"\0")
        version, size = struct.unpack_from("<II", body, position + 8)
        found.append((name, version, body[position + 16 : position + 16 + size]))
        position += 16 + size
    assert position == len(body)
    return found


def draco_of(data: bytes) -> bytes:
    core = chunks(data)[0][2]
    (length,) = struct.unpack_from("<I", core)
    assert length == len(core) - 4
    return core[4:]


def test_the_layout_is_the_captured_one() -> None:
    mesh = grid(10, 10)
    data = clay.write_filemesh7(mesh)
    assert data.startswith(b"version 7.00\n")
    assert [(name, version) for name, version, _data in chunks(data)] == [
        (b"COREMESH", 2), (b"LODS", 1),
    ]  # fmt: skip
    draco = draco_of(data)
    assert draco.startswith(CAPTURED_HEADER)
    # 200 faces, 121 points (varints), uncompressed indices as u8 (fewer than 256 points).
    assert draco[11:15] == bytes([0xC8, 0x01, 121, 1])
    after_indices = 15 + 3 * len(mesh.faces)
    assert draco[after_indices : after_indices + len(CAPTURED_ATTRIBUTES)] == CAPTURED_ATTRIBUTES
    lods = chunks(data)[1][2]
    assert lods == struct.pack("<HBI2I", 4, 1, 2, 0, len(mesh.faces))
    report = "\n".join(litmus.mesh_lines(data))
    assert "id 1: generic float32 x 3, coding 0" in report
    assert "type 4, high-quality levels 1, face offsets [0, 200]" in report


@pytest.mark.parametrize(("columns", "rows"), [(1, 1), (20, 20), (300, 300)])
def test_an_independent_decoder_reads_every_attribute_back(columns: int, rows: int) -> None:
    """u8, u16 and varint indices (fewer than 256, 65,536 and 2,097,152 points)."""
    mesh = grid(columns, rows)
    decoded = DracoPy.decode(draco_of(clay.write_filemesh7(mesh)))
    assert len(decoded.points) == len(mesh.vertices)
    assert np.array_equal(np.asarray(decoded.faces), np.asarray(mesh.faces))
    assert np.allclose(decoded.points, [v.position for v in mesh.vertices], atol=1e-6)
    shapes = {a["unique_id"]: (a["attribute_type"], a["data_type"]) for a in decoded.attributes}
    assert shapes == {0: (0, 9), 1: (4, 9), 2: (3, 9), 3: (4, 2), 4: (2, 2)}
    normals = decoded.get_attribute_by_unique_id(1)["data"]
    assert np.allclose(normals, [v.normal for v in mesh.vertices])
    assert np.allclose(decoded.tex_coord, [v.uv for v in mesh.vertices])
    assert np.all(np.asarray(decoded.colors) == 255)  # noqa: PLR2004
    assert not np.asarray(decoded.get_attribute_by_unique_id(3)["data"]).any()
    again = clay.read_mesh(clay.write_filemesh7(mesh))  # and Verdra's own reader
    assert again.faces == mesh.faces
    assert np.allclose([v.position for v in again.vertices], [v.position for v in mesh.vertices])


def test_only_the_first_level_of_detail_is_read() -> None:
    mesh = grid(4, 4)  # 32 faces
    data = clay.write_filemesh7(mesh)
    name, version, _lods = chunks(data)[1]
    body = data[: data.index(b"LODS")]
    two_levels = struct.pack("<HBI3I", 4, 2, 3, 0, 20, 32)
    data = body + name.ljust(8, b"\0") + struct.pack("<II", version, len(two_levels)) + two_levels
    assert len(clay.read_mesh(data).faces) == 20  # noqa: PLR2004


def test_remove_is_one_triangle_with_no_area() -> None:
    removed = clay.read_mesh(clay.write_filemesh7(clay.Mesh((), ())))
    assert removed.faces == ((0, 1, 2),)
    assert {v.position for v in removed.vertices} == {(0.0, 0.0, 0.0)}


def test_too_many_triangles_are_refused_with_a_reason() -> None:
    point = clay.Vertex((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0))
    mesh = clay.Mesh((point, point, point), ((0, 1, 2),) * (clay.MAX_FACES + 1))
    with pytest.raises(clay.ClayError, match="at most 1,000,000"):
        clay.write_filemesh7(mesh)


def test_an_obj_without_normals_gets_them() -> None:
    served = clay.read_mesh(clay.write_filemesh7(grid(3, 3, normals=False)))
    for vertex in served.vertices:
        assert math.isclose(math.dist((0, 0, 0), vertex.normal), 1.0, rel_tol=1e-5)
    flat = clay.read_mesh(
        clay.write_filemesh7(clay.read_obj(b"v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"))
    )
    assert {v.normal for v in flat.vertices} == {(0.0, 0.0, 1.0)}


def test_damaged_draco_is_refused_with_a_reason() -> None:
    data = bytearray(clay.write_filemesh7(grid(2, 2)))
    start = data.index(b"DRACO")
    data[start : start + 5] = b"XXXXX"
    with pytest.raises(clay.ClayError, match="compressed geometry is damaged"):
        clay.read_mesh(bytes(data))


def test_the_summary_of_something_that_isnt_draco() -> None:
    assert clay.draco_summary(b"nothing") == ["not a Draco bitstream"]
    assert clay.draco_summary(CAPTURED_HEADER + b"\x80")[-1] == "(ends early)"
