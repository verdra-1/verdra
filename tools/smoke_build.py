# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Smoke test of routing in a running Verdra: the built app, or a source run for comparison.

Written after the M2 final test of 15 October 2026: the release dry-run ZIP routed nothing that
Verdra intercepts, while a source run on the same PC minutes earlier did, and its log had no
line about it. This test runs Verdra as a user does and checks what Roblox relies on:

1. Verdra starts routing by itself (setup done, "Route on launch" on) and adds its certificate
   to the Player's trust file. The Player is a fake install in a throwaway `%LOCALAPPDATA%`:
   a version folder with an empty `RobloxPlayerBeta.exe` and `ssl\\cacert.pem` (W-01, W-05).
2. Pass-through: a CONNECT to a host Verdra doesn't intercept reaches it, both ways.
3. A picture replacement, end to end: the saved profile replaces asset 1111111 with a local
   PNG (a File replacement, so Verdra decrypts the asset batch host and the CDN host and
   prepares the picture at start-up). A stand-in Player, trusting only the certificates in the
   fake Player's `cacert.pem` as the Player does, asks for the asset's batch entry and
   downloads it, through Verdra. Verdra's own upstream is a fake Roblox (`FakeUpstream`): an
   HTTP proxy, set as Verdra's internet connection, that answers for `assetdelivery.roblox.com`
   and `fts.rbxcdn.com` with a test CA's certificates and an original picture. The download
   must come back as the replacement, and the log must say so. Nothing reaches Roblox.

   Verdra verifies upstream certificates against the system's trust store, always. So the test
   CA is added to it for the run and removed afterwards, only where that is a throwaway machine:
   a GitHub Actions runner (Windows: the machine's Root store). From source on Linux (paused)
   `SSL_CERT_FILE` names a bundle with it instead. Anywhere else the check is skipped and says
   so.

4. Launch: Verdra is started with a `roblox-player:` link, so it launches the fake Player, a
   small program compiled on the runner that writes the environment it was given and the DLL
   directory it inherited. The Player must get the proxy variables and nothing of Verdra's own
   build: no variable pointing into the built app's folder (PyInstaller's runtime hooks put its
   `_internal` folder first on PATH and set QT_PLUGIN_PATH for Verdra's own Qt), and no
   inherited DLL directory. On Linux (paused) the Player is an empty file and isn't launched.

Everything stays in throwaway folders (`VERDRA_HOME`), except what Verdra writes for any user:
its CA key in the secret store and, while routing, its `roblox-player:` link handler. On a CI
runner both go with the machine.

Usage:
    uv run python tools/smoke_build.py dist/Verdra      the built app (verdra.exe)
    uv run python tools/smoke_build.py --source         `python -m verdra` from this checkout
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402

from verdra.bark import resin  # noqa: E402 - found through the path added above
from verdra.soil import terrain  # noqa: E402
from verdra.strata import ochre  # noqa: E402

#: Seconds to wait for routing after the start (the window is ready in ~2 s on a runner).
ROUTING_TIMEOUT_S = 90.0
ROUTING = "Routing status changed from Idle to Routing"
INTERCEPTED_HOST = "assetdelivery.roblox.com"
CONTENT_HOST = "fts.rbxcdn.com"
#: The asset the saved profile replaces, and the colors of its original and its replacement.
ASSET = 1111111
ORIGINAL_RGBA = (255, 0, 0, 255)
REPLACEMENT_RGBA = (0, 160, 0, 255)
PICTURE_SIDE = 64
#: The log lines that show the replacement was served (Detailed logging is on).
SERVED = f"Served the replacement for asset {ASSET}"
NOT_REACHING = "Roblox isn't reaching Verdra"
#: A link Verdra accepts and passes to the Player unchanged (S-12).
LINK = "roblox-player:1+launchmode:app"
#: The fake Player: writes its environment and inherited DLL directory next to itself.
FAKE_PLAYER = r"""
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
public static class Player {
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    static extern uint GetDllDirectoryW(uint length, StringBuilder buffer);
    public static void Main(string[] args) {
        var lines = new StringBuilder();
        var dll = new StringBuilder(4096);
        GetDllDirectoryW(4096, dll);
        lines.AppendLine("DLL_DIRECTORY=" + dll.ToString());
        foreach (System.Collections.DictionaryEntry e in Environment.GetEnvironmentVariables())
            lines.AppendLine(e.Key + "=" + e.Value);
        File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "env.txt"),
            lines.ToString());
    }
}
"""
VERSION_FOLDER = "version-0000000000smoke"


@dataclass
class Result:
    """What the smoke test found; `problems` empty means it passed."""

    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def fake_player(local: Path) -> Path:
    """A fake per-user Player install; return its trust file."""
    folder = local / "Roblox" / "Versions" / VERSION_FOLDER
    (folder / "ssl").mkdir(parents=True)
    player = folder / "RobloxPlayerBeta.exe"
    if sys.platform == "win32":
        source = folder.parent / "player.cs"
        source.write_text(FAKE_PLAYER, encoding="utf-8")
        script = (
            f"Add-Type -Path '{source}' -OutputAssembly '{player}' -OutputType ConsoleApplication"
        )
        subprocess.run(  # noqa: S603
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],  # noqa: S607
            check=True,
        )
        source.unlink()
    else:
        player.write_bytes(b"")
    trust = folder / "ssl" / "cacert.pem"
    trust.write_bytes(b"")
    return trust


