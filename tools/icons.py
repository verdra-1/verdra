# SPDX-FileCopyrightText: 2026 The Verdra Authors
# SPDX-License-Identifier: Apache-2.0
"""Generate every logo, wordmark, app-icon and tray-icon file from the master geometry and tokens.

Master plan 4.4 and 4.6: icons are generated from the SVG masters, never drawn by hand. Colours
come from `src/verdra/assets/brand/tokens.json` by name; the geometry is the 64 x 64 master from
4.4; the wordmark is outlined from the display font, so the font never needs to ship for it.

    python tools/icons.py            write the SVG files into src/verdra/assets/brand/
    python tools/icons.py --check    fail if the committed SVG files are out of date (CI)
    python tools/icons.py --raster   also render every PNG, ICO and ICNS size into
                                     src/verdra/assets/brand/generated/ (or --out DIR)
"""

from __future__ import annotations

import argparse
import importlib
import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "src" / "verdra" / "assets" / "brand"
TOKENS = BRAND / "tokens.json"
DISPLAY_FONT = ROOT / "src" / "verdra" / "assets" / "fonts" / "Sora-SemiBold.ttf"

# --- Master geometry (Master plan 4.4, 64 x 64 grid) ------------------------------------------

LEFT_LEAF = "M5 6C3 25 13 44 31.2 55.5C26 41 19 24 5 6Z"
RIGHT_LEAF = "M59 12C60 29 50 45 32.8 55.5C37 43 44 27 59 12Z"
NODE = (32.0, 59.6, 3.4)  # cx, cy, r
GRID = 64.0

# App icon: brand-canopy tile with corner radius 14; symbol scaled 0.69 and offset (10, 7);
# node radius 4.4 in the symbol's own units so it stays visible at 16 px.
APP_ICON_SCALE = 0.69
APP_ICON_OFFSET = (10.0, 7.0)
APP_ICON_NODE_RADIUS = 4.4
APP_ICON_CORNER = 14.0

# Wordmark (4.4): weight 600, letter-spacing -2 %, node dot over the final "a" with a diameter of
# 22 % of the x-height and a gap above the x-height equal to its diameter.
WORDMARK_TEXT = "Verdra"
WORDMARK_TRACKING = -0.02
DOT_TO_X_HEIGHT = 0.22

# Tray (4.6): status dot at the bottom right, 40 % of the icon height.
TRAY_DOT = 0.40
TRAY_STATES = ("idle", "routing", "degraded", "error")
TRAY_STATUS_TOKEN = {"routing": "success", "degraded": "warning", "error": "danger"}

# Raster sizes (4.6).
WINDOWS_ICO = (16, 20, 24, 32, 40, 48, 64, 256)
WINDOWS_TILES = (44, 150, 310)
MACOS_ICNS = (16, 32, 64, 128, 256, 512, 1024)
LINUX_HICOLOR = (16, 22, 24, 32, 48, 64, 128, 256, 512)
FAVICON = (16, 32, 48)
TRAY_WINDOWS = (16, 20, 24, 32)
TRAY_LINUX = (22, 24)
TRAY_MACOS_POINTS = 18


@dataclass(frozen=True)
class Palette:
    """The colours one logo variant uses, by role."""

    leaves: str
    node: str


def load_colours() -> dict[str, dict[str, str]]:
    """Return {token name: {theme: value}} for every colour token, resolving aliases."""
    data = json.loads(TOKENS.read_text(encoding="utf-8"))
    themes = [theme["id"] for theme in data["color"]["themes"]]
    raw = {token["name"]: token["value"] for token in data["color"]["tokens"]}

    def resolve(value: object, theme: str) -> str:
        if isinstance(value, dict):
            value = value.get(theme, value[themes[0]])
        assert isinstance(value, str)  # noqa: S101 - tokens.json is ours; fail loudly
        if value.startswith("{") and value.endswith("}"):
            return resolve(raw[value[1:-1]], theme)
        return value

    return {name: {theme: resolve(value, theme) for theme in themes} for name, value in raw.items()}


def svg(view_box: str, body: str) -> str:
    """Wrap SVG elements in a document with a stable layout, so --check can compare text."""
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}">\n{body}</svg>\n'


