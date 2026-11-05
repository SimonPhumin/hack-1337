"""Native ligatures: glyphs constructed from Hack's own strokes (see src/ligatures/recipes.py).

Recipes work in "cell space": an n-character ligature is drawn across x = 0 … n·W (W = Hack's
advance width), using the style's own glyphs as they are. Note that Hack Italic keeps most
operators upright (`= < > | . ~ ≤ ≥ ≠ ≡`); only a few, such as `-` `:` `!`, are slanted. Recipes
can use k.slant where a part should follow the italic angle.

The finished glyph is shifted left by (n-1)·W: like JetBrains Mono's ligatures, it sits on the
last character and extends over the spacers that replace the characters before it.

This module also writes the substitution rules (the `calt` feature) for every ligature:

  - spacer style: c1 c2 … cn becomes LIG … LIG <glyph>, so the text keeps one glyph per character
  - leftmost-longest, like a tokenizer: one lookup scans the line left to right and at each
    position forms the longest ligature that matches there (`<=<=` is `<=` `<=`, `->=>` is `->` `=>`)
  - by default a ligature doesn't form inside a longer run of its first or last character
    (`====` stays plain); `plain_runs=False` turns that off
  - `yields=True` marks decorative ligatures (`$>`, `:<`, `-<`, …) that give way when their tail
    starts another ligature: `:>=` is `:` `>=`
  - per-ligature exceptions: `ignore=["⟨<-⟩[0-9]>"]` (don't form when followed by digits and '>'),
    and `only=[...]` to form exclusively in the given contexts. Patterns are written as
    BEFORE⟨SEQUENCE⟩AFTER, where BEFORE/AFTER are characters or classes like [0-9] or [ .].
"""
import importlib.util
import math
import re
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
    ignore: tuple[str, ...] = ()
    only: tuple[str, ...] = ()
    plain_runs: bool = True
    yields: bool = False

    @property
    def glyph_name(self) -> str:
        return "_".join(UV2AGL.get(ord(c), f"uni{ord(c):04X}") for c in self.sequence) + ".liga"


@dataclass
class Registry:
    ligatures: dict[str, Ligature] = field(default_factory=dict)

    def __call__(self, sequence: str, note: str = "", ignore=(), only=(), plain_runs=True, yields=False):
        def register(fn):
            self.ligatures[sequence] = Ligature(sequence, fn, note, tuple(ignore), tuple(only), plain_runs, yields)
            return fn
        return register

    def rules(self, sequence: str, ignore=(), only=(), plain_runs=None, yields=None):
        """Attach rule settings to an already registered ligature (e.g. one built in a loop)."""
        lig = self.ligatures[sequence]
        lig.ignore += tuple(ignore)
        lig.only += tuple(only)
        if plain_runs is not None:
            lig.plain_runs = plain_runs
        if yields is not None:
            lig.yields = yields


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
    """Add the native ligature glyphs to `font` and return (feature code, glyph names)."""
    recipes = recipes or load_recipes()
    kit = Kit(font)
    glyf, hmtx = font["glyf"], font["hmtx"]
    order = font.getGlyphOrder()

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
        glyf.glyphs[name] = glyph
        hmtx.metrics[name] = (kit.W, getattr(glyph, "xMin", 0))
        built.append(name)

    font.setGlyphOrder(order)
    glyf.glyphOrder = order
    return feature_code(recipes, kit.cmap), built


_TOKEN = re.compile(r"\[((?:\\.|[^\]])+)\]|\\(.)|(.)", re.S)


def _tokens(text: str) -> list[set[int]]:
    """Parse 'ab[0-9][ .]' into a list of code point sets."""
    out = []
    for cls, esc, ch in _TOKEN.findall(text):
        if cls:
            items = [x[-1] for x in re.findall(r"\\.|.", cls, re.S)]
            cps, i = set(), 0
            while i < len(items):
                if i + 2 < len(items) and items[i + 1] == "-":
                    cps |= set(range(ord(items[i]), ord(items[i + 2]) + 1)); i += 3
                else:
                    cps.add(ord(items[i])); i += 1
            out.append(cps)
        else:
            out.append({ord(esc or ch)})
    return out


def _pattern(pattern: str, seq: str) -> tuple[list[set[int]], list[set[int]]]:
    m = re.fullmatch(r"(.*)⟨(.*)⟩(.*)", pattern, re.S)
    if not m or m.group(2) != seq:
        raise ValueError(f"pattern {pattern!r} must look like BEFORE⟨{seq}⟩AFTER")
    return _tokens(m.group(1)), _tokens(m.group(3))


