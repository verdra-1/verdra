# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""One connection: HTTP/1.1 through h11, keep-alive, chunked bodies, the symbiont pipeline.

Spec S-11, interception. For a host in the active interception set, roots/mycelium answers the
CONNECT and hands the connection here. Verdra terminates TLS with an S-10 leaf certificate held
only in memory (TLS 1.2 and 1.3, ALPN http/1.1), reads each request with h11, runs the request
symbionts, forwards it upstream over roots/taproot's verified TLS, runs the response symbionts
and answers the client.

- A body is buffered only when a symbiont asks for it, up to 64 MB; beyond that it is streamed
  and those symbionts are skipped for that message (S-11 rule 1). Request and response bodies
  are decoded for the symbionts (identity, gzip, deflate, zstd; RFC 9110 section 8.4), within
  plan 10.7's limits: at most 100 times the received size and never over the buffer limit.
  A body that can't be decoded (another encoding, damaged data, over a limit) is streamed as is,
  and each symbiont that asked for it hears why through its optional `on_unread`.
- Unmodified messages keep their status, headers (names, case, order) and body bytes, including
  their content encoding; chunked bodies keep their chunk sizes. Modified bodies are sent decoded
  (no Content-Encoding) with a correct Content-Length.
- An exception in a symbiont is logged, redacted, and that symbiont is skipped for that message;
  the request still completes (S-11 rule 3).
- An upstream certificate that doesn't verify answers the client with HTTP 502, writes M-PROXY-02
  to Activity and calls `on_verification_failure` (the routing status turns Degraded, S-14).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import ssl
import zlib
from collections.abc import Awaitable, Callable, Collection, Sequence
from compression import zstd
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Final, Literal, Protocol

import h11
from cryptography.hazmat.primitives import serialization
from PySide6.QtCore import QCoreApplication

from verdra.bark import resin, veil
from verdra.roots import rules, taproot
from verdra.soil import humus

log = logging.getLogger(__name__)

#: S-11 rule 1: the largest body Verdra buffers for a symbiont.
MAX_BUFFERED_BODY: Final = 64 * 1024 * 1024
#: Plan 10.7: a compressed body may decode to at most this many times its size,
MAX_RATIO: Final = 100
#: and to at most this size (the buffer limit above is lower, so it applies first).
MAX_DECODED: Final = 1024 * 1024 * 1024
#: Leaves are issued again this long before they expire.
LEAF_RENEW_BEFORE: Final = resin.BACKDATE
_CHUNK: Final = 64 * 1024
#: A chunk of a chunked body is forwarded whole up to this size, then in pieces.
_MAX_PIECE: Final = 1024 * 1024
_MAX_HEAD_BYTES: Final = 64 * 1024
_FRAMING: Final = frozenset({b"content-length", b"transfer-encoding", b"content-encoding"})
_NO_BODY_STATUSES: Final = frozenset({204, 304})

Headers = tuple[tuple[bytes, bytes], ...]
Streams = tuple[asyncio.StreamReader, asyncio.StreamWriter]
Opener = Callable[[str, int], Awaitable[Streams]]
#: Called with (host, side, TLS object) after each handshake; side is "client" or "upstream".
TlsObserver = Callable[[str, Literal["client", "upstream"], ssl.SSLObject], None]


@dataclass(frozen=True, slots=True)
class Request:
    """An HTTP request as symbionts see it.

    `body` is None unless a symbiont asked for it, and then it is the decoded content;
    `coding` is the content coding it was sent with ("" for none).
    """

    host: str
    method: bytes
    target: bytes
    headers: Headers
    body: bytes | None = None
    coding: str = ""


@dataclass(frozen=True, slots=True)
class Response:
    """An HTTP response as symbionts see it. `body` is the decoded content when buffered."""

    status: int
    headers: Headers
    reason: bytes = b""
    body: bytes | None = None


class Symbiont(Protocol):
    """A request or response handler in the proxy pipeline (Reference R1, roots/symbionts)."""

    @property
    def name(self) -> str:
        """The symbiont's name in log lines."""
        ...

    def wants_request_body(self, request: Request) -> bool:
        """Return whether `on_request` needs the request body."""
        ...

    def on_request(self, request: Request) -> Request | Response | None:
        """Return a changed request, a response to answer with, or None to leave it."""
        ...

    def wants_response_body(self, request: Request, response: Response) -> bool:
        """Return whether `on_response` needs the response body."""
        ...

    def on_response(self, request: Request, response: Response) -> Response | None:
        """Return a changed response, or None to leave it."""
        ...


