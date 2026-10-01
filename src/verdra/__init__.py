# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Exposes the version, read from package metadata. Nothing else."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__: str = version("verdra")
except PackageNotFoundError:  # pragma: no cover - only when running from an unbuilt tree
    __version__ = "0.0.0"

__all__ = ["__version__"]
