"""Hack 1337 native ligatures, built from Hack's own strokes.

Each recipe receives a Kit for the style being built (Regular, Bold, Italic, Bold Italic) and
returns the ligature drawn across n cells (x = 0 … n·W), upright. Measurements come from Hack's
own glyphs, so the same recipe produces the right weight in every style.

Kit:   k.W (cell width) · k.axis (centre of '=', '<', '>') · k.stroke (thickness of '-')
       k.bar_width (thickness of '|') · k.glyph(c) · k.cell(c, i) · k.bbox(c) · k.bands(c)
Paths: rect · polygon · move · scale · mirror · union · intersect · subtract · hull · bounds

k.slant is the italic angle's tangent (0 upright).
"""
import math

import pathops

from native import Registry, mirror, polygon, bounds, center_x, hull, intersect, move, rect, scale, subtract, union

ligature = Registry()


# --- arrows: Hack's '<' / '>' as heads, shafts at the math axis ----------------------------

HEAD_ANGLE = 50  # degrees between an arrowhead arm and the shaft (Hack's '>' is a flat ~21°)


def _head(k, tip_x, side="right"):
    """An arrowhead: a mitred chevron with Hack's stroke, as tall as Hack's '>', arms cut level."""
    _, y0, _, y1 = k.bbox(">")
    half, t = (y1 - y0) / 2, k.stroke
    angle = math.radians(HEAD_ANGLE)
    reach = (half + t) / math.tan(angle)                         # horizontal run of the arms
    vertex = tip_x - (t / 2) / math.sin(math.pi / 2 - angle)     # so the mitre tip lands on tip_x
    arms = pathops.Path()
    arms.moveTo(vertex - reach, k.axis + half + t)
    arms.lineTo(vertex, k.axis)
    arms.lineTo(vertex - reach, k.axis - half - t)
    arms.stroke(t, pathops.LineCap.BUTT_CAP, pathops.LineJoin.MITER_JOIN, 10)
    head = intersect(arms, rect(-10 * k.W, k.axis - half, 10 * k.W, k.axis + half))
    return head if side == "right" else mirror(head, tip_x)


def _chevron(k, edge_x, pointing, align):
    """A chevron pointing 'right' or 'left', placed so that its `align` side ('tip' or 'arms')
    sits on x = edge_x."""
    head = _head(k, 0, pointing)
    x0, _, x1, _ = bounds(head)
    if pointing == "right":
        ref = x1 if align == "tip" else x0
    else:
        ref = x0 if align == "tip" else x1
    return move(head, edge_x - ref)


def _end(k, kind, at, edge_x):
    """End piece of an arrow at the `at` ('left'/'right') end, outer edge on edge_x.
    Returns (shapes, inner) — `inner` is the piece the shafts run into."""
    out = 1 if at == "right" else -1                 # direction pointing out of the arrow
    outward = "right" if at == "right" else "left"
    inward = "left" if at == "right" else "right"
    # Spacing of doubled heads/tails: one chevron stroke (measured horizontally) plus white space,
    # so Bold doesn't clog up.
    gap = k.stroke / math.sin(math.radians(HEAD_ANGLE)) + max(0.12 * k.W, 0.8 * k.stroke)
    if kind == "head":
        piece = _chevron(k, edge_x, outward, "tip")
        return [piece], piece
    if kind == "head2":
        outer = _chevron(k, edge_x, outward, "tip")
        inner = _chevron(k, edge_x - out * gap, outward, "tip")
        return [outer, inner], inner
    if kind == "tail":
        piece = _chevron(k, edge_x, inward, "arms")
        return [piece], piece
    if kind == "tail2":
        outer = _chevron(k, edge_x, inward, "arms")
        inner = _chevron(k, edge_x - out * gap, inward, "arms")
        return [outer, inner], inner
    if kind in ("bar", "bar2"):
        _, y0, _, y1 = k.bbox(">")
        bars = []
        for i in range(2 if kind == "bar2" else 1):
            edge = edge_x - out * i * 0.45 * k.W
            x0, x1 = sorted((edge, edge - out * k.bar_width))
            bars.append(rect(x0, y0, x1, y1))
        return bars, bars[-1]
    raise ValueError(kind)


