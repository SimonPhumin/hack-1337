"""Copy the programming ligatures (the `calt` feature) of a source font such as JetBrains Mono
into a target monospaced font such as Hack.

How it works:
  1. Walk the source font's `calt` lookups (plus every lookup they call) and translate them
     to OpenType feature code (.fea). Glyphs that are encoded in both fonts are referenced by
     the target's glyph for the same code point; ligature glyphs (`*.liga`) and the spacer
     (`SPC`) are copied over. Rules that need a glyph the target lacks are dropped, and so are
     substitutions to anything other than ligatures/spacers (e.g. JBM's raised `colon.case`),
     so Hack keeps its own letterforms.
  2. Copy those glyphs, scaled to the target's cell width and em, shifted so the source's math
     axis (centre of `-` and `=`) lands on the target's, and re-slanted for italics.
  3. Compile the .fea and splice it into the target's existing GSUB (see otl.py). The build
     (build.py) compiles it together with src/features/native.fea instead.

Usage: ligaturize.py TARGET.ttf SOURCE.ttf OUT.ttf [--fea OUT.fea]
"""
import argparse
import math

from fontTools.misc.transform import Transform
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

from otl import add_features


def is_ligature_glyph(name: str) -> bool:
    return name == "SPC" or name.endswith(".liga")


def calt_closure(font: TTFont) -> tuple[list[int], list[int]]:
    """Return (top-level calt lookup indices, all lookups reachable from them), both sorted."""
    gsub = font["GSUB"].table
    lookups = gsub.LookupList.Lookup
    top = sorted({i for fr in gsub.FeatureList.FeatureRecord if fr.FeatureTag == "calt"
                  for i in fr.Feature.LookupListIndex})
    seen, stack = set(), list(top)
    while stack:
        i = stack.pop()
        if i in seen:
            continue
        seen.add(i)
        for st in lookups[i].SubTable:
            for rec in _subst_records(st):
                stack.append(rec.LookupListIndex)
    return top, sorted(seen)


def _subst_records(st):
    yield from getattr(st, "SubstLookupRecord", None) or []
    for attr, rule_attr in (("ChainSubRuleSet", "ChainSubRule"), ("ChainSubClassSet", "ChainSubClassRule")):
        for ruleset in getattr(st, attr, None) or []:
            for rule in getattr(ruleset, rule_attr, None) or [] if ruleset else []:
                yield from rule.SubstLookupRecord