class Unread(Protocol):
    """A symbiont that wants to hear when a body it asked for couldn't be read (optional)."""

    def on_unread(self, request: Request, response: Response | None, reason: str) -> None:
        """The body of `request` (or of `response`, when given) couldn't be read: `reason`."""
        ...


@dataclass(frozen=True, slots=True)
class Decoded:
    """A body without its content codings, or why it couldn't be decoded (`body` None)."""

    body: bytes | None
    #: The content codings as received, outermost last ("" for none).
    coding: str = ""
    problem: str = ""


@dataclass(frozen=True, slots=True)
class Pipeline:
    """The symbionts in order (S-11): request trail guard → grafter → forager; response
    forager → grafter → climate → mimicry. An empty pipeline changes nothing."""

    request: Sequence[Symbiont] = ()
    response: Sequence[Symbiont] = ()


class LeafContexts:
    """Server TLS contexts with an in-memory S-10 leaf per host, issued on first use."""

    def __init__(
        self, authority: resin.Authority, clock: Callable[[], datetime] | None = None
    ) -> None:
        self.authority = authority
        self.clock = clock or (lambda: datetime.now(UTC))
        self._contexts: dict[str, tuple[datetime, ssl.SSLContext]] = {}

    def context_for(self, host: str) -> ssl.SSLContext:
        """Return the server context for `host`, issuing a new leaf near expiry."""
        now = self.clock()
        cached = self._contexts.get(host)
        if cached is not None and now < cached[0]:
            return cached[1]
        leaf = resin.issue_leaf(self.authority, host, now)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.set_alpn_protocols(["http/1.1"])
        key = leaf.key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        humus.current().load_cert_chain(context, resin.certificate_pem(leaf.certificate), key)
        renew = leaf.certificate.not_valid_after_utc - LEAF_RENEW_BEFORE
        self._contexts[host] = (renew, context)
        return context