def symbol_elements(palette: Palette, node_radius: float = NODE[2]) -> str:
    """Return the three shapes of the Living V."""
    cx, cy, _ = NODE
    return (
        f'  <path fill="{palette.leaves}" d="{LEFT_LEAF}"/>\n'
        f'  <path fill="{palette.leaves}" d="{RIGHT_LEAF}"/>\n'
        f'  <circle fill="{palette.node}" cx="{cx:g}" cy="{cy:g}" r="{node_radius:g}"/>\n'
    )


def symbol_svg(palette: Palette) -> str:
    """Return the symbol on the 64 x 64 grid."""
    return svg(f"0 0 {GRID:g} {GRID:g}", symbol_elements(palette))


def app_icon_svg(tile: str, palette: Palette) -> str:
    """Return the app icon: the symbol on a rounded brand tile."""
    dx, dy = APP_ICON_OFFSET
    shapes = symbol_elements(palette, APP_ICON_NODE_RADIUS).replace("\n  <", "\n    <")
    body = (
        f'  <rect fill="{tile}" width="{GRID:g}" height="{GRID:g}" rx="{APP_ICON_CORNER:g}"/>\n'
        f'  <g transform="translate({dx:g} {dy:g}) scale({APP_ICON_SCALE:g})">\n'
        f"  {shapes}  </g>\n"
    )
    return svg(f"0 0 {GRID:g} {GRID:g}", body)


def tray_svg(state: str, ink: str, status: str | None) -> str:
    """Return a colour tray icon for Windows and Linux: the symbol plus a status dot."""
    body = symbol_elements(Palette(leaves=ink, node=ink))
    if status is not None:
        radius = GRID * TRAY_DOT / 2
        centre = GRID - radius
        body += f'  <circle fill="{status}" cx="{centre:g}" cy="{centre:g}" r="{radius:g}"/>\n'
    return svg(f"0 0 {GRID:g} {GRID:g}", body)


def tray_template_svg(state: str) -> str:
    """Return a macOS template tray icon: one colour, the node carries the status.

    Template images must be black with alpha (macOS recolours them), so they use the SVG keyword
    `black` rather than a brand token.
    """
    cx, cy, r = NODE
    body = f'  <path fill="black" d="{LEFT_LEAF}"/>\n  <path fill="black" d="{RIGHT_LEAF}"/>\n'
    if state == "idle":
        ring = f'cx="{cx:g}" cy="{cy:g}" r="{r - 0.8:g}"'
        body += f'  <circle fill="none" stroke="black" stroke-width="1.6" {ring}/>\n'
    elif state == "routing":
        body += f'  <circle fill="black" cx="{cx:g}" cy="{cy:g}" r="{r:g}"/>\n'
    elif state == "degraded":
        top, base = cy - r - 0.4, cy + r - 0.4
        triangle = f"M{cx:g} {top:g}L{cx + r + 0.4:g} {base:g}H{cx - r - 0.4:g}Z"
        body += f'  <path fill="black" d="{triangle}"/>\n'
    else:
        d = r * 0.8
        cross = (
            f"M{cx - d:g} {cy - d:g}L{cx + d:g} {cy + d:g}"
            f"M{cx + d:g} {cy - d:g}L{cx - d:g} {cy + d:g}"
        )
        body += (
            f'  <path fill="none" stroke="black" stroke-width="1.8" stroke-linecap="round" '
            f'd="{cross}"/>\n'
        )
    return svg(f"0 0 {GRID:g} {GRID:g}", body)


# --- Wordmark ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Wordmark:
    """The outlined wordmark in font units, with its metrics."""

    path: str
    dot: tuple[float, float, float]  # cx, cy, r (y grows downwards)
    width: float
    cap_height: float
    ascent: float  # top of the dot, above the baseline
    baseline_to_bottom: float  # descent of the outlines below the baseline (0 for "Verdra")


