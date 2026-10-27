# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""tools/third_party.py: every bundled library's license text, Qt's LGPL-3.0, gaps never silent."""

import hashlib

from tools import third_party


def test_a_package_carries_its_own_license_files() -> None:
    text, missing = third_party.build(["pillow"])
    assert missing == []
    assert "License: MIT-CMU" in text
    assert "--- licenses/LICENSE ---" in text
    assert "GNU LESSER GENERAL PUBLIC LICENSE" not in text


def test_qt_points_to_its_source_and_brings_the_gnu_texts() -> None:
    text, missing = third_party.build(["pyside6", "shiboken6"])
    assert missing == []
    assert text.count("under the GNU Lesser General Public License version 3") == 2
    assert "https://download.qt.io/official_releases/QtForPython/" in text
    assert text.count("GNU LESSER GENERAL PUBLIC LICENSE\n") == 1
    assert text.count("GNU GENERAL PUBLIC LICENSE\n") == 1


def test_dnspython_uses_its_vendored_license_text() -> None:
    # dnspython 2.9.0 ships no license file in its wheel or its sdist; the text is vendored from
    # packaging/licenses/ so the build still carries its attribution (not reported as a gap).
    text, missing = third_party.build(["dnspython"])
    assert missing == []
    assert "License: ISC" in text
    assert "Copyright (C) Dnspython Contributors" in text


def test_a_package_without_license_text_is_reported() -> None:
    _, missing = third_party.build(["no-such-package-verdra"])
    assert missing == ["no-such-package-verdra: not installed"]


def test_every_runtime_package_has_a_license_text() -> None:
    _, missing = third_party.build(third_party.runtime_packages())
    assert missing == []


def test_the_gnu_texts_are_the_published_ones() -> None:
    # The Free Software Foundation's texts of 29 June 2007 (gnu.org/licenses), byte for byte.
    digests = [hashlib.sha256(path.read_bytes()).hexdigest() for path in third_party.GNU_TEXTS]
    assert digests == [
        "e3a994d82e644b03a792a930f574002658412f62407f5fee083f2555c5f23118",
        "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986",
    ]
