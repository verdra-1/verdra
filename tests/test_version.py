# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Tests for the package version."""

from importlib.metadata import version

import verdra


def test_version_comes_from_package_metadata() -> None:
    assert verdra.__version__ == version("verdra")