def settings(home: Path, port: int, upstream: int) -> None:
    """Setup done, routing on launch, this proxy port, the fake upstream, detailed logging."""
    path = home / "config" / terrain.SETTINGS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "format": "verdra.settings",
        "version": 1,
        "general": {"onboarding_done": True, "route_on_launch": True},
        "routing": {
            "proxy_port": port,
            "handle_roblox_links": False,
            "upstream": {"kind": "http", "host": "127.0.0.1", "port": upstream},
        },
        "advanced": {
            "detailed_logging": True,
            "detailed_logging_since": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        },
    }
    path.write_text(json.dumps(document), encoding="utf-8")


def picture(rgba: tuple[int, int, int, int]) -> bytes:
    """A PNG of one color, PICTURE_SIDE pixels square."""
    pixels = ochre.Pixels(PICTURE_SIDE, PICTURE_SIDE, bytes(rgba) * PICTURE_SIDE * PICTURE_SIDE)
    return ochre.to_png(pixels)


def profile(home: Path) -> None:
    """One saved replacement: asset ASSET by a local PNG (a File replacement), so Verdra
    decrypts the asset batch host and the CDN host (plan 10.1) and serves the picture itself."""
    from verdra.trunk.branches import grafts  # noqa: PLC0415 - the repository's own writer

    replacement = home / "replacement.png"
    replacement.write_bytes(picture(REPLACEMENT_RGBA))
    now = datetime.now(UTC)
    saved = grafts.Profile(
        id="00000000-0000-4000-8000-000000000001",
        name="Smoke",
        created=now,
        modified=now,
        replacements=[
            grafts.Replacement(
                id="00000000-0000-4000-8000-000000000002",
                original=grafts.Original(asset_id=ASSET),
                target=grafts.Target(kind="file", value=str(replacement)),
            )
        ],
    )
    folder = home / "config" / "profiles"
    folder.mkdir(parents=True, exist_ok=True)
    grafts.write_profile(folder / "Smoke.json", saved)