def _yield_patterns(lig: Ligature, all_seqs) -> list[str]:
    """For a yielding ligature X: don't form X when its tail starts another ligature Y."""
    x = lig.sequence
    out = []
    for y in all_seqs:
        if y == x:
            continue
        for k in range(1, len(x)):
            if len(y) > k and x[-k:] == y[:k]:
                out.append(f"⟨{x}⟩" + "".join(_escape(c) for c in y[k:]))
    return out


def _escape(c: str) -> str:
    return "\\" + c if c in "[]\\⟨⟩" else c


def _merge(c1, c2):
    """Intersect two (before, after) contexts; None if they can't both hold."""
    def zip_sets(a, b, reverse):
        a, b = (a[::-1], b[::-1]) if reverse else (a, b)
        out = []
        for i in range(max(len(a), len(b))):
            x = a[i] if i < len(a) else None
            y = b[i] if i < len(b) else None
            z = x if y is None else y if x is None else x & y
            if not z:
                return None
            out.append(z)
        return out[::-1] if reverse else out
    b = zip_sets(c1[0], c2[0], reverse=True)
    a = zip_sets(c1[1], c2[1], reverse=False)
    return None if b is None or a is None else (b, a)


def feature_code(recipes: dict[str, Ligature], cmap: dict[int, str]) -> str:
    """One leftmost-longest lookup for all ligatures (see module docstring)."""
    def cls(cps) -> str | None:
        names = sorted({cmap[c] for c in cps if c in cmap})
        if not names:
            return None
        return f"\\{names[0]}" if len(names) == 1 else "[" + " ".join(f"\\{n}" for n in names) + "]"

    chars = sorted({ord(c) for seq in recipes for c in seq})
    lines = [f"lookup to_spacer {{\n    sub {cls(chars)} by \\{SPACER};\n}} to_spacer;\n"]
    finals = {}
    for lig in recipes.values():
        look = "to_" + lig.glyph_name.replace(".", "_")
        finals[lig.sequence] = look
        lines.append(f"lookup {look} {{\n    sub {cls({ord(lig.sequence[-1])})} by \\{lig.glyph_name};\n}} {look};\n")

    seqs = list(recipes)

    def ignore_contexts(lig):
        seq = lig.sequence
        patterns = [_pattern(p, seq) for p in lig.ignore]
        if lig.yields:
            patterns += [_pattern(p, seq) for p in _yield_patterns(lig, seqs)]
        if lig.plain_runs:
            patterns = [([{ord(seq[0])}], []), ([], [{ord(seq[-1])}])] + patterns
        return patterns

    def emit(lig, ctx=([], [])):
        """Rules for `lig`, restricted to context `ctx` (before, after)."""
        seq = lig.sequence
        g = [cls({ord(c)}) for c in seq]
        if None in g:
            return []
        out = []
        prefixes = sorted((recipes[seq[:k]] for k in range(len(seq) - 1, 1, -1) if seq[:k] in recipes),
                          key=lambda l: -len(l.sequence))
        for pattern in ignore_contexts(lig):
            c = _merge(pattern, ctx)
            if c is None:
                continue
            # Before giving up on `seq` here, let shorter ligatures that start the same way try,
            # in exactly this context (expressed relative to them).
            for p in prefixes:
                rest = [{ord(ch)} for ch in seq[len(p.sequence):]]
                out += emit(p, (c[0], rest + c[1]))
            line = _line("ignore sub", c, [g[0] + "'"] + g[1:], cls)
            if line:
                out.append(line)
        subst = [f"{x}' lookup to_spacer" for x in g[:-1]] + [f"{g[-1]}' lookup {finals[seq]}"]
        contexts = [_pattern(p, seq) for p in lig.only] or [([], [])]
        for only in contexts:
            c = _merge(only, ctx)
            if c is not None:
                line = _line("sub", c, subst, cls)
                if line:
                    out.append(line)
        return out

    body = []
    for lig in sorted(recipes.values(), key=lambda l: (-len(l.sequence), l.sequence)):
        body.append(f"    # {lig.sequence}")
        body += emit(lig)
    lines.append("lookup ligatures {\n" + "\n".join(body) + "\n} ligatures;\n")
    return ("# Native ligature rules (scripts/native.py)\n\n" + "\n".join(lines)
            + "\nfeature calt {\n    lookup ligatures;\n} calt;\n")


def _line(keyword, ctx, inner, cls) -> str | None:
    before = [cls(t) for t in ctx[0]]
    after = [cls(t) for t in ctx[1]]
    if None in before or None in after:
        return None
    return f"    {keyword} {' '.join(before + inner + after)};"