def _wave(k, x0, x1, anchor_left=True, anchor_right=True):
    """A sine stroke with the height and weight of Hack's '~', crossing the math axis at the
    anchored ends (so it can run into an arrowhead) — one wave per cell, like '~'."""
    tx0, ty0, tx1, ty1 = k.bbox("~")
    amp, t = (ty1 - ty0 - k.stroke) / 2, k.stroke
    length = x1 - x0
    wavelength = tx1 - tx0
    if anchor_left and anchor_right:  # fit a whole number of half waves
        wavelength = length / max(1, round(2 * length / wavelength)) * 2
    phase_x = x0 if anchor_left or not anchor_right else x1
    steps = max(16, int(64 * length / wavelength))
    line = pathops.Path()
    for i in range(steps + 1):
        x = x0 + length * i / steps
        y = k.axis + amp * math.sin(2 * math.pi * (x - phase_x) / wavelength)
        (line.moveTo if i == 0 else line.lineTo)(x, y)
    line.stroke(t, pathops.LineCap.BUTT_CAP, pathops.LineJoin.ROUND_JOIN, 4)
    line.convertConicsToQuads()  # round joins come out as conics, which fonts can't store
    return union(line)


def _attach(body, piece, at, kind):
    """Clip `body` (the shafts) so it ends inside `piece` and merges into it.

    Heads and bars: the shafts may run through the head's open pocket up to its tip.
    Tails: the pocket opens away from the shafts, so they stop at the back of the chevron."""
    px0, _, px1, _ = bounds(piece)
    W = 10_000
    if kind.startswith("tail"):
        inner_side = rect(px0 - 1, -W, W, W) if at == "left" else rect(-W, -W, px1 + 1, W)
        pocket = subtract(hull(piece), piece)
        return intersect(body, subtract(inner_side, pocket))
    open_side = rect(-W, -W, px0 + 1, W) if at == "right" else rect(px1 - 1, -W, W, W)
    return intersect(body, union(open_side, hull(piece)))


def arrow(k, n, shaft="-", left=None, right=None):
    """An n-cell arrow. shaft: '-' (one shaft at the math axis, Hack's '-' thickness) or '='
    (Hack's '=' bars) or '~' (a wave like Hack's '~'). Ends: None, 'head', 'head2', 'tail',
    'tail2', 'bar' or 'bar2'. Outer edges land where Hack's '<' starts and '>' ends; plain ends
    stop where Hack's '-'/'='/'~' would."""
    sx0, _, sx1, _ = k.bbox(shaft)
    L, R = k.bbox("<")[0], (n - 1) * k.W + k.bbox(">")[2]
    x0 = L if left else sx0
    x1 = R if right else (n - 1) * k.W + sx1
    if shaft == "~":
        # Anchor the wave on the axis where it meets a head, so it runs into the tip.
        body = _wave(k, x0, x1, anchor_left=bool(left), anchor_right=bool(right))
    else:
        bands = [(k.axis - k.stroke / 2, k.axis + k.stroke / 2)] if shaft == "-" else k.bands("=")
        body = union(*(rect(x0, b, x1, t) for b, t in bands))
        body = body.transform(skewX=k.slant, translateX=-k.slant * k.axis)  # italic shaft ends
    shapes = []
    for kind, at, edge in ((left, "left", L), (right, "right", R)):
        if kind:
            pieces, inner = _end(k, kind, at, edge)
            body = _attach(body, inner, at, kind)
            shapes += pieces
    return union(body, *shapes)


