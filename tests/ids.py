# SPDX-FileCopyrightText: 2026 q0f7
# SPDX-License-Identifier: Apache-2.0
"""Real-size Roblox IDs for tests.

Roblox asset, place, universe and user IDs are larger than Qt's 32-bit `int` (a Toolbox image
can be 15553230204), and a test with only small invented IDs can't see an overflow at the Qt
boundary. Every test file that uses such IDs also uses both of these
(`tests/test_real_size_ids.py` checks it).
"""

from __future__ import annotations

from typing import Final

#: Above a signed 32-bit int (Qt's `int`), below an unsigned one.
ABOVE_INT32: Final = 2**31 + 7
#: Above an unsigned 32-bit int: a public Toolbox image, the size real asset IDs have today.
ABOVE_UINT32: Final = 15553230204
