# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Single instance through a local socket; forwards a second launch's link.

The first Verdra listens on a local socket named for the user (Reference R3). A second launch
connects, sends one JSON line with its `roblox-player:` link (if any), and exits; the first
instance brings its window forward and handles the link (spec S-01).
"""

from __future__ import annotations

import getpass
import hashlib
import json
import logging

from PySide6.QtCore import QCoreApplication, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from verdra.soil import terrain

log = logging.getLogger(__name__)

CONNECT_TIMEOUT_MS = 500
MAX_MESSAGE_BYTES = 64 * 1024


def channel_name(user: str | None = None) -> str:
    """Return the local socket name for a user: verdra-<hash of the user name>."""
    name = user if user is not None else getpass.getuser()
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:16]
    return terrain.SINGLE_INSTANCE_PREFIX + digest


class SingleInstance(QObject):
    """Claims the single-instance channel, or hands over to the instance that holds it.

    Signals:
        activated(link): Another launch asked this instance to come forward; `link` is its
            `roblox-player:` link, or an empty string.
    """

    activated = Signal(str)

    def __init__(self, name: str | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.name = name or channel_name()
        self._server: QLocalServer | None = None
        # Server-side connections still being read; they belong to the server, which deletes
        # them when it goes.
        self._pending: list[QLocalSocket] = []

    def claim(self, link: str | None = None) -> bool:
        """Become the running instance, or forward `link` to it.

        Returns:
            True if this process is now the single instance and should start; False if another
            instance took over and this process should exit.
        """
        if self._forward(link):
            return False
        server = QLocalServer(self)
        server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not server.listen(self.name):
            # A crashed instance can leave a stale socket file behind on macOS and Linux.
            QLocalServer.removeServer(self.name)
            if not server.listen(self.name):
                log.warning(
                    "%s",
                    QCoreApplication.translate(
                        "M-SHELL-06",
                        "Verdra couldn't set up its single-instance check, so opening Verdra "
                        "again may start a second copy.",
                    ),
                )
                log.debug("Single-instance channel: %s", server.errorString())
                return True
        server.newConnection.connect(self._accept)
        self._server = server
        return True

    def hand_over(self, link: str | None = None) -> bool:
        """Forward `link` to a running instance; return whether one took it.

        This works before the Qt application exists (plan 8.4 step 1).
        """
        return self._forward(link)

    def release(self) -> None:
        """Stop listening and drop any half-read connections (on quit)."""
        for socket in self._pending:
            socket.abort()
        self._pending.clear()
        if self._server is not None:
            self._server.close()
            self._server = None

    def _forward(self, link: str | None) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self.name)
        if not socket.waitForConnected(CONNECT_TIMEOUT_MS):
            return False
        message = json.dumps({"link": link or ""}) + "\n"
        socket.write(message.encode("utf-8"))
        socket.waitForBytesWritten(CONNECT_TIMEOUT_MS)
        socket.disconnectFromServer()
        return True

    def _accept(self) -> None:
        assert self._server is not None  # noqa: S101 - only connected while listening
        while (socket := self._server.nextPendingConnection()) is not None:
            self._pending.append(socket)
            socket.readyRead.connect(self._drain)
            socket.disconnected.connect(self._drain)
        self._drain()

    def _drain(self) -> None:
        """Read the message of every connection that has sent one; forget closed ones."""
        for socket in list(self._pending):
            if socket.canReadLine():
                self._handle(bytes(socket.readLine().data()))
                socket.disconnectFromServer()
            elif socket.bytesAvailable() > MAX_MESSAGE_BYTES:
                socket.abort()
            # disconnectFromServer can re-enter this method through `disconnected`.
            if (
                socket.state() == QLocalSocket.LocalSocketState.UnconnectedState
                and socket in self._pending
            ):
                self._pending.remove(socket)

    def _handle(self, raw: bytes) -> None:
        try:
            message = json.loads(raw.decode("utf-8"))
            link = str(message.get("link", "")) if isinstance(message, dict) else ""
        except ValueError:
            link = ""
        if link and not link.lower().startswith(terrain.URL_SCHEME + ":"):
            link = ""
        log.info(
            "%s",
            QCoreApplication.translate(
                "M-SHELL-07", "Another launch of Verdra brought this window to the front."
            ),
        )
        self.activated.emit(link)