ARROWS = {
    # sequence: (shaft, left end, right end)
    "->": ("-", None, "head"),     "<-": ("-", "head", None),     "<->": ("-", "head", "head"),
    "-->": ("-", None, "head"),    "<--": ("-", "head", None),
    "->>": ("-", None, "head2"),   "<<-": ("-", "head2", None),
    ">->": ("-", "tail", "head"),  "<-<": ("-", "head", "tail"),
    "-<": ("-", None, "tail"),     ">-": ("-", "tail", None),
    "-<<": ("-", None, "tail2"),   ">>-": ("-", "tail2", None),
    "|->": ("-", "bar", "head"),   "<-|": ("-", "head", "bar"),
    "-|": ("-", None, "bar"),      "|-": ("-", "bar", None),
    "=>": ("=", None, "head"),     "==>": ("=", None, "head"),    "<==": ("=", "head", None),
    "<=>": ("=", "head", "head"),  "<==>": ("=", "head", "head"),
    "=>>": ("=", None, "head2"),   "<<=": ("=", "head2", None),
    ">=>": ("=", "tail", "head"),  "<=<": ("=", "head", "tail"),
    "=<<": ("=", None, "tail2"),   ">>=": ("=", "tail2", None),
    "|=>": ("=", "bar", "head"),   "<=|": ("=", "head", "bar"),
    "|=": ("=", "bar", None),      "||=": ("=", "bar2", None),    "||-": ("-", "bar2", None),
    "~>": ("~", None, "head"),     "~~>": ("~", None, "head"),    "<~": ("~", "head", None),
    "<~~": ("~", "head", None),    "<~>": ("~", "head", "head"),  "<<~": ("~", "head2", None),
    "~~": ("~", None, None),
}

for _seq, (_shaft, _left, _right) in ARROWS.items():
    ligature(_seq)(lambda k, n=len(_seq), s=_shaft, l=_left, r=_right: arrow(k, n, s, l, r))


def _outlined(shape, stroke):
    """A ring of constant thickness `stroke` just inside `shape`'s outline (mitred corners)."""
    band = pathops.Path(shape)
    band.stroke(2 * stroke, pathops.LineCap.BUTT_CAP, pathops.LineJoin.MITER_JOIN, 10)
    return intersect(shape, band)


def _triangle(k, back_x, pointing="right"):
    """An outlined triangle with Hack's '|' stroke and '>' proportions (enlarged so the counter
    stays open in Bold), its vertical back edge at x = back_x."""
    x0, y0, x1, y1 = k.bbox(">")
    w, h = 1.3 * (x1 - x0), 1.15 * (y1 - y0)
    tri = _outlined(polygon([(back_x, k.axis - h / 2), (back_x + w, k.axis), (back_x, k.axis + h / 2)]),
                    k.bar_width)
    return tri if pointing == "right" else mirror(tri, back_x)


def _triangle_width(k):
    x0, _, x1, _ = k.bbox(">")
    return 1.3 * (x1 - x0)


def _triangle_height(k):
    _, y0, _, y1 = k.bbox(">")
    return 1.15 * (y1 - y0)


@ligature("|>", "pipeline: an outlined triangle with Hack's '|' stroke and '>' proportions")
def _(k):
    return _triangle(k, k.W - _triangle_width(k) / 2)


@ligature("<|")
def _(k):
    return _triangle(k, k.W + _triangle_width(k) / 2, "left")


@ligature("<|>", "two triangles back to back: an outlined diamond split by a '|'")
def _(k):
    mid, w, h = 1.5 * k.W, _triangle_width(k), _triangle_height(k)
    diamond = polygon([(mid - w, k.axis), (mid, k.axis - h / 2), (mid + w, k.axis), (mid, k.axis + h / 2)])
    bar = intersect(diamond, rect(mid - k.bar_width / 2, -k.W, mid + k.bar_width / 2, 2 * k.W))
    return union(_outlined(diamond, k.bar_width), bar)


def _bars_then_triangle(k, n, extra):
    """`extra` more '|' strokes in front of a '|>' triangle (pointing right), filling n cells."""
    w = _triangle_width(k)
    back = n * k.W - (k.W - w / 2) - w   # triangle in the last two cells, like '|>'
    y0, y1 = k.axis - _triangle_height(k) / 2, k.axis + _triangle_height(k) / 2
    bars = [rect(back - (i + 1) * 0.45 * k.W, y0, back - (i + 1) * 0.45 * k.W + k.bar_width, y1)
            for i in range(extra)]
    return union(_triangle(k, back), *bars)


@ligature("||>")
def _(k):
    return _bars_then_triangle(k, 3, 1)


@ligature("|||>")
def _(k):
    return _bars_then_triangle(k, 4, 2)


@ligature("<||")
def _(k):
    return mirror(_bars_then_triangle(k, 3, 1), 1.5 * k.W)


