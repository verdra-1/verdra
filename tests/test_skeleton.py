# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Every module in the package tree imports cleanly on every system."""

import importlib
import pkgutil

import pytest

import verdra

MODULES = sorted(
    info.name
    for info in pkgutil.walk_packages(verdra.__path__, prefix="verdra.")
    if info.name != "verdra.__main__"
)


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name: str) -> None:
    module = importlib.import_module(name)
    assert module.__doc__, f"{name} has no docstring"