def echo_server() -> tuple[socket.socket, int]:
    """A loopback server that sends back what it gets, for the pass-through check."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()

    def serve() -> None:
        while True:
            try:
                client, _address = server.accept()
            except OSError:
                return
            with client:
                data = client.recv(1024)
                client.sendall(data)

    threading.Thread(target=serve, daemon=True).start()
    return server, server.getsockname()[1]


def connect(proxy_port: int, host: str, port: int) -> socket.socket:
    """Open a tunnel through Verdra's proxy; raise if it answers anything but 200."""
    tunnel = socket.create_connection(("127.0.0.1", proxy_port), timeout=15)
    tunnel.sendall(f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode())
    head = b""
    while b"\r\n\r\n" not in head:
        chunk = tunnel.recv(1024)
        if not chunk:
            msg = "the proxy closed the connection before answering CONNECT"
            raise ConnectionError(msg)
        head += chunk
    status = head.split(b"\r\n", 1)[0].decode("latin-1")
    if " 200 " not in status + " ":
        tunnel.close()
        msg = f"the proxy answered {status!r}"
        raise ConnectionError(msg)
    return tunnel


def check_pass_through(proxy_port: int, result: Result) -> None:
    server, port = echo_server()
    try:
        with connect(proxy_port, "127.0.0.1", port) as tunnel:
            tunnel.sendall(b"verdra smoke")
            answer = tunnel.recv(1024)
        if answer != b"verdra smoke":
            result.problems.append(f"pass-through: got {answer!r} back")
        else:
            result.notes.append("pass-through: bytes went both ways")
    except OSError as error:
        result.problems.append(f"pass-through: {error}")
    finally:
        server.close()


def read_head(stream: socket.socket | ssl.SSLSocket) -> tuple[bytes, dict[str, str]]:
    """Read an HTTP head; return its first line and its headers (names in lower case)."""
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = stream.recv(1)
        if not chunk:
            msg = "the connection closed in the middle of a head"
            raise ConnectionError(msg)
        data += chunk
    first, *lines = data[:-4].decode("latin-1").split("\r\n")
    headers = {}
    for line in lines:
        name, _, value = line.partition(":")
        headers[name.strip().lower()] = value.strip()
    return first.encode("latin-1"), headers


