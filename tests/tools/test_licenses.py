# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Tests for the licence gate."""

import pytest
from tools.licenses import (
    canonical,
    expression_allowed,
    load_config,
    missing_packages,
    normalize,
)

from tools import licenses

ALLOWED = {normalize(name) for name in ["MIT", "BSD-3-Clause", "LGPL-3.0-only", "MPL-2.0"]}


def test_classifier_names_map_onto_spdx() -> None:
    assert normalize("MIT License") == "MIT"
    assert normalize("Mozilla Public License 2.0 (MPL 2.0)") == "MPL-2.0"


def test_or_passes_when_one_alternative_is_allowed() -> None:
    assert expression_allowed("LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only", ALLOWED)


def test_and_needs_every_part() -> None:
    assert expression_allowed("MIT AND BSD-3-Clause", ALLOWED)
    assert not expression_allowed("MIT AND GPL-3.0-only", ALLOWED)


def test_gpl_alone_is_rejected() -> None:
    assert not expression_allowed("GPL-3.0-only", ALLOWED)
    assert not expression_allowed("UNKNOWN", ALLOWED)


def test_semicolon_separated_classifiers_are_alternatives() -> None:
    assert expression_allowed("GNU General Public License v3 (GPLv3); MIT License", ALLOWED)


def test_package_names_are_compared_in_canonical_form() -> None:
    assert canonical("PySide6_Essentials") == canonical("pyside6-essentials")
    assert canonical("jaraco.context") == "jaraco-context"


def test_gate_fails_when_a_locked_package_is_missing() -> None:
    installed = [{"name": "PySide6", "version": "6.11", "license": "LGPL-3.0-only"}]
    problems = missing_packages(installed, {"pyside6", "pyinstaller"})
    assert len(problems) == 1
    assert problems[0].startswith("pyinstaller: locked but not installed")


def test_zero_clause_bsd_is_allowed_by_the_real_config() -> None:
    from tools.licenses import load_config

    allowed = {normalize(name) for name in load_config()["licenses"]["allowed"]}
    assert expression_allowed("0BSD", allowed)


def test_the_qt_named_exceptions_are_recorded_and_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """Plan 16.2: AFL-2.1 (the libdbus-1 headers in Qt D-Bus) is a named exception with a reason."""
    qt = load_config()["licenses"]["qt-exceptions"]
    assert set(qt) == {"AFL-2.1"}
    assert "dbus_minimal_p.h" in qt["AFL-2.1"]
    monkeypatch.setattr(licenses, "installed_licenses", lambda: [])
    assert "| AFL-2.1 | The libdbus-1 headers" in licenses.report()


def test_the_numpy_exception_names_the_runtime_library_exception() -> None:
    reason = load_config()["licenses"]["exceptions"]["numpy"]
    assert "GPL-3.0 with GCC Runtime Library Exception 3.1" in reason
    assert "permits distribution inside non-GPL programs" in reason
