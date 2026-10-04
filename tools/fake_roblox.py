# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""A fake Roblox server for the proxy integration tests (Master plan 12.1, spec S-11).

A test tool, not shipped. It serves the hosts of plan 10.2 over real TLS on loopback, each with a
certificate from a test CA made for the session (never a real certificate), chosen by SNI. Its
responses come from the fixtures in `tests/fixtures/roblox/` and are replayed byte for byte.

Fixtures are raw HTTP responses after a few `#` header lines: `origin` (where the fixture comes
from), `host`, `request` (method and path) and optionally `body: random N` for a binary body of N
seeded bytes. In the response and the path, `{{n}}`, `{{hex}}`, `{{hex12}}`, `{{octet}}` and
`{{port}}` become invented values derived from a seed, so `responses(1000)` gives 1,000 distinct
responses. Each is sent in every framing the fixture allows: identity, gzip and zstd content
encoding (brotli isn't among the plan's dependencies), with Content-Length or chunked transfer.

A request picks its response with `?replay=<index>` (see `Replay.target`); any other request gets
404. Modes for the negative tests: `self_signed`, `wrong_host` and `tls11` (TLS 1.1 at most).

    python tools/fake_roblox.py --ca-out ca.pem   serve until Ctrl+C; print the port
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import gzip
import hashlib
import random
import ssl
import tempfile
import warnings
from compression import zstd
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

from verdra.bark import resin

ROOT = Path(__file__).resolve().parent.parent
FIXTURES: Final = ROOT / "tests" / "fixtures" / "roblox"
#: Plan 10.2: the hosts it stands in for (the asset CDN host stands in for the other CDN hosts).
HOSTS: Final = (
    "assetdelivery.roblox.com",
    "fts.rbxcdn.com",
    "clientsettings.roblox.com",
    "clientsettingscdn.roblox.com",
    "gamejoin.roblox.com",
    "apis.roblox.com",
)
Encoding = Literal["identity", "gzip", "zstd"]
Framing = Literal["length", "chunked"]
Mode = Literal["normal", "self_signed", "wrong_host", "tls11"]
ENCODINGS: Final[tuple[Encoding, ...]] = ("identity", "gzip", "zstd")
FRAMINGS: Final[tuple[Framing, ...]] = ("length", "chunked")
_NO_BODY: Final = (b" 204 ", b" 304 ")
_CHUNK: Final = 1000


@dataclass(frozen=True, slots=True)
class Fixture:
    """One fixture file: a response template for one host and request."""

    name: str
    origin: str
    host: str
    method: str
    path: str
    head: str
    body: str
    random_body: int = 0

    @property
    def has_body(self) -> bool:
        return not any(status in self.head.split("\n", 1)[0].encode() for status in _NO_BODY)


def load(folder: Path = FIXTURES) -> list[Fixture]:
    """Read every fixture in `folder`, in name order."""
    fixtures: list[Fixture] = []
    for path in sorted(folder.glob("*.http")):
        meta: dict[str, str] = {}
        lines = path.read_text(encoding="utf-8").split("\n")
        while lines and lines[0].startswith("#"):
            key, _, value = lines.pop(0)[1:].strip().partition(":")
            meta[key.strip()] = value.strip()
        text = "\n".join(lines)
        head, _, body = text.partition("\n\n")
        method, _, target = meta["request"].partition(" ")
        random_body = int(meta["body"].split()[1]) if "body" in meta else 0
        fixtures.append(
            Fixture(
                path.stem,
                meta["origin"],
                meta["host"],
                method,
                target,
                head,
                body.removesuffix("\n"),
                random_body,
            )
        )
    return fixtures


