"""Native ligatures: glyphs constructed from Hack's own strokes (see src/ligatures/recipes.py).

Recipes work in "cell space": an n-character ligature is drawn across x = 0 … n·W (W = Hack's
advance width), using the style's own glyphs as they are. Note that Hack Italic keeps most
operators upright (`= < > | . ~ ≤ ≥ ≠ ≡`); only a few, such as `-` `:` `!`, are slanted. Recipes
can use k.slant where a part should follow the italic angle.

The finished glyph is shifted left by (n-1)·W: like JetBrains Mono's ligatures, it sits on the
last character and extends over the spacers that replace the characters before it.

Native glyphs either replace a JetBrains Mono ligature glyph of the same name (the JetBrains
Mono `calt` rules keep working) or add a new ligature, for which this module also writes the
substitution rules.
"""
import importlib.util
import math
from dataclasses import dataclass, field

import pathops
from fontTools.agl import UV2AGL
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

from config import ROOT

SPACER = "LIG"


# --- path helpers -------------------------------------------------------------------------

def rect(x0: float, y0: float, x1: float, y1: float) -> pathops.Path:
    return polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def polygon(points) -> pathops.Path:
    p = pathops.Path()
    p.moveTo(*points[0])
    for pt in points[1:]:
        p.lineTo(*pt)
    p.close()
    return p


def move(p: pathops.Path, dx: float = 0, dy: float = 0) -> pathops.Path:
    return p.transform(translateX=dx, translateY=dy)


def scale(p: pathops.Path, sx: float, sy: float | None = None, origin=(0, 0)) -> pathops.Path:
    sy = sx if sy is None else sy
    ox, oy = origin
    return p.transform(scaleX=sx, scaleY=sy, translateX=ox - ox * sx, translateY=oy - oy * sy)


def mirror(p: pathops.Path, axis_x: float) -> pathops.Path:
    return p.transform(scaleX=-1, translateX=2 * axis_x)


def union(*paths: pathops.Path) -> pathops.Path:
    # Pairwise ops on purpose: skia's OpBuilder has an all-union fast path that merges by winding
    # direction, so overlapping parts drawn in opposite directions cancel out.
    out = pathops.Path()
    for p in paths:
        out = pathops.op(out, p, pathops.PathOp.UNION, fix_winding=True)
    return out


def intersect(a: pathops.Path, b: pathops.Path) -> pathops.Path:
    return pathops.op(a, b, pathops.PathOp.INTERSECTION, fix_winding=True)


def subtract(a: pathops.Path, b: pathops.Path) -> pathops.Path:
    return pathops.op(a, b, pathops.PathOp.DIFFERENCE, fix_winding=True)


def bounds(p: pathops.Path) -> tuple[float, float, float, float]:
    return p.bounds


def center_x(p: pathops.Path) -> float:
    x0, _, x1, _ = p.bounds
    return (x0 + x1) / 2


def hull(p: pathops.Path) -> pathops.Path:
    """Convex hull of a path's points (monotone chain)."""
    pts = sorted({(round(x, 3), round(y, 3)) for x, y in p.points})
    def half(points):
        out = []
        for pt in points:
            while len(out) >= 2 and ((out[-1][0] - out[-2][0]) * (pt[1] - out[-2][1])
                                     - (out[-1][1] - out[-2][1]) * (pt[0] - out[-2][0])) <= 0:
                out.pop()
            out.append(pt)
        return out
    lower, upper = half(pts), half(reversed(pts))
    return polygon(lower[:-1] + upper[:-1])


# --- the per-style kit --------------------------------------------------------------------

class Kit:
    """Hack's parts and measurements for one style."""

    def __init__(self, font: TTFont):
        self.font = font
        self.glyphset = font.getGlyphSet()
        self.cmap = font.getBestCmap()
        self.W = font["hmtx"][self.cmap[ord("0")]][0]
        self.slant = math.tan(math.radians(-font["post"].italicAngle))
        x0, y0, x1, y1 = self.bbox("=")
        self.axis = (y0 + y1) / 2                       # math axis: centre of '=' (and of '<' '>')
        self.stroke = self.bbox("-")[3] - self.bbox("-")[1]  # horizontal stroke thickness
        self.bar_width = self.bbox("|")[2] - self.bbox("|")[0]  # vertical stroke thickness

    def glyph(self, char: str) -> pathops.Path:
        rec = DecomposingRecordingPen(self.glyphset)
        self.glyphset[self.cmap[ord(char)]].draw(rec)
        p = pathops.Path()
        rec.replay(p.getPen())
        return p

    def contours(self, char: str) -> list[pathops.Path]:
        """The glyph's contours, top to bottom."""
        out = []
        for c in self.glyph(char).contours:
            out.append(c)
        return sorted(out, key=lambda c: -c.bounds[3])

    def bbox(self, char: str) -> tuple[float, float, float, float]:
        return self.glyph(char).bounds

    def bands(self, char: str) -> list[tuple[float, float]]:
        """(bottom, top) of each contour, top to bottom — the bars of '=', '≡', …"""
        return [(c.bounds[1], c.bounds[3]) for c in self.contours(char)]

    def cell(self, char: str, index: float) -> pathops.Path:
        """Hack's glyph for `char`, placed in cell `index` (fractions allowed)."""
        return move(self.glyph(char), index * self.W)


