# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Windows.

`PLATFORM` is this package's implementation of the Platform protocol (soil/humus).
"""

from __future__ import annotations

import ctypes
import os
import secrets
import subprocess
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

from verdra.soil import humus
from verdra.soil.meadow import launcher

if TYPE_CHECKING:
    import ssl

#: SystemParametersInfo action that reads "Show animations in Windows" (client-area animation).
_SPI_GETCLIENTAREAANIMATION: Final = 0x1042


class Meadow:
    """The Windows platform."""

    @property
    def system(self) -> Literal["windows"]:
        """The system this package is for."""
        return "windows"

    @property
    def name(self) -> str:
        """The system's name as people read it in messages (M-PLAT-01)."""
        return "Windows"

    @property
    def key_file_fallback(self) -> bool:
        """Whether the CA key may live in a user-only file when there is no secret store."""
        return False

    def support(self) -> humus.Unsupported | None:
        """Return None: Windows is Verdra's main platform."""
        return None

    def prefers_reduced_motion(self) -> bool | None:
        """Return the inverse of "Show animations in Windows", or None when it can't be read."""
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            return None
        enabled = ctypes.c_int()
        ok = windll.user32.SystemParametersInfoW(
            _SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(enabled), 0
        )
        return None if not ok else not enabled.value

    def load_cert_chain(self, context: ssl.SSLContext, certificate: bytes, key: bytes) -> None:
        """Load the PEM certificate and key through one-shot named pipes (nothing on disk).

        Each pipe takes one client, only from this process (its process ID is checked before
        a byte is written), and closes once OpenSSL has read it.
        """
        pipes = [_OneShotPipe(certificate), _OneShotPipe(key)]
        try:
            context.load_cert_chain(pipes[0].name, pipes[1].name)
        finally:
            for pipe in pipes:
                pipe.finish()
        for pipe in pipes:
            if pipe.error is not None:
                raise pipe.error

    def roblox_clients(self) -> list[humus.RobloxClient] | humus.Unsupported:
        """Return the installed Players: per-user first, then all-users (W-01 to W-03)."""
        return launcher.find_clients(
            launcher.local_appdata(os.environ),
            launcher.program_folders(os.environ),
            launcher.WindowsRegistry(),
        )

    def trust_files_in(self, version_folder: Path) -> list[Path]:
        """Return a new Player version folder's trust file; none for any other folder."""
        if not launcher.is_player_folder(version_folder):
            return []
        return [version_folder.joinpath(*launcher.TRUST_FILE)]

    def launch_roblox(
        self,
        client: humus.RobloxClient,
        link: str | None,
        proxy_port: int,
        environment: Mapping[str, str],
        spawn: humus.Spawn = subprocess.Popen,
    ) -> int:
        """Start the Player directly with the proxy variables; return its process ID."""
        return launcher.launch(client, link, proxy_port, environment, spawn)

    def link_handler(self) -> humus.LinkHandler | humus.Unsupported:
        """Return the per-user `roblox-player:` handler in HKCU (W-03)."""
        return launcher.WindowsLinkHandler(launcher.WindowsRegistry())


# Win32 constants (CreateNamedPipeW, winbase.h).
_PIPE_ACCESS_OUTBOUND: Final = 0x00000002
_FILE_FLAG_FIRST_PIPE_INSTANCE: Final = 0x00080000
_PIPE_REJECT_REMOTE_CLIENTS: Final = 0x00000008
_ERROR_PIPE_CONNECTED: Final = 535
_INVALID_HANDLE_VALUE: Final = ctypes.c_void_p(-1).value


class _OneShotPipe:
    """A named pipe that hands `data` to one client in this process, then closes."""

    def __init__(self, data: bytes) -> None:
        from ctypes import wintypes  # noqa: PLC0415 - Windows only

        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        self.kernel32.CreateNamedPipeW.restype = wintypes.HANDLE
        self.kernel32.CreateNamedPipeW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
        ]
        self.kernel32.ConnectNamedPipe.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        self.kernel32.GetNamedPipeClientProcessId.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.ULONG),
        ]
        self.kernel32.WriteFile.argtypes = [
            wintypes.HANDLE,
            ctypes.c_char_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p,
        ]
        for name in ("FlushFileBuffers", "DisconnectNamedPipe", "CloseHandle"):
            getattr(self.kernel32, name).argtypes = [wintypes.HANDLE]
        self.name = rf"\\.\pipe\verdra-{secrets.token_hex(16)}"
        self.error: OSError | None = None
        self.handle = self.kernel32.CreateNamedPipeW(
            self.name,
            _PIPE_ACCESS_OUTBOUND | _FILE_FLAG_FIRST_PIPE_INSTANCE,
            _PIPE_REJECT_REMOTE_CLIENTS,
            1,
            len(data),
            0,
            0,
            None,
        )
        if self.handle in (None, _INVALID_HANDLE_VALUE):
            raise ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]
        self.thread = threading.Thread(target=self._serve, args=(data,), daemon=True)
        self.thread.start()

    def _serve(self, data: bytes) -> None:
        from ctypes import wintypes  # noqa: PLC0415 - Windows only

        k = self.kernel32
        try:
            if not k.ConnectNamedPipe(self.handle, None):
                code = ctypes.get_last_error()  # type: ignore[attr-defined]
                if code != _ERROR_PIPE_CONNECTED:
                    self.error = ctypes.WinError(code)  # type: ignore[attr-defined]
                    return
            client = wintypes.ULONG()
            if not k.GetNamedPipeClientProcessId(self.handle, ctypes.byref(client)):
                self.error = ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]
                return
            if client.value != os.getpid():
                self.error = PermissionError("another process opened the pipe")
                return
            written = wintypes.DWORD()
            view = memoryview(data)
            while view:
                if not k.WriteFile(
                    self.handle, bytes(view), len(view), ctypes.byref(written), None
                ):
                    self.error = ctypes.WinError(ctypes.get_last_error())  # type: ignore[attr-defined]
                    return
                view = view[written.value :]
            k.FlushFileBuffers(self.handle)
        finally:
            k.DisconnectNamedPipe(self.handle)
            k.CloseHandle(self.handle)

    def finish(self) -> None:
        """Wait for the pipe to close; if OpenSSL never opened it, open it once to release it."""
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            try:
                with open(self.name, "rb") as handle:  # noqa: PTH123 - a pipe name, not a path
                    handle.read()
            except OSError:
                pass
            self.thread.join(timeout=5)


PLATFORM: Final = Meadow()