def read_exactly(stream: socket.socket | ssl.SSLSocket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = stream.recv(size - len(data))
        if not chunk:
            msg = "the connection closed in the middle of a body"
            raise ConnectionError(msg)
        data += chunk
    return data


def read_body(stream: socket.socket | ssl.SSLSocket, headers: dict[str, str]) -> bytes:
    """Read a body framed by Content-Length or chunked transfer coding."""
    if headers.get("transfer-encoding", "").lower() == "chunked":
        body = b""
        while True:
            size_line = read_line(stream)
            size = int(size_line.split(b";")[0], 16)
            if size == 0:
                read_line(stream)  # the empty line after the last chunk (no trailers)
                return body
            body += read_exactly(stream, size)
            read_exactly(stream, 2)
    return read_exactly(stream, int(headers.get("content-length", "0")))


def read_line(stream: socket.socket | ssl.SSLSocket) -> bytes:
    line = b""
    while not line.endswith(b"\r\n"):
        chunk = stream.recv(1)
        if not chunk:
            msg = "the connection closed in the middle of a line"
            raise ConnectionError(msg)
        line += chunk
    return line[:-2]


class FakeUpstream:
    """A fake Roblox behind an HTTP proxy, for Verdra's own upstream connections.

    Every CONNECT is answered by this process: TLS with a test CA's certificate for the name
    asked for, then the asset batch (`assetdelivery.roblox.com`) or the original picture
    (`fts.rbxcdn.com`). What it was asked is kept in `requests` ("host method path").
    """

    def __init__(self, folder: Path) -> None:
        now = datetime.now(UTC)
        self.authority = resin.create_authority(now)
        self.ca = folder / "smoke-ca.pem"
        self.ca.write_bytes(resin.certificate_pem(self.authority.certificate))
        self.contexts = {
            host: self._context(folder, host, now) for host in (INTERCEPTED_HOST, CONTENT_HOST)
        }
        self.requests: list[str] = []
        self.server = socket.socket()
        self.server.bind(("127.0.0.1", 0))
        self.server.listen()
        self.port: int = self.server.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True).start()

    def _context(self, folder: Path, host: str, now: datetime) -> ssl.SSLContext:
        leaf = resin.issue_leaf(self.authority, host, now)
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
        return context

    def close(self) -> None:
        self.server.close()

    def _accept(self) -> None:
        while True:
            try:
                client, _address = self.server.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(client,), daemon=True).start()

    def _serve(self, client: socket.socket) -> None:
        with client, contextlib.suppress(OSError, ValueError):
            client.settimeout(30)
            first, _headers = read_head(client)
            host = first.split(b" ")[1].decode("latin-1").rpartition(":")[0]
            if host not in self.contexts:
                client.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
                return
            client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            with self.contexts[host].wrap_socket(client, server_side=True) as tls:
                while True:
                    try:
                        first, headers = read_head(tls)
                    except ConnectionError:
                        return
                    body = read_body(tls, headers)
                    method, path = first.decode("latin-1").split(" ")[:2]
                    self.requests.append(f"{host} {method} {path}")
                    tls.sendall(self._answer(host, method, path, body))

    def _answer(self, host: str, method: str, path: str, body: bytes) -> bytes:
        if host == INTERCEPTED_HOST and method == "POST" and path == "/v1/assets/batch":
            items = json.loads(body)
            answer = json.dumps(
                [
                    {
                        "requestId": item["requestId"],
                        "location": f"https://{CONTENT_HOST}/smoke/{item['assetId']}",
                        "assetTypeId": 1,
                        "isArchived": False,
                    }
                    for item in items
                ]
            ).encode()
            kind = b"application/json"
        elif host == CONTENT_HOST and method == "GET" and path == f"/smoke/{ASSET}":
            answer, kind = picture(ORIGINAL_RGBA), b"image/png"
        else:
            return b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n"
        return (
            b"HTTP/1.1 200 OK\r\nContent-Type: "
            + kind
            + b"\r\nContent-Length: "
            + str(len(answer)).encode()
            + b"\r\n\r\n"
            + answer
        )


@contextlib.contextmanager
def upstream_trust(ca: Path, environment: dict[str, str]) -> Iterator[str | None]:
    """Make the system trust the test CA for the run; yield None, or why it couldn't.

    Only on a throwaway machine: a GitHub Actions runner on Windows (the machine's Root store,
    removed again afterwards), or Linux, through `SSL_CERT_FILE` for Verdra alone.
    """
    if sys.platform != "win32":
        bundle = ca.with_name("bundle.pem")
        system = ssl.get_default_verify_paths().cafile
        extra = Path(system).read_bytes() if system and Path(system).exists() else b""
        bundle.write_bytes(extra + b"\n" + ca.read_bytes())
        environment["SSL_CERT_FILE"] = str(bundle)
        yield None
        return
    if os.environ.get("GITHUB_ACTIONS") != "true":
        yield "the test CA is only added to the trust store of a GitHub Actions runner"
        return
    serial = format(x509.load_pem_x509_certificate(ca.read_bytes()).serial_number, "x")
    subprocess.run(["certutil", "-addstore", "-f", "Root", str(ca)], check=True)  # noqa: S603, S607
    try:
        yield None
    finally:
        subprocess.run(["certutil", "-delstore", "Root", serial], check=False)  # noqa: S603, S607


