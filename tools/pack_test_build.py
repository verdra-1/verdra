# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Pack the built app into the Windows test build ZIP, and unpack it for the build check.

Plan 16.2 ("Next steps", item 2) and decision record 0019: a portable test build the owner can
unzip and double-click, built by CI on every push to main and kept as a workflow artifact. It is
not a release and has no installer. The ZIP holds one folder, `Verdra`, with `verdra.exe` (Reference
R3), what PyInstaller put next to it, and `READ-ME.txt`.

The build check runs on that exact ZIP: `--unpack` extracts it into an empty folder, and
`tools/check_build.py` checks the extracted `Verdra` folder (Qt modules, legal texts, launch).

    python tools/pack_test_build.py dist/Verdra dist/Verdra-windows-test.zip --commit <sha>
    python tools/pack_test_build.py --unpack dist/Verdra-windows-test.zip unpacked
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Final

from verdra.soil import terrain

ZIP_NAME: Final = "Verdra-windows-test.zip"
FOLDER: Final = "Verdra"
#: Reference R3: the executable's name, which never changes ("verdra.exe").
EXECUTABLE: Final = f"{terrain.EXECUTABLE}.exe"
READ_ME: Final = "READ-ME.txt"

READ_ME_TEXT: Final = """\
Verdra test build (Windows)

This is a test build of Verdra, made automatically from the source code
(commit {commit}). It is for testing only. It isn't a release, and it isn't
signed, so the first time you start it Windows may say "Windows protected
your PC". Click "More info", then "Run anyway".

Start: double-click verdra.exe in this folder.

Update to a newer test build: quit Verdra (tray icon > Quit Verdra), delete
this Verdra folder, and unzip the new test build in its place. Your settings
and replacement profiles are in %LOCALAPPDATA%\\Verdra and are kept.

Undo what Verdra changed on this PC: in Verdra, Settings > System changes >
Reset everything, before you delete the folder.
"""


def pack(built: Path, target: Path, commit: str) -> Path:
    """Write the test build ZIP of the built folder `built` (with verdra.exe) to `target`."""
    if not (built / EXECUTABLE).is_file():
        msg = f"{built} has no {EXECUTABLE}"
        raise FileNotFoundError(msg)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = READ_ME_TEXT.format(commit=commit).replace("\n", "\r\n")  # Notepad-friendly
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(built.rglob("*")):
            if path.is_file():
                archive.write(path, PurePosixPath(FOLDER, *path.relative_to(built).parts))
        archive.writestr(f"{FOLDER}/{READ_ME}", text.encode("utf-8"))
    return target


def unpack(archive_path: Path, destination: Path) -> Path:
    """Extract the test build ZIP into the empty folder `destination`; return its Verdra folder.

    Raises:
        ValueError: the ZIP isn't a test build: an entry outside `Verdra/`, a path that climbs
            out, or no verdra.exe or READ-ME.txt.
    """
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        msg = f"{destination} isn't empty"
        raise ValueError(msg)
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        for name in names:
            parts = PurePosixPath(name).parts
            if not parts or parts[0] != FOLDER or ".." in parts or name.startswith("/"):
                msg = f"unexpected entry {name!r} in {archive_path.name}"
                raise ValueError(msg)
        for needed in (EXECUTABLE, READ_ME):
            if f"{FOLDER}/{needed}" not in names:
                msg = f"{archive_path.name} has no {FOLDER}/{needed}"
                raise ValueError(msg)
        archive.extractall(destination)
    return destination / FOLDER


def main(argv: list[str] | None = None) -> int:
    """Pack (the default) or unpack the test build ZIP."""
    parser = argparse.ArgumentParser(description="Pack or unpack the Windows test build ZIP.")
    parser.add_argument("source", type=Path, help="the built folder, or the ZIP with --unpack")
    parser.add_argument("target", type=Path, help="the ZIP to write, or the folder to unpack to")
    parser.add_argument("--commit", default="unknown", help="the commit the build was made from")
    parser.add_argument("--unpack", action="store_true", help="extract a test build ZIP")
    arguments = parser.parse_args(argv)
    try:
        if arguments.unpack:
            print(unpack(arguments.source, arguments.target))  # noqa: T201 - for the next step
        else:
            print(pack(arguments.source, arguments.target, arguments.commit))  # noqa: T201
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"error: {error}", file=sys.stderr)  # noqa: T201
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
