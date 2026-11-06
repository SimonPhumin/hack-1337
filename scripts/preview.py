"""Render the preview images and regenerate docs/ligatures.md.

Code is highlighted by Shiki (scripts/highlight.mjs) with the Tokyo Night theme, the one
Conductor and many editors use. Each line is shaped with HarfBuzz, one run per font style
(italic and bold tokens use Hack 1337 Italic and Bold, as in an editor), and each glyph is
rasterized by FreeType in its token's colour.
"""
import json
import subprocess
from pathlib import Path

import freetype
import uharfbuzz as hb
from PIL import Image

from check import Shaper, ligature_set
from config import FAMILY, ROOT

THEME = "tokyo-night"
SAMPLES = ["bisect.py", "debounce.ts"]
SIZE = 32             # font size in px (images are 2x, for high-density screens)
LINE_HEIGHT = 1.3     # in em, like an editor (the font's own line height is 1.0 em)
MARGIN = 48

Token = tuple[str, str, str]  # text, colour, style ("", "italic", "bold", "bold italic")
FONT_STYLES = {"": "Regular", "italic": "Italic", "bold": "Bold", "bold italic": "Bold Italic"}


class Font:
    """One style of Hack 1337, for shaping (HarfBuzz) and rasterizing (FreeType)."""

    def __init__(self, path: Path, size: int):
        self.hb = hb.Font(hb.Face(hb.Blob(path.read_bytes())))
        self.ft = freetype.Face(str(path))
        self.ft.set_char_size(size * 64)
        self.scale = size / self.ft.units_per_EM
        self.ascent = self.ft.ascender * self.scale

    def shape(self, text: str, ligatures: bool) -> tuple[list[tuple[int, int, float]], float]:
        """([(glyph id, index of its character, x in px)], advance of the whole run in px)"""
        buf = hb.Buffer()
        buf.add_codepoints([ord(c) for c in text])
        buf.guess_segment_properties()
        hb.shape(self.hb, buf, {"calt": ligatures})
        out, x = [], 0
        for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
            out.append((info.codepoint, info.cluster, (x + pos.x_offset) * self.scale))
            x += pos.x_advance
        return out, x * self.scale

    def draw(self, img: Image.Image, gid: int, x: float, baseline: float, color: str) -> None:
        # Render at the exact subpixel x position, so monospace columns stay even.
        frac = x - int(x)
        self.ft.set_transform(freetype.Matrix(0x10000, 0, 0, 0x10000), freetype.Vector(round(frac * 64), 0))
        self.ft.load_glyph(gid, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
        g = self.ft.glyph
        bm = g.bitmap
        if not bm.width or not bm.rows:
            return
        mask = Image.frombytes("L", (bm.pitch, bm.rows), bytes(bm.buffer)).crop((0, 0, bm.width, bm.rows))
        img.paste(color, (int(x) + g.bitmap_left, round(baseline) - g.bitmap_top), mask)


def render(lines: list[list[Token]], out: Path, bg: str, ligatures: bool = True, size: int = SIZE,
           line_height: float = LINE_HEIGHT) -> None:
    fonts = {style: Font(ROOT / "ttf" / f"{FAMILY} {name}.ttf", size) for style, name in FONT_STYLES.items()}
    regular = fonts[""]
    cell = regular.ft.max_advance_width * regular.scale
    step = size * line_height
    width = round(2 * MARGIN + cell * max(sum(len(t) for t, _, _ in line) for line in lines))
    height = round(2 * MARGIN + step * len(lines))
    img = Image.new("RGB", (width, height), bg)

    for row, line in enumerate(lines):
        # Baseline: centre the font's 1 em line box in the taller editor line.
        baseline = MARGIN + row * step + (step - size) / 2 + regular.ascent
        x = MARGIN
        for style, run in _runs(line):
            text = "".join(t for t, _, _ in run)
            colors = [c for t, c, _ in run for _ in t]
            glyphs, advance = fonts[style].shape(text, ligatures)
            for gid, cluster, dx in glyphs:
                fonts[style].draw(img, gid, x + dx, baseline, colors[cluster])
            x += advance
    img.save(out, optimize=True)


def _runs(line: list[Token]) -> list[tuple[str, list[Token]]]:
    """Group consecutive tokens with the same font style (editors shape each such run on its own)."""
    runs: list[tuple[str, list[Token]]] = []
    for tok in line:
        style = tok[2] if tok[0].strip() else (runs[-1][0] if runs else "")
        if runs and runs[-1][0] == style:
            runs[-1][1].append(tok)
        else:
            runs.append((style, [tok]))
    return runs


def highlight(files: list[Path]) -> dict:
    cmd = ["node", str(ROOT / "scripts" / "highlight.mjs"), THEME, *map(str, files)]
    return json.loads(subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True).stdout)


def main() -> None:
    hl = highlight([ROOT / "preview" / "samples" / f for f in SAMPLES])
    lines: list[list[Token]] = []
    for i, file in enumerate(hl["files"]):
        lines += ([[]] if i else []) + file

    render(lines, ROOT / "preview" / "code.png", hl["bg"])
    render(lines, ROOT / "preview" / "code-no-ligatures.png", hl["bg"], ligatures=False)

    regular = ROOT / "ttf" / f"{FAMILY} Regular.ttf"
    ligs = sorted(ligature_set(Shaper(regular.read_bytes())).values(), key=lambda s: (len(s), s))
    per_row = 16
    rows = ["  ".join(ligs[i:i + per_row]) for i in range(0, len(ligs), per_row)]
    render([[(r, hl["fg"], "")] for r in rows], ROOT / "preview" / "ligatures.png", hl["bg"], line_height=1.5)

    table = ["| Ligature | Characters |", "| --- | --- |"]
    table += [f"| <code>{s.replace('|', '&#124;')}</code> | {' '.join(f'`U+{ord(c):04X}`' for c in s)} |" for s in ligs]
    (ROOT / "docs" / "ligatures.md").write_text(
        "# Ligatures\n\n"
        f"Hack 1337 has {len(ligs)} programming ligatures, drawn from Hack's own strokes by "
        "`src/ligatures/recipes.py`. They live in the `calt` (contextual alternates) feature.\n\n"
        "This file is generated by `make previews`.\n\n"
        "![Ligatures](../preview/ligatures.png)\n\n"
        "## Stylistic sets\n\n"
        "| Feature | Effect |\n| --- | --- |\n"
        "| `ss01` | Plain comparison operators: no ligatures for `<=` `>=` `==` `!=` "
        "(and sequences built on them, such as `===` `!==` `<=>` `==>`). |\n\n"
        "## All ligatures\n\n" + "\n".join(table) + "\n"
    )
    print(f"rendered previews, {len(ligs)} ligatures")


if __name__ == "__main__":
    main()
