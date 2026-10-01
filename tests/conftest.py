# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Shared test configuration: Hypothesis profiles for pull requests and nightly runs."""

import os

from hypothesis import HealthCheck, settings

# Pull requests run short property tests; the nightly workflow sets HYPOTHESIS_PROFILE=nightly.
settings.register_profile("ci", max_examples=100, deadline=None)
settings.register_profile(
    "nightly",
    max_examples=20_000,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci"))
