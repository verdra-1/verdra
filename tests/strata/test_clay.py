# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""strata/clay: FileMesh versions 1.00 to 5.00, version 2.00 writing, OBJ, and plan 10.7."""

from __future__ import annotations

import contextlib
import struct

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from verdra.strata import clay

TRIANGLE = clay.Mesh(
    (
        clay.Vertex((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0)),
        clay.Vertex((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0)),
        clay.Vertex((0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0)),
    ),
    ((0, 1, 2),),
)
#: A second, smaller level of detail that a reader must skip.
LOW = (0, 2, 1)


def vertex_bytes(mesh: clay.Mesh, size: int) -> bytes:
    out = b""
    for v in mesh.vertices:
        out += struct.pack("<8f", *v.position, *v.normal, *v.uv)
        out += b"\0" * (size - 32)  # w / tangent / colour
    return out


def faces_bytes(faces: list[tuple[int, int, int]]) -> bytes:
    return b"".join(struct.pack("<3I", *f) for f in faces)


def v2(mesh: clay.Mesh = TRIANGLE, vertex_size: int = 40) -> bytes:
    head = struct.pack("<HBBII", 12, vertex_size, 12, len(mesh.vertices), len(mesh.faces))
    return (
        b"version 2.00\n" + head + vertex_bytes(mesh, vertex_size) + faces_bytes(list(mesh.faces))
    )


def v3(version: str = "3.00") -> bytes:
    faces = [*TRIANGLE.faces, LOW]
    head = struct.pack("<HBBHHII", 16, 40, 12, 4, 3, 3, len(faces))
    lods = struct.pack("<3I", 0, 1, 2)
    return (
        f"version {version}\n".encode()
        + head
        + vertex_bytes(TRIANGLE, 40)
        + faces_bytes(faces)
        + lods
    )


def v4(version: str = "4.00", *, bones: int = 1) -> bytes:
    faces = [*TRIANGLE.faces, LOW]
    header_size = 32 if version == "5.00" else 24
    head = struct.pack("<HHIIHHIHBB", header_size, 0, 3, len(faces), 3, bones, 5, 1, 1, 0)
    if version == "5.00":
        head += struct.pack("<II", 0, 0)
    skinning = b"\0" * 8 * 3 if bones else b""
    lods = struct.pack("<3I", 0, 1, 2)
    rest = b"\0" * 60 * bones + b"Root\0" + b"\0" * 72  # bones, names, one subset
    return (
        f"version {version}\n".encode() + head + vertex_bytes(TRIANGLE, 40) + skinning
        + faces_bytes(faces) + lods + rest
    )  # fmt: skip


def v1(version: str) -> bytes:
    corners = ""
    for vertex in TRIANGLE.vertices:
        x, y, z = (c * (2 if version == "1.00" else 1) for c in vertex.position)
        u, v = vertex.uv
        corners += f"[{x},{y},{z}][0,0,1][{u},{1 - v},0]"
    return f"version {version}\n1\n{corners}".encode()


@pytest.mark.parametrize(
    "data",
    [v1("1.00"), v1("1.01"), v2(), v2(vertex_size=36), v3("3.00"), v3("3.01"), v4("4.00"),
     v4("4.01", bones=0), v4("5.00")],
    ids=["1.00", "1.01", "2.00", "2.00-36", "3.00", "3.01", "4.00", "4.01-static", "5.00"],
)  # fmt: skip
def test_every_supported_version_reads_the_same_triangle(data: bytes) -> None:
    mesh = clay.read_mesh(data)
    assert mesh == TRIANGLE  # the higher-detail level only; version 1.00's half scale undone


def test_writing_is_version_2_and_round_trips() -> None:
    data = clay.write_filemesh(TRIANGLE)
    assert data.startswith(b"version 2.00\n") and clay.mesh_version(data) == "2.00"
    assert clay.read_mesh(data) == TRIANGLE


def test_obj_round_trips_and_flips_v() -> None:
    text = clay.write_obj(TRIANGLE).decode()
    assert "vt 0 1" in text  # V = 0 at the top in FileMesh is V = 1 in OBJ
    assert clay.read_obj(text.encode()) == TRIANGLE