def player_context(trust: Path) -> ssl.SSLContext:
    """Only the Player's trust file, like the Player: no system certificates."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cadata=trust.read_text(encoding="ascii"))
    return context


def fetch(proxy_port: int, trust: Path, host: str, request: bytes) -> tuple[str, bytes, str]:
    """Send one request to `host` through Verdra as the Player would; return the status line,
    the body and the issuer of the certificate Verdra showed."""
    with (
        connect(proxy_port, host, 443) as tunnel,
        player_context(trust).wrap_socket(tunnel, server_hostname=host) as tls,
    ):
        tls.settimeout(30)
        certificate = tls.getpeercert() or {}
        names = [pair for part in certificate.get("issuer", ()) for pair in part]
        issuer = next((value for key, value in names if key == "commonName"), "?")
        tls.sendall(request)
        first, headers = read_head(tls)
        return first.decode("latin-1"), read_body(tls, headers), issuer


def check_replacement(proxy_port: int, trust: Path, result: Result) -> None:
    """The stand-in Player asks for asset ASSET and downloads it; it must get the replacement."""
    batch = json.dumps([{"requestId": "smoke-1", "assetId": ASSET}]).encode()
    try:
        status, body, issuer = fetch(
            proxy_port,
            trust,
            INTERCEPTED_HOST,
            b"POST /v1/assets/batch HTTP/1.1\r\nHost: "
            + INTERCEPTED_HOST.encode()
            + b"\r\nContent-Type: application/json\r\nContent-Length: "
            + str(len(batch)).encode()
            + b"\r\nConnection: close\r\n\r\n"
            + batch,
        )
        result.notes.append(f"interception: {INTERCEPTED_HOST} answered by Verdra ({issuer})")
        if " 200 " not in status + " ":
            result.problems.append(f"replacement: the asset batch answered {status!r}")
            return
        location = json.loads(body)[0]["location"]
        path = location.split(CONTENT_HOST, 1)[1]
        status, body, _issuer = fetch(
            proxy_port,
            trust,
            CONTENT_HOST,
            f"GET {path} HTTP/1.1\r\nHost: {CONTENT_HOST}\r\nConnection: close\r\n\r\n".encode(),
        )
    except (OSError, ssl.SSLError, ValueError, KeyError, IndexError) as error:
        result.problems.append(f"replacement: {type(error).__name__}: {error}")
        return
    if " 200 " not in status + " ":
        result.problems.append(f"replacement: the download answered {status!r}")
        return
    try:
        pixels = ochre.read_image(body)
    except ochre.OchreError as error:
        result.problems.append(f"replacement: the download isn't a picture ({error})")
        return
    color = tuple(pixels.rgba[:4])
    if color == REPLACEMENT_RGBA:
        result.notes.append(
            f"replacement: asset {ASSET} downloaded as the replacement picture "
            f"({pixels.width} x {pixels.height})"
        )
    elif color == ORIGINAL_RGBA:
        result.problems.append(f"replacement: asset {ASSET} downloaded as the original picture")
    else:
        result.problems.append(f"replacement: asset {ASSET} downloaded in color {color}")


def check_launch(trust: Path, port: int, build: Path | None, result: Result) -> None:
    """The environment the fake Player was started with (Windows only)."""
    written = trust.parent.parent / "env.txt"
    deadline = time.monotonic() + 30
    while not written.exists() and time.monotonic() < deadline:
        time.sleep(0.25)
    if not written.exists():
        result.problems.append("launch: the fake Player wasn't started (no env.txt after 30 s)")
        return
    found: dict[str, str] = {}
    for line in written.read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        found[name.upper()] = value
    proxy = f"http://{terrain.PROXY_HOST}:{port}"
    if found.get("HTTPS_PROXY") != proxy:
        result.problems.append(f"launch: HTTPS_PROXY is {found.get('HTTPS_PROXY')!r}, not {proxy}")
    else:
        result.notes.append("launch: the Player got the proxy variables")
    if found.get("DLL_DIRECTORY"):
        result.problems.append(
            f"launch: the Player inherited the DLL directory {found['DLL_DIRECTORY']}"
        )
    if build is not None:
        inside = str(build.resolve()).lower()
        leaked = sorted(
            name
            for name, value in found.items()
            if inside in value.lower() and name != "DLL_DIRECTORY"
        )
        if leaked:
            result.problems.append(
                "launch: the Player got the built app's folder in " + ", ".join(leaked)
            )
        else:
            result.notes.append(
                "launch: nothing of the built app's folder in the Player's environment"
            )


def check_log(text: str, *, replaced: bool, result: Result) -> None:
    """The log must show what happened: the pass-through, and the replacement served."""
    if "through unchanged" not in text:
        result.problems.append("log: no line for the connection passed through")
    else:
        result.notes.append("log: shows the connection passed through")
    if replaced and SERVED not in text:
        result.problems.append(f"log: no line {SERVED!r}")
    elif replaced:
        result.notes.append("log: shows the replacement served")
    if NOT_REACHING in text or "couldn't open a secure connection" in text:
        result.problems.append("log: Verdra reported that Roblox isn't reaching it")


def run(
    command: list[str], *, build: Path | None = None, timeout: float = ROUTING_TIMEOUT_S
) -> tuple[Result, str]:
    """Start Verdra with `command`, run the checks, stop it; return the result and its log."""
    result = Result()
    with tempfile.TemporaryDirectory() as scratch, contextlib.ExitStack() as stack:
        home, local = Path(scratch) / "home", Path(scratch) / "local"
        local.mkdir()
        home.mkdir()
        trust = fake_player(local)
        upstream = FakeUpstream(Path(scratch))
        stack.callback(upstream.close)
        port = free_port()
        settings(home, port, upstream.port)
        profile(home)
        environment = os.environ | {
            "VERDRA_HOME": str(home),
            "LOCALAPPDATA": str(local),
            "QT_QPA_PLATFORM": "offscreen",
        }
        untrusted = stack.enter_context(upstream_trust(upstream.ca, environment))
        log = home / "logs" / terrain.LOG_FILE
        launch = [*command, LINK] if sys.platform == "win32" else command
        process = subprocess.Popen(launch, env=environment, cwd=ROOT)  # noqa: S603
        text = ""
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
                if ROUTING in text or process.poll() is not None:
                    break
                time.sleep(0.25)
            if ROUTING not in text:
                state = (
                    f"exited with code {process.returncode}"
                    if process.poll() is not None
                    else f"still not routing after {timeout:.0f} s"
                )
                result.problems.append(f"routing: Verdra {state}")
                return result, text
            block = trust.read_bytes()
            if b"BEGIN CERTIFICATE" not in block:
                result.problems.append("certificate: the Player's cacert.pem has no certificate")
            else:
                result.notes.append("certificate: added to the Player's cacert.pem")
            check_pass_through(port, result)
            if untrusted is None:
                check_replacement(port, trust, result)
            else:
                result.notes.append(f"replacement: skipped, {untrusted}")
            if sys.platform == "win32":
                check_launch(trust, port, build, result)
            time.sleep(1.0)  # let the app write what it saw
            text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
            check_log(text, replaced=untrusted is None, result=result)
            result.notes.append("upstream saw: " + "; ".join(upstream.requests or ["nothing"]))
        finally:
            process.kill()
            process.wait()
    return result, text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke test of routing in a running Verdra.")
    parser.add_argument("folder", nargs="?", type=Path, help="the built app's folder")
    parser.add_argument("--source", action="store_true", help="run `python -m verdra` instead")
    args = parser.parse_args(argv)
    if args.source:
        command = [sys.executable, "-m", "verdra"]
        label = "source run"
    elif args.folder is not None:
        suffix = ".exe" if sys.platform == "win32" else ""
        executable = args.folder / (terrain.EXECUTABLE + suffix)
        command = [str(executable)]
        label = f"built app {executable}"
    else:
        parser.error("give the built app's folder or --source")
    result, log = run(command, build=None if args.source else args.folder)
    print(f"Smoke test of the {label}:")
    for note in result.notes:
        print(f"  ok      {note}")
    for problem in result.problems:
        print(f"  FAILED  {problem}")
    print("--- Verdra's log ---")
    print(log.rstrip() or "(empty)")
    return 1 if result.problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
