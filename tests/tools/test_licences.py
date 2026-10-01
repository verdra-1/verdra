# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Tests for the licence gate."""

from tools.licences import expression_allowed, normalise

ALLOWED = {normalise(name) for name in ["MIT", "BSD-3-Clause", "LGPL-3.0-only", "MPL-2.0"]}


def test_classifier_names_map_onto_spdx() -> None:
    assert normalise("MIT License") == "MIT"
    assert normalise("Mozilla Public License 2.0 (MPL 2.0)") == "MPL-2.0"


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