@dataclass(frozen=True, slots=True)
class Replay:
    """One concrete response: a fixture filled from a seed, in one encoding and framing."""

    index: int
    fixture: Fixture
    encoding: Encoding
    framing: Framing
    raw: bytes = field(repr=False)

    @property
    def host(self) -> str:
        return self.fixture.host

    @property
    def target(self) -> bytes:
        path = _fill(self.fixture.path, self.index)
        joiner = "&" if "?" in path else "?"
        return f"{path}{joiner}replay={self.index}".encode()

    def request(self) -> bytes:
        """A request for this response, with a body for POST."""
        body = b'{"example":true}' if self.fixture.method == "POST" else b""
        length = f"Content-Length: {len(body)}\r\n" if body else ""
        return (
            f"{self.fixture.method} {self.target.decode()} HTTP/1.1\r\nHost: {self.host}\r\n"
            f"Accept-Encoding: gzip, zstd\r\n{length}\r\n"
        ).encode() + body


def responses(count: int, fixtures: list[Fixture] | None = None) -> list[Replay]:
    """Return `count` distinct responses, cycling through fixtures, encodings and framings."""
    fixtures = fixtures or load()
    variants: list[tuple[Encoding, Framing]] = [(e, f) for e in ENCODINGS for f in FRAMINGS]
    result: list[Replay] = []
    for index in range(count):
        fixture = fixtures[index % len(fixtures)]
        encoding: Encoding
        framing: Framing
        encoding, framing = variants[(index // len(fixtures)) % len(variants)]
        if not fixture.has_body:
            encoding, framing = "identity", "length"
        result.append(
            Replay(index, fixture, encoding, framing, render(fixture, index, encoding, framing))
        )
    return result


def render(fixture: Fixture, seed: int, encoding: Encoding, framing: Framing) -> bytes:
    """Return the raw response bytes for `fixture` filled from `seed`."""
    head = _fill(fixture.head, seed).split("\n")
    if not fixture.has_body:
        return ("\r\n".join(head) + "\r\n\r\n").encode()
    if fixture.random_body:
        body = random.Random(seed).randbytes(fixture.random_body)  # noqa: S311 - test data
    else:
        body = _fill(fixture.body, seed).encode()
    if encoding == "gzip":
        body = gzip.compress(body, mtime=0)
        head.append("Content-Encoding: gzip")
    elif encoding == "zstd":
        body = zstd.compress(body)
        head.append("Content-Encoding: zstd")
    if framing == "length":
        head.append(f"Content-Length: {len(body)}")
        return ("\r\n".join(head) + "\r\n\r\n").encode() + body
    head.append("Transfer-Encoding: chunked")
    chunks = b"".join(
        f"{len(piece):x}\r\n".encode() + piece + b"\r\n"
        for piece in (body[i : i + _CHUNK] for i in range(0, len(body), _CHUNK))
    )
    return ("\r\n".join(head) + "\r\n\r\n").encode() + chunks + b"0\r\n\r\n"


def _fill(template: str, seed: int) -> str:
    digest = hashlib.sha256(str(seed).encode()).hexdigest()
    return (
        template.replace("{{n}}", str(seed + 1))
        .replace("{{hex12}}", digest[:12])
        .replace("{{hex}}", digest[:32])
        .replace("{{octet}}", str(seed % 254 + 1))
        .replace("{{port}}", str(50000 + seed % 10000))
    )


class FakeRoblox:
    """The fake server. `async with FakeRoblox() as server:` gives `server.port`."""

    def __init__(
        self,
        replays: list[Replay] | None = None,
        *,
        mode: Mode = "normal",
        now: datetime | None = None,
    ) -> None:
        self.replays = {replay.index: replay for replay in replays or []}
        self.mode = mode
        self.now = now or datetime.now(UTC)
        self.authority = resin.create_authority(self.now)
        self.port = 0
        self.sni: list[str | None] = []
        self.requests: list[bytes] = []
        self._server: asyncio.Server | None = None
        self._contexts: dict[str, ssl.SSLContext] = {}
        self._folder = tempfile.TemporaryDirectory(prefix="fake-roblox-")

    @property
    def ca_pem(self) -> str:
        """The test CA a client must trust to talk to this server directly."""
        return resin.certificate_pem(self.authority.certificate).decode()

    def client_context(self) -> ssl.SSLContext:
        """A client context that trusts only this server's test CA (TLS 1.2 or newer)."""
        context = ssl.create_default_context(cadata=self.ca_pem)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        return context

    async def __aenter__(self) -> FakeRoblox:
        default = self._context_for(HOSTS[0])
        default.sni_callback = self._pick
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0, ssl=default)
        self.port = int(self._server.sockets[0].getsockname()[1])
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._server.wait_closed(), timeout=2)
        self._folder.cleanup()

    def _pick(self, connection: ssl.SSLObject, name: str | None, _context: object) -> None:
        self.sni.append(name)
        connection.context = self._context_for(name or HOSTS[0])

    def _context_for(self, host: str) -> ssl.SSLContext:
        if host in self._contexts:
            return self._contexts[host]
        if self.mode == "self_signed":
            leaf = resin.issue_leaf(resin.create_authority(self.now), host, self.now)
            leaf = resin.Leaf(_self_signed(leaf, host, self.now), leaf.key)
        else:
            name = "wrong.example.com" if self.mode == "wrong_host" else host
            leaf = resin.issue_leaf(self.authority, name, self.now)
        folder = Path(self._folder.name)
        cert, key = folder / f"{host}.pem", folder / f"{host}.key"
        cert.write_bytes(resin.certificate_pem(leaf.certificate))
        key.write_bytes(
            leaf.key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        context.set_alpn_protocols(["http/1.1"])
        if self.mode == "tls11":
            # Really offer TLS 1.1 (OpenSSL 3 needs security level 0 for it), so a refusal is
            # the client's own policy.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                context.minimum_version = ssl.TLSVersion.TLSv1
                context.maximum_version = ssl.TLSVersion.TLSv1_1
            context.set_ciphers("DEFAULT:@SECLEVEL=0")
        self._contexts[host] = context
        return context

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                head = await reader.readuntil(b"\r\n\r\n")
                length = 0
                for line in head.split(b"\r\n")[1:]:
                    name, _, value = line.partition(b":")
                    if name.strip().lower() == b"content-length":
                        length = int(value)
                body = await reader.readexactly(length) if length else b""
                self.requests.append(head + body)
                writer.write(self._answer(head.split(b" ", 2)[1]))
                await writer.drain()
        except asyncio.IncompleteReadError, ConnectionError, ssl.SSLError:
            pass
        finally:
            writer.close()

    def _answer(self, target: bytes) -> bytes:
        _, _, query = target.partition(b"?")
        for part in query.split(b"&"):
            name, _, value = part.partition(b"=")
            if name == b"replay" and value.isdigit() and int(value) in self.replays:
                return self.replays[int(value)].raw
        return b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n"


def _self_signed(leaf: resin.Leaf, host: str, now: datetime) -> x509.Certificate:
    """The leaf's certificate signed by its own key: trusted by no CA."""
    certificate = leaf.certificate
    builder = (
        x509.CertificateBuilder()
        .subject_name(certificate.subject)
        .issuer_name(certificate.subject)
        .public_key(leaf.key.public_key())
        .serial_number(certificate.serial_number)
        .not_valid_before(now - resin.BACKDATE)
        .not_valid_after(now + resin.LEAF_VALIDITY)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]), critical=False)
    )
    return builder.sign(leaf.key, hashes.SHA256())


async def _serve(ca_out: Path | None, count: int) -> None:
    async with FakeRoblox(responses(count)) as server:
        if ca_out is not None:
            ca_out.write_text(server.ca_pem, encoding="utf-8")
        print(f"fake Roblox on 127.0.0.1:{server.port}, {count} responses, hosts: {HOSTS}")
        await asyncio.Event().wait()


def main(argv: list[str] | None = None) -> int:
    """Serve the fixtures until interrupted."""
    parser = argparse.ArgumentParser(description="Serve the fake Roblox fixtures over TLS.")
    parser.add_argument("--ca-out", type=Path, help="write the test CA certificate here")
    parser.add_argument("--count", type=int, default=1000, help="responses to serve")
    args = parser.parse_args(argv)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_serve(args.ca_out, args.count))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
