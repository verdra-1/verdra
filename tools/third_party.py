# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Write THIRD_PARTY_NOTICES.md: every runtime package the build ships, with its license texts.

Plan 13.6 and decision records 0002 and 0025: the Windows build carries Verdra's own LICENSE and
NOTICE and, in this file (shown by About › Third-party notices), the license of each library it
bundles. The package list is the runtime group of the
lockfile for this system (`uv export --no-dev`, platform markers evaluated); each package's
license expression and the full text of every license file its installed metadata carries
(`*.dist-info/licenses/`, or LICENSE, COPYING, NOTICE and AUTHORS files) are copied as they are.
Qt for Python's wheels carry no license file: Verdra uses Qt under LGPL-3.0 (decision record
0002), so those packages point to where their source is published and the file ends with the full
LGPL-3.0 and GPL-3.0 texts (`packaging/licenses/`, the Free Software Foundation's published texts).
Any other package whose metadata carries no license file is reported and the tool exits 1, so a
gap is never silent.

    python tools/third_party.py OUT_FILE
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[1]
FILE_NAME: Final = "THIRD_PARTY_NOTICES.md"
#: Qt for Python: used under LGPL-3.0 (decision record 0002); the wheels carry no license file.
QT_PACKAGES: Final = frozenset({"pyside6", "pyside6-essentials", "pyside6-addons", "shiboken6"})
#: The full texts LGPL-3.0 needs next to it: LGPL-3.0 adds to GPL-3.0, so both are included.
GNU_TEXTS: Final = (
    ROOT / "packaging" / "licenses" / "LGPL-3.0.txt",
    ROOT / "packaging" / "licenses" / "GPL-3.0.txt",
)
QT_NOTE: Final = """\
Verdra uses Qt and Qt for Python under the GNU Lesser General Public License version 3
(LGPL-3.0); its full text, and the GPL-3.0 text it builds on, are at the end of this file.
The Qt libraries are separate, replaceable files in the _internal folder.
Source code: Qt https://download.qt.io/official_releases/qt/ and
Qt for Python https://download.qt.io/official_releases/QtForPython/ (version {version})."""
_LICENSE_FILE = re.compile(r"(^|/)(LICEN[CS]E|COPYING|NOTICE|AUTHORS)[^/]*$", re.IGNORECASE)


def canonical(name: str) -> str:
    """A package name in its normalized form (PEP 503)."""
    return re.sub(r"[-_.]+", "-", name).lower()


def runtime_packages() -> list[str]:
    """The runtime group's packages for this system, from the lockfile, sorted."""
    from packaging.markers import Marker  # noqa: PLC0415 - a build tool's own dependency

    exported = subprocess.run(  # noqa: S603 - fixed argument list, no shell
        ["uv", "export", "--frozen", "--no-dev", "--no-hashes", "--no-emit-project"],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
    ).stdout
    packages = set()
    for line in exported.splitlines():
        if not line or line.startswith(("#", " ", "-")):
            continue
        requirement, _, marker = line.partition(";")
        if marker.strip() and not Marker(marker.strip()).evaluate():
            continue
        packages.add(canonical(requirement.split("==")[0].strip()))
    return sorted(packages)


def license_of(distribution: metadata.Distribution) -> str:
    meta = distribution.metadata
    expression = meta.get("License-Expression") or ""
    if expression:
        return expression
    classifiers = [
        value.split("::")[-1].strip()
        for value in meta.get_all("Classifier") or []
        if value.startswith("License ::")
    ]
    short = (meta.get("License") or "").strip()
    if short and "\n" not in short and len(short) < 100:  # noqa: PLR2004 - a name, not a text
        return short
    return "; ".join(classifiers) or "(not stated in its metadata)"


def license_files(distribution: metadata.Distribution) -> list[tuple[str, str]]:
    """(file name, text) of every license file the installed package's metadata carries."""
    found = []
    for path in distribution.files or []:
        text = str(path)
        if ".dist-info/" in text and _LICENSE_FILE.search(text):
            content = Path(path.locate()).read_bytes().decode("utf-8", "replace")
            found.append((text.split(".dist-info/", 1)[1], content))
    return sorted(found)


def build(packages: list[str]) -> tuple[str, list[str]]:
    """The file's text, and the packages that had no license file."""
    parts = [
        "Third-party software in Verdra",
        "",
        "Verdra's own license is in LICENSE and its notices in NOTICE. The Windows build",
        "also contains the following libraries, each under its own license, reproduced here",
        "as their published packages carry it.",
        "",
    ]
    missing = []
    for name in packages:
        try:
            distribution = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            missing.append(f"{name}: not installed")
            continue
        version = distribution.version
        parts += [
            "=" * 78,
            f"{distribution.metadata['Name']} {version}",
            f"License: {license_of(distribution)}",
        ]
        if canonical(name) in QT_PACKAGES:
            parts += ["", QT_NOTE.format(version=version), ""]
            continue
        files = license_files(distribution)
        if not files:
            missing.append(f"{name} {version}: no license file in its metadata")
        for file_name, content in files:
            parts += ["", f"--- {file_name} ---", "", content.rstrip(), ""]
        parts.append("")
    if QT_PACKAGES & {canonical(name) for name in packages}:
        for text in GNU_TEXTS:
            parts += ["=" * 78, text.stem, "", text.read_text(encoding="utf-8").rstrip(), ""]
    return "\n".join(parts) + "\n", missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path, help=f"where to write {FILE_NAME}")
    arguments = parser.parse_args(argv)
    text, missing = build(runtime_packages())
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text(text, encoding="utf-8")
    for line in missing:
        print(f"no license text: {line}", file=sys.stderr)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