# --- registry -----------------------------------------------------------------------------

@dataclass
class Ligature:
    sequence: str
    build: callable
    note: str = ""

    @property
    def glyph_name(self) -> str:
        return "_".join(UV2AGL.get(ord(c), f"uni{ord(c):04X}") for c in self.sequence) + ".liga"


@dataclass
class Registry:
    ligatures: dict[str, Ligature] = field(default_factory=dict)

    def __call__(self, sequence: str, note: str = ""):
        def register(fn):
            self.ligatures[sequence] = Ligature(sequence, fn, note)
            return fn
        return register


def load_recipes() -> dict[str, Ligature]:
    spec = importlib.util.spec_from_file_location("recipes", ROOT / "src" / "ligatures" / "recipes.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ligature.ligatures


# --- building -----------------------------------------------------------------------------

def to_glyph(path: pathops.Path):
    pen = TTGlyphPen(None)
    path.draw(Cu2QuPen(pen, max_err=1.0, reverse_direction=False))
    return pen.glyph()


def build(font: TTFont, recipes: dict[str, Ligature] | None = None) -> tuple[str, list[str]]:
    """Add/replace native ligature glyphs in `font`.

    Returns (feature code for ligatures JetBrains Mono doesn't have, names of native glyphs).
    """
    recipes = recipes or load_recipes()
    kit = Kit(font)
    glyf, hmtx = font["glyf"], font["hmtx"]
    order = font.getGlyphOrder()
    new_rules = []

    if SPACER not in glyf.glyphs:
        glyf.glyphs[SPACER] = TTGlyphPen(None).glyph()
        hmtx.metrics[SPACER] = (kit.W, 0)
        order.append(SPACER)

    built = []
    for seq, lig in recipes.items():
        n = len(seq)
        path = lig.build(kit)
        path = move(path, -(n - 1) * kit.W)
        path.simplify(fix_winding=True, keep_starting_points=False, clockwise=True)
        glyph = to_glyph(path)
        glyph.recalcBounds(glyf)
        name = lig.glyph_name
        if name not in glyf.glyphs:
            order.append(name)
            new_rules.append(rules(seq, name, kit.cmap))
        glyf.glyphs[name] = glyph
        hmtx.metrics[name] = (kit.W, getattr(glyph, "xMin", 0))
        built.append(name)

    font.setGlyphOrder(order)
    glyf.glyphOrder = order
    # Longest sequences first, so `..=` wins over `..`.
    new_rules.sort(key=lambda r: -r[0])
    fea = "".join(r[1] for r in new_rules)
    if fea:
        fea = f"# Native ligatures (scripts/native.py)\n{fea}\nfeature calt {{\n" + "".join(
            f"    lookup {line.split()[1]};\n" for _, line in new_rules) + "} calt;\n"
    return fea, built


def rules(seq: str, name: str, cmap: dict[int, str]) -> tuple[int, str]:
    """Spacer-style substitution rules: c1 c2 … cn -> LIG … LIG name, not inside longer runs."""
    g = [f"\\{cmap[ord(c)]}" for c in seq]
    n = len(g)
    lookup = "native_" + name.replace(".", "_")
    lines = [
        f"    ignore sub {g[0]} {g[0]}' {' '.join(g[1:])};",
        f"    ignore sub {g[0]}' {' '.join(g[1:])} {g[-1]};",
    ]
    for i in range(n):
        before = " ".join([f"\\{SPACER}"] * i)
        after = " ".join(g[i + 1:])
        out = f"\\{name}" if i == n - 1 else f"\\{SPACER}"
        lines.append(f"    sub {before} {g[i]}' {after} by {out};".replace("  ", " "))
    return n, f"lookup {lookup} {{\n" + "\n".join(lines) + f"\n}} {lookup};\n"
