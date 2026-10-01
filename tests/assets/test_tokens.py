# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""tokens.json holds every value from Master plan 5 and 6, and every colour pair passes WCAG."""

import json
import re
from pathlib import Path

import pytest

TOKENS = Path(__file__).resolve().parents[2] / "src" / "verdra" / "assets" / "brand" / "tokens.json"
DATA = json.loads(TOKENS.read_text(encoding="utf-8"))
THEMES = ("light", "dark")
RAW = {token["name"]: token["value"] for token in DATA["color"]["tokens"]}

SEMANTIC = [
    "bg", "surface", "surface-raised", "surface-sunken", "ink", "ink-muted", "ink-disabled",
    "divider", "border-strong", "primary", "primary-hover", "primary-pressed", "on-primary",
    "primary-tint", "focus-ring", "tooltip-bg", "tooltip-ink", "scrim", "success", "success-tint",
    "success-ink", "warning", "warning-tint", "warning-ink", "danger", "danger-tint", "danger-ink",
]  # fmt: skip
BRAND = ["brand-canopy", "brand-verdigris", "brand-sprout", "brand-mist"]


def colour(name: str, theme: str) -> str:
    value = RAW[name]
    if isinstance(value, dict):
        value = value[theme]
    if value.startswith("{"):
        return colour(value[1:-1], theme)
    return value


def luminance(value: str) -> float:
    digits = value.lstrip("#")
    channels = [int(digits[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(fore: str, back: str, theme: str) -> float:
    a, b = luminance(colour(fore, theme)), luminance(colour(back, theme))
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


# Master plan 5.3: (foreground, background, light ratio, dark ratio, minimum).
PAIRS = [
    ("ink", "bg", 15.7, 15.6, 4.5),
    ("ink", "surface", 16.8, 14.2, 4.5),
    ("ink", "surface-sunken", 14.5, 16.2, 4.5),
    ("ink", "surface-raised", 16.8, 12.9, 4.5),
    ("ink-muted", "bg", 6.8, 8.2, 4.5),
    ("ink-muted", "surface", 7.3, 7.5, 4.5),
    ("ink-muted", "surface-sunken", 6.3, 8.6, 4.5),
    ("primary", "bg", 5.6, 9.6, 4.5),
    ("primary", "surface", 6.0, 8.8, 4.5),
    ("on-primary", "primary", 6.0, 9.6, 4.5),
    ("on-primary", "primary-hover", 7.9, 11.4, 4.5),
    ("on-primary", "primary-pressed", 9.5, 12.8, 4.5),
    ("ink", "primary-tint", 14.0, 10.6, 4.5),
    ("tooltip-ink", "tooltip-bg", 15.7, 15.6, 4.5),
    ("success", "surface", 6.2, 8.3, 4.5),
    ("warning", "surface", 5.4, 8.5, 4.5),
    ("danger", "surface", 6.5, 6.9, 4.5),
    ("success-ink", "success-tint", 7.8, 8.6, 4.5),
    ("warning-ink", "warning-tint", 7.7, 8.7, 4.5),
    ("danger-ink", "danger-tint", 7.5, 8.3, 4.5),
    ("border-strong", "bg", 3.3, 4.0, 3.0),
    ("border-strong", "surface", 3.6, 3.6, 3.0),
    ("border-strong", "surface-sunken", 3.1, 4.1, 3.0),
    ("border-strong", "surface-raised", 3.6, 3.3, 3.0),
    ("focus-ring", "surface-sunken", 5.2, 10.0, 3.0),
    ("focus-ring", "primary-tint", 5.0, 6.5, 3.0),
]


def test_every_token_from_section_5_is_present() -> None:
    assert set(SEMANTIC + BRAND) <= RAW.keys()
    for name in SEMANTIC:
        for theme in THEMES:
            assert re.fullmatch(r"#[0-9A-F]{6}|rgba\(.+\)", colour(name, theme)), name
    assert RAW["focus-ring"] == "{primary}"


def test_brand_tokens_match_their_semantic_twins() -> None:
    assert colour("brand-verdigris", "light") == colour("primary", "light")
    assert colour("brand-sprout", "light") == colour("primary", "dark")
    assert colour("brand-mist", "light") == colour("primary-tint", "light")


@pytest.mark.parametrize(("fore", "back", "light", "dark", "minimum"), PAIRS)
def test_contrast_matches_section_5_3(
    fore: str, back: str, light: float, dark: float, minimum: float
) -> None:
    for theme, stated in (("light", light), ("dark", dark)):
        ratio = contrast(fore, back, theme)
        assert ratio >= minimum, f"{fore} on {back} ({theme}) is {ratio:.2f}"
        assert abs(ratio - stated) < 0.1, (
            f"{fore} on {back} ({theme}): {ratio:.2f}, plan says {stated}"
        )


def test_known_gap_border_on_primary_tint() -> None:
    # 5.3: controls inside a selected row use primary as their border instead.
    assert contrast("border-strong", "primary-tint", "dark") < 3.0
    assert contrast("primary", "primary-tint", "dark") >= 3.0
    assert contrast("primary", "primary-tint", "light") >= 3.0


def test_type_scale_matches_section_6_1() -> None:
    styles = {style["name"]: style for style in DATA["type"]["styles"]}
    expected = {
        "display": ("display", 40, 44, 600, -1),
        "title-l": ("display", 24, 30, 600, 0),
        "title-m": ("display", 18, 24, 600, 0),
        "body": ("sans", 14, 20, 400, 0),
        "body-strong": ("sans", 14, 20, 600, 0),
        "caption": ("sans", 12, 16, 400, 0),
        "label": ("sans", 11, 14, 600, 6),
        "mono": ("mono", 13, 18, 400, 0),
    }
    for name, (family, size, line, weight, tracking) in expected.items():
        style = styles[name]
        assert (style["family"], style["size"], style["lineHeight"]) == (family, size, line)
        assert (style["weight"], style["trackingPercent"]) == (weight, tracking)
    assert styles["label"]["uppercase"] is True
    assert DATA["type"]["textScales"] == [90, 100, 115, 130]


def test_font_files_exist_with_their_licences() -> None:
    assets = TOKENS.parent.parent
    for font in DATA["type"]["fonts"]:
        assert (assets / font["file"]).is_file()
        assert "SIL Open Font License" in (assets / font["license"]).read_text(encoding="utf-8")


def test_spacing_radius_and_motion() -> None:
    spacing = {t["name"]: t["value"] for t in DATA["spacing"]["tokens"]}
    assert spacing == {f"space-{n}": f"{4 * n}px" for n in (1, 2, 3, 4, 6, 8, 10, 12)}
    radius = {t["name"]: t["value"] for t in DATA["radius"]["tokens"]}
    assert radius == {
        "radius-s": "4px",
        "radius-m": "8px",
        "radius-l": "14px",
        "radius-full": "999px",
    }
    motion = {t["name"]: (t["duration"], t["easing"]) for t in DATA["motion"]["tokens"]}
    assert motion == {
        "instant": (80, [0.4, 0, 0.2, 1]),
        "quick": (150, [0.4, 0, 0.2, 1]),
        "settle": (240, [0.22, 1, 0.36, 1]),
        "grow": (400, [0.22, 1, 0.36, 1]),
        "bloom": (700, [0.16, 1, 0.3, 1]),
    }