@ligature("<|||")
def _(k):
    return mirror(_bars_then_triangle(k, 4, 2), 2 * k.W)


# --- equality and comparison: Hack's '=' bars, stretched -----------------------------------

def _bars(k, char, n):
    x0, _, x1, _ = k.bbox(char)
    return union(*(rect(x0, b, (n - 1) * k.W + x1, t) for b, t in k.bands(char)))


@ligature("==")
def _(k):
    return _bars(k, "=", 2)


@ligature("===", "three bars at the heights of Hack's '≡'")
def _(k):
    return _bars(k, "≡", 3)


def _slash(k, char, bars_char):
    """The slash of a crossed sign ('≠', '≢'): the glyph minus its bars."""
    g = k.glyph(char)
    cut = union(*(rect(-10 * k.W, b - 1, 10 * k.W, t + 1) for b, t in k.bands(bars_char)))
    return subtract(g, cut), center_x(g)


def _crossed(k, n, bars_char, crossed_char, at):
    """Bars of `bars_char` across n cells, crossed by the slash of `crossed_char` centred on x=at."""
    slash, cx = _slash(k, crossed_char, bars_char)
    return union(_bars(k, bars_char, n), move(slash, at - cx))


@ligature("!=", "long '=' bars with the slash of Hack's '≠'")
def _(k):
    return _crossed(k, 2, "=", "≠", k.W)


@ligature("!==", "three bars with the slash of Hack's '≢'")
def _(k):
    return _crossed(k, 3, "≡", "≢", 1.5 * k.W)


@ligature("=/=")
def _(k):
    return _crossed(k, 3, "=", "≠", 1.5 * k.W)


@ligature("/=")
def _(k):
    return _crossed(k, 2, "=", "≠", 0.62 * k.W)


@ligature("/==")
def _(k):
    return _crossed(k, 3, "=", "≠", 0.62 * k.W)


def _wide(k, char, factor=1.65):
    """Hack's `char` stretched horizontally across the pair (vertical strokes keep their weight)."""
    g = k.glyph(char)
    x0, y0, x1, y1 = bounds(g)
    g = scale(g, factor, 1, origin=((x0 + x1) / 2, 0))
    return move(g, k.W - center_x(g))


@ligature("<=", "Hack's '≤', widened across the pair")
def _(k):
    return _wide(k, "≤")


@ligature(">=", "Hack's '≥', widened across the pair")
def _(k):
    return _wide(k, "≥")


# --- assignment and colon operators: colons centred on the math axis -----------------------

def center_y(p):
    _, y0, _, y1 = bounds(p)
    return (y0 + y1) / 2


def _seq(k, parts):
    """Place glyphs at given cell positions: parts = [(char, x_center_in_cells, raise_to_axis)]."""
    out = []
    for char, pos, to_axis in parts:
        g = k.glyph(char)
        dy = k.axis - center_y(g) if to_axis else 0
        out.append(move(g, pos * k.W - center_x(g), dy))
    return union(*out)


@ligature(":=")
def _(k):
    return _seq(k, [(":", 0.62, True), ("=", 1.42, False)])


@ligature("=:")
def _(k):
    return _seq(k, [("=", 0.58, False), (":", 1.38, True)])


@ligature("::=")
def _(k):
    return _seq(k, [(":", 0.75, True), (":", 1.32, True), ("=", 2.4, False)])


@ligature("=:=")
def _(k):
    return _seq(k, [("=", 0.62, False), (":", 1.5, True), ("=", 2.38, False)])


@ligature("=!=")
def _(k):
    return _seq(k, [("=", 0.62, False), ("!", 1.5, False), ("=", 2.38, False)])


# --- comments and doubled punctuation ------------------------------------------------------

@ligature("/*", "the asterisk drops to the middle of the line")
def _(k):
    return _seq(k, [("/", 0.5, False), ("*", 1.5, True)])


@ligature("*/")
def _(k):
    return _seq(k, [("*", 0.5, True), ("/", 1.5, False)])


@ligature("/**")
def _(k):
    return _seq(k, [("/", 0.5, False), ("*", 1.5, True), ("*", 2.5, True)])