def wordmark() -> Wordmark:
    """Shape "Verdra" with HarfBuzz, outline it with fontTools, and place the node dot."""
    hb: Any = importlib.import_module("uharfbuzz")  # dev-only dependency, loaded on use
    from fontTools.pens.boundsPen import BoundsPen  # noqa: PLC0415
    from fontTools.pens.svgPathPen import SVGPathPen  # noqa: PLC0415
    from fontTools.pens.transformPen import TransformPen  # noqa: PLC0415
    from fontTools.ttLib import TTFont  # noqa: PLC0415

    data = DISPLAY_FONT.read_bytes()
    font = TTFont(io.BytesIO(data))
    glyph_set = font.getGlyphSet()
    head: Any = font["head"]
    os2: Any = font["OS/2"]
    units = head.unitsPerEm
    x_height, cap_height = float(os2.sxHeight), float(os2.sCapHeight)

    shaper = hb.Font(hb.Face(data))
    buffer = hb.Buffer()
    buffer.add_str(WORDMARK_TEXT)
    buffer.guess_segment_properties()
    hb.shape(shaper, buffer, {"kern": True, "liga": False})

    pen = SVGPathPen(glyph_set, ntos=lambda value: f"{round(value, 1):g}")
    tracking = WORDMARK_TRACKING * units
    x = 0.0
    last_bounds = (0.0, 0.0, 0.0, 0.0)
    glyph_names = font.getGlyphOrder()
    for index, (info, position) in enumerate(
        zip(buffer.glyph_infos, buffer.glyph_positions, strict=True)
    ):
        name = glyph_names[info.codepoint]
        # Flip y so the outlines read top-down like the rest of the SVG.
        glyph_set[name].draw(TransformPen(pen, (1, 0, 0, -1, x + position.x_offset, 0)))
        if index == len(buffer.glyph_infos) - 1:
            bounds_pen = BoundsPen(glyph_set)
            glyph_set[name].draw(bounds_pen)
            left, _bottom, right, _top = bounds_pen.bounds or (0, 0, 0, 0)
            last_bounds = (x + left, 0.0, x + right, 0.0)
        x += position.x_advance + tracking
    width = x - tracking

    diameter = DOT_TO_X_HEIGHT * x_height
    radius = diameter / 2
    centre_x = (last_bounds[0] + last_bounds[2]) / 2
    centre_y = -(x_height + diameter + radius)
    return Wordmark(
        path=pen.getCommands(),
        dot=(round(centre_x, 1), round(centre_y, 1), round(radius, 1)),
        width=round(width, 1),
        cap_height=cap_height,
        ascent=-(centre_y - radius),
        baseline_to_bottom=0.0,
    )


def wordmark_body(mark: Wordmark, ink: str, node: str, *, dx: float, dy: float) -> str:
    """Return the wordmark's elements placed with its baseline at dy."""
    cx, cy, r = mark.dot
    return (
        f'  <g transform="translate({dx:g} {dy:g}) scale(1)">\n'
        f'    <path fill="{ink}" d="{mark.path}"/>\n'
        f'    <circle fill="{node}" cx="{cx:g}" cy="{cy:g}" r="{r:g}"/>\n'
        f"  </g>\n"
    )


def wordmark_svg(mark: Wordmark, ink: str, node: str) -> str:
    """Return the wordmark alone, in font units."""
    height = mark.ascent
    body = wordmark_body(mark, ink, node, dx=0, dy=height)
    return svg(f"0 0 {mark.width:g} {round(height, 1):g}", body)


def symbol_bounds() -> tuple[float, float, float, float]:
    """Return the ink bounds of the symbol on the 64 grid."""
    from fontTools.pens.boundsPen import BoundsPen  # noqa: PLC0415
    from fontTools.svgLib.path import parse_path  # noqa: PLC0415

    pen = BoundsPen(None)
    parse_path(LEFT_LEAF, pen)
    parse_path(RIGHT_LEAF, pen)
    left, top, right, bottom = pen.bounds or (0.0, 0.0, GRID, GRID)
    cx, cy, r = NODE
    return min(left, cx - r), min(top, cy - r), max(right, cx + r), max(bottom, cy + r)