class FeaWriter:
    """Translates the source calt closure into .fea using target glyph names."""

    def __init__(self, source: TTFont, target: TTFont, copied: dict[str, str]):
        self.source = source
        self.lookups = source["GSUB"].table.LookupList.Lookup
        src_cmap = source.getBestCmap()
        tgt_cmap = target.getBestCmap()
        self.map: dict[str, str] = {}
        for cp, gname in sorted(src_cmap.items()):
            if cp in tgt_cmap and gname not in self.map:
                self.map[gname] = tgt_cmap[cp]
        self.map.update(copied)
        self.emitted: set[int] = set()

    def glyph(self, name: str) -> str | None:
        return self.map.get(name)

    def glyphs(self, names) -> list[str]:
        return sorted({self.map[n] for n in names if n in self.map})

    @staticmethod
    def cls(names: list[str]) -> str:
        names = [f"\\{n}" for n in names]
        return names[0] if len(names) == 1 else "[" + " ".join(names) + "]"

    def single_lookup(self, index: int) -> str | None:
        """Emit a single-substitution lookup restricted to ligature/spacer outputs."""
        lines = []
        for st in self.lookups[index].SubTable:
            for src, dst in st.mapping.items():
                if is_ligature_glyph(dst) and src in self.map and dst in self.map:
                    lines.append(f"    sub \\{self.map[src]} by \\{self.map[dst]};")
        if not lines:
            return None
        return f"lookup jbm_{index} {{\n" + "\n".join(lines) + f"\n}} jbm_{index};\n"

    def rule(self, backtrack, inputs, lookahead, records, valid_lookups) -> str | None:
        """backtrack is given closest-first (binary order); each entry is a list of source glyphs."""
        seqs = [self.glyphs(g) for g in backtrack] + [self.glyphs(g) for g in inputs] + [self.glyphs(g) for g in lookahead]
        if any(not s for s in seqs):
            return None  # needs a glyph the target doesn't have
        actions: dict[int, list[int]] = {}
        for rec in records:
            if rec.LookupListIndex not in valid_lookups:
                return None  # the substitution would produce a glyph we don't copy
            actions.setdefault(rec.SequenceIndex, []).append(rec.LookupListIndex)
        bt = [self.cls(self.glyphs(g)) for g in reversed(backtrack)]
        la = [self.cls(self.glyphs(g)) for g in lookahead]
        inp = []
        for pos, g in enumerate(inputs):
            part = self.cls(self.glyphs(g)) + "'"
            for li in actions.get(pos, []):
                part += f" lookup jbm_{li}"
            inp.append(part)
        body = " ".join(bt + inp + la)
        return f"    {'ignore sub' if not records else 'sub'} {body};"

    def chain_lookup(self, index: int, valid_lookups: set[int]) -> str | None:
        lines = []
        for st in self.lookups[index].SubTable:
            if st.Format == 1:
                for first, ruleset in zip(st.Coverage.glyphs, st.ChainSubRuleSet):
                    for r in ruleset.ChainSubRule:
                        lines.append(self.rule([[g] for g in r.Backtrack], [[first]] + [[g] for g in r.Input],
                                               [[g] for g in r.LookAhead], r.SubstLookupRecord, valid_lookups))
            elif st.Format == 2:
                def members(classdef, k, restrict=None):
                    if k == 0:
                        raise NotImplementedError("class 0 in chain context rules")
                    g = [n for n, c in classdef.classDefs.items() if c == k]
                    return [n for n in g if n in restrict] if restrict is not None else g
                cov = set(st.Coverage.glyphs)
                for k, classset in enumerate(st.ChainSubClassSet or []):
                    if classset is None:
                        continue
                    for r in classset.ChainSubClassRule:
                        lines.append(self.rule(
                            [members(st.BacktrackClassDef, c) for c in r.Backtrack],
                            [members(st.InputClassDef, k, cov)] + [members(st.InputClassDef, c) for c in r.Input],
                            [members(st.LookAheadClassDef, c) for c in r.LookAhead],
                            r.SubstLookupRecord, valid_lookups))
            elif st.Format == 3:
                lines.append(self.rule([c.glyphs for c in st.BacktrackCoverage], [c.glyphs for c in st.InputCoverage],
                                       [c.glyphs for c in st.LookAheadCoverage], st.SubstLookupRecord, valid_lookups))
        lines = [l for l in lines if l]
        if not any(l.lstrip().startswith("sub ") for l in lines):
            return None  # nothing but ignore rules left: the lookup has no effect
        return f"lookup jbm_{index} {{\n" + "\n".join(lines) + f"\n}} jbm_{index};\n"

    def write(self) -> str:
        top, closure = calt_closure(self.source)
        blocks, valid = [], set()
        for i in closure:
            if self.lookups[i].LookupType == 1:
                block = self.single_lookup(i)
                if block:
                    blocks.append(block); valid.add(i)
            elif self.lookups[i].LookupType != 6:
                raise NotImplementedError(f"lookup type {self.lookups[i].LookupType} in calt")
        used_top = []
        for i in top:
            if self.lookups[i].LookupType == 6:
                block = self.chain_lookup(i, valid)
                if block:
                    blocks.append(block); used_top.append(i)
            elif i in valid:
                used_top.append(i)
        feature = "feature calt {\n" + "".join(f"    lookup jbm_{i};\n" for i in used_top) + "} calt;\n"
        return "# Generated by scripts/ligaturize.py — do not edit.\n\n" + "\n".join(blocks) + "\n" + feature