def test_obj_quads_become_two_triangles_and_negative_indices_work() -> None:
    obj = b"v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nvt 0 0\nvt 1 1\nf 1/1 2/1 3/2 4/2\nf -4 -3 -2\n"
    mesh = clay.read_obj(obj)
    assert len(mesh.faces) == 3
    assert mesh.faces[0] == (0, 1, 2) and mesh.faces[1] == (0, 2, 3)


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b"not a mesh", "isn't a Roblox mesh file"),
        (b"version 6.00\n" + b"COREMESH" + b"\0" * 32, "6.00 isn't supported yet"),
        (b"version 7.00\n" + b"\0" * 40, "7.00 isn't supported yet"),
        (b"version 2.00\n" + struct.pack("<HBBII", 12, 40, 12, 1_000_000, 1), "claims 1,000,000"),
        (b"version 2.00\n" + struct.pack("<HBBII", 12, 50, 12, 1, 1), "aren't a known layout"),
        (b"version 2.00\n\x0c\x00", "ends early"),
        (v2()[:-4], "claims 1"),
        (b"version 1.00\nmany\n", "count isn't a number"),
        (b"version 1.00\n2\n[0,0,0][0,0,1][0,0,0]", "claims 2"),
    ],
)
def test_what_clay_cant_read_is_refused_with_a_reason(data: bytes, reason: str) -> None:
    with pytest.raises(clay.ClayError, match=reason):
        clay.read_mesh(data)


def test_a_triangle_pointing_past_the_vertices_is_refused() -> None:
    with pytest.raises(clay.ClayError, match="only 3"):
        clay.Mesh(TRIANGLE.vertices, ((0, 1, 3),))
    with pytest.raises(clay.ClayError, match="only 3"):
        clay.read_mesh(v2()[:-12] + struct.pack("<3I", 0, 1, 9))


def test_obj_problems_name_the_line() -> None:
    with pytest.raises(clay.ClayError, match="line 2"):
        clay.read_obj(b"v 0 0 0\nv a b c\n")
    with pytest.raises(clay.ClayError, match="line 2 of the OBJ file: .* doesn't exist"):
        clay.read_obj(b"v 0 0 0\nf 1 2 3\n")
    with pytest.raises(clay.ClayError, match="no faces"):
        clay.read_obj(b"v 0 0 0\n")


def test_meshes_over_64_mb_are_refused() -> None:
    with pytest.raises(clay.ClayError, match="64 MB"):
        clay.read_mesh(b"version 2.00\n" + b"\0" * clay.MAX_MESH_BYTES)


@settings(max_examples=300, deadline=None)
@given(st.binary(max_size=300))
def test_random_bytes_never_raise_anything_but_clay_error(data: bytes) -> None:
    for prefix in (b"", b"version 1.00\n", b"version 2.00\n", b"version 3.00\n", b"version 4.00\n",
                   b"version 5.00\n"):  # fmt: skip
        with contextlib.suppress(clay.ClayError):
            clay.read_mesh(prefix + data)
    with contextlib.suppress(clay.ClayError):
        clay.read_obj(data)


@settings(max_examples=50, deadline=None)
@given(
    st.lists(
        st.tuples(*[st.floats(-1e3, 1e3, allow_nan=False, width=32)] * 8), min_size=3, max_size=30
    ),
    st.data(),
)
def test_any_mesh_round_trips_through_filemesh(
    rows: list[tuple[float, ...]], data: st.DataObject
) -> None:
    vertices = tuple(clay.Vertex(r[0:3], r[3:6], r[6:8]) for r in rows)  # type: ignore[arg-type]
    index = st.integers(0, len(vertices) - 1)
    faces = tuple(data.draw(st.lists(st.tuples(index, index, index), min_size=1, max_size=20)))
    mesh = clay.Mesh(vertices, faces)
    assert clay.read_mesh(clay.write_filemesh(mesh)) == mesh