def lockup_svg(mark: Wordmark, palette: Palette, ink: str, *, stacked: bool) -> str:
    """Return a lockup in wordmark units (4.4).

    Horizontal: symbol height = 1.6 x cap height, gap = 0.5 x symbol width, symbol bottom on the
    baseline. Stacked: symbol height = 2 x cap height, centred above the wordmark, gap = 0.25 x
    symbol height.
    """
    left, top, right, bottom = symbol_bounds()
    symbol_height = (2.0 if stacked else 1.6) * mark.cap_height
    scale = symbol_height / (bottom - top)
    symbol_width = (right - left) * scale
    shapes = symbol_elements(palette).replace("\n  <", "\n    <")
    if stacked:
        width = max(symbol_width, mark.width)
        gap = 0.25 * symbol_height
        sx = (width - symbol_width) / 2 - left * scale
        baseline = symbol_height + gap + mark.cap_height
        wx = (width - mark.width) / 2
        height = baseline
    else:
        gap = 0.5 * symbol_width
        baseline = max(symbol_height, mark.ascent)
        sx = -left * scale
        wx = symbol_width + gap
        width = wx + mark.width
        height = baseline
    sy = (baseline - symbol_height) - top * scale if not stacked else -top * scale
    place = f"translate({round(sx, 1):g} {round(sy, 1):g}) scale({round(scale, 4):g})"
    body = f'  <g transform="{place}">\n  {shapes}  </g>\n' + wordmark_body(
        mark, ink, palette.node, dx=round(wx, 1), dy=round(baseline, 1)
    )
    return svg(f"0 0 {round(width, 1):g} {round(height, 1):g}", body)


# --- File set ---------------------------------------------------------------------------------


def svg_files() -> dict[str, str]:
    """Return {file name: SVG text} for every vector file under assets/brand/."""
    colours = load_colours()

    def token(name: str, theme: str = "light") -> str:
        return colours[name][theme]

    light = Palette(leaves=token("brand-canopy"), node=token("brand-verdigris"))
    reversed_ = Palette(leaves=token("brand-mist"), node=token("brand-sprout"))
    mono_dark = token("ink", "light")
    mono_light = token("on-primary", "light")
    files = {
        "symbol.svg": symbol_svg(light),
        "symbol-reversed.svg": symbol_svg(reversed_),
        "symbol-mono-dark.svg": symbol_svg(Palette(mono_dark, mono_dark)),
        "symbol-mono-light.svg": symbol_svg(Palette(mono_light, mono_light)),
        "app-icon.svg": app_icon_svg(token("brand-canopy"), reversed_),
    }
    for state in TRAY_STATES:
        status_token = TRAY_STATUS_TOKEN.get(state)
        for theme in ("light", "dark"):
            status = token(status_token, theme) if status_token else None
            files[f"tray-{state}-{theme}.svg"] = tray_svg(state, token("ink-muted", theme), status)
        files[f"tray-{state}-template.svg"] = tray_template_svg(state)
    mark = wordmark()
    files["wordmark.svg"] = wordmark_svg(mark, light.leaves, light.node)
    files["wordmark-reversed.svg"] = wordmark_svg(mark, reversed_.leaves, reversed_.node)
    files["lockup-horizontal.svg"] = lockup_svg(mark, light, light.leaves, stacked=False)
    files["lockup-horizontal-reversed.svg"] = lockup_svg(
        mark, reversed_, reversed_.leaves, stacked=False
    )
    files["lockup-stacked.svg"] = lockup_svg(mark, light, light.leaves, stacked=True)
    files["lockup-stacked-reversed.svg"] = lockup_svg(
        mark, reversed_, reversed_.leaves, stacked=True
    )
    return files