def _pulled(k, char, n, step):
    """n copies of `char`, `step` cells apart (but never closer than the glyph's width plus half
    a stroke, so heavy weights don't collide), centred on the ligature."""
    x0, _, x1, _ = k.bbox(char)
    step = max(step, (x1 - x0 + 0.5 * k.stroke) / k.W)
    mid = n / 2
    return _seq(k, [(char, mid + (i - (n - 1) / 2) * step, False) for i in range(n)])


@ligature("//")
def _(k):
    return _pulled(k, "/", 2, 0.7)


@ligature("///")
def _(k):
    return _pulled(k, "/", 3, 0.7)


@ligature("&&")
def _(k):
    return _pulled(k, "&", 2, 0.8)


@ligature("&&&")
def _(k):
    return _pulled(k, "&", 3, 0.8)


@ligature("||")
def _(k):
    return _pulled(k, "|", 2, 0.6)


def _joined_plus(k, n):
    """Pluses pulled together and joined by their crossbars."""
    out = _pulled(k, "+", n, 0.75)
    x0, _, x1, _ = bounds(out)
    # The crossbar's real height, measured at the left end of '+'. The joining bar sits 1 unit
    # inside it: exactly coincident edges trip up the boolean operations.
    px0 = k.bbox("+")[0]
    _, b, _, t = bounds(intersect(k.glyph("+"), rect(px0, -k.W, px0 + 10, 2 * k.W)))
    return union(out, rect(x0 + 1, b + 1, x1 - 1, t - 1))


@ligature("++")
def _(k):
    return _joined_plus(k, 2)


@ligature("+++")
def _(k):
    return _joined_plus(k, 3)


def _dashes(k, n):
    """Hack's '-' lengthened so the dashes almost touch."""
    x0, y0, x1, y1 = k.bbox("-")
    gap = 0.16 * k.W
    seg = (n * k.W - (n - 1) * gap - 2 * x0) / n
    return union(*(rect(x0 + i * (seg + gap), y0, x0 + i * (seg + gap) + seg, y1) for i in range(n)))


@ligature("--")
def _(k):
    return _dashes(k, 2)


@ligature("---")
def _(k):
    return _dashes(k, 3)


@ligature("__", "a continuous underscore")
def _(k):
    x0, y0, x1, y1 = k.bbox("_")
    return rect(x0, y0, k.W + x1, y1)


# --- punctuation: Hack's dots, re-spaced ---------------------------------------------------

@ligature("::")
def _(k):
    c = k.glyph(":")
    d = 0.35 * k.W
    return union(move(c, k.W - d - center_x(c)), move(c, k.W + d - center_x(c)))


@ligature("...")
def _(k):
    p = k.glyph(".")
    s = 0.85 * k.W
    return union(*(move(p, 1.5 * k.W + i * s - center_x(p)) for i in (-1, 0, 1)))


# --- from Fira Code (not in JetBrains Mono) ------------------------------------------------

@ligature("~=", "Fira Code's '~=': a wide '≃' from Hack's '~' and '=' strokes")
def _(k):
    tilde = k.glyph("~")
    (top_b, top_t), (bot_b, bot_t) = k.bands("=")
    tx0, ty0, tx1, ty1 = bounds(tilde)
    width = 1.45 * (tx1 - tx0)
    tilde = scale(tilde, width / (tx1 - tx0), 1, origin=((tx0 + tx1) / 2, (ty0 + ty1) / 2))
    tilde = move(tilde, k.W - center_x(tilde), (top_b + top_t) / 2 + k.stroke * 0.35 - (ty0 + ty1) / 2)
    bar = rect(k.W - width / 2, bot_b, k.W + width / 2, bot_t)
    return union(tilde, bar)


@ligature("..=", "Rust's inclusive range: two dots tucked against '='")
def _(k):
    p, eq = k.glyph("."), k.glyph("=")
    eq = move(eq, 2 * k.W - 0.08 * k.W)
    ex0 = bounds(eq)[0]
    s = 0.62 * k.W
    dots = [move(p, ex0 - 0.5 * k.W - i * s - center_x(p)) for i in (1, 0)]
    return union(*dots, eq)


# --- tightened sequences -------------------------------------------------------------------

