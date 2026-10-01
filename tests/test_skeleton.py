# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Every module in the package tree imports cleanly on every system."""

import importlib
import pkgutil
from pathlib import Path

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


def test_tests_mirror_the_package_tree() -> None:
    # Master plan 13.1: tests/ mirrors src/verdra/.
    source = Path(verdra.__file__).parent
    tests = Path(__file__).parent
    for init in source.rglob("__init__.py"):
        package = init.parent.relative_to(source)
        assert (tests / package / "__init__.py").exists(), f"tests/{package.as_posix()}/ is missing"
