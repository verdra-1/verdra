# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Shared test configuration: Hypothesis profiles, the Qt lifetime guard, shuffled order."""

import os

from hypothesis import HealthCheck, settings

# The Qt lifetime guard runs after every test; every test gets its own Verdra home folder and an
# in-memory secret store; --shuffle runs the tests in a random order; on a non-Windows development
# machine the paused platform gets a test-only certificate loader (decision record 0018).
pytest_plugins = [
    "tests.support.qt_lifetimes",
    "tests.support.isolation",
    "tests.support.shuffle",
    "tests.support.dev_machine",
]

# Pull requests run short property tests; the nightly workflow sets HYPOTHESIS_PROFILE=nightly.
settings.register_profile("ci", max_examples=100, deadline=None)
settings.register_profile(
    "nightly",
    max_examples=20_000,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci"))