def _tight(k, seq, step, raise_chars=""):
    """Hack's glyphs for `seq`, `step` cells apart (never so close that neighbours collide),
    centred on the ligature. Characters in `raise_chars` are centred on the math axis."""
    widths = [k.bbox(c)[2] - k.bbox(c)[0] for c in seq]
    xs = [0.0]
    for a, b in zip(widths, widths[1:]):
        xs.append(xs[-1] + max(step * k.W, (a + b) / 2 + 0.4 * k.stroke))
    shift = len(seq) * k.W / 2 - (xs[0] + xs[-1]) / 2
    return _seq(k, [(c, (x + shift) / k.W, c in raise_chars) for c, x in zip(seq, xs)])


TIGHT = {
    # sequence: (step in cells, characters centred on the math axis)
    "!!": (0.6, ""),   "??": (0.75, ""),  "???": (0.75, ""), ";;": (0.62, ""),  ";;;": (0.62, ""),
    ":::": (0.7, ""),  "..": (0.62, ""),  "..<": (0.62, ""), "***": (0.7, "*"),
    "##": (0.8, ""),   "###": (0.8, ""),  "####": (0.8, ""),
    "{{": (0.7, ""),   "}}": (0.7, ""),   "{|": (0.55, ""),  "|}": (0.55, ""),  "[|": (0.55, ""),
    "|]": (0.55, ""),  "!!}": (0.62, ""), "{!!": (0.62, ""),
    "#!": (0.75, ""),  "#(": (0.75, ""),  "#:": (0.75, ":"), "#=": (0.75, ""),  "#?": (0.75, ""),
    "#[": (0.75, ""),  "#_": (0.75, ""),  "#{": (0.75, ""),  "]#": (0.75, ""),  "#_(": (0.75, ""),
    "$>": (0.75, ""),  "<$": (0.75, ""),  "<$>": (0.75, ""), "+>": (0.75, ""),  "<+": (0.75, ""),
    "<+>": (0.75, ""), "*>": (0.75, "*"), "<*": (0.75, "*"), "<*>": (0.75, "*"),
    ":<": (0.7, ":"),  ":>": (0.7, ":"),  "<:": (0.7, ":"),  ">:": (0.7, ":"),  "<:<": (0.7, ":"),
    ":?": (0.7, ":"),  ":?>": (0.7, ":"), "?:": (0.7, ":"),  ".=": (0.7, "."),  ".?": (0.7, ""),
    "?.": (0.7, ""),   "?=": (0.75, ""),  "/>": (0.7, ""),   "</": (0.7, ""),   "</>": (0.7, ""),
    ">]": (0.7, ""),   "[<": (0.7, ""),   "&=": (0.8, ""),   "^=": (0.75, ""),  "@_": (0.75, ""),
    "~@": (0.75, ""),  "//=": (0.7, ""),
}

for _seq_, (_step, _raise) in TIGHT.items():
    ligature(_seq_)(lambda k, s=_seq_, st=_step, r=_raise: _tight(k, s, st, r))


# --- nested chevrons and the diamond -------------------------------------------------------

def _nested(k, char, n):
    """Hack's '<'/'>' nested inside each other: their arms are parallel, so they can sit much
    closer than their width — as close as an arm's horizontal thickness plus some air."""
    g = k.glyph(char)
    _, _, _, top = bounds(g)
    y = (k.axis + top) / 2
    ax0, _, ax1, _ = bounds(intersect(g, rect(-k.W, y - 1, 2 * k.W, y + 1)))
    step = max(0.45 * k.W, (ax1 - ax0) + 1.0 * k.stroke) / k.W
    return _seq(k, [(char, n / 2 + (i - (n - 1) / 2) * step, False) for i in range(n)])


@ligature("<<")
def _(k):
    return _nested(k, "<", 2)


@ligature(">>")
def _(k):
    return _nested(k, ">", 2)


@ligature("<<<")
def _(k):
    return _nested(k, "<", 3)


@ligature(">>>")
def _(k):
    return _nested(k, ">", 3)


@ligature("<>", "a diamond: Hack's '<' and '>' joined at their arm ends")
def _(k):
    lt, gt = k.glyph("<"), k.glyph(">")
    overlap = 2  # avoid exactly coincident edges
    lt = move(lt, k.W + overlap - bounds(lt)[2])
    gt = move(gt, k.W - overlap - bounds(gt)[0])
    return union(lt, gt)