def _center(font: TTFont, char: str) -> tuple[float, float]:
    gs = font.getGlyphSet()
    pen = BoundsPen(gs)
    gs[font.getBestCmap()[ord(char)]].draw(pen)
    x0, y0, x1, y1 = pen.bounds
    return (x0 + x1) / 2, (y0 + y1) / 2


def glyph_transform(source: TTFont, target: TTFont) -> tuple[Transform, int]:
    src_width = source["hmtx"][source.getBestCmap()[ord("0")]][0]
    tgt_width = target["hmtx"][target.getBestCmap()[ord("0")]][0]
    sx = tgt_width / src_width
    sy = target["head"].unitsPerEm / source["head"].unitsPerEm
    # Vertical: put the source math axis (midway between the centres of '-' and '=') on the target's.
    src_axis = (_center(source, "-")[1] + _center(source, "=")[1]) / 2
    tgt_axis = (_center(target, "-")[1] + _center(target, "=")[1]) / 2
    dy = tgt_axis - src_axis * sy
    # Italics: re-slant from the source angle to the target angle, pivoting on the math axis.
    shear = math.tan(math.radians(-target["post"].italicAngle)) - math.tan(math.radians(-source["post"].italicAngle))
    t = Transform(sx, 0, shear * sy, sy, shear * (dy - tgt_axis), dy)
    # Horizontal: centre '-' over the target's '-' (matters for italics, ~0 for upright).
    sxc, syc = _center(source, "-")
    dx = _center(target, "-")[0] - t.transformPoint((sxc, syc))[0]
    return Transform(sx, 0, shear * sy, sy, shear * (dy - tgt_axis) + dx, dy), tgt_width


def copy_glyphs(source: TTFont, target: TTFont, names: list[str]) -> dict[str, str]:
    """Copy glyphs (decomposed, transformed) from source to target. Returns source->target names."""
    transform, width = glyph_transform(source, target)
    src_glyphs = source.getGlyphSet()
    order = target.getGlyphOrder()
    existing = set(order)
    glyf, hmtx = target["glyf"], target["hmtx"]
    renamed = {}
    for name in names:
        new = name if name not in existing else f"{name}.jbm"
        rec = DecomposingRecordingPen(src_glyphs)
        src_glyphs[name].draw(rec)
        pen = TTGlyphPen(None)
        rec.replay(TransformPen(pen, transform))
        glyph = pen.glyph()
        glyph.recalcBounds(glyf)
        glyf.glyphs[new] = glyph
        hmtx.metrics[new] = (width, getattr(glyph, "xMin", 0))
        order.append(new)
        existing.add(new)
        renamed[name] = new
    target.setGlyphOrder(order)
    glyf.glyphOrder = order
    return renamed


def ligaturize(target: TTFont, source: TTFont) -> str:
    """Copy the ligature glyphs into `target` and return the feature code that uses them.
    The caller compiles the feature code (see otl.add_features / features.apply)."""
    _, closure = calt_closure(source)
    lookups = source["GSUB"].table.LookupList.Lookup
    wanted = sorted({dst for i in closure if lookups[i].LookupType == 1
                     for st in lookups[i].SubTable for dst in st.mapping.values() if is_ligature_glyph(dst)})
    copied = copy_glyphs(source, target, wanted)
    for table in ("DSIG", "hdmx", "LTSH", "VDMX"):  # stale once glyphs are added
        if table in target:
            del target[table]
    return FeaWriter(source, target, copied).write()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("target"); ap.add_argument("source"); ap.add_argument("out")
    ap.add_argument("--fea", help="also write the generated feature code here")
    a = ap.parse_args()
    font = TTFont(a.target)
    fea = ligaturize(font, TTFont(a.source))
    if a.fea:
        with open(a.fea, "w") as f:
            f.write(fea)
    add_features(font, fea)
    font.save(a.out)
