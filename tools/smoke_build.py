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
3. Interception: with one saved replacement (an Asset ID swap, so Verdra decrypts the asset
   batch host), a CONNECT to `assetdelivery.roblox.com` completes a TLS handshake for that
   name, trusting only the certificates in the fake Player's `cacert.pem`, exactly as the
   Player does. No request is sent, so nothing reaches Roblox.

Everything stays in throwaway folders (`VERDRA_HOME`), except what Verdra writes for any user:
its CA key in the secret store and, while routing, its `roblox-player:` link handler. On a CI
runner both go with the machine.

Usage:
    uv run python tools/smoke_build.py dist/Verdra      the built app (verdra.exe)
    uv run python tools/smoke_build.py --source         `python -m verdra` from this checkout
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from verdra.soil import terrain  # noqa: E402 - found through the path added above

#: Seconds to wait for routing after the start (the window is ready in ~2 s on a runner).
ROUTING_TIMEOUT_S = 90.0
ROUTING = "Routing status changed from Idle to Routing"
INTERCEPTED_HOST = "assetdelivery.roblox.com"
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
    (folder / "RobloxPlayerBeta.exe").write_bytes(b"")
    trust = folder / "ssl" / "cacert.pem"
    trust.write_bytes(b"")
    return trust


def settings(home: Path, port: int) -> None:
    """Setup done, routing on launch, this proxy port, detailed logging."""
    path = home / "config" / terrain.SETTINGS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "format": "verdra.settings",
        "version": 1,
        "general": {"onboarding_done": True, "route_on_launch": True},
        "routing": {"proxy_port": port, "handle_roblox_links": False},
        "advanced": {
            "detailed_logging": True,
            "detailed_logging_since": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        },
    }
    path.write_text(json.dumps(document), encoding="utf-8")


def profile(home: Path) -> None:
    """One saved replacement (an Asset ID swap), so Verdra intercepts the asset batch host: it
    decrypts only the hosts the current replacements need (plan 10.1)."""
    from datetime import UTC, datetime  # noqa: PLC0415

    from verdra.trunk.branches import grafts  # noqa: PLC0415 - the repository's own writer

    now = datetime.now(UTC)
    saved = grafts.Profile(
        id="00000000-0000-4000-8000-000000000001",
        name="Smoke",
        created=now,
        modified=now,
        replacements=[
            grafts.Replacement(
                id="00000000-0000-4000-8000-000000000002",
                original=grafts.Original(asset_id=1111111),
                target=grafts.Target(kind="asset_id", value="2222222"),
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


def check_interception(proxy_port: int, trust: Path, result: Result) -> None:
    # Only the Player's trust file, like the Player: no system certificates.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    try:
        context.load_verify_locations(cadata=trust.read_text(encoding="ascii"))
        with (
            connect(proxy_port, INTERCEPTED_HOST, 443) as tunnel,
            context.wrap_socket(tunnel, server_hostname=INTERCEPTED_HOST) as tls,
        ):
            certificate = tls.getpeercert() or {}
            names = [pair for part in certificate.get("issuer", ()) for pair in part]
            issuer = next((value for key, value in names if key == "commonName"), "?")
            result.notes.append(
                f"interception: TLS {tls.version()} for {INTERCEPTED_HOST}, issued by {issuer}"
            )
    except (OSError, ssl.SSLError) as error:
        result.problems.append(f"interception: {type(error).__name__}: {error}")


def run(command: list[str], *, timeout: float = ROUTING_TIMEOUT_S) -> tuple[Result, str]:
    """Start Verdra with `command`, run the checks, stop it; return the result and its log."""
    result = Result()
    with tempfile.TemporaryDirectory() as scratch:
        home, local = Path(scratch) / "home", Path(scratch) / "local"
        local.mkdir()
        trust = fake_player(local)
        port = free_port()
        settings(home, port)
        profile(home)
        environment = os.environ | {
            "VERDRA_HOME": str(home),
            "LOCALAPPDATA": str(local),
            "QT_QPA_PLATFORM": "offscreen",
        }
        log = home / "logs" / terrain.LOG_FILE
        process = subprocess.Popen(command, env=environment, cwd=ROOT)  # noqa: S603
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
            check_interception(port, trust, result)
            time.sleep(1.0)  # let the app write what it saw
            text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
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
    result, log = run(command)
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