# --- waves meeting straight shafts ---------------------------------------------------------

@ligature("-~")
def _(k):
    hx0 = k.bbox("-")[0]
    straight = rect(hx0, k.axis - k.stroke / 2, k.W + 1, k.axis + k.stroke / 2)
    return union(straight, _wave(k, k.W, k.W + k.bbox("~")[2], anchor_left=True, anchor_right=False))


@ligature("~-")
def _(k):
    hx1 = k.bbox("-")[2]
    straight = rect(k.W - 1, k.axis - k.stroke / 2, k.W + hx1, k.axis + k.stroke / 2)
    return union(_wave(k, k.bbox("~")[0], k.W, anchor_left=False, anchor_right=True), straight)


# --- markup comments -----------------------------------------------------------------------

def _gap(k, cx, char):
    """A vertical slot around a glyph centred on cx, to cut out of a shaft."""
    x0, _, x1, _ = k.bbox(char)
    half = (x1 - x0) / 2 + 0.12 * k.W
    return rect(cx - half, -k.W, cx + half, 2 * k.W)


def _shaft(k, x0, x1):
    return rect(x0, k.axis - k.stroke / 2, x1, k.axis + k.stroke / 2)


@ligature("<!--", "HTML comment: an arrow with '!' set into its shaft")
def _(k):
    body = subtract(arrow(k, 4, "-", "head", None), _gap(k, 1.5 * k.W, "!"))
    return union(body, _seq(k, [("!", 1.5, False)]))


@ligature("<#--")
def _(k):
    body = subtract(arrow(k, 4, "-", "head", None), _gap(k, 1.5 * k.W, "#"))
    return union(body, _seq(k, [("#", 1.5, False)]))


@ligature("{!--")
def _(k):
    parts = _seq(k, [("{", 0.6, False), ("!", 1.35, False)])
    x = bounds(parts)[2] + 0.15 * k.W
    return union(parts, _shaft(k, x, 3 * k.W + k.bbox("-")[2]))


@ligature("{{--")
def _(k):
    parts = _tight(k, "{{", 0.7)
    parts = move(parts, 0.95 * k.W - center_x(parts))
    x = bounds(parts)[2] + 0.15 * k.W
    return union(parts, _shaft(k, x, 3 * k.W + k.bbox("-")[2]))


@ligature("--}}")
def _(k):
    parts = _tight(k, "}}", 0.7)
    parts = move(parts, 3.05 * k.W - center_x(parts))
    x = bounds(parts)[0] - 0.15 * k.W
    return union(_shaft(k, k.bbox("-")[0], x), parts)


# --- one-offs ------------------------------------------------------------------------------

@ligature("_|_", "bottom: '⊥' from Hack's '_' and '|' strokes")
def _(k):
    ux0, uy0, ux1, uy1 = k.bbox("_")
    cap = k.bbox("H")[3]
    base = rect(ux0, uy0, 2 * k.W + ux1, uy1)
    stem = rect(1.5 * k.W - k.bar_width / 2, uy1 - 1, 1.5 * k.W + k.bar_width / 2, cap)
    return union(base, stem)


# --- ASCII art: '/\' and '\/' between dots or spaces ---------------------------------------

def _peak(k, first, second):
    """Hack's '/' and '\\' moved together until their strokes meet in a point."""
    a, b = k.glyph(first), k.glyph(second)
    # Shift the second glyph left until it touches the first, then overlap by a hair.
    lo, hi = 0.0, k.W
    for _ in range(20):
        mid = (lo + hi) / 2
        if intersect(a, move(b, k.W - mid)).area > 0:
            hi = mid
        else:
            lo = mid
    pair = union(a, move(b, k.W - lo - 2))
    return move(pair, k.W - center_x(pair))


@ligature("/\\", "'Λ': Hack's '/' and '\\' meeting at the top")
def _(k):
    return _peak(k, "/", "\\")


@ligature("\\/", "'V': Hack's '\\' and '/' meeting at the bottom")
def _(k):
    return _peak(k, "\\", "/")
