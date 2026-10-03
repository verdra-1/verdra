# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Run the tests in a shuffled order: `pytest --shuffle=random` or `--shuffle=SEED`.

Used by the nightly repeated UI runs to find tests that depend on what ran before them. The seed
is printed in the report header, so a failing order can be replayed with `--shuffle=SEED`. No
third-party plugin is needed for this.
"""

from __future__ import annotations

import os
import random

import pytest

SEED_KEY = pytest.StashKey[int]()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--shuffle",
        metavar="SEED",
        default=os.environ.get("VERDRA_TEST_SHUFFLE"),
        help="run tests in a shuffled order: a number, or 'random' for a new seed",
    )


def pytest_configure(config: pytest.Config) -> None:
    value = config.getoption("--shuffle")
    if value:
        seed = random.SystemRandom().randrange(2**32) if value == "random" else int(value)
        config.stash[SEED_KEY] = seed


def pytest_report_header(config: pytest.Config) -> str | None:
    seed = config.stash.get(SEED_KEY, None)
    return None if seed is None else f"shuffled test order, seed {seed} (replay: --shuffle={seed})"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    seed = config.stash.get(SEED_KEY, None)
    if seed is not None:
        random.Random(seed).shuffle(items)  # noqa: S311 - test order, not security