def render_png(svg_text: str, size: int) -> bytes:
    """Render SVG text into a square PNG of the given pixel size."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt  # noqa: PLC0415
    from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: PLC0415
    from PySide6.QtSvg import QSvgRenderer  # noqa: PLC0415

    if QGuiApplication.instance() is None:
        render_png.app = QGuiApplication(["icons", "-platform", "offscreen"])  # type: ignore[attr-defined]
    renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    # PySide6 stubs type the format as bytes, but the binding only accepts str here.
    image.save(buffer, "PNG")  # pyright: ignore[reportArgumentType, reportCallIssue]
    return bytes(data.data())


def raster_files(files: dict[str, str], out: Path) -> list[Path]:
    """Render every raster size from 4.6 into `out` and return the files written."""
    from PIL import Image  # noqa: PLC0415

    from verdra.soil import terrain  # noqa: PLC0415

    written: list[Path] = []

    def write(relative: str, data: bytes) -> None:
        path = out / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        written.append(path)

    def image(svg_name: str, size: int) -> Image.Image:
        return Image.open(io.BytesIO(render_png(files[svg_name], size))).convert("RGBA")

    def multi(fmt: str, sizes: tuple[int, ...]) -> bytes:
        frames = [image("app-icon.svg", size) for size in sizes]
        buffer = io.BytesIO()
        largest = frames[-1]
        if fmt == "ICO":
            largest.save(buffer, fmt, sizes=[(s, s) for s in sizes], append_images=frames[:-1])
        else:
            largest.save(buffer, fmt, append_images=frames[:-1])
        return buffer.getvalue()

    app_id = terrain.LINUX_ICON_NAME
    write("windows/verdra.ico", multi("ICO", WINDOWS_ICO))
    for size in WINDOWS_TILES:
        write(f"windows/tile-{size}.png", render_png(files["app-icon.svg"], size))
    write("macos/verdra.icns", multi("ICNS", MACOS_ICNS))
    for size in LINUX_HICOLOR:
        write(
            f"linux/hicolor/{size}x{size}/apps/{app_id}.png",
            render_png(files["app-icon.svg"], size),
        )
    write(f"linux/hicolor/scalable/apps/{app_id}.svg", files["app-icon.svg"].encode("utf-8"))
    write(
        f"linux/hicolor/symbolic/apps/{terrain.LINUX_TRAY_ICON_NAME}.svg",
        files["tray-routing-template.svg"].encode("utf-8"),
    )
    write("flatpak/icon-128.png", render_png(files["app-icon.svg"], 128))
    write("favicon/favicon.svg", files["app-icon.svg"].encode("utf-8"))
    buffer = io.BytesIO()
    frames = [image("app-icon.svg", size) for size in FAVICON]
    frames[-1].save(buffer, "ICO", sizes=[(s, s) for s in FAVICON], append_images=frames[:-1])
    write("favicon/favicon.ico", buffer.getvalue())
    for state in TRAY_STATES:
        for theme in ("light", "dark"):
            name = f"tray-{state}-{theme}.svg"
            for size in TRAY_WINDOWS:
                write(f"tray/windows/{state}-{theme}-{size}.png", render_png(files[name], size))
            for size in TRAY_LINUX:
                write(f"tray/linux/{state}-{theme}-{size}.png", render_png(files[name], size))
            write(f"tray/linux/{state}-{theme}.svg", files[name].encode("utf-8"))
        template = files[f"tray-{state}-template.svg"]
        title = state.capitalize()
        write(f"tray/macos/{title}Template.png", render_png(template, TRAY_MACOS_POINTS))
        write(f"tray/macos/{title}Template@2x.png", render_png(template, TRAY_MACOS_POINTS * 2))
    return written


def main() -> int:
    """Write, check or render the icon set and return a process exit code."""
    parser = argparse.ArgumentParser(description="Generate Verdra's icons")
    parser.add_argument("--check", action="store_true", help="fail if committed SVGs are stale")
    parser.add_argument("--raster", action="store_true", help="also render raster sizes")
    parser.add_argument("--out", type=Path, default=BRAND / "generated")
    arguments = parser.parse_args()

    files = svg_files()
    if arguments.check:
        stale = [
            name
            for name, text in files.items()
            if not (BRAND / name).exists() or (BRAND / name).read_text(encoding="utf-8") != text
        ]
        for name in stale:
            print(f"src/verdra/assets/brand/{name} is out of date; run python tools/icons.py")
        return 1 if stale else 0
    for name, text in files.items():
        (BRAND / name).write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {len(files)} SVG files.")
    if arguments.raster:
        written = raster_files(files, arguments.out)
        print(f"Rendered {len(written)} raster files into {arguments.out}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