class Interception:
    """Decides which CONNECT targets are intercepted and serves them (used by roots/mycelium)."""

    def __init__(
        self,
        leaves: LeafContexts,
        hosts: Callable[[], Collection[str]],
        open_upstream: Opener,
        pipeline: Callable[[], Pipeline] = Pipeline,
        *,
        on_verification_failure: Callable[[str, str], None] | None = None,
        on_tls: TlsObserver | None = None,
        idle_timeout: float = 30.0,
        max_body: int = MAX_BUFFERED_BODY,
    ) -> None:
        self.leaves = leaves
        self.hosts = hosts
        self.open_upstream = open_upstream
        self.pipeline = pipeline
        self.on_verification_failure = on_verification_failure
        self.on_tls = on_tls
        self.idle_timeout = idle_timeout
        self.max_body = max_body

    def wants(self, host: str, port: int) -> bool:  # noqa: ARG002 - the set holds hosts only
        """Return whether a CONNECT to host:port is intercepted (S-11 rule 5)."""
        return rules.host_name(host) in self.hosts()  # any case, with or without the root dot

    async def serve(
        self, host: str, port: int, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Terminate the client's TLS with a leaf for `host` and serve its requests."""
        await writer.start_tls(
            self.leaves.context_for(host.lower()), ssl_handshake_timeout=self.idle_timeout
        )
        self.observe(host, "client", writer)
        try:
            await Hyphae(self, host, port).serve(reader, writer)
        except h11.ProtocolError as error:
            log.debug("Closed a connection to %s: %s", host, error)

    def observe(
        self, host: str, side: Literal["client", "upstream"], writer: asyncio.StreamWriter
    ) -> None:
        """Report a finished handshake to `on_tls`; an observer's error never fails a request."""
        tls = writer.get_extra_info("ssl_object")
        if self.on_tls is None or not isinstance(tls, ssl.SSLObject):
            return
        try:
            self.on_tls(host, side, tls)
        except Exception as error:  # noqa: BLE001 - observing must not break the connection
            log.debug("The TLS observer failed on %s: %s", host, type(error).__name__)


class ClientLeftError(ConnectionError):
    """The client closed its connection while Verdra was still writing to it."""


@dataclass(slots=True)
class _Side:
    """One h11 connection and the stream under it."""

    conn: h11.Connection
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    timeout: float
    client: bool = False

    async def next_event(self) -> object:
        while True:
            event = self.conn.next_event()
            if event is not h11.NEED_DATA:
                return event
            if self.conn.they_are_waiting_for_100_continue:
                await self.send(
                    h11.InformationalResponse(status_code=100, headers=[], reason=b"Continue")
                )
            data = await asyncio.wait_for(self.reader.read(_CHUNK), timeout=self.timeout)
            self.conn.receive_data(data)

    async def send(self, *events: h11.Event) -> None:
        for event in events:
            data = self.conn.send(event)
            if data:
                self.writer.write(data)
        try:
            await self.writer.drain()
        except OSError as error:
            if self.client:
                raise ClientLeftError from error
            raise


class Body:
    """A message body read from one side: whole chunks (up to 1 MB), then the trailers."""

    def __init__(self, side: _Side) -> None:
        self.side = side
        self.trailers: list[tuple[bytes, bytes]] = []
        self.done = False
        self._in_chunk = False

    async def next(self) -> bytes | None:
        """Return the next piece, or None at the end of the body."""
        if self.done:
            return None
        piece = bytearray()
        while True:
            event = await self.side.next_event()
            if isinstance(event, h11.Data):
                piece += event.data
                if event.chunk_start:
                    self._in_chunk = True
                if event.chunk_end:
                    self._in_chunk = False
                if piece and (not self._in_chunk or len(piece) >= _MAX_PIECE):
                    return bytes(piece)
                continue
            if isinstance(event, h11.EndOfMessage):
                self.trailers = list(event.headers.raw_items())
                self.done = True
                return bytes(piece) if piece else None
            raise h11.RemoteProtocolError(f"unexpected {type(event).__name__} in a body")

    async def drain(self) -> None:
        """Read and drop the rest of the body."""
        while await self.next() is not None:
            pass


@dataclass(slots=True)
class _Buffered:
    """A body read into memory for the symbionts, or as much as fit (`complete` False)."""

    pieces: list[bytes] = field(default_factory=list[bytes])
    complete: bool = True

    @property
    def data(self) -> bytes:
        return b"".join(self.pieces)


class Hyphae:
    """One intercepted client connection, with keep-alive on both sides."""

    def __init__(self, interception: Interception, host: str, port: int) -> None:
        self.interception = interception
        self.host = host
        self.port = port
        self.timeout = interception.idle_timeout
        self.upstream: _Side | None = None

    async def serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Serve requests until either side closes, a framing error, or the idle timeout."""
        client = _Side(
            h11.Connection(h11.SERVER, max_incomplete_event_size=_MAX_HEAD_BYTES),
            reader,
            writer,
            self.timeout,
            client=True,
        )
        try:
            while True:
                event = await client.next_event()
                if not isinstance(event, h11.Request):
                    return
                await self._exchange(client, event)
                if client.conn.our_state is not h11.DONE or client.conn.their_state is not h11.DONE:
                    return
                client.conn.start_next_cycle()
        except h11.RemoteProtocolError as error:
            log.debug("Closed a connection to %s: %s", self.host, error)
            if client.conn.our_state in (h11.IDLE, h11.SEND_RESPONSE):
                with contextlib.suppress(h11.LocalProtocolError, OSError):
                    await client.send(*_plain(400, b"Bad Request"))
        finally:
            await self._close_upstream()

    async def _exchange(self, client: _Side, head: h11.Request) -> None:
        pipeline = self.interception.pipeline()
        if rules.is_protected(self.host, head.target):
            # Plan 16.2: Roblox's integrity and safety traffic is never touched.
            log.debug("Protected endpoint on %s passed through unchanged", self.host)
            pipeline = Pipeline()
        request = Request(self.host, head.method, head.target, tuple(head.headers.raw_items()))
        log.debug("%s %s %s", request.method.decode("latin-1"), self.host, _target_for_log(request))
        body = Body(client)
        buffered: _Buffered | None = None
        unread = ""
        if self._any_wants(pipeline.request, "wants_request_body", request):
            buffered = await self._buffer(body)
            request, unread = self._decoded(request, buffered)
        original = request
        answer: Response | None = None
        for symbiont in pipeline.request:
            if request.body is None and _wants(symbiont, request):
                if unread:
                    _call(symbiont, "on_unread", request, None, unread)
                continue
            result = _call(symbiont, "on_request", request)
            if isinstance(result, Response):
                answer = result
                break
            if isinstance(result, Request):
                request = result
        if answer is not None:
            await body.drain()
            await client.send(*_complete(answer, head_only=head.method == b"HEAD"))
            return
        try:
            upstream = await self._upstream()
            await self._send_request(upstream, original, request, buffered, body)
            await self._relay_response(client, upstream, request, pipeline)
        except taproot.UpstreamVerificationError as error:
            log.warning(
                "%s",
                QCoreApplication.translate(
                    "M-PROXY-02",
                    "A Roblox server's certificate couldn't be verified ({host}). That request "
                    "was blocked.",
                ).format(host=error.host),
            )
            callback = self.interception.on_verification_failure
            if callback is not None:
                callback(error.host, error.reason)
            await self._fail(client, error)
        except ClientLeftError as error:
            # Not an upstream failure: Roblox stopped reading (it drops video segments it no
            # longer needs, for example). Nothing can be answered on a closed connection.
            log.debug("The client left %s mid-response: %s", self.host, error.__cause__)
            await self._close_upstream()
            raise h11.RemoteProtocolError("the client left") from error
        except (OSError, TimeoutError, h11.ProtocolError) as error:
            log.debug("Upstream %s failed: %s", self.host, veil.redact_text(str(error)))
            await self._fail(client, error)

    async def _fail(self, client: _Side, error: BaseException) -> None:
        """Answer 502 if nothing was sent yet, then close the connection."""
        await self._close_upstream()
        if client.conn.our_state is h11.SEND_RESPONSE:
            with contextlib.suppress(h11.LocalProtocolError, OSError):
                await client.send(*_plain(502, b"Bad Gateway"))
        raise h11.RemoteProtocolError(f"upstream failed: {type(error).__name__}")

    async def _upstream(self) -> _Side:
        side = self.upstream
        if side is not None and (side.conn.our_state is not h11.IDLE or side.reader.at_eof()):
            await self._close_upstream()
            side = None
        if side is None:
            reader, writer = await asyncio.wait_for(
                self.interception.open_upstream(self.host, self.port), timeout=self.timeout
            )
            side = _Side(h11.Connection(h11.CLIENT), reader, writer, self.timeout)
            self.upstream = side
            self.interception.observe(self.host, "upstream", writer)
        return side

    async def _close_upstream(self) -> None:
        side, self.upstream = self.upstream, None
        if side is not None:
            side.writer.close()
            with contextlib.suppress(OSError, ssl.SSLError, TimeoutError):
                await asyncio.wait_for(side.writer.wait_closed(), timeout=1)

    async def _send_request(
        self,
        upstream: _Side,
        original: Request,
        request: Request,
        buffered: _Buffered | None,
        body: Body,
    ) -> None:
        if request.body is not None and request.body != original.body:
            await body.drain()
            headers = _with_length(request.headers, len(request.body))
            await upstream.send(
                h11.Request(method=request.method, target=request.target, headers=headers),
                h11.Data(data=request.body),
                h11.EndOfMessage(),
            )
            return
        await upstream.send(
            h11.Request(method=request.method, target=request.target, headers=list(request.headers))
        )
        await _forward(upstream, buffered, body)

    async def _relay_response(
        self, client: _Side, upstream: _Side, request: Request, pipeline: Pipeline
    ) -> None:
        response = await _response_head(upstream, client)
        body = Body(upstream)
        has_body = request.method != b"HEAD" and response.status not in _NO_BODY_STATUSES
        buffered: _Buffered | None = None
        decoded: bytes | None = None
        unread = ""
        if has_body and self._any_wants(
            pipeline.response, "wants_response_body", request, response
        ):
            buffered = await self._buffer(body)
            if buffered.complete:
                read = decode(response.headers, buffered.data, self.interception.max_body)
                decoded, unread = read.body, read.problem
            else:
                unread = "over 64 MB"
            if decoded is None:
                log.debug(
                    "Response from %s streamed without the symbionts that read it (%s)",
                    self.host,
                    unread,
                )
        result = replace(response, body=decoded)
        for symbiont in pipeline.response:
            if decoded is None and _wants(symbiont, request, response):
                if unread:
                    _call(symbiont, "on_unread", request, response, unread)
                continue
            changed = _call(symbiont, "on_response", request, result)
            if isinstance(changed, Response):
                result = changed
        if result.body is not None and result.body != decoded:
            await body.drain()
            await client.send(*_complete(result, head_only=not has_body))
        else:
            await client.send(
                h11.Response(
                    status_code=result.status, headers=list(result.headers), reason=result.reason
                )
            )
            await _forward(client, buffered, body)
        if upstream.conn.our_state is h11.DONE and upstream.conn.their_state is h11.DONE:
            upstream.conn.start_next_cycle()
        else:
            await self._close_upstream()

    def _decoded(self, request: Request, buffered: _Buffered) -> tuple[Request, str]:
        """The request with its decoded body, and why there is none ("" when there is)."""
        if not buffered.complete:
            return request, "over 64 MB"
        decoded = decode(request.headers, buffered.data, self.interception.max_body)
        return replace(request, body=decoded.body, coding=decoded.coding), decoded.problem

    async def _buffer(self, body: Body) -> _Buffered:
        buffered = _Buffered()
        size = 0
        while (piece := await body.next()) is not None:
            buffered.pieces.append(piece)
            size += len(piece)
            if size > self.interception.max_body:
                buffered.complete = False
                log.info(
                    "%s",
                    QCoreApplication.translate(
                        "M-PROXY-05",
                        "A request or response for {host} was over 64 MB, so Verdra passed it "
                        "on without changing it.",
                    ).format(host=self.host),
                )
                break
        return buffered

    def _any_wants(self, symbionts: Sequence[Symbiont], method: str, *args: object) -> bool:
        return any(_call(symbiont, method, *args) is True for symbiont in symbionts)


async def _response_head(upstream: _Side, client: _Side) -> Response:
    """Read the final response head, passing any 1xx responses on to the client."""
    while True:
        event = await upstream.next_event()
        if isinstance(event, h11.InformationalResponse):
            await client.send(event)
            continue
        if not isinstance(event, h11.Response):
            raise h11.RemoteProtocolError("the server closed without a response")
        return Response(event.status_code, tuple(event.headers.raw_items()), event.reason)


async def _forward(side: _Side, buffered: _Buffered | None, body: Body) -> None:
    """Send what was buffered, stream the rest of the body, then the trailers."""
    for piece in buffered.pieces if buffered is not None else ():
        await side.send(h11.Data(data=piece))
    while (piece := await body.next()) is not None:
        await side.send(h11.Data(data=piece))
    await side.send(h11.EndOfMessage(headers=body.trailers))


def _wants(symbiont: Symbiont, request: Request, response: Response | None = None) -> bool:
    if response is None:
        return _call(symbiont, "wants_request_body", request) is True
    return _call(symbiont, "wants_response_body", request, response) is True


def _call(symbiont: Symbiont, method: str, *args: object) -> object:
    """Call a symbiont; an exception is logged (redacted) and counts as "no change".

    A symbiont without the method (the optional `on_unread`) is left alone.
    """
    function = getattr(symbiont, method, None)
    if function is None:
        return None
    try:
        return function(*args)
    except Exception as error:  # noqa: BLE001 - S-11 rule 3: a symbiont never fails a request
        host = next((arg.host for arg in args if isinstance(arg, Request)), "")
        log.debug(
            "%s.%s raised on %s", getattr(symbiont, "name", type(symbiont).__name__), method, host
        )
        log.warning(
            "%s",
            QCoreApplication.translate(
                "M-PROXY-04",
                "Part of a feature failed on {host}, so it was skipped for that request ({error}).",
            ).format(host=host, error=veil.redact_text(f"{type(error).__name__}: {error}")),
        )
        return None


def decode(headers: Headers, data: bytes, limit: int = MAX_BUFFERED_BODY) -> Decoded:
    """Return the body without its content codings (RFC 9110 section 8.4), within the limits.

    gzip (RFC 1952), deflate (zlib, RFC 1950, or raw, RFC 1951, as some servers send it) and
    zstd (RFC 8878) are decoded, outermost first. The decoded body may be at most `MAX_RATIO`
    times the received size and at most `limit` (plan 10.7), checked while decoding, so a
    small compressed body can't grow without bound in memory.
    """
    codings = [
        coding.strip().lower().decode("latin-1")
        for name, value in headers
        if name.lower() == b"content-encoding"
        for coding in value.split(b",")
        if coding.strip()
    ]
    named = ", ".join(codings)
    ceiling = min(limit, MAX_DECODED, MAX_RATIO * len(data))
    for coding in reversed(codings):
        if coding == "identity":
            continue
        if coding not in _DECODERS:
            return Decoded(None, named, f"compressed as {coding}, which Verdra can't read")
        try:
            data = _DECODERS[coding](data, ceiling)
        except _TooLargeError:
            return Decoded(None, named, f"{coding} data that would be too large once decompressed")
        except (zlib.error, zstd.ZstdError, EOFError) as error:
            log.debug("A body couldn't be decoded: %s", error)
            return Decoded(None, named, f"damaged {coding} data")
    return Decoded(data, named if any(c != "identity" for c in codings) else "")


class _TooLargeError(Exception):
    """A body would decode to more than its limit."""


def _inflate(data: bytes, ceiling: int, wbits: int) -> bytes:
    """Decode zlib, raw deflate or gzip data (every gzip member), never past `ceiling`."""
    out = bytearray()
    while True:
        inflater = zlib.decompressobj(wbits)
        out += inflater.decompress(data, ceiling + 1 - len(out))
        if len(out) > ceiling:
            raise _TooLargeError
        if not inflater.eof:
            # Stopped early: input left over (only when the output reached its cap) or cut short.
            if inflater.unconsumed_tail:
                raise _TooLargeError
            msg = "the compressed data ends early"
            raise EOFError(msg)
        data = inflater.unused_data
        if wbits != 31 or not data:  # gzip allows several members, one after another
            return bytes(out)


def _gunzip(data: bytes, ceiling: int) -> bytes:
    return _inflate(data, ceiling, 31)


def _inflate_deflate(data: bytes, ceiling: int) -> bytes:
    try:
        return _inflate(data, ceiling, 15)
    except zlib.error:
        return _inflate(data, ceiling, -15)


def _unzstd(data: bytes, ceiling: int) -> bytes:
    out = bytearray()
    while True:
        decompressor = zstd.ZstdDecompressor()
        out += decompressor.decompress(data, ceiling + 1 - len(out))
        if len(out) > ceiling:
            raise _TooLargeError
        if not decompressor.eof:
            if not decompressor.needs_input:
                raise _TooLargeError
            msg = "the compressed data ends early"
            raise EOFError(msg)
        data = decompressor.unused_data
        if not data:  # zstd allows several frames, one after another
            return bytes(out)


_DECODERS: Final[dict[str, Callable[[bytes, int], bytes]]] = {
    "gzip": _gunzip,
    "x-gzip": _gunzip,
    "deflate": _inflate_deflate,
    "zstd": _unzstd,
}


def _with_length(headers: Headers, length: int) -> list[tuple[bytes, bytes]]:
    kept = [(name, value) for name, value in headers if name.lower() not in _FRAMING]
    return [*kept, (b"Content-Length", str(length).encode())]


def _complete(response: Response, *, head_only: bool) -> tuple[h11.Event, ...]:
    """A whole response with a decoded body and a correct Content-Length."""
    body = response.body or b""
    head = h11.Response(
        status_code=response.status,
        headers=_with_length(response.headers, len(body)),
        reason=response.reason,
    )
    if head_only or not body:
        return head, h11.EndOfMessage()
    return head, h11.Data(data=body), h11.EndOfMessage()


def _plain(status: int, reason: bytes) -> tuple[h11.Event, ...]:
    return (
        h11.Response(
            status_code=status,
            headers=[(b"Content-Length", b"0"), (b"Connection", b"close")],
            reason=reason,
        ),
        h11.EndOfMessage(),
    )


def _target_for_log(request: Request) -> str:
    return veil.redact_text(request.target.decode("latin-1"))
